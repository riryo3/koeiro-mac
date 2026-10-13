"""Whisper mode: give whispered input a voice the converter can actually work with.

A voice conversion model is trained on *voiced* speech. Whispered speech has the
words and the rhythm but no glottal pulse, so the model hears something close to
noise, and the person who whispered at 2 a.m. gets a mangled or silent result.

This stage puts a pulse back. It does not try to be a trained whisper-to-speech
model; it synthesises a periodic excitation at the user's pitch, shapes it with
the block's own level, and mixes it under the original by ``amount``. The result
keeps the whisper's timing and consonants while giving the converter a
fundamental to lock onto.

Voicing is re-estimated from the last 1024 samples every fourth block, inside
the callback but never waiting on anything: no IPC, no locks, two small bounded
FFTs (tens of microseconds), and the estimate steers the *next* blocks
(AGENTS.md: prior controls for subsequent chunks). Voiced speech, fricatives
and silence keep passing through untouched; only an unvoiced block with
vowel-like low-band energy gets the pulse. :func:`voicedness` is the offline
measurement used by tests and tools.
"""
import math

import numpy as np

from .base import AudioProcessor

TABLE_SIZE = 2048
# Below this RMS a block is silence, not a whisper; nothing is added to it.
RMS_FLOOR = 0.003
DEFAULT_PITCH_HZ = 200.0
# The auto detector reads this many recent samples: long enough for an 80 Hz
# period, short enough to follow speech onsets within a few blocks.
HISTORY_FRAMES = 1024
# Re-estimate voicing this often. Between estimates the previous answer steers
# the next blocks, so audio never waits on the measurement (AGENTS.md: prior
# controls for subsequent chunks).
MEASURE_EVERY_BLOCKS = 4
# Normalised autocorrelation peak at or above this is a voice, not a whisper.
VOICED_PERIODICITY = 0.4
# Whispered vowels carry formant energy down low; fricatives and hiss do not.
# Power ratio of 100..900 Hz over 3..8 kHz, measured on synthetic fixtures as
# ~140 for a whispered vowel, ~1 for white noise and ~0 for an /s/-like hiss.
WHISPER_BAND_RATIO = 5.0


def voicedness(audio, sample_rate, minimum_hz=80.0, maximum_hz=400.0):
    """``(f0_hz, periodicity)`` for one window via autocorrelation.

    Periodicity is the normalised autocorrelation peak in the plausible pitch range:
    near 1 for a clear voice, near 0 for a whisper or noise. Offline only (an FFT per
    call), which is why the callback never uses it.
    """
    signal = np.asarray(audio, dtype=np.float64).reshape(-1)
    if len(signal) < 256:
        return 0.0, 0.0
    signal = signal - signal.mean()
    energy = float(signal @ signal)
    if energy <= 0:
        return 0.0, 0.0
    size = 1 << (2 * len(signal) - 1).bit_length()
    spectrum = np.fft.rfft(signal, size)
    correlation = np.fft.irfft(spectrum * np.conjugate(spectrum), size)[:len(signal)]
    low_lag = max(1, int(sample_rate / maximum_hz))
    high_lag = min(len(signal) - 1, int(sample_rate / minimum_hz))
    if high_lag <= low_lag:
        return 0.0, 0.0
    window = correlation[low_lag:high_lag + 1]
    index = int(np.argmax(window))
    # float() on both: arithmetic with a numpy scalar returns numpy types, and this is
    # a control-path reading that callers compare with ``is``.
    peak = float(window[index]) / float(correlation[0])
    return float(sample_rate / (low_lag + index)), float(max(0.0, min(1.0, peak)))


def analyze_frame(audio, sample_rate):
    """``(f0_hz, periodicity, lowhi)`` for one window, measured, not guessed.

    ``lowhi`` is the power ratio of 100..900 Hz over 3..8 kHz: whispered vowels
    keep formant energy down low while fricatives and hiss concentrate up high,
    so the ratio tells a whispered vowel apart from an /s/ that is equally
    unvoiced. Offline and control-side only, like :func:`voicedness`.
    """
    signal = np.asarray(audio, dtype=np.float32).reshape(-1)
    f0_hz, periodicity = voicedness(signal, sample_rate)
    windowed = signal * np.hanning(len(signal)).astype(np.float32)
    magnitudes = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    low = np.mean(magnitudes[(frequencies >= 100.0) & (frequencies < 900.0)])
    high = np.mean(magnitudes[(frequencies >= 3000.0) & (frequencies < 8000.0)])
    return f0_hz, periodicity, float(low / (high + 1e-12))


def _table():
    """One period of a glottal-ish pulse: a smoothed saw, unit RMS."""
    phase = np.linspace(0.0, 1.0, TABLE_SIZE, endpoint=False)
    pulse = 2.0 * phase - 1.0
    # A one-pole low-pass round the table edge keeps the pulse from buzzing.
    smoothing = 0.5
    smoothed = np.empty_like(pulse)
    value = 0.0
    for index, sample in enumerate(pulse):
        value = smoothing * value + (1.0 - smoothing) * sample
        smoothed[index] = value
    smoothed -= smoothed.mean()
    return (smoothed / np.sqrt(np.mean(smoothed ** 2))).astype(np.float32)


TABLE = _table()


