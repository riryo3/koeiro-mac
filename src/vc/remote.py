"""Distributed inference: let a GPU machine on the LAN do the heavy work.

The app already runs inference in a separate process; this module puts that process
on the network. A weak laptop keeps the microphone, the routing and the UI, and asks
a desktop with a GPU to do the slow parts.

The transport is deliberately boring -- a TCP connection, a length-prefixed JSON
header, an optional length-prefixed binary body -- because the interesting part of
this feature is *where* the work runs, not the wire format. Both frames are length
prefixed, so a partial read or a truncated payload is detected rather than silently
reinterpreted as audio.

What is real today: the connection, the request/response round trip, timeouts,
malformed-input rejection, and two working jobs -- synthetic speech and translation --
served by ``tools/remote_worker.py``. What is not wired yet: the voice-conversion
model itself, which would need the audio ring shared across the network; the worker
reports that honestly in ``describe`` instead of pretending to accept it.

Nothing here is called from the audio callback: a network round trip per block would
guarantee overruns.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
import numpy as np
import socket
import struct

log = logging.getLogger(__name__)

HEADER = struct.Struct('>I')
MAX_PAYLOAD = 64 * 1024 * 1024
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT = 5.0
AUDIO_DTYPE = np.dtype('<f4')
PROTOCOL = 1


class RemoteError(RuntimeError):
    """The worker refused, answered with an error, or the transport failed."""


@dataclass(frozen=True)
class RemoteStatus:
    available: bool
    detail: str
    worker: str = ''
    version: int = PROTOCOL


def pack(array):
    return np.asarray(array, dtype=AUDIO_DTYPE).tobytes()


def unpack(payload):
    return np.frombuffer(payload, dtype=AUDIO_DTYPE).astype(np.float32)


def _send(sock, payload):
    if len(payload) > MAX_PAYLOAD:
        raise RemoteError('Payload too large')
    sock.sendall(HEADER.pack(len(payload)) + payload)


def _receive(sock):
    head = _read_exactly(sock, HEADER.size)
    (length,) = HEADER.unpack(head)
    if length > MAX_PAYLOAD:
        raise RemoteError('Declared payload is too large')
    return _read_exactly(sock, length)


def _read_exactly(sock, count):
    chunks = []
    remaining = count
    while remaining:
        chunk = sock.recv(min(remaining, 1 << 20))
        if not chunk:
            raise RemoteError('Connection closed mid-message')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


class RemoteClient:
    """One connection to a worker. Serial: one request at a time, by design."""

    def __init__(self, host, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        if not isinstance(host, str) or not host.strip():
            raise ValueError('A worker host is required')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Port must be 1..65535')
        self.host = host.strip()
        self.port = port
        self.timeout = float(timeout)
        self._socket = None

    @property
    def connected(self):
        return self._socket is not None

    def connect(self):
        try:
            self._socket = socket.create_connection((self.host, self.port), self.timeout)
            self._socket.settimeout(self.timeout)
        except OSError as error:
            self._socket = None
            raise RemoteError(f'{self.host}:{self.port} に接続できません: {error}') from error
        return self

    def close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exception):
        self.close()
        return False

    @contextmanager
    def session(self):
        try:
            if not self.connected:
                self.connect()
            yield self
        finally:
            self.close()

    def exchange(self, action, body=b'', **fields):
        """Send one request and return ``(header, payload)``.

        Connects on first use, so a caller can hold a client for a worker that may
        not be awake yet without deciding when to dial.
        """
        if not self.connected:
            self.connect()
        request = {'action': action, 'protocol': PROTOCOL, **fields}
        try:
            _send(self._socket, json.dumps(request, ensure_ascii=False).encode('utf-8'))
            _send(self._socket, body)
            header = json.loads(_receive(self._socket).decode('utf-8'))
            payload = _receive(self._socket)
        except (OSError, ValueError, UnicodeDecodeError) as error:
            self.close()
            raise RemoteError(f'Worker request failed: {error}') from error
        if not isinstance(header, dict):
            raise RemoteError('Worker answered with a malformed header')
        if header.get('error'):
            raise RemoteError(str(header['error']))
        return header, payload

    def describe(self):
        """Ask the worker what it is and what it can do."""
        try:
            header, _ = self.exchange('describe')
        except RemoteError as error:
            return RemoteStatus(False, str(error))
        return RemoteStatus(True, header.get('detail', ''), header.get('worker', ''),
                            int(header.get('protocol', PROTOCOL)))

    def ping(self):
        header, _ = self.exchange('ping')
        return bool(header.get('pong'))

    def synth(self, text, voice=''):
        """Synthesize on the worker; returns float32 mono at the worker's rate."""
        header, payload = self.exchange('synth', text=text, voice=voice)
        return int(header.get('sample_rate', 48000)), unpack(payload)

    def translate(self, text, source='ja', target='en'):
        header, _ = self.exchange('translate', text=text, source=source, target=target)
        return str(header.get('text', ''))


def serve_connection(connection, handler, timeout=DEFAULT_TIMEOUT):
    """Answer requests on ``connection`` until the client stops asking."""
    connection.settimeout(timeout)
    while True:
        try:
            request = json.loads(_receive(connection).decode('utf-8'))
            body = _receive(connection)
        except RemoteError:
            return
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(request, dict):
            return
        try:
            header, payload = handler(request.get('action'), request, body)
        except Exception as error:  # a bad job must not take the worker down
            log.warning('Worker job failed: %s', error, exc_info=True)
            header, payload = {'error': str(error)}, b''
        try:
            _send(connection, json.dumps(header, ensure_ascii=False).encode('utf-8'))
            _send(connection, payload)
        except OSError:
            return
