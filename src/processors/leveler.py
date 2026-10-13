"""Automatic input levelling for small voices, off by default.

A quiet input is what a conversion model grips worst: the embedding drowns and
male residue survives. This stage rides a slow gain toward a fixed speech RMS
so the model always sees the same level, capped so a whisper never becomes a
noise blast and frozen below the floor so silence is never boosted. Attack is
quicker than release (half a second up, two seconds down), all in time
constants rather than block counts so any buffer size behaves the same.

Off is a true pass-through: the same buffer back, untouched.
"""
import math

import numpy as np

from .base import AudioProcessor

TARGET_RMS = 0.1
MAX_GAIN_DB = 12.0
MIN_GAIN_DB = -12.0
ATTACK_SECONDS = 0.5
RELEASE_SECONDS = 2.0
# Below this block RMS the gain holds: boosting the floor feeds the model hiss.
FLOOR_RMS = 10.0 ** (-50.0 / 20.0)


class AutoLevelProcessor(AudioProcessor):
    """Slow ride toward a fixed speech level, or nothing at all."""

    def __init__(self, enabled=False, target_rms=TARGET_RMS):
        if type(target_rms) not in (int, float) or not 0 < target_rms <= 1.0:
            raise ValueError('Level target must be within 0..1')
        self.enabled = bool(enabled)
        self.target_rms = float(target_rms)
        self._rate = 48000.0
        self._gain_db = 0.0
        self._applied = 1.0

    def prepare(self, sample_rate, max_frames):
        self._rate = float(sample_rate)
        self._gain_db = 0.0
        self._applied = 1.0

    def reset(self):
        self._gain_db = 0.0
        self._applied = 1.0

    def _block_coeff(self, seconds, frames):
        return 1.0 - math.exp(-frames / (seconds * self._rate))

    def process(self, audio, sample_rate):
        if not self.enabled:
            return audio
        out = np.asarray(audio[:, 0], dtype=np.float32)
        frames = len(out)
        if frames == 0:
            return audio
        rms = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
        if rms >= FLOOR_RMS:
            want_db = 20.0 * math.log10(self.target_rms / max(rms, 1e-9))
            want_db = min(MAX_GAIN_DB, max(MIN_GAIN_DB, want_db))
            tc = ATTACK_SECONDS if want_db > self._gain_db else RELEASE_SECONDS
            self._gain_db += self._block_coeff(tc, frames) * (want_db - self._gain_db)
        target = 10.0 ** (self._gain_db / 20.0)
        # The follower barely moves per block, but ramping from the last
        # applied gain keeps even a freshly enabled stage from stepping.
        out *= np.linspace(self._applied, target, frames).astype(np.float32)
        self._applied = target
        return audio
