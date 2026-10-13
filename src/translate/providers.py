"""Real providers for the translation seam, and timbre matching to keep a voice.

:mod:`src.translate.pipeline` defines the seam; this module fills it.

* ``KokoroSynth`` is the Kokoro backend from ``src.tts`` -- which already speaks the
  ``SpeechSynth`` protocol, so the wiring is a construction, not an adapter.
* ``PreservingSynth`` wraps any synthesizer and pulls its output towards the timbre of
  a registered voice. What it does is measurable and bounded: it matches long-term
  average spectra (a smoothed, clamped gain curve over the STFT) and level. What it
  is not: a speaker-identity clone. The words are the model's voice; only the
  brightness and body of the reference are borrowed.
* ``ArgosTranslator`` is the optional offline MT model (argostranslate, MIT). It is
  imported lazily and absent by default, so an uninstalled model degrades to the
  pass-through translator the base build already ships.

Everything here runs off the audio callback, on the utterance side.
"""
from dataclasses import dataclass
import logging
import math

import numpy as np

log = logging.getLogger(__name__)

BANDS = 32
# The matching curve is capped so a bad reference cannot turn speech into noise.
MAX_GAIN_DB = 6.0
FRAME = 1024
HOP = 256


@dataclass(frozen=True)
class Voiceprint:
    """What "this voice's timbre" means here: a band curve, a pitch and a level."""

    bands_db: np.ndarray
    f0_hz: float
    rms: float
    seconds: float


