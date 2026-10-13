"""Synthesize one phrase with the installed Kokoro model and report honest timing.

Run this with the TTS runtime (``vc_models/tts/.venv``), not the GUI environment. It
writes a WAV so the result can actually be listened to, and prints model load time,
synthesis time and the real-time factor. Those numbers are model-only: they are not an
end-to-end latency and they are not a listening test -- a human still has to listen to
the WAV to judge it.
"""
from pathlib import Path
import argparse
import sys
import time
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.tts.provider import KokoroProvider, available, model_dir  # noqa: E402


def write_wav(path, samples, sample_rate):
    data = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (data * 32767.0).astype('<i2')
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser(description='Verify the installed Kokoro TTS')
    parser.add_argument('--text', default='Hello. This is Koeiro speaking.')
    parser.add_argument('--voice', default='af_heart')
    parser.add_argument('--lang', default='en-us')
    parser.add_argument('--out', type=Path, default=ROOT / 'tts_preview.wav')
    args = parser.parse_args()
    if not available(ROOT):
        print(f'Model not installed under {model_dir(ROOT)}. Run: python tools/install_tts.py')
        return 2
    started = time.perf_counter()
    provider = KokoroProvider(ROOT, voice=args.voice, lang=args.lang)
    load = time.perf_counter() - started
    started = time.perf_counter()
    audio = provider.synthesize(args.text, sample_rate=24000)
    synthesis = time.perf_counter() - started
    seconds = len(audio) / 24000
    write_wav(args.out, audio, 24000)
    # ASCII only: the Windows console default code page (cp932 here) cannot encode
    # a middle dot, and a formatting failure must not look like a synthesis failure.
    print(f'load {load:.2f}s | synth {synthesis:.2f}s | audio {seconds:.2f}s'
          f' | RTF {synthesis / max(seconds, 1e-6):.2f} | {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
