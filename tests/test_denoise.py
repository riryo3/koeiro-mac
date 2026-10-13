import numpy as np
import pytest

from src.processors.chain import ProcessorChain
from src.processors.denoise import NoiseSuppressionProcessor
from src.audio.controller import AudioController
from src.settings.manager import AppSettings


FRAME = 1024
RATE = 48000


def rms(values):
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def feed(processor, signal, blocks):
    audio = np.empty((FRAME, 1), dtype=np.float32)
    collected = []
    for index in range(blocks):
        audio[:, 0] = signal[index * FRAME:(index + 1) * FRAME]
        processor.process(audio, RATE)
        collected.append(audio[:, 0].copy())
    return np.concatenate(collected)


def test_strength_zero_is_a_true_pass_through():
    processor = NoiseSuppressionProcessor(0.0)
    processor.prepare(RATE, FRAME)
    audio = np.full((FRAME, 1), 0.25, dtype=np.float32)
    original = audio.copy()
    assert processor.process(audio, RATE) is audio
    np.testing.assert_array_equal(audio, original)


@pytest.mark.parametrize("strength", [0.25, 0.6, 1.0])
def test_shape_dtype_and_finite(strength):
    processor = NoiseSuppressionProcessor(strength)
    processor.prepare(RATE, FRAME)
    rng = np.random.default_rng(1)
    for _ in range(5):
        audio = rng.normal(0, 0.05, (FRAME, 1)).astype(np.float32)
        result = processor.process(audio, RATE)
        assert result is audio and result.shape == (FRAME, 1) and result.dtype == np.float32
        assert np.isfinite(result).all()


def test_stationary_noise_is_attenuated():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.02, FRAME * 48).astype(np.float32)
    processor = NoiseSuppressionProcessor(0.8, floor_db=-12.0)
    processor.prepare(RATE, FRAME)
    output = feed(processor, noise, 48)
    quiet = slice(38 * FRAME, 48 * FRAME)
    assert rms(output[quiet]) < 0.6 * rms(noise[quiet])


def test_non_stationary_burst_survives_the_floor():
    rng = np.random.default_rng(7)
    signal = rng.normal(0, 0.02, FRAME * 48).astype(np.float32)
    burst = slice(35 * FRAME, 37 * FRAME)
    signal[burst] += (0.3 * rng.normal(0, 1, 2 * FRAME)).astype(np.float32)
    processor = NoiseSuppressionProcessor(0.8, floor_db=-12.0)
    processor.prepare(RATE, FRAME)
    output = feed(processor, signal, 48)
    # The loud, time-varying burst is not the floor, so most of it passes...
    assert rms(output[burst]) > 0.6 * rms(signal[burst])
    # ...while the steady noise around it is still suppressed.
    quiet = slice(40 * FRAME, 48 * FRAME)
    assert rms(output[quiet]) < 0.6 * rms(signal[quiet])


def test_clearing_after_reset_relearns_the_floor():
    processor = NoiseSuppressionProcessor(0.8)
    processor.prepare(RATE, FRAME)
    rng = np.random.default_rng(5)
    feed(processor, rng.normal(0, 0.02, FRAME * 12).astype(np.float32), 12)
    processor.reset()
    audio = np.full((FRAME, 1), 0.3, dtype=np.float32)
    assert processor.process(audio, RATE) is audio and audio[0, 0] == pytest.approx(0.3)


@pytest.mark.parametrize("strength", [-0.1, 1.1, float("nan"), "loud"])
def test_invalid_strength(strength):
    with pytest.raises(ValueError):
        NoiseSuppressionProcessor(strength)


@pytest.mark.parametrize("floor_db", [-41, -2, float("inf")])
def test_invalid_floor(floor_db):
    with pytest.raises(ValueError):
        NoiseSuppressionProcessor(0.5, floor_db=floor_db)


def test_chain_carries_a_denoise_stage_that_is_off_by_default():
    chain = ProcessorChain()
    assert chain.pre_processors[1] is chain.denoise
    assert chain.denoise.strength == 0.0
    chain.prepare(RATE, 256)
    # Let the gate finish opening, so the only stage under test is the passive one.
    for _ in range(60):
        audio = np.full((256, 1), 0.1, dtype=np.float32)
        result = chain.process(audio, RATE)
    np.testing.assert_allclose(result, 0.1, rtol=1e-4)


def test_controller_toggle_sets_the_strength():
    controller = AudioController.__new__(AudioController)
    controller.engine = type("Engine", (), {"chain": ProcessorChain()})()
    controller.set_denoise(0.5)
    assert controller.engine.chain.denoise.strength == 0.5
    controller.set_denoise(0.0)
    assert controller.engine.chain.denoise.strength == 0.0


def test_settings_roundtrip_includes_denoise(tmp_path):
    from src.settings.manager import SettingsManager
    manager = SettingsManager(tmp_path / "settings.json")
    assert manager.save(AppSettings(denoise=True, denoise_strength=0.35))
    saved = manager.load()
    assert saved.denoise is True and saved.denoise_strength == pytest.approx(0.35)


def test_invalid_denoise_settings_fall_back():
    settings = AppSettings.from_dict({"denoise": "yes", "denoise_strength": 5})
    assert settings.denoise is False and settings.denoise_strength == 0.6
