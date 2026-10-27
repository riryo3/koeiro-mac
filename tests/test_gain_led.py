import numpy as np

from src.processors.gain import GainProcessor


def test_gain_peak_is_the_loudest_sample_after_the_gain_and_resets_on_read():
    gain = GainProcessor(6.0)
    gain.prepare(48000, 256)
    block = np.full((256, 1), 0.4, dtype=np.float32)
    block[10, 0] = -0.5
    gain.process(block, 48000)
    assert abs(gain.take_peak() - 0.5 * 10 ** (6.0 / 20)) < 1e-3
    assert gain.take_peak() == 0.0


def test_gain_led_states():
    from src.gui.shell import GainLed
    assert GainLed.state_for(0.0) == 'off'
    assert GainLed.state_for(0.1) == 'ok'
    assert GainLed.state_for(0.6) == 'loud'
    assert GainLed.state_for(1.2) == 'clip'
