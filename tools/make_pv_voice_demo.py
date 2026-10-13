"""Render a promo voice sample through the app's own AI Voice route, offline.

Reads any audio file, resamples it to the 48 kHz mono the route expects, converts it
with the exact parameters the shipped app would send, and writes the original and the
converted audio next to each other. No audio device is opened and nothing is listened
to: this is computation over files.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.settings.manager import SettingsManager
from src.vc.client import ServiceClient
from tools.compare_meanvc2_continuity import require_idle_voice_worker

RATE = 48000


def decode(source: Path, work: Path) -> np.ndarray:
    """Any media file to 48 kHz mono float32, through ffmpeg's decoder."""
    wav = work / 'source_48k.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source),
                    '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', str(wav)],
                   check=True)
    with wave.open(str(wav), 'rb') as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()),
                             dtype='<i2').astype(np.float32) / 32768


def write_wav(destination: Path, audio: np.ndarray) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())


def report(audio: np.ndarray) -> dict:
    return {'seconds': round(len(audio) / RATE, 3),
            'peak': round(float(np.max(np.abs(audio))), 4),
            'rms': round(float(np.sqrt(np.mean(np.square(audio)))), 4)}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Any audio file (mp3/wav/...). Decoded by ffmpeg.')
    parser.add_argument('--original-out', type=Path,
                        default=ROOT / 'promo/public/audio/voice_demo_original.wav')
    parser.add_argument('--converted-out', type=Path,
                        default=ROOT / 'promo/public/audio/voice_demo_converted.wav')
    parser.add_argument('--report', type=Path,
                        default=ROOT / 'promo/public/audio/voice_demo.json')
    args = parser.parse_args()

    require_idle_voice_worker()
    parameters = SettingsManager(ROOT / 'settings.json').load().ai_parameters()
    print('ROUTE ' + json.dumps({'model': parameters.model, 'delivery': parameters.delivery,
                                 'enhancer': parameters.enhancer, 'experiment': parameters.experiment,
                                 'quality': parameters.quality, 'threads': parameters.threads,
                                 'device': parameters.device}, ensure_ascii=False))

    with tempfile.TemporaryDirectory() as temporary:
        audio = decode(args.source, Path(temporary))
    print('SOURCE ' + json.dumps(report(audio)))

    client = ServiceClient(parameters)
    client.start()
    started = time.monotonic()
    try:
        while True:
            header, _ = client.read()
            if header['status'] == 'Ready':
                break
            if time.monotonic() - started > 300:
                raise RuntimeError('the worker never reported Ready')
        print('CONVERTING %.1f s of audio' % (len(audio) / RATE), flush=True)
        wall = time.monotonic()
        header, result = client.request({'op': 'utterance'}, audio)
        elapsed = time.monotonic() - wall
    finally:
        client.close()

    if len(result) < len(audio) // 2:
        raise RuntimeError('the route returned almost nothing: %d samples for %.1f s'
                           % (len(result), len(audio) / RATE))
    assert np.isfinite(result).all(), 'the route returned non-finite samples'

    write_wav(args.original_out, audio)
    write_wav(args.converted_out, result)
    summary = {'kind': 'OFFLINE file-to-file through the app worker; no audio device, no listening',
               'source': str(args.source), 'route': {'model': parameters.model,
              'delivery': parameters.delivery, 'enhancer': parameters.enhancer,
              'experiment': parameters.experiment, 'quality': parameters.quality},
               'original': report(audio), 'converted': report(result),
               'wall_seconds': round(elapsed, 2), 'stats': header.get('stats'),
               'original_file': str(args.original_out), 'converted_file': str(args.converted_out)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