def _band_edges(sample_rate, bands=BANDS, low=80.0, high=None):
    high = high or min(16000.0, sample_rate / 2 * 0.95)
    edges = np.geomspace(low, high, bands + 1)
    return np.round(edges / (sample_rate / 2) * (FRAME // 2)).astype(int)


def _ltas(audio, sample_rate):
    """Mean log magnitude per geometric band, in dB, from a Hann-windowed STFT."""
    signal = np.asarray(audio, dtype=np.float64).reshape(-1)
    if len(signal) < FRAME:
        signal = np.pad(signal, (0, FRAME - len(signal)))
    window = np.hanning(FRAME)
    frames = [np.abs(np.fft.rfft(signal[start:start + FRAME] * window))
              for start in range(0, len(signal) - FRAME + 1, HOP)]
    spectrum = np.mean(np.stack(frames), axis=0)
    edges = _band_edges(sample_rate)
    values = []
    for index in range(len(edges) - 1):
        # Geometric edges can land on the same FFT bin at the bottom of the range, so
        # a band is always at least one bin wide and never empty.
        low = max(1, int(edges[index]))
        high = max(low + 1, int(edges[index + 1]))
        band = spectrum[low:high]
        values.append(20.0 * math.log10(float(band.mean()) + 1e-9))
    return np.array(values, dtype=np.float64)


def voiceprint(audio, sample_rate):
    """Measure a reference recording: band curve, median pitch and level."""
    from src.processors.whisper import voicedness
    signal = np.asarray(audio, dtype=np.float64).reshape(-1)
    if len(signal) < FRAME:
        raise ValueError('A voiceprint needs at least one analysis frame')
    pitch = 0.0
    for start in range(0, max(1, len(signal) - FRAME + 1), FRAME * 2):
        found, periodicity = voicedness(signal[start:start + FRAME * 2], sample_rate)
        if found and periodicity >= 0.35:
            pitch = found if not pitch else (pitch + found) / 2
    return Voiceprint(_ltas(signal, sample_rate), float(pitch),
                      float(np.sqrt(np.mean(signal ** 2))), len(signal) / sample_rate)


def _gain_curve(source_db, target_db, strength, sample_rate):
    difference = np.clip((target_db - source_db) * strength, -MAX_GAIN_DB, MAX_GAIN_DB)
    # A one-pass smoothing keeps the curve from notching single bands.
    smoothed = np.convolve(difference, np.ones(3) / 3.0, mode='same')
    edges = _band_edges(sample_rate)
    bins = max(2, FRAME // 2 + 1)
    curve = np.zeros(bins)
    for index in range(len(edges) - 1):
        low = min(bins - 1, max(1, int(edges[index])))
        high = min(bins, max(low + 1, int(edges[index + 1])))
        curve[low:high] = smoothed[index]
    return curve


def timbre_match(audio, sample_rate, target, strength=1.0):
    """Pull ``audio`` towards ``target``'s band curve and level.

    ``strength`` 0 is a bit-exact pass-through (the window sum divides out), 1 is the
    full, capped match.
    """
    if not 0 <= strength <= 1:
        raise ValueError('Matching strength must be between 0 and 1')
    signal = np.asarray(audio, dtype=np.float32).reshape(-1)
    if signal.size == 0 or strength == 0:
        return signal.copy()
    curve = _gain_curve(_ltas(signal, sample_rate), target.bands_db, strength, sample_rate)
    gains = 10.0 ** (curve / 20.0)
    # One frame of silence on each side, then cropped back: without it the first and
    # last window would have no overlap to divide by and the edges would fade to zero.
    padded = np.concatenate([np.zeros(FRAME, dtype=np.float64), signal.astype(np.float64),
                             np.zeros(FRAME, dtype=np.float64)])
    window = np.hanning(FRAME).astype(np.float64)
    output = np.zeros(padded.size + FRAME, dtype=np.float64)
    normaliser = np.zeros_like(output)
    squared = window ** 2
    for start in range(0, padded.size - FRAME + 1, HOP):
        frame = padded[start:start + FRAME] * window
        spectrum = np.fft.rfft(frame) * gains[:FRAME // 2 + 1]
        output[start:start + FRAME] += np.fft.irfft(spectrum, FRAME) * window
        normaliser[start:start + FRAME] += squared
    scaled = np.divide(output, normaliser, out=np.zeros_like(output), where=normaliser > 1e-6)
    result = scaled[FRAME:FRAME + signal.size].astype(np.float32)
    # The delivered level stays where it was: this borrows a timbre, not a loudness,
    # and a quiet reference must not make the translated speech quiet too.
    level = float(np.sqrt(np.mean(result ** 2)))
    source_level = float(np.sqrt(np.mean(signal ** 2)))
    if level > 1e-6 and source_level > 0:
        result = (result * (source_level / level)).astype(np.float32)
    return np.clip(result, -1.0, 1.0)


class PreservingSynth:
    """A :class:`~src.translate.pipeline.SpeechSynth` in the user's own timbre."""

    def __init__(self, inner, reference=None, sample_rate=48000, strength=0.6):
        self.inner = inner
        self.sample_rate = int(sample_rate)
        self.strength = float(strength)
        self.print = voiceprint(reference, self.sample_rate) if reference is not None else None

    @property
    def preserving(self):
        return self.print is not None

    def synthesize(self, text, voice, sample_rate):
        audio = self.inner.synthesize(text, voice, sample_rate)
        if self.print is None or audio.size == 0 or sample_rate != self.sample_rate:
            return np.asarray(audio, dtype=np.float32)
        return timbre_match(audio, sample_rate, self.print, self.strength)


class ArgosTranslator:
    """Offline ja -> en via argostranslate when the user has installed it."""

    def __init__(self, source='ja', target='en'):
        from argostranslate import translate  # noqa: F401  (raises when absent)
        self._translate = translate
        self.source = source
        self.target = target
        languages = {language.code for language in translate.get_installed_languages()}
        if source not in languages or target not in languages:
            raise RuntimeError(f'argostranslate has no {source}->{target} package installed')

    def translate(self, text, source, target):
        if not (text or '').strip():
            return ''
        return self._translate.translate(text, self.source, self.target)


def translator_for(kind, source='ja', target='en'):
    """A translator for a provider name, or None when it is not installed."""
    if kind != 'argos':
        return None
    try:
        return ArgosTranslator(source, target)
    except Exception as error:  # import error, missing package, malformed data
        log.info('argostranslate unavailable: %s', error)
        return None


def build_pipeline(root, provider='off', voice='', reference=None, sample_rate=48000,
                   translator=None, source='ja', target='en'):
    """Assemble the translation pipeline and report what it ended up using.

    Returns ``(pipeline, status)``. A provider that is not installed is reported in
    ``status`` and the base stubs are used, so the caller can always route audio.
    When ``translator`` is None and ``provider`` is not ``'off'``, the optional
    offline translator is tried first (ja -> en by default); absence still
    degrades to the pass-through translator instead of raising.
    """
    from src.translate.pipeline import TranslationPipeline
    from src.tts import provider as tts

    synthesizer = None
    if provider == 'kokoro':
        built = tts.build_provider(root)
        if built is None:
            status = 'Kokoro未導入のため、無音TTSで動作します（tools/install_tts.py）'
        else:
            synthesizer = PreservingSynth(built, reference, sample_rate) if reference is not None \
                else built
            status = ('声色を寄せたKokoro音声' if reference is not None else 'Kokoro音声') \
                + f'（{voice or tts.DEFAULT_VOICE}）'
    else:
        status = '翻訳なし（素通し・無音）'
    resolved = translator
    translator_note = ''
    if resolved is None and provider != 'off':
        # Default wiring: the offline pack translator when installed, otherwise
        # the base pass-through. Never raises; absence is reported in status.
        resolved = translator_for('argos', source, target)
        if resolved is None:
            translator_note = '・翻訳器は未導入で、入力文をそのまま読み上げます'
        else:
            translator_note = f'・翻訳 {source}->{target}で翻訳します'
    pipeline = TranslationPipeline(translator=resolved or None, synthesizer=synthesizer,
                                   sample_rate=sample_rate, provider=provider)
    status += translator_note
    return pipeline, status
