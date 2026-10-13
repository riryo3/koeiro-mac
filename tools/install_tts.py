"""Install the optional Kokoro text-to-speech model and its runtime environment.

Explicit setup, no app-time downloads -- the same rule every other model in this repo
follows. The user (or an AI agent following the README) runs this once.

Licenses: Kokoro-82M's weights are Apache-2.0 and kokoro-onnx is MIT, so fetching the
weights here does not change Koeiro's MIT distribution. The weights are never bundled
into the repository, only downloaded to a local ``models/tts`` folder.

The int8 build is the default: about 110 MB of weights instead of 325 MB, which is the
point of this being the low-spec option.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RELEASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'
FILES = {
    'kokoro-v1.0.int8.onnx': RELEASE + 'kokoro-v1.0.int8.onnx',
    'voices-v1.0.bin': RELEASE + 'voices-v1.0.bin',
}
TARGET = ROOT / 'models' / 'tts' / 'kokoro'
DEFAULT_VENV = ROOT / 'vc_models' / 'tts' / '.venv'
PACKAGES = ('kokoro-onnx',)
LICENSE = {
    'model': 'Apache-2.0 (Kokoro-82M, hexgrad)',
    'runtime': 'MIT (kokoro-onnx, thewh1teagle)',
    'voices_file': 'see hexgrad/Kokoro-82M VOICES.md (per-voice attributions)',
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download(url, destination):
    if destination.is_file() and destination.stat().st_size > 0:
        print(f'keep  {destination.name} ({destination.stat().st_size/1e6:.0f} MB)')
        return digest(destination)
    temporary = destination.with_suffix(destination.suffix + '.part')
    print(f'fetch {url}')
    with urllib.request.urlopen(url) as response, temporary.open('wb') as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    if temporary.stat().st_size == 0:
        temporary.unlink()
        raise ValueError(f'Empty download for {url}')
    temporary.replace(destination)
    print(f'wrote {destination.name} ({destination.stat().st_size/1e6:.0f} MB)')
    return digest(destination)


def make_venv(venv, python, dry_run=False):
    launcher = venv / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if launcher.is_file():
        print(f'venv  {venv} (exists)')
    else:
        print(f'venv  {venv} (creating)')
        if not dry_run:
            venv.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([python, '-m', 'venv', str(venv)], check=True)
    steps = ([str(launcher), '-m', 'pip', 'install', '--upgrade', 'pip'],
             [str(launcher), '-m', 'pip', 'install', *PACKAGES])
    for step in steps:
        print('pip   ' + ' '.join(step[2:]))
        if not dry_run:
            subprocess.run(step, check=True)
    return launcher


def main():
    parser = argparse.ArgumentParser(description='Install the optional Kokoro TTS model')
    parser.add_argument('--venv', type=Path, default=DEFAULT_VENV,
                        help='Where to create the TTS runtime venv')
    parser.add_argument('--python', default=sys.executable,
                        help='Interpreter used to create the venv')
    parser.add_argument('--no-venv', action='store_true', help='Download models only')
    parser.add_argument('--no-models', action='store_true', help='Create the venv only')
    parser.add_argument('--dry-run', action='store_true', help='Show the steps without doing them')
    args = parser.parse_args()

    if not args.no_models:
        TARGET.mkdir(parents=True, exist_ok=True)
        hashes = {}
        if args.dry_run:
            for name, url in FILES.items():
                print(f'would fetch {url} -> {TARGET / name}')
        else:
            for name, url in FILES.items():
                hashes[name] = download(url, TARGET / name)
            (TARGET / 'metadata.json').write_text(json.dumps(
                dict(source=RELEASE, files=hashes, license=LICENSE,
                     sample_rate=24000, voices='af_heart (en-us)', precision='int8'),
                ensure_ascii=False, indent=2), encoding='utf-8')
            print('wrote metadata.json')
    if not args.no_venv:
        make_venv(args.venv, args.python, args.dry_run)
        runner = args.venv / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        print(f'\nVerify with:\n  {runner} tools/verify_tts.py --text "Hello" --out tts.wav')
    return 0


if __name__ == '__main__':
    sys.exit(main())
