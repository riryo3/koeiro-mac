"""Streaming output conditioner for converted voices.

The utterance (one-shot) path already finishes audio in the worker
(level/tame_sibilance/lift_consonants/tame_plosives/suppress_floor/fade_edges in
:mod:`src.vc.utterance`). The streaming path had nothing after the model but the
safety clamp, so chunk joins could click and harsh fricatives passed through
untouched. This stage ports the two streaming-safe parts of that finishing work
into the callback, bounded and subtle:

* click repair at block joins (same 0.25 jump / quiet-only gate as
  :func:`src.vc.utterance.detect_clicks`, 64-sample raised-cosine from the held
  tail -- loud onsets are never touched);
* gentle sibilance taming: the block's 6..12 kHz share (same detector as the
  offline stage) steers at most 3 dB of wideband cut, attack fast, release
  slow, applied as a ramp so a moving follower never steps.

Off by default (``enabled=False`` is a true pass-through) and only armed for
converted routes by the chain -- Original never passes through here. One small
rFFT per block for the measurement, no allocation past temporaries, no waiting
on anything: scalar followers and a short blend on detected clicks only.
"""
import math

import numpy as np

from .base import AudioProcessor

# A join jump at or above this in a quiet block is a click, not music.
CLICK_JUMP = 0.25
# Only quiet blocks are repaired: a loud onset is supposed to jump.
CLICK_QUIET_RMS = 0.1
# Raised-cosine blend length from the held tail, in samples.
BLEND = 64
# Sibilance share (6..12 kHz power over 0.3..12 kHz) at which taming starts, and
# the span over which it reaches full depth. Same detector as the offline stage
# (:func:`src.vc.utterance.tame_sibilance`): voiced tone ~0.00, whispered vowel
# ~0.02, white noise ~0.25, /s/-hiss ~0.7.
SIB_RATIO = 0.6
SIB_SPAN = 0.2
MAX_CUT_DB = 3.0
# Follower ballistics, in seconds.
SHARE_TC = 0.030
ATTACK_TC = 0.010
RELEASE_TC = 0.150
# Below this broadband power the followers hold and the gain eases back to 1.
SILENCE_POWER = 1e-8


class NaturalFinishProcessor(AudioProcessor):
    """De-click and de-hiss the converted output, subtly or not at all."""

    def __init__(self, enabled=False, max_cut_db=MAX_CUT_DB):
        if type(max_cut_db) not in (int, float) or not 0 <= max_cut_db <= 12:
            raise ValueError('Finish cut must be 0..12 dB')
        self.enabled = bool(enabled)
        self.max_cut_db = float(max_cut_db)
        # Set per block by the chain: converted routes only, never Original.
        self.route_active = True
        self._tail = 0.0
        self._share = 0.0
        self._gain = 1.0
        self._applied = 1.0
        self._rate = 48000.0
        # Usable before prepare() too; prepare() re-sizes to the stream.
        self._work = np.zeros(4096, dtype=np.float64)
        self._window = np.hanning(4096)

    def prepare(self, sample_rate, max_frames):
        self._rate = float(sample_rate)
        self._tail = 0.0
        self._share = 0.0
        self._gain = 1.0
        self._applied = 1.0
        # Scratch for the measurement path, so the callback never allocates
        # per block beyond the FFT's own small temporaries.
        self._work = np.empty(max_frames, dtype=np.float64)
        self._window = np.hanning(max_frames)

    def reset(self):
        self._tail = 0.0
        self._share = 0.0
        self._gain = 1.0
        self._applied = 1.0

    def _block_coeff(self, seconds, frames):
        return 1.0 - math.exp(-frames / (seconds * self._rate))

    def _share_of(self, work, frames):
        """High-band share of one block, same bands as the offline stage.

        ``work`` holds the block as float64 on entry and is reused as scratch.
        """
        window = self._window[:frames] if len(self._window) >= frames else np.hanning(frames)
        np.multiply(work, window, out=work)
        magnitudes = np.abs(np.fft.rfft(work)) ** 2 + 1e-12
        bins = np.fft.rfftfreq(frames, 1.0 / self._rate)
        high = np.sum(magnitudes[(bins >= 6000.0) & (bins <= 12000.0)])
        voice = np.sum(magnitudes[(bins >= 300.0) & (bins <= 12000.0)])
        return float(high / max(voice, 1e-12))

    def process(self, audio, sample_rate):
        out = np.asarray(audio[:, 0], dtype=np.float32)
        frames = len(out)
        if frames == 0:
            return audio
        live = self.enabled and self.route_active
        if live:
            # One cast copy; the dot product and the spectrum below share it.
            work = self._work[:frames] if len(self._work) >= frames else np.empty(frames)
            work[:] = out
            broad = float(np.dot(work, work)) / frames
        else:
            broad = 0.0
            work = None
        # A loud block is supposed to move: only a quiet join jump is a click.
        if live and broad < CLICK_QUIET_RMS ** 2 and abs(float(out[0]) - self._tail) >= CLICK_JUMP:
            # A quiet join jump: rewind the head onto the held tail over BLEND
            # samples instead of letting the step through.
            tail = self._tail
            head = out[:BLEND].astype(np.float64)
            phase = np.arange(len(head)) / max(1, len(head))
            blend = 0.5 - 0.5 * np.cos(np.pi * np.clip(phase, 0.0, 1.0))
            out[:len(head)] = (tail * (1.0 - blend) + head * blend).astype(np.float32)
        if live and broad >= SILENCE_POWER and frames >= 128:
            share = self._share_of(work, frames)
            self._share += self._block_coeff(SHARE_TC, frames) * (share - self._share)
            depth = min(1.0, max(0.0, (self._share - SIB_RATIO) / SIB_SPAN))
            target = 10.0 ** (-depth * self.max_cut_db / 20.0)
            tc = ATTACK_TC if target < self._gain else RELEASE_TC
            self._gain += self._block_coeff(tc, frames) * (target - self._gain)
        else:
            # Silence, a short block, or the stage is off: ease back to unity.
            self._gain += self._block_coeff(RELEASE_TC, frames) * (1.0 - self._gain)
            if abs(self._gain - 1.0) < 1e-6:
                self._gain = 1.0
        if self._gain != 1.0 or self._applied != 1.0:
            # Ramp from last block's applied gain so a moving follower never
            # steps audibly inside sustained hiss.
            out *= np.linspace(self._applied, self._gain, frames).astype(np.float32)
            self._applied = self._gain
        self._tail = float(out[-1])
        return audio
