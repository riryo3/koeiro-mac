"""Synthesize one utterance inside the TTS environment, then exit.

The GUI never imports ``kokoro-onnx``: the weights live in ``models/tts/kokoro`` and
the runtime in the separate ``vc_models/tts/.venv`` that ``tools/install_tts.py``
creates, so a missing runtime cannot weigh on the voice route and a packaged build
stays small. This module is the process that runs *inside* that environment. It reads
one small JSON request, writes a 16-bit PCM WAV and prints one JSON result line, which
is everything :mod:`src.tts.client` needs -- and it keeps the client testable without
the model.

    vc_models/tts/.venv/Scripts/python -m src.tts.service --request request.json
"""
from pathlib import Path
import argparse
import json
import sys
import time
import wave

import numpy as np


def write_wav(path, samples, sample_rate):
    """Write mono 16-bit PCM and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes((clipped * 32767.0).astype('<i2').tobytes())
    return path


def synthesize(request):
    """Run one request dict and return its result dict. Raises on any failure.

    The model is built per call because the process exits after one request: the load
    time is reported back rather than hidden, so the caller can tell a slow machine
    from a slow model.
    """
    from src.tts.provider import DEFAULT_LANG, DEFAULT_VOICE, KokoroProvider

    text = str(request.get('text') or '').strip()
    if not text:
        raise ValueError('A request needs non-empty text')
    sample_rate = int(request.get('sample_rate') or 48000)
    voice = str(request.get('voice') or DEFAULT_VOICE)
    started = time.perf_counter()
    provider = KokoroProvider(str(request['root']), voice=voice,
                              lang=str(request.get('lang') or DEFAULT_LANG),
                              speed=float(request.get('speed') or 1.0))
    load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    audio = provider.synthesize(text, voice=voice, sample_rate=sample_rate)
    synthesis_seconds = time.perf_counter() - started
    if audio.size == 0:
        raise ValueError('Synthesis produced no audio')
    write_wav(request['out'], audio, sample_rate)
    return dict(status='ok', engine='kokoro-onnx', voice=voice, sample_rate=sample_rate,
                seconds=len(audio) / sample_rate, load_seconds=load_seconds,
                synthesis_seconds=synthesis_seconds)


def main():
    parser = argparse.ArgumentParser(description='Synthesize one utterance in the TTS environment')
    parser.add_argument('--request', required=True, type=Path,
                        help='JSON file describing root, text, voice and output WAV')
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding='utf-8'))
        if not isinstance(request, dict):
            raise ValueError('A request must be a JSON object')
        result = synthesize(request)
    except Exception as error:  # one JSON line either way; the client reports the rest
        print(json.dumps(dict(status='error', kind=type(error).__name__, error=str(error)),
                         ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
