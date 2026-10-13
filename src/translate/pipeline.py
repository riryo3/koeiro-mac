"""Realtime translation voice -- the routing shell for the translation pack.

The base build ships no translation model. It ships this pipeline, which defines the
seam a pack fills: recognised text -> a translator -> a synthesizer -> audio in the
target voice. Model work runs off the audio callback (on the utterance/worker side),
and with no pack installed the pipeline degrades to a pass-through translator and a
bounded silent waveform, so selecting it can never break the voice route.

Providers are :class:`typing.Protocol` seams, not imports: the heavy translation
model (a distilled NLLB-200, say) and the anime-style multilingual TTS live in the
installable pack. Keeping them behind a protocol is what lets the routing, the empty
input handling and the length bound be tested here, with a deterministic stub,
without the gigabytes of weights.
"""
from dataclasses import dataclass
from typing import Protocol

import numpy as np

# A translated utterance is bounded like a conversion input, so a runaway transcript
# cannot ask a synthesizer for minutes of audio.
MAX_SECONDS = 30.0
# A rough speaking-rate estimate for the stub only; a real TTS reports its own length.
SECONDS_PER_CHARACTER = 0.12


class Translator(Protocol):
    def translate(self, text: str, source: str, target: str) -> str:
        """Return ``text`` rendered in ``target``."""


class SpeechSynth(Protocol):
    def synthesize(self, text: str, voice: str, sample_rate: int) -> "np.ndarray":
        """Return mono float32 audio for ``text`` in ``voice``."""


@dataclass(frozen=True)
class LanguagePack:
    """A translation direction, and the label to show for it."""

    id: str
    source: str
    target: str
    label: str = ""


class PassthroughTranslator:
    """The base-build translator: returns the text unchanged.

    This is what an uninstalled pack behaves as, which makes "translation on but no
    pack" a no-op that still produces audio rather than an error.
    """

    def translate(self, text, source, target):
        return text


class SilentSynth:
    """The base-build synthesizer: a bounded, all-zero waveform.

    Silence, not noise: it is honest that no TTS is installed, and it keeps the
    output well formed for anything downstream that expects a full utterance.
    """

    def __init__(self, max_seconds=MAX_SECONDS, seconds_per_character=SECONDS_PER_CHARACTER):
        self.max_seconds = float(max_seconds)
        self.seconds_per_character = float(seconds_per_character)

    def synthesize(self, text, voice, sample_rate):
        seconds = min(self.max_seconds, max(0.2, len(text) * self.seconds_per_character))
        return np.zeros(round(seconds * sample_rate), dtype=np.float32)


class TranslationPipeline:
    """Routes recognised text through a translator and a synthesizer."""

    def __init__(self, translator=None, synthesizer=None, sample_rate=48000, provider="base"):
        self._translator = translator or PassthroughTranslator()
        self._synth = synthesizer or SilentSynth()
        self.sample_rate = int(sample_rate)
        # Where the providers came from: "base" for the stubs, otherwise a pack id.
        self.provider = provider

    def translate(self, text, source="ja", target="en"):
        text = (text or "").strip()
        return self._translator.translate(text, source, target) if text else ""

    def speak(self, text, voice=""):
        text = (text or "").strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        audio = self._synth.synthesize(text, voice, self.sample_rate)
        return np.asarray(audio, dtype=np.float32)

    def process(self, text, source="ja", target="en", voice=""):
        """Return ``(translated_text, audio)`` for one recognised utterance."""
        translated = self.translate(text, source, target)
        return translated, self.speak(translated, voice)
