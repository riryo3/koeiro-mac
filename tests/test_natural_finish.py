"""The streaming output conditioner: de-click joins, tame harsh fricatives."""
import time

import numpy as np
import pytest

from src.processors.natural_finish import (
    CLICK_JUMP,
    NaturalFinishProcessor,
)
from src.processors.chain import ProcessorChain
from src.processors.passthrough import PassthroughProcessor

SAMPLE_RATE = 48000


def sine(frames=4800, pitch=220.0, level=0.2):
    times = np.arange(frames) / SAMPLE_RATE
    return (np.sin(2 * np.pi * pitch * times) * level).astype(np.float32)


def hiss(frames=4800, seed=7):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, frames)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(frames, 1 / SAMPLE_RATE)
    shelf = np.clip((freqs - 2500) / 2000, 0, None) + 0.005
    shaped = np.fft.irfft(spectrum * shelf, frames)
    return (shaped / np.sqrt(np.mean(shaped ** 2)) * 0.1).astype(np.float32)


def run(stage, signal, block=480):
    out = np.empty_like(signal)
    for start in range(0, len(signal), block):
        chunk = signal[start:start + block].reshape(-1, 1)
        out[start:start + len(chunk)] = stage.process(chunk.copy(), SAMPLE_RATE)[:, 0]
    return out


def high_energy(signal):
    return float(np.mean(signal.astype(np.float64) ** 2))


def _fresh():
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 480)
    return stage


def test_off_is_a_bit_exact_pass_through():
    stage = NaturalFinishProcessor()
    stage.prepare(SAMPLE_RATE, 480)
    for signal in (sine(), hiss(), np.zeros(4800, dtype=np.float32)):
        np.testing.assert_array_equal(run(stage, signal), signal)


def test_original_is_never_touched_even_when_enabled():
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 480)
    stage.route_active = False
    signal = hiss()
    np.testing.assert_array_equal(run(stage, signal), signal)


def test_a_quiet_join_click_is_repaired():
    tone = sine(frames=4800, pitch=220.0, level=0.05)
    for start in (960, 2880):
        tone[start] += 0.3  # a chunk-join style step, not music
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 480)
    out = run(stage, tone)
    jumps = np.abs(np.diff(out))
    assert jumps.max() < CLICK_JUMP
    # A clean tone has no joins to repair: bit-exact.
    clean = sine(frames=4800, pitch=220.0, level=0.05)
    np.testing.assert_array_equal(run(stage, clean), clean)


def test_a_loud_onset_is_not_mistaken_for_a_click():
    tone = sine(frames=4800, pitch=220.0, level=0.5)
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 480)
    np.testing.assert_array_equal(run(stage, tone), tone)


def test_harsh_fricatives_are_tamed_within_3db_and_voices_pass():
    harsh = hiss()
    tamed = run(_fresh(), harsh)
    assert high_energy(tamed) < high_energy(harsh)
    cut_db = 10 * np.log10(high_energy(harsh) / high_energy(tamed))
    assert 0 < cut_db <= 3.0 + 0.5
    # Fresh followers per signal: a voice never inherits a hiss dip.
    for signal in (sine(), np.zeros(4800, dtype=np.float32)):
        np.testing.assert_array_equal(run(_fresh(), signal), signal)


def test_shape_dtype_and_validation():
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 1024)
    out = stage.process(np.zeros((1024, 1), dtype=np.float32), SAMPLE_RATE)
    assert out.shape == (1024, 1) and out.dtype == np.float32
    with pytest.raises(ValueError):
        NaturalFinishProcessor(max_cut_db=99)


def test_reset_returns_to_unity():
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 480)
    run(stage, hiss())
    assert stage._gain < 1.0
    stage.reset()
    assert stage._gain == 1.0 and stage._applied == 1.0


def test_block_processing_stays_inside_budget():
    stage = NaturalFinishProcessor(enabled=True)
    stage.prepare(SAMPLE_RATE, 256)
    block = hiss(frames=256).reshape(-1, 1)
    started = time.perf_counter()
    for _ in range(200):
        stage.process(block.copy(), SAMPLE_RATE)
    elapsed_ms = (time.perf_counter() - started) * 1000 / 200
    assert elapsed_ms < 2.0  # 5.3 ms budget for a 256-frame block


class ModeStub(PassthroughProcessor):
    def __init__(self, mode):
        self.mode = mode


def test_the_chain_arms_the_finish_for_converted_routes_only():
    chain = ProcessorChain(main_processor=ModeStub('original'))
    chain.finish.enabled = True
    chain.prepare(SAMPLE_RATE, 480)
    harsh = hiss()

    def energy_db(signal):
        return 10 * np.log10(high_energy(signal) + 1e-12)

    before = energy_db(harsh)
    # Settle the chain once (the gate opens on the first blocks), then measure
    # the second pass: Original must stay within a tenth of a dB.
    run(chain, harsh)
    assert abs(energy_db(run(chain, harsh)) - before) < 0.1
    for mode in ('ai_voice', 'female_dsp'):
        chain.main_processor.mode = mode
        run(chain, harsh)
        cut = before - energy_db(run(chain, harsh))
        assert 0 < cut <= 3.0 + 0.5, (mode, cut)
