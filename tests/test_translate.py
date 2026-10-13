import numpy as np
import pytest

from src.translate.pipeline import (LanguagePack, PassthroughTranslator, SilentSynth,
                                    TranslationPipeline)


def test_passthrough_translator_and_empty_input():
    pipeline = TranslationPipeline()
    assert pipeline.translate("こんにちは", "ja", "en") == "こんにちは"
    assert pipeline.translate("", "ja", "en") == ""
    assert pipeline.translate(None, "ja", "en") == ""
    assert pipeline.speak("").shape == (0,)


def test_silent_synth_is_bounded_and_well_formed():
    synth = SilentSynth(max_seconds=1.0, seconds_per_character=0.05)
    short = synth.synthesize("ab", "", 48000)
    assert short.dtype == np.float32 and short.shape == (round(0.2 * 48000),)
    assert np.all(short == 0.0)
    long = synth.synthesize("x" * 100, "", 48000)
    assert long.shape == (48000,)  # capped at max_seconds, never minutes of audio


def test_process_returns_translated_text_and_audio():
    pipeline = TranslationPipeline()
    translated, audio = pipeline.process("hello", "en", "ja", voice="anime")
    assert translated == "hello"
    assert audio.dtype == np.float32 and audio.ndim == 1 and len(audio) > 0


def test_a_pack_provider_replaces_the_stubs():
    class UpperTranslator:
        def translate(self, text, source, target):
            return f"{text.upper()}[{source}->{target}]"

    class ToneSynth:
        def synthesize(self, text, voice, sample_rate):
            return np.full(8, 0.5, dtype=np.float32)

    pipeline = TranslationPipeline(translator=UpperTranslator(), synthesizer=ToneSynth(),
                                   sample_rate=16000, provider="translate-ja-en")
    translated, audio = pipeline.process("hi", "ja", "en")
    assert translated == "HI[ja->en]" and pipeline.provider == "translate-ja-en"
    np.testing.assert_array_equal(audio, np.full(8, 0.5, dtype=np.float32))


def test_language_pack_is_a_plain_value():
    pack = LanguagePack(id="ja-en", source="ja", target="en", label="日本語 → English")
    assert pack.label == "日本語 → English" and pack.source == "ja" and pack.target == "en"
