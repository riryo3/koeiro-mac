import socket
import struct
import threading

import numpy as np
import pytest

from src.vc import remote
from tools.remote_worker import serve

PROTOCOL = remote.PROTOCOL


class Worker:
    """A worker on 127.0.0.1 that answers the two jobs this feature really ships."""

    def __init__(self):
        self.stop = threading.Event()
        self.bound = {}
        self.ready = threading.Event()
        self.thread = threading.Thread(target=serve, args=('127.0.0.1', 0, self.handle),
                                       kwargs={'on_ready': self._on_ready, 'stop': self.stop},
                                       daemon=True)

    def _on_ready(self, host, port):
        self.bound = {'host': host, 'port': port}
        self.ready.set()

    def handle(self, action, request, body):
        if action == 'ping':
            return {'pong': True}, b''
        if action == 'describe':
            return {'worker': 'test-worker', 'protocol': PROTOCOL, 'detail': 'テスト'}, b''
        if action == 'synth':
            tone = np.full(480, 0.25, dtype=np.float32)
            return {'sample_rate': 48000}, remote.pack(tone)
        if action == 'translate':
            return {'text': str(request.get('text', '')).upper()}, b''
        if action == 'explode':
            raise RuntimeError('job failed on purpose')
        raise ValueError(f'unknown action: {action}')

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(5), 'worker did not start'
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)


def test_describe_and_ping_round_trip():
    with Worker() as worker, remote.RemoteClient(worker.bound['host'], worker.bound['port']) as client:
        assert client.ping() is True
        status = client.describe()
        assert status.available and status.worker == 'test-worker' and status.version == PROTOCOL


def test_audio_comes_back_as_float32_frames():
    with Worker() as worker, remote.RemoteClient(worker.bound['host'], worker.bound['port']) as client:
        rate, audio = client.synth('こんにちは')
        assert rate == 48000 and audio.dtype == np.float32
        assert audio.shape == (480,) and np.allclose(audio, 0.25)


def test_a_translation_job_uses_the_same_connection():
    with Worker() as worker:
        client = remote.RemoteClient(worker.bound['host'], worker.bound['port']).connect()
        assert client.translate('hello') == 'HELLO'
        assert client.translate('again') == 'AGAIN'
        client.close()


def test_a_failing_job_raises_and_keeps_the_client_usable():
    with Worker() as worker, remote.RemoteClient(worker.bound['host'], worker.bound['port']) as client:
        with pytest.raises(remote.RemoteError) as failure:
            client.exchange('explode')
        assert 'job failed on purpose' in str(failure.value)
        assert client.ping() is True


def test_an_unknown_job_is_reported_as_an_error():
    with Worker() as worker, remote.RemoteClient(worker.bound['host'], worker.bound['port']) as client:
        with pytest.raises(remote.RemoteError):
            client.exchange('nonsense')


def test_describe_reports_a_dead_worker_instead_of_raising():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing is listening here now
    status = remote.RemoteClient('127.0.0.1', port, timeout=1.0).describe()
    assert status.available is False and status.detail


def test_a_truncated_message_is_rejected_not_reinterpreted():
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]

    def lie():
        connection, _ = server.accept()
        connection.recv(4096)
        connection.sendall(struct.pack('>I', 4096) + b'only a few bytes')
        connection.close()

    threading.Thread(target=lie, daemon=True).start()
    client = remote.RemoteClient('127.0.0.1', port, timeout=2.0).connect()
    with pytest.raises(remote.RemoteError):
        client.ping()
    server.close()


def test_the_client_validates_its_own_configuration():
    with pytest.raises(ValueError):
        remote.RemoteClient('')
    with pytest.raises(ValueError):
        remote.RemoteClient('host', port=0)
    with pytest.raises(ValueError):
        remote.RemoteClient('host', port=70000)


def test_the_client_connects_on_first_use():
    with Worker() as worker:
        client = remote.RemoteClient(worker.bound['host'], worker.bound['port'])
        assert client.connected is False
        assert client.ping() is True
        assert client.connected is True
        client.close()
        assert client.connected is False


def test_audio_packing_round_trips_exactly():
    original = np.linspace(-1, 1, 1000, dtype=np.float32)
    assert np.array_equal(remote.unpack(remote.pack(original)), original)
