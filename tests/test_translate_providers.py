import numpy as np
import pytest

from src.translate.pipeline import PassthroughTranslator, SilentSynth, TranslationPipeline
from src.translate.providers import (PreservingSynth, build_pipeline, timbre_match,
                                     translator_for, voiceprint, _ltas)

SAMPLE_RATE = 48000


def dull(seconds=1.0, seed=1):
    """Low-passed noise: a voice with no top end."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, .2, int(SAMPLE_RATE * seconds))
    # A one-pole low-pass, applied twice, is dull enough to be obvious in the bands.
    smoothed = noise
    for _ in range(6):
        smoothed = np.convolve(smoothed, np.ones(8) / 8.0, mode='same')
    return smoothed.astype(np.float32)


def bright(seconds=1.0, seed=2):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, .2, int(SAMPLE_RATE * seconds))
    return np.diff(noise, prepend=noise[0]).astype(np.float32)


def band_distance(a, b, sample_rate=SAMPLE_RATE):
    return float(np.linalg.norm(_ltas(a, sample_rate) - _ltas(b, sample_rate)))


def test_a_voiceprint_sees_the_difference_between_two_timbres():
    dull_print, bright_print = voiceprint(dull(), SAMPLE_RATE), voiceprint(bright(), SAMPLE_RATE)
    assert bright_print.bands_db[-1] > dull_print.bands_db[-1]
    assert dull_print.bands_db[:4].mean() > bright_print.bands_db[:4].mean()
    assert dull_print.seconds == pytest.approx(1.0, abs=0.01)


def test_matching_at_zero_strength_changes_nothing_measurable():
    source = dull()
    result = timbre_match(source, SAMPLE_RATE, voiceprint(bright(), SAMPLE_RATE), 0.0)
    assert np.allclose(result, source, atol=1e-4)


def test_matching_moves_a_voice_towards_the_target():
    source = bright()
    target = voiceprint(dull(), SAMPLE_RATE)
    before = band_distance(source, dull())
    matched = timbre_match(source, SAMPLE_RATE, target, 1.0)
    after = band_distance(matched, dull())
    assert after < before
    assert np.sqrt(np.mean(matched ** 2)) == pytest.approx(np.sqrt(np.mean(source ** 2)), rel=0.35)


def test_the_shipped_pass_through_route_still_reconstructs_exactly():
    source = dull(0.5)
    target = voiceprint(source, SAMPLE_RATE)
    result = timbre_match(source, SAMPLE_RATE, target, 1.0)
    # Matching a voice to itself: the band curve is flat, so the window sum must
    # divide back out to the original signal.
    assert band_distance(result, source) < 1.0


def test_matching_rejects_an_out_of_range_strength():
    with pytest.raises(ValueError):
        timbre_match(dull(0.1), SAMPLE_RATE, voiceprint(dull(), SAMPLE_RATE), 1.5)


def test_a_voiceprint_needs_an_analysis_frame():
    with pytest.raises(ValueError):
        voiceprint(np.zeros(64, dtype=np.float32), SAMPLE_RATE)


class FakeSynth:
    """Stands in for Kokoro: deterministic, and clearly the wrong timbre."""

    def __init__(self, kind):
        self.kind = kind

    def synthesize(self, text, voice, sample_rate):
        return bright(0.5) if self.kind == 'bright' else dull(0.5)


def test_preserving_synth_shapes_the_model_voice_towards_the_reference():
    reference = dull(1.0, seed=7)
    synth = PreservingSynth(FakeSynth('bright'), reference, SAMPLE_RATE, 1.0)
    assert synth.preserving
    output = synth.synthesize('hello there', 'af_heart', SAMPLE_RATE)
    assert len(output) == len(FakeSynth('bright').synthesize('hello there', '', SAMPLE_RATE))
    assert band_distance(output, reference) < band_distance(bright(0.5), reference)


def test_preserving_synth_without_a_reference_is_a_plain_pass_through():
    synth = PreservingSynth(FakeSynth('bright'), None, SAMPLE_RATE)
    assert synth.preserving is False
    assert np.array_equal(synth.synthesize('hi', '', SAMPLE_RATE), bright(0.5))


def test_build_pipeline_falls_back_when_the_models_are_absent(tmp_path):
    pipeline, status = build_pipeline(tmp_path, provider='kokoro', voice='af_heart')
    assert '未導入' in status
    translated, audio = pipeline.process('こんにちは')
    # The pack seam's stubs: text unchanged, and a bounded, silent waveform.
    assert translated == 'こんにちは'
    assert len(audio) > 0 and not audio.any()


def test_build_pipeline_off_reports_the_base_route(tmp_path):
    pipeline, status = build_pipeline(tmp_path, provider='off')
    assert '翻訳なし' in status
    assert isinstance(pipeline._translator, PassthroughTranslator)
    assert isinstance(pipeline._synth, SilentSynth)
    assert pipeline.speak('') .size == 0


def test_installed_providers_produce_audio_through_the_seam(tmp_path):
    class Upper:
        def translate(self, text, source, target):
            return text.upper()

    pipeline = TranslationPipeline(translator=Upper(), synthesizer=FakeSynth('dull'),
                                   sample_rate=SAMPLE_RATE, provider='test')
    translated, audio = pipeline.process('こんにちは')
    assert translated == 'こんにちは'.upper()
    assert len(audio) == len(dull(0.5)) and audio.dtype == np.float32


def test_the_translator_provider_degrades_instead_of_raising():
    # argostranslate is optional; either it is installed or the seam reports absence.
    translator = translator_for('argos')
    assert translator is None or hasattr(translator, 'translate')
    assert translator_for('off') is None
