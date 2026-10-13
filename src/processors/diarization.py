"""More than one person, one microphone, one voice each.

Two friends share a mic; both want their own character voice. Splitting them needs a
speaker decision per block, and that decision must be cheap and stable, because it
drives which voice is loaded.

The tracker works on a two-number description of a block -- the fundamental and the
spectral centroid, both on log scales -- clustered online into at most ``speakers``
centroids. It is a *feature-space* tracker, not a neural diariser: honest about what
it can and cannot do. Two speakers with different pitch or brightness separate well;
two people whose pitch and brightness both match will not separate, and no amount of
tuning fixes that because the information is not in the features.

Voiced frames only. A whisper, a cough or a fan has no pitch to be identified by, and
claiming a speaker there would just flicker the routed voice, so those frames return
``None`` and the caller keeps the voice it already had.

:func:`features` is offline (an FFT per block) and belongs on the analysis side, like
the prosody path; the tracker itself is pure arithmetic and can be fed from wherever
those numbers come from.
"""
from dataclasses import dataclass
import math

import numpy as np

# A centroid below this is treated as voiced-ish content rather than a click.
MIN_RMS = 0.004
# How conservative segmentation is: a new speaker must be clearly far from every
# existing centroid, and a reassignment must beat the current one by this margin.
NEW_SPEAKER_DISTANCE = 0.55
REASSIGN_MARGIN = 0.15
EMA = 0.25


def features(audio, sample_rate):
    """``(f0_hz, centroid_hz, rms, voiced)`` for one block. Offline, analysis side."""
    from .whisper import voicedness
    signal = np.asarray(audio, dtype=np.float64).reshape(-1)
    if len(signal) < 256:
        return 0.0, 0.0, 0.0, False
    rms = float(np.sqrt(np.mean(signal ** 2)))
    if rms < MIN_RMS:
        return 0.0, 0.0, rms, False
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    frequencies = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    total = float(spectrum.sum())
    centroid = float((spectrum * frequencies).sum() / total) if total > 0 else 0.0
    f0, periodicity = voicedness(signal, sample_rate)
    return f0, centroid, rms, bool(periodicity >= 0.35)


@dataclass(frozen=True)
class SpeakerState:
    label: int | None
    speakers: int
    reason: str


class SpeakerTracker:
    """Online nearest-centroid clustering of (log pitch, log centroid).

    A new speaker is admitted only after the same far-away description repeats, so a
    cough or a chair creak cannot take one of the slots. The candidate buffer is what
    makes "the second person starts talking later" work at all: the first speaker
    must not consume the discovery budget by simply speaking first.
    """

    def __init__(self, speakers=2, minimum_frames=3):
        if type(speakers) is not int or not 2 <= speakers <= 4:
            raise ValueError('Speaker count must be 2..4')
        if type(minimum_frames) is not int or not 1 <= minimum_frames <= 100:
            raise ValueError('Invalid minimum frame count')
        self.maximum = speakers
        self.minimum_frames = minimum_frames
        self.reset()

    def reset(self):
        self._centroids = []
        self._weights = []
        self._candidates = []
        self._frames = 0
        self._label = None

    @staticmethod
    def _vector(f0, centroid, sample_rate=48000.0):
        return np.array([math.log2(max(1.0, f0)), math.log2(max(1.0, centroid))])

    def _promote(self, vector):
        self._centroids.append(np.asarray(vector, dtype=np.float64))
        self._weights.append(1.0)
        self._label = len(self._centroids) - 1
        return self._label

    def _candidate(self, vector):
        """The pending candidate this frame continues, if any."""
        for candidate in self._candidates:
            if float(np.linalg.norm(vector - candidate['vector'])) <= NEW_SPEAKER_DISTANCE / 2:
                return candidate
        return None

    def observe(self, f0, centroid, voiced=True):
        """Fold one analysis block in and return the current speaker label."""
        self._frames += 1
        if not voiced or f0 <= 0 or centroid <= 0:
            return SpeakerState(self._label, len(self._centroids), 'unvoiced')
        vector = self._vector(f0, centroid)
        if not self._centroids:
            return SpeakerState(self._promote(vector), 1, 'first speaker')
        distances = [float(np.linalg.norm(vector - centre)) for centre in self._centroids]
        nearest = int(np.argmin(distances))
        if distances[nearest] > NEW_SPEAKER_DISTANCE and len(self._centroids) < self.maximum:
            candidate = self._candidate(vector)
            if candidate is None:
                # Remember the description but follow the closest known speaker until
                # it repeats; at most one pending candidate per open slot.
                if len(self._candidates) >= self.maximum:
                    oldest = min(self._candidates, key=lambda item: item['frame'])
                    self._candidates.remove(oldest)
                self._candidates.append({'vector': vector, 'seen': 1, 'frame': self._frames})
                return SpeakerState(nearest, len(self._centroids), 'candidate')
            candidate['vector'] = candidate['vector'] * (1 - EMA) + vector * EMA
            candidate['seen'] += 1
            candidate['frame'] = self._frames
            if candidate['seen'] >= self.minimum_frames:
                self._candidates.remove(candidate)
                label = self._promote(candidate['vector'])
                return SpeakerState(label, len(self._centroids), 'new speaker')
            return SpeakerState(nearest, len(self._centroids), 'candidate')
        if self._label is not None and nearest != self._label:
            current = distances[self._label] if self._label < len(distances) else float('inf')
            if current - distances[nearest] < REASSIGN_MARGIN:
                nearest = self._label
                distances[nearest] = current
        weight = self._weights[nearest]
        self._centroids[nearest] = (self._centroids[nearest] * (1 - EMA) + vector * EMA)
        self._weights[nearest] = min(50.0, weight + 1.0)
        self._label = nearest
        return SpeakerState(nearest, len(self._centroids), 'tracked')

    @property
    def label(self):
        return self._label


class SpeakerRouting:
    """Which registered voice answers for which speaker."""

    def __init__(self, mapping=None):
        self.mapping = {}
        for speaker, voice in (mapping or {}).items():
            self.set(speaker, voice)

    def set(self, speaker, voice_id):
        if type(speaker) is not int or not 0 <= speaker <= 3:
            raise ValueError('Speaker label must be 0..3')
        if voice_id is None:
            self.mapping.pop(speaker, None)
        elif isinstance(voice_id, str) and 0 < len(voice_id) <= 64:
            self.mapping[speaker] = voice_id
        else:
            raise ValueError('Invalid voice id')
        return self

    def voice_for(self, speaker):
        """The voice for a label, or None when there is no decision (keep the current one)."""
        if speaker is None:
            return None
        return self.mapping.get(speaker)
