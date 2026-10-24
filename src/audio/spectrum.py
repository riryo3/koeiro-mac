import math

import numpy as np

FREQ_MIN = 40.0
FREQ_MAX = 12000.0
BANDS = 28


def band_edges(count=BANDS, low=FREQ_MIN, high=FREQ_MAX):
    """Log-spaced band edges (count + 1 values) from low to high Hz."""
    ratio = (high / low) ** (1.0 / count)
    return [low * ratio ** index for index in range(count + 1)]


def band_levels(samples, sample_rate, edges=None):
    """Per-band level in dBFS (a full-scale sine reads about 0 dB), -90 for silence.

    GUI-side observation of the output tail; the audio callback never calls this.
    """
    edges = edges or band_edges()
    samples = np.asarray(samples, dtype=np.float32)
    count = len(edges) - 1
    if len(samples) < 256:
        return [-90.0] * count
    window = np.hanning(len(samples)).astype(np.float32)
    magnitude = np.abs(np.fft.rfft(samples * window)) * (2.0 / float(window.sum()))
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)
    levels = []
    for index in range(count):
        selected = (freqs >= edges[index]) & (freqs < edges[index + 1])
        if not selected.any():
            # A band narrower than one FFT bin: read the nearest bin so it does not blink off.
            nearest = int(np.argmin(np.abs(freqs - math.sqrt(edges[index] * edges[index + 1]))))
            power = float(magnitude[nearest]) ** 2
        else:
            power = float(np.sum(magnitude[selected] ** 2))
        levels.append(max(-90.0, 10.0 * math.log10(power)) if power > 1e-12 else -90.0)
    return levels