class WhisperVoicer(AudioProcessor):
    """Add a voiced excitation while the input is whisper-like.

    Voicing is re-estimated from recent input every few blocks: voiced speech
    and fricatives pass through untouched, silence stays silence, and only an
    unvoiced block with vowel-like low-band energy gets the pulse. An explicit
    ``set_control(voiced=...)`` pins the flag instead (tests and external
    controllers); a pitch-only update keeps the automatic detection running.
    """

    def __init__(self, amount=0.5, fallback_pitch=DEFAULT_PITCH_HZ, rms_floor=RMS_FLOOR):
        if type(amount) not in (int, float) or not 0 <= amount <= 1:
            raise ValueError('Whisper amount must be between 0 and 1')
        if type(fallback_pitch) not in (int, float) or not 80 <= fallback_pitch <= 400:
            raise ValueError('Fallback pitch must be 80..400 Hz')
        self.amount = float(amount)
        self.fallback_pitch = float(fallback_pitch)
        self.rms_floor = float(rms_floor)
        # Prior controls, written by the analysis thread and read here.
        self._pitch = float(fallback_pitch)
        self._voiced = True
        self._pinned = False
        self._phase = 0.0
        self.sample_rate = 48000.0
        self._history = np.zeros(HISTORY_FRAMES, dtype=np.float32)
        # Start counted so the first block measures immediately: there is no
        # prior yet, and measuring silence reports voiced (pass-through).
        self._blocks_since_measure = MEASURE_EVERY_BLOCKS

    def set_control(self, pitch_hz=None, voiced=None):
        """Update the prior pitch/voicing. Control thread only; no locks in the callback."""
        if pitch_hz is not None:
            if not 80 <= float(pitch_hz) <= 400 or not math.isfinite(float(pitch_hz)):
                raise ValueError('Pitch must be 80..400 Hz')
            self._pitch = float(pitch_hz)
        if voiced is not None:
            # An explicit flag pins the detector until reset(): whoever drives it
            # owns the decision, and the automatic measurement stays out of the way.
            self._voiced = bool(voiced)
            self._pinned = True

    def prepare(self, sample_rate, max_frames):
        self.sample_rate = float(sample_rate)
        self._scale = TABLE_SIZE / self.sample_rate
        self._scratch = np.empty(max_frames, dtype=np.float32)
        self._squares = np.empty(max_frames, dtype=np.float32)
        self._history = np.zeros(HISTORY_FRAMES, dtype=np.float32)
        self._blocks_since_measure = MEASURE_EVERY_BLOCKS
        self._phase = 0.0

    def reset(self):
        self._phase = 0.0
        self._pitch = self.fallback_pitch
        self._voiced = True
        self._pinned = False
        self._history = np.zeros(HISTORY_FRAMES, dtype=np.float32)
        self._blocks_since_measure = MEASURE_EVERY_BLOCKS

    def _measure(self):
        """Fold the recent input into the voicing flag. Bounded and allocation-light."""
        _, periodicity, lowhi = analyze_frame(self._history, self.sample_rate)
        # Silence and hiss report no periodicity either; the band ratio is what
        # keeps the pulse away from them. A stale True is the safe direction:
        # doubt means pass-through, never added buzz.
        self._voiced = not (periodicity < VOICED_PERIODICITY and lowhi >= WHISPER_BAND_RATIO)

    def _excitation(self, frames, level):
        phase = self._phase + self._scale * self._pitch * np.arange(frames, dtype=np.float64)
        positions = np.mod(phase, TABLE_SIZE)
        index = positions.astype(np.int64)
        fraction = (positions - index).astype(np.float32)
        table = TABLE[index % TABLE_SIZE]
        following = TABLE[(index + 1) % TABLE_SIZE]
        np.multiply(following - table, fraction, out=self._scratch[:frames])
        np.add(self._scratch[:frames], table, out=self._scratch[:frames])
        self._phase = float(np.mod(positions[-1] + self._scale * self._pitch, TABLE_SIZE))
        np.multiply(self._scratch[:frames], level, out=self._scratch[:frames])
        return self._scratch[:frames]

    def process(self, audio, sample_rate):
        if self.amount <= 0:
            return audio
        if not self._pinned:
            mono = np.asarray(audio[:, 0], dtype=np.float32).reshape(-1)
            if mono.size >= HISTORY_FRAMES:
                self._history = mono[-HISTORY_FRAMES:].copy()
            elif mono.size:
                self._history = np.roll(self._history, -mono.size)
                self._history[-mono.size:] = mono
            self._blocks_since_measure += 1
            if self._blocks_since_measure >= MEASURE_EVERY_BLOCKS:
                self._blocks_since_measure = 0
                self._measure()
        if self._voiced:
            return audio
        frames = len(audio)
        squares = self._squares[:frames]
        np.multiply(audio[:, 0], audio[:, 0], out=squares)
        level = math.sqrt(float(np.mean(squares)))
        if level < self.rms_floor:
            # Silence stays silence: adding a pulse to nothing would be a noise source.
            return audio
        excitation = self._excitation(frames, level)
        mix = float(self.amount)
        np.multiply(audio[:, 0], 1.0 - mix, out=audio[:, 0])
        np.multiply(excitation, mix, out=self._scratch[:frames])
        np.add(audio[:, 0], self._scratch[:frames], out=audio[:, 0])
        return audio
