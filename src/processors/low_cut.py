import math

from .base import AudioProcessor


class _ButterworthCascade(AudioProcessor):
    """Fourth-order Butterworth filter (two biquads) with a live, settable cutoff.

    Switching off resets the filter state; changing the cutoff keeps it, so a slider drag
    never clicks. process() allocates nothing but the sample list and takes no lock.
    """

    # Section Qs of a Butterworth filter; order 4 here, subclasses may use more sections.
    _QS = (0.5411961, 1.3065630)

    def __init__(self, cutoff_hz):
        self.cutoff_hz = float(cutoff_hz)
        self._enabled = False
        self._designed = None
        self._sections = []
        self._state = [[0.0, 0.0] for _ in self._QS]

    def set_enabled(self, enabled):
        # Single flag publication from the control thread; process() never locks.
        self._enabled = bool(enabled)

    def set_cutoff(self, cutoff_hz):
        self.cutoff_hz = float(cutoff_hz)

    def _coefficients(self, cos_w0, alpha):
        raise NotImplementedError

    def _design(self, sample_rate):
        cutoff = self.cutoff_hz
        w0 = 2.0 * math.pi * min(cutoff, sample_rate * 0.45) / sample_rate
        cos_w0 = math.cos(w0)
        self._sections = [self._coefficients(cos_w0, math.sin(w0) / (2.0 * q)) for q in self._QS]
        self._designed = (sample_rate, cutoff)

    def prepare(self, sample_rate, max_frames):
        self._design(sample_rate)
        self.reset()

    def reset(self):
        self._state = [[0.0, 0.0] for _ in self._QS]

    def process(self, audio, sample_rate):
        if not self._enabled:
            self._state = [[0.0, 0.0] for _ in self._QS]
            return audio
        if self._designed != (sample_rate, self.cutoff_hz):
            self._design(sample_rate)
        samples = audio[:, 0].tolist()
        for section, state in zip(self._sections, self._state):
            b0, b1, b2, a1, a2 = section
            z1, z2 = state
            for index, value in enumerate(samples):
                out = b0 * value + z1
                z1 = b1 * value - a1 * out + z2
                z2 = b2 * value - a2 * out
                samples[index] = out
            state[0], state[1] = z1, z2
        audio[:, 0] = samples
        return audio


class InputLowCutProcessor(_ButterworthCascade):
    """High-pass: removes the low band (desk thumps, breath, plosives, a model's thud).

    Used on the microphone signal ahead of everything, and again on converted output.
    Off by default.
    """

    def __init__(self, cutoff_hz=100.0):
        super().__init__(cutoff_hz)

    def _coefficients(self, cos_w0, alpha):
        a0 = 1.0 + alpha
        return ((1.0 + cos_w0) / 2.0 / a0, -(1.0 + cos_w0) / a0, (1.0 + cos_w0) / 2.0 / a0,
                -2.0 * cos_w0 / a0, (1.0 - alpha) / a0)


class OutputHighCutProcessor(_ButterworthCascade):
    """Low-pass: removes the high band (hiss, sibilant bursts) from converted output.

    Order 8 (48 dB per octave): a loud burst still stood out above the cutoff at order 4.
    """

    _QS = (0.5097955, 0.6013449, 0.8999762, 2.5629154)

    def __init__(self, cutoff_hz=6000.0):
        super().__init__(cutoff_hz)

    def _coefficients(self, cos_w0, alpha):
        a0 = 1.0 + alpha
        return ((1.0 - cos_w0) / 2.0 / a0, (1.0 - cos_w0) / a0, (1.0 - cos_w0) / 2.0 / a0,
                -2.0 * cos_w0 / a0, (1.0 - alpha) / a0)
