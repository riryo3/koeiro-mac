import numpy as np

from src.processors.low_cut import InputLowCutProcessor


def _gain_db(frequency, enabled=True, rate=48000):
    processor = InputLowCutProcessor()
    processor.prepare(rate, 4800)
    processor.set_enabled(enabled)
    t = np.arange(rate) / rate
    audio = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32).reshape(-1, 1)
    out = processor.process(audio.copy(), rate)
    tail = slice(rate // 2, None)
    return 20 * np.log10(np.sqrt(np.mean(out[tail] ** 2)) / np.sqrt(np.mean(audio[tail] ** 2)))


def test_low_frequencies_are_cut():
    assert _gain_db(40) < -30
    assert _gain_db(60) < -16


def test_voice_band_is_kept():
    assert abs(_gain_db(300)) < 0.5
    assert abs(_gain_db(1000)) < 0.1


def test_disabled_is_identity():
    processor = InputLowCutProcessor()
    processor.prepare(48000, 256)
    audio = np.random.default_rng(0).uniform(-0.5, 0.5, (256, 1)).astype(np.float32)
    assert np.array_equal(processor.process(audio.copy(), 48000), audio)


def test_shape_and_dtype_are_kept():
    processor = InputLowCutProcessor()
    processor.prepare(48000, 256)
    processor.set_enabled(True)
    out = processor.process(np.zeros((256, 1), dtype=np.float32), 48000)
    assert out.shape == (256, 1) and out.dtype == np.float32


def _high_cut_gain_db(frequency, cutoff=6000.0, rate=48000):
    from src.processors.low_cut import OutputHighCutProcessor
    processor = OutputHighCutProcessor(cutoff)
    processor.prepare(rate, 4800)
    processor.set_enabled(True)
    t = np.arange(rate) / rate
    audio = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32).reshape(-1, 1)
    out = processor.process(audio.copy(), rate)
    tail = slice(rate // 2, None)
    return 20 * np.log10(np.sqrt(np.mean(out[tail] ** 2)) / np.sqrt(np.mean(audio[tail] ** 2)))


def test_high_cut_removes_the_top_and_keeps_the_voice():
    assert abs(_high_cut_gain_db(500)) < 0.1
    assert abs(_high_cut_gain_db(3000)) < 0.5
    assert _high_cut_gain_db(6000) < -2.5
    assert _high_cut_gain_db(12000) < -40
    assert _high_cut_gain_db(6000, cutoff=3000.0) < -40


def test_high_cut_cutoff_is_settable_live():
    from src.processors.low_cut import OutputHighCutProcessor
    processor = OutputHighCutProcessor(6000.0)
    processor.prepare(48000, 256)
    processor.set_enabled(True)
    processor.process(np.zeros((256, 1), dtype=np.float32), 48000)
    processor.set_cutoff(3000.0)
    out = processor.process(np.ones((256, 1), dtype=np.float32) * 0.1, 48000)
    assert out.shape == (256, 1) and np.isfinite(out).all()


def test_band_levels_find_the_tone():
    from src.audio.spectrum import band_edges, band_levels
    rate = 48000
    t = np.arange(2048) / rate
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    edges = band_edges()
    levels = band_levels(tone, rate, edges)
    loudest = int(np.argmax(levels))
    assert edges[loudest] <= 1000 < edges[loudest + 1]
    assert levels[loudest] > -12 and levels[0] < -50 and levels[-1] < -50
    assert set(band_levels(np.zeros(2048), rate, edges)) == {-90.0}


def test_silence_mute_follows_the_input_after_the_hold():
    from src.processors.chain import SilenceMute
    rate, block = 48000, 256
    mute = SilenceMute(hold_seconds=1.5)  # explicit: the test is about the timing logic
    mute.prepare(rate, block)
    mute.armed = True

    def run(seconds, input_open):
        mute.input_open = input_open
        last = None
        for _ in range(int(seconds * rate / block)):
            last = mute.process(np.full((block, 1), 0.1, dtype=np.float32), rate)
        return float(np.abs(last).max())

    assert run(0.5, True) > 0.099      # speech: untouched
    assert run(1.0, False) > 0.099     # silent, but inside the hold: the word tail survives
    assert run(1.0, False) == 0.0      # past the hold: muted
    assert run(0.2, True) > 0.099      # speech again: back at full level
    mute.armed = False
    assert run(3.0, False) > 0.099     # not the AI route: never muted


def test_silence_mute_learns_the_delay_and_blocks_bursts_between_words():
    from src.processors.chain import SilenceMute
    rate, block, delay = 48000, 256, 2.4
    mute = SilenceMute()
    mute.prepare(rate, block)
    mute.armed = True
    speech = [(1.0, 2.0), (6.0, 7.5), (11.0, 11.8), (15.0, 16.5)]   # input-open spans (s)
    bursts = [(4.2, 4.4), (9.3, 9.5), (13.4, 13.6)]                  # hiss while the input is silent
    total = 22.0
    n_blocks = int(total * rate / block)
    kept_voice = lost_voice = leaked = 0
    for i in range(n_blocks):
        t = i * block / rate
        mute.input_open = any(a <= t < b for a, b in speech)
        voice = any(a + delay <= t < b + delay for a, b in speech)
        burst = any(a <= t < b for a, b in bursts)
        audio = np.full((block, 1), 0.2 if (voice or burst) else 0.0, dtype=np.float32)
        out = mute.process(audio, rate)
        if voice:
            if float(np.abs(out).max()) > 0.19:
                kept_voice += 1
            else:
                lost_voice += 1
        elif burst and float(np.abs(out).max()) > 0.01:
            leaked += 1
    assert mute.delay_seconds is not None and abs(mute.delay_seconds - delay) < 0.2
    # Only the very first utterance may lose its start, while the delay is still unknown.
    assert lost_voice <= 2 * rate * 0.02 / block + 6
    assert kept_voice > 0.95 * (kept_voice + lost_voice)
    assert leaked == 0
