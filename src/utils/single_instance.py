"""One Koeiro per data directory.

Launching the executable twice would open two windows fighting over the same
settings file and audio devices, so the second process hands over to the first
and exits instead. The hand-off uses a Qt local socket/server pair: a named pipe
on Windows, a Unix domain socket elsewhere. The name is derived from the data
directory, so a separate profile (``--data-dir``) or a parallel test run still
starts normally. A stale name left behind by a crash is cleared before listening.
"""
import hashlib

from PySide6.QtNetwork import QLocalServer, QLocalSocket

CONNECT_TIMEOUT_MS = 400
ACTIVATE_MESSAGE = b'activate'


def instance_key(data_dir):
    """A stable, filesystem-safe server name for one data directory."""
    digest = hashlib.sha1(str(data_dir).lower().encode('utf-8')).hexdigest()[:16]
    return f'Koeiro-{digest}'


class SingleInstance:
    """Acquire-once guard: the first caller owns the key, later ones hand over."""

    def __init__(self, key):
        self.key = key
        self.server = None
        self._callback = None

    def acquire(self):
        """Return True when this process owns the app, False when another already does."""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if socket.waitForConnected(CONNECT_TIMEOUT_MS):
            socket.write(ACTIVATE_MESSAGE)
            socket.flush()
            socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
            socket.disconnectFromServer()
            return False
        # Nobody is listening: become the owner. removeServer clears a pipe or
        # socket file a crash left behind, so listen() cannot fail on a dead name.
        QLocalServer.removeServer(self.key)
        server = QLocalServer()
        if not server.listen(self.key):
            # A broken pipe name must never stop the app from starting.
            return True
        self.server = server
        self.server.newConnection.connect(self._accept)
        return True

    def on_activate(self, callback):
        """Run callback (on the Qt thread) when a second launch asks for the window."""
        self._callback = callback

    def _accept(self):
        socket = self.server.nextPendingConnection()
        if socket is not None:
            socket.waitForReadyRead(CONNECT_TIMEOUT_MS)
        if self._callback is not None:
            self._callback()

    def close(self):
        if self.server is not None:
            self.server.close()
            QLocalServer.removeServer(self.key)
            self.server = None
