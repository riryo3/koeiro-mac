"""Spoken-translation playback for the translate route.

The control side (see :mod:`src.translate.live`) appends one fully synthesized
utterance at a time; the callback consumes it block by block. The handoff is a
plain rebinding (atomic under the GIL): no locks, no waiting, no allocation in
the callback beyond the slice it is already handed. A short fade rises out of
silence and another settles each utterance tail, so joins never click; between
utterances the route is honest silence, never the untranslated microphone.
"""
import numpy as np

FADE = 64
# Utterances waiting while one plays; beyond this the oldest is dropped and
# counted, so a fast talker cannot grow the queue without bound.
MAX_QUEUED = 4


class TranslatePlayback:
    """FIFO of finished TTS utterances rendered into the audio callback."""

    def __init__(self):
        self._queue = []
        self._current = np.zeros(0, dtype=np.float32)
        self._offset = 0
        self._from_silence = True
        self.played_utterances = 0
        self.dropped_utterances = 0

    def reset(self):
        self._queue = []
        self._current = np.zeros(0, dtype=np.float32)
        self._offset = 0
        self._from_silence = True

    @property
    def queued_seconds(self):
        total = sum(len(part) for part in self._queue) + max(0, len(self._current) - self._offset)
        return total / 48000.0

    def offer(self, audio):
        """Queue one synthesized utterance. Control side only."""
        part = np.asarray(audio, dtype=np.float32).reshape(-1)
        if part.size == 0 or not np.isfinite(part).all():
            return False
        part = np.clip(part, -1.0, 1.0)
        self._queue.append(part)
        while len(self._queue) > MAX_QUEUED:
            self._queue.pop(0)
            self.dropped_utterances += 1
        return True

    def _next(self):
        self._current = self._queue.pop(0) if self._queue else np.zeros(0, dtype=np.float32)
        self._offset = 0
        if self._current.size:
            self.played_utterances += 1

    def render_into(self, destination):
        """Fill ``destination`` with translated speech or silence. Callback side."""
        out = np.asarray(destination).reshape(-1)
        filled = 0
        while filled < len(out):
            if self._offset >= len(self._current):
                if not self._queue:
                    out[filled:] = 0.0
                    self._from_silence = True
                    return out
                self._next()
                continue
            take = min(len(out) - filled, len(self._current) - self._offset)
            chunk = self._current[self._offset:self._offset + take]
            if self._from_silence:
                # Rise out of silence instead of starting mid-waveform.
                span = min(take, FADE)
                ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(span) / max(1, span))
                out[filled:filled + span] = chunk[:span] * ramp
                out[filled + span:filled + take] = chunk[span:take]
                self._from_silence = False
            else:
                out[filled:filled + take] = chunk
            self._offset += take
            filled += take
            if self._offset >= len(self._current) and not self._queue:
                # Settle the tail instead of chopping it onto silence.
                tail = min(filled, FADE)
                if tail > 1:
                    ramp = 0.5 + 0.5 * np.cos(np.pi * np.arange(tail) / max(1, tail))
                    out[filled - tail:filled] *= ramp
        return out
