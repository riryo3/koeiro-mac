"""Automatic input levelling: one steady level in, silence never boosted."""
import numpy as np
import pytest

from src.processors.chain import ProcessorChain
from src.processors.leveler import (
    MAX_GAIN_DB,
    AutoLevelProcessor,
)
from src.processors.passthrough import PassthroughProcessor

SAMPLE_RATE = 48000


def stepped(levels_db=(-30.0, -12.0), seconds_each=2.0, block=480):
    parts = []
    if isinstance(seconds_each, (int, float)):
        seconds_each = [seconds_each] * len(levels_db)
    for level_db, seconds in zip(levels_db, seconds_each):
        amplitude = 10.0 ** (level_db / 20.0)
        t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
        parts.append((np.sin(2 * np.pi * 180 * t) * amplitude).astype(np.float32))
    return np.concatenate(parts)


def run(stage, signal, block=480):
    stage.prepare(SAMPLE_RATE, block)
    out = np.empty_like(signal)
    for start in range(0, len(signal), block):
        chunk = signal[start:start + block].reshape(-1, 1).copy()
        out[start:start + len(chunk)] = stage.process(chunk, SAMPLE_RATE)[:, 0]
    return out


def rms_db(signal):
    return 20.0 * np.log10(float(np.sqrt(np.mean(signal.astype(float) ** 2))) + 1e-12)


def test_off_is_a_bit_exact_pass_through():
    stage = AutoLevelProcessor()
    signal = stepped()
    np.testing.assert_array_equal(run(stage, signal), signal)


def test_quiet_takes_come_up_to_the_same_level():
    stage = AutoLevelProcessor(enabled=True)
    out = run(stage, stepped((-30.0, -12.0), (2.0, 4.0)))
    # Settled tails only: the ramp itself is part of the honest measurement.
    first_settled = rms_db(out[int(1.5 * SAMPLE_RATE):int(2.0 * SAMPLE_RATE)])
    assert abs(first_settled - (-20.0)) < 4.0
    # The loud take releases back down toward the same target.
    loud_head = rms_db(out[int(2.0 * SAMPLE_RATE):int(2.5 * SAMPLE_RATE)])
    loud_tail = rms_db(out[int(5.5 * SAMPLE_RATE):int(6.0 * SAMPLE_RATE)])
    assert loud_tail < loud_head - 2.0
    assert -22.0 < loud_tail < -14.0


def test_silence_is_never_boosted():
    stage = AutoLevelProcessor(enabled=True)
    quiet = np.zeros(48000, dtype=np.float32)
    np.testing.assert_array_equal(run(stage, quiet), quiet)
    assert stage._gain_db == 0.0


def test_gain_stays_inside_its_caps():
    stage = AutoLevelProcessor(enabled=True)
    hot = (np.sin(2 * np.pi * 180 * np.arange(48000) / SAMPLE_RATE) * 0.9).astype(np.float32)
    run(stage, hot)
    assert -MAX_GAIN_DB - 1e-6 <= stage._gain_db <= MAX_GAIN_DB + 1e-6
    assert np.isfinite(run(stage, hot)).all()


def test_shape_dtype_and_validation():
    stage = AutoLevelProcessor(enabled=True)
    out = run(stage, np.zeros((1024,), dtype=np.float32))
    assert out.shape == (1024,) and out.dtype == np.float32
    with pytest.raises(ValueError):
        AutoLevelProcessor(target_rms=0.0)
    with pytest.raises(ValueError):
        AutoLevelProcessor(target_rms=2.0)


def test_the_chain_carries_a_leveler_that_starts_off():
    try:
        chain = ProcessorChain(main_processor=PassthroughProcessor())
        chain.prepare(SAMPLE_RATE, 480)
    except (OSError, RuntimeError):
        pytest.skip('Female DSP native library unavailable')
    assert chain.leveler.enabled is False
    signal = stepped()
    out = np.concatenate([chain.process(signal[i:i + 480].reshape(-1, 1).copy(), SAMPLE_RATE)[:, 0]
                          for i in range(0, len(signal), 480)])
    # Past the gate's opening transient, a disabled chain is transparent.
    np.testing.assert_array_equal(out[48000:], signal[48000:])
