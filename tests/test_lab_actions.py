import json
import socket
import threading

import numpy as np
import pytest

from src.lab import actions
from src.vc import remote
from tools.remote_worker import serve


def registration(root, name, pitch, seconds=4.0, rate=48000):
    """A registration whose reference is a real 16-bit PCM WAV of one pitched voice."""
    identifier = 'user_' + name.rjust(32, '0')
    folder = root / 'models' / 'user_voices' / identifier
    folder.mkdir(parents=True)
    times = np.arange(int(rate * seconds)) / rate
    tone = (0.15 * np.sign(np.sin(2 * np.pi * pitch * times))).astype(np.float32)
    actions.write_wav(folder / 'reference.wav', tone, rate)
    (folder / 'profile.json').write_text(json.dumps({
        'schema': 1, 'id': identifier, 'name': name, 'reference_seconds': seconds,
        'source_filename': 'reference.wav'}), encoding='utf-8')
    (folder / 'runtime.json').write_text('{}', encoding='utf-8')
    np.save(folder / 'fixed_embedding.npy', np.full(8, pitch, dtype=np.float32))
    return folder


def test_writing_and_reading_a_wav_round_trips():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'nested' / 'tone.wav'
        times = np.arange(4800) / 48000
        tone = (0.5 * np.sin(2 * np.pi * 300 * times)).astype(np.float32)
        actions.write_wav(target, tone, 48000)
        rate, samples = actions.load_wav(target)
        assert rate == 48000 and samples.size == 4800
        assert np.sqrt(np.mean(samples ** 2)) == pytest.approx(0.5 / np.sqrt(2), rel=0.05)
        assert (target.parent / 'tone.wav').is_file()


def test_a_reference_that_is_not_pcm_is_reported():
    """One error type for every unreadable file, because the callers catch ValueError.

    The wave module answers a float-encoded DAW export, an empty file and a renamed
    text file with its own wave.Error/EOFError, so an `except ValueError` upstream
    let them through; `pytest.raises(Exception)` used to accept any of that.
    """
    import struct
    import tempfile
    import wave
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)

        def expect_value_error(path):
            try:
                actions.load_wav(path)
            except ValueError:
                return
            except Exception as error:
                pytest.fail(f'{path.name} leaked {type(error).__name__}: {error}')
            pytest.fail(f'{path.name} loaded but it is not usable audio')

        text = root / 'text.wav'
        text.write_bytes(b'not a wav')
        expect_value_error(text)

        empty = root / 'empty.wav'
        empty.write_bytes(b'')
        expect_value_error(empty)

        # A 32-bit float WAV: a normal export from a DAW, and not what this reads.
        payload = np.zeros(1200, dtype='<f4').tobytes()
        floats = root / 'float.wav'
        floats.write_bytes(b'RIFF' + struct.pack('<I', 20 + len(payload)) + b'WAVE'
                           + b'fmt ' + struct.pack('<IHHIIHH', 16, 3, 1, 48000, 192000, 4, 32)
                           + b'data' + struct.pack('<I', len(payload)) + payload)
        expect_value_error(floats)

        header_only = root / 'silent.wav'
        with wave.open(str(header_only), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b'')
        expect_value_error(header_only)

        # What the function does accept still round-trips, stereo folded to mono.
        stereo = root / 'stereo.wav'
        with wave.open(str(stereo), 'wb') as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(np.full(2400, 1000, dtype='<i2').tobytes())
        rate, samples = actions.load_wav(stereo)
        assert rate == 48000 and samples.size == 1200


def test_the_translation_job_writes_a_file_and_reports_what_it_measured(tmp_path):
    from pathlib import Path
    output = Path(tmp_path) / 'lab' / 'translate.wav'
    message = actions.translate_test(tmp_path, 'off', '', None, 'こんにちは', output)
    assert output.is_file() and output.stat().st_size > 44
    # The base route is a pass-through translator and silence: say so, and say that
    # nothing was listened to.
    assert '翻訳なし' in message and '聴感は未確認' in message


def test_the_translation_job_uses_a_reference_when_given_one(tmp_path):
    folder = registration(tmp_path, 'alice', 140.0)
    output = tmp_path / 'translate.wav'
    message = actions.translate_test(tmp_path, 'off', '', folder / 'reference.wav', 'こんにちは',
                                     output)
    assert output.is_file() and '聴感は未確認' in message


def test_the_worker_probe_explains_a_missing_host():
    assert '未設定' in actions.probe_worker('', 8765)


def test_the_worker_probe_reports_a_dead_worker():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    assert '接続できません' in actions.probe_worker('127.0.0.1', port)


def test_the_worker_probe_describes_a_live_worker():
    ready, stop = threading.Event(), threading.Event()
    bound = {}

    def handler(action, request, body):
        if action == 'describe':
            return {'worker': 'lab-test', 'protocol': remote.PROTOCOL, 'detail': 'TTS可'}, b''
        return {'pong': True}, b''

    def on_ready(host, port):
        bound.update(host=host, port=port)
        ready.set()

    thread = threading.Thread(target=serve, args=('127.0.0.1', 0, handler),
                              kwargs={'on_ready': on_ready, 'stop': stop}, daemon=True)
    thread.start()
    try:
        assert ready.wait(5)
        message = actions.probe_worker(bound['host'], bound['port'])
        assert 'lab-test に接続しました' in message and 'TTS可' in message
    finally:
        stop.set()
        thread.join(5)


def test_speaker_test_separates_two_different_voices(tmp_path):
    first = registration(tmp_path, 'alice', 120.0)
    second = registration(tmp_path, 'bob', 260.0)
    message = actions.speaker_test(first, second, 2)
    assert '分離しました' in message


def test_speaker_test_admits_when_two_recordings_are_the_same_voice(tmp_path):
    first = registration(tmp_path, 'alice', 180.0)
    second = registration(tmp_path, 'bob', 180.0)
    message = actions.speaker_test(first, second, 2)
    assert '分離できませんでした' in message
