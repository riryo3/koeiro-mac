import math

import numpy as np

from .base import AudioProcessor


class GainProcessor(AudioProcessor):
    """Gain with a 5 ms exponential transition to avoid abrupt slider steps."""

    def __init__(self, gain_db: float = 0.0):
        self.set_gain(gain_db)
        self._current = self._target
        self.peak = 0.0   # loudest sample since the GUI last looked (observation only)

    def set_gain(self, gain_db: float) -> None:
        if not math.isfinite(gain_db) or not -20 <= gain_db <= 20:
            raise ValueError("Gain must be between -20 and +20 dB")
        # Called by the UI/control thread, never does allocation in process().
        self._target = 10.0 ** (gain_db / 20.0)

    def prepare(self, sample_rate, max_frames):
        self._decay = np.exp(-np.arange(1, max_frames + 1, dtype=np.float32)
                             / (0.005 * sample_rate)).reshape(-1, 1)
        self._ramp = np.empty((max_frames, 1), dtype=np.float32)
        self.reset()

    def reset(self):
        self._current = self._target

    def process(self, audio, sample_rate):
        target = self._target  # Single scalar publication; no callback lock.
        if abs(self._current - target) < 1e-6:
            self._current = target
            np.multiply(audio, target, out=audio)
        else:
            ramp = self._ramp[:len(audio)]
            np.multiply(self._decay[:len(audio)], self._current - target, out=ramp)
            np.add(ramp, target, out=ramp)
            self._current = float(ramp[-1, 0])
            np.multiply(audio, ramp, out=audio)
        if len(audio):
            loudest = max(float(audio.max()), -float(audio.min()))   # reductions only: no allocation here
            if loudest > self.peak:
                self.peak = loudest
        return audio

    def take_peak(self):
        """The loudest sample after the gain since the last call (the GUI's LED reads this)."""
        peak, self.peak = self.peak, 0.0
        return peak
