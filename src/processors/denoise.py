"""Optional spectral noise reduction, off by default.

Strength 0 is a true pass-through: no FFT, no allocation, the callback gets the
same buffer back. Above 0 the processor rfft's each block, tracks a per-bin noise
floor with a slow exponential average of the magnitude, subtracts a
strength-scaled share of it and irfft's back. A slow average is what makes a
steady floor learnable while a loud, time-varying signal passes: the floor moves
~8% per block, so a short burst barely raises it, while stationary noise (whose
magnitude sits at the floor) is attenuated. No window and no overlap-add, so the
frame count and the pass-through signal are preserved exactly and no internal
latency is added; the price is that the gain is piecewise per block, which is why
the control is a user choice rather than always on.
"""
import math

import numpy as np

from .base import AudioProcessor

MAX_STRENGTH = 1.0
FLOOR_DB_LOW = -40.0
FLOOR_DB_HIGH = -3.0
# How much of the current magnitude the floor adopts each block. Small enough that
# a short burst is not mistaken for the floor, large enough to converge quickly.
FLOOR_TRACKING = 0.08


class NoiseSuppressionProcessor(AudioProcessor):
    """Per-block spectral subtraction with a gain floor and a slow noise floor."""

    def __init__(self, strength=0.0, floor_db=-12.0):
        self._strength = 0.0
        self.set_floor(floor_db)
        self.set_strength(strength)

    def set_strength(self, strength):
        """0..1. 0 disables the stage entirely; the callback never sees an FFT."""
        if type(strength) not in (int, float) or not math.isfinite(strength) or not 0.0 <= strength <= MAX_STRENGTH:
            raise ValueError("Noise reduction strength must be between 0 and 1")
        self._strength = float(strength)
        return self._strength

    def set_floor(self, floor_db):
        """How far a fully-noise bin is attenuated, in dB (a floor, never silence)."""
        if (type(floor_db) not in (int, float) or not math.isfinite(floor_db)
                or not FLOOR_DB_LOW <= floor_db <= FLOOR_DB_HIGH):
            raise ValueError("Noise reduction floor must be -40..-3 dB")
        self._floor = 10.0 ** (float(floor_db) / 20.0)

    @property
    def strength(self):
        return self._strength

    def prepare(self, sample_rate, max_frames):
        bins = max_frames // 2 + 1
        self._noise = np.zeros(bins, dtype=np.float32)
        self._gain = np.empty(bins, dtype=np.float32)
        self._seen = False

    def reset(self):
        self._seen = False
        noise = getattr(self, "_noise", None)
        if noise is not None:
            noise.fill(0.0)

    def process(self, audio, sample_rate):
        strength = self._strength
        if strength <= 0.0:
            return audio
        spectrum = np.fft.rfft(audio[:, 0])
        magnitude = np.abs(spectrum)
        noise = self._noise
        if not self._seen:
            # The first block *is* the floor; suppressing against zero would pass it.
            noise[:] = magnitude
            self._seen = True
            return audio
        gain = self._gain
        # gain is first a scratch for magnitude*beta, then becomes the real gain.
        np.multiply(magnitude, FLOOR_TRACKING, out=gain)
        np.multiply(noise, 1.0 - FLOOR_TRACKING, out=noise)
        np.add(noise, gain, out=noise)
        np.multiply(noise, strength, out=gain)
        np.subtract(magnitude, gain, out=gain)
        np.maximum(gain, 0.0, out=gain)
        np.divide(gain, magnitude + 1e-9, out=gain)
        np.clip(gain, self._floor, 1.0, out=gain)
        np.multiply(spectrum, gain, out=spectrum)
        audio[:, 0] = np.fft.irfft(spectrum, len(audio))
        return audio
