"""Serve speech synthesis and translation from this machine to another Koeiro.

Run this on the machine with the GPU (or just with the models installed), then point
the other machine's 実験室 → 分散推論 at its address. The heavy per-utterance work
happens here, off the caller's audio callback.

    python tools/remote_worker.py --port 8765

The worker only ever answers the jobs it can actually do. Voice conversion over the
network is not one of them yet (it would need the audio ring shared across the wire),
so ``describe`` says so instead of accepting a job it would fail.

Safety: this listens on the LAN and executes model jobs for whoever connects, on the
audio the caller sends. Run it on a network you trust, and do not expose the port to
the internet -- there is no authentication yet, which is stated here rather than
discovered later.
"""
import argparse
import logging
from pathlib import Path
import socket
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.vc import remote  # noqa: E402  (needs the path above)


def build_handler(root, voice=''):
    """The jobs this worker answers. Models are loaded on first use, then reused."""
    state = {'pipeline': None, 'translator': None, 'status': ''}

    def pipeline():
        if state['pipeline'] is None:
            from src.translate.providers import build_pipeline
            state['pipeline'], state['status'] = build_pipeline(root, 'kokoro', voice)
        return state['pipeline']

    def translator():
        if state['translator'] is None:
            from src.translate.providers import translator_for
            state['translator'] = translator_for('argos')
            if state['translator'] is None:
                raise RuntimeError('argostranslate が未導入です（pip install argostranslate）')
        return state['translator']

    def handler(action, request, body):
        if action == 'ping':
            return {'pong': True}, b''
        if action == 'describe':
            from src.tts import provider as tts
            return {'worker': socket.gethostname(), 'protocol': remote.PROTOCOL,
                    'tts': tts.available(root), 'voice_conversion': False,
                    'detail': ('TTS/翻訳を実行します。声変換モデルのLAN配信は未対応です。'
                               + ('（Kokoro導入済み）' if tts.available(root)
                                  else '（Kokoro未導入: tools/install_tts.py）'))}, b''
        if action == 'synth':
            audio = pipeline().speak(str(request.get('text', '')), request.get('voice', ''))
            return {'sample_rate': pipeline().sample_rate}, remote.pack(audio)
        if action == 'translate':
            text = pipeline().translate(str(request.get('text', '')), request.get('source', 'ja'),
                                        request.get('target', 'en'))
            if text == str(request.get('text', '')) and state['status'] == '翻訳なし（素通し・無音）':
                text = translator().translate(str(request.get('text', '')), 'ja', 'en')
            return {'text': text}, b''
        raise ValueError(f'unknown action: {action}')

    return handler


def serve(host, port, handler, on_ready=None, stop=None, timeout=5.0):
    """Accept connections until ``stop`` is set. Returns the bound address."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(4)
    server.settimeout(0.2)
    bound = server.getsockname()
    logging.getLogger(__name__).info('Remote worker listening on %s:%s', *bound)
    if on_ready is not None:
        on_ready(*bound)
    try:
        while not (stop is not None and stop.is_set()):
            try:
                connection, address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            logging.getLogger(__name__).info('Worker connection from %s', address[0])
            threading.Thread(target=remote.serve_connection,
                             args=(connection, handler),
                             kwargs={'timeout': timeout}, daemon=True).start()
    finally:
        server.close()
    return bound


def main(argv=None):
    parser = argparse.ArgumentParser(description='Koeiro LAN inference worker (TTS and translation)')
    parser.add_argument('--host', default='0.0.0.0', help='Interface to bind (default all)')
    parser.add_argument('--port', type=int, default=remote.DEFAULT_PORT)
    parser.add_argument('--voice', default='', help='Default TTS voice for synth requests')
    parser.add_argument('--root', default=str(ROOT), help='Folder holding models/')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    handler = build_handler(args.root, args.voice)
    try:
        serve(args.host, args.port, handler)
    except KeyboardInterrupt:
        print('worker stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
