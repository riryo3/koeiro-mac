import numpy as np
import pytest

from src.processors.whisper import WhisperVoicer, voicedness

SAMPLE_RATE = 48000


def whisper(frames=4800, seed=3):
    """Band-shaped noise with a speech-like envelope: words, no pitch."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, frames)
    shaped = np.diff(noise, prepend=noise[0])
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * np.arange(frames) / SAMPLE_RATE)
    return (0.15 * shaped / np.std(shaped) * envelope).astype(np.float32)


def voiced(frames=4800, pitch=200.0):
    times = np.arange(frames) / SAMPLE_RATE
    pulse = np.sign(np.sin(2 * np.pi * pitch * times)) * 0.2
    return pulse.astype(np.float32)


def whisper_vowel(frames=4800, seed=11):
    """Whispered vowel: noise through formant peaks, words without a pulse."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, frames)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(frames, 1 / SAMPLE_RATE)
    envelope = (np.exp(-((freqs - 500) / 400) ** 2)
                + 0.7 * np.exp(-((freqs - 1500) / 600) ** 2)
                + 0.4 * np.exp(-((freqs - 2500) / 800) ** 2) + 0.02)
    shaped = np.fft.irfft(spectrum * envelope, frames)
    return (shaped / np.sqrt(np.mean(shaped ** 2)) * 0.1).astype(np.float32)


def fricative(frames=4800, seed=11):
    """An /s/-like hiss: unvoiced like a whisper, but with no low-band energy."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, frames)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(frames, 1 / SAMPLE_RATE)
    shelf = np.clip((freqs - 2500) / 2000, 0, None) + 0.005
    shaped = np.fft.irfft(spectrum * shelf, frames)
    return (shaped / np.sqrt(np.mean(shaped ** 2)) * 0.1).astype(np.float32)


def stream(voicer, signal, block=480):
    """Run a mono signal through the stage the way the callback would."""
    out = np.empty_like(signal)
    for start in range(0, len(signal), block):
        chunk = signal[start:start + block].reshape(-1, 1)
        out[start:start + len(chunk)] = voicer.process(chunk.copy(), SAMPLE_RATE)[:, 0]
    return out


def test_a_whisper_has_no_periodicity():
    _, periodicity = voicedness(whisper(), SAMPLE_RATE)
    assert periodicity < 0.3


def test_a_voiced_tone_is_measured_as_voiced():
    pitch, periodicity = voicedness(voiced(), SAMPLE_RATE)
    assert periodicity > 0.5 and pitch == pytest.approx(200, rel=0.08)


def test_the_voicer_gives_the_whisper_a_pitch_to_lock_onto():
    audio = whisper().reshape(-1, 1)
    before_pitch, before = voicedness(audio[:, 0], SAMPLE_RATE)
    voicer = WhisperVoicer(amount=0.8, fallback_pitch=180.0)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(pitch_hz=180.0, voiced=False)
    output = voicer.process(audio.copy(), SAMPLE_RATE)
    after_pitch, after = voicedness(output[:, 0], SAMPLE_RATE)
    assert after > before + 0.3
    assert after_pitch == pytest.approx(180.0, rel=0.15)
    assert before_pitch < 180 * 0.9 or before < 0.3


def test_the_voicer_keeps_the_level_in_the_same_place():
    audio = whisper().reshape(-1, 1)
    voicer = WhisperVoicer(amount=0.7, fallback_pitch=200.0)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(voiced=False)
    level_before = float(np.sqrt(np.mean(audio ** 2)))
    output = voicer.process(audio.copy(), SAMPLE_RATE)
    level_after = float(np.sqrt(np.mean(output ** 2)))
    assert level_after == pytest.approx(level_before, rel=0.4)


def test_voiced_input_is_left_alone():
    audio = voiced().reshape(-1, 1)
    voicer = WhisperVoicer(amount=0.9)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(pitch_hz=200.0, voiced=True)
    original = audio.copy()
    assert np.array_equal(voicer.process(audio, SAMPLE_RATE), original)


def test_silence_is_left_alone():
    audio = np.zeros((2400, 1), dtype=np.float32)
    voicer = WhisperVoicer(amount=1.0)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(voiced=False)
    assert np.array_equal(voicer.process(audio, SAMPLE_RATE), audio)


def test_amount_zero_is_a_pass_through():
    audio = whisper().reshape(-1, 1)
    voicer = WhisperVoicer(amount=0.0)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(voiced=False)
    original = audio.copy()
    assert np.array_equal(voicer.process(audio, SAMPLE_RATE), original)


def test_shape_and_dtype_survive_the_stage():
    audio = whisper(1024).reshape(-1, 1)
    voicer = WhisperVoicer(amount=0.5)
    voicer.prepare(SAMPLE_RATE, len(audio))
    voicer.set_control(voiced=False)
    output = voicer.process(audio, SAMPLE_RATE)
    assert output.shape == audio.shape and output.dtype == np.float32


def test_reset_returns_to_the_fallback_pitch():
    voicer = WhisperVoicer(fallback_pitch=150.0)
    voicer.set_control(pitch_hz=300.0, voiced=False)
    voicer.reset()
    assert voicer._pitch == 150.0 and voicer._voiced is True and voicer._phase == 0.0


def test_controls_and_construction_are_validated():
    with pytest.raises(ValueError):
        WhisperVoicer(amount=1.5)
    with pytest.raises(ValueError):
        WhisperVoicer(fallback_pitch=10)
    voicer = WhisperVoicer()
    with pytest.raises(ValueError):
        voicer.set_control(pitch_hz=1000)
    # Too short to measure: reported as unvoiced rather than guessed at.
    assert voicedness(np.zeros(10), SAMPLE_RATE) == (0.0, 0.0)
    assert voicedness(np.zeros(4800), SAMPLE_RATE) == (0.0, 0.0)


def test_the_detector_tells_a_whispered_vowel_from_a_hiss():
    from src.processors.whisper import analyze_frame
    _, whisper_per, whisper_ratio = analyze_frame(whisper_vowel(), SAMPLE_RATE)
    _, hiss_per, hiss_ratio = analyze_frame(fricative(), SAMPLE_RATE)
    # Both are unvoiced; only the vowel keeps formant energy down low.
    assert whisper_per < 0.4 and hiss_per < 0.4
    assert whisper_ratio > 5.0 > hiss_ratio


def test_auto_mode_engages_on_a_whisper_and_releases_on_voice():
    voicer = WhisperVoicer(amount=0.8, fallback_pitch=180.0)
    voicer.prepare(SAMPLE_RATE, 480)
    assert voicer._voiced is True  # doubt means pass-through until measured
    out = stream(voicer, whisper_vowel(frames=4800))
    assert voicer._voiced is False
    _, before = voicedness(whisper_vowel(frames=4800)[:2400], SAMPLE_RATE)
    _, after = voicedness(out[:2400], SAMPLE_RATE)
    assert after > before + 0.3
    out = stream(voicer, voiced(frames=4800))
    assert voicer._voiced is True
    # The flip takes effect at the next measurement: the stale prior steers a
    # few blocks first (prior controls for subsequent chunks), then releases.
    np.testing.assert_array_equal(out[1920:], voiced(frames=4800)[1920:])


def test_auto_mode_leaves_hiss_and_silence_alone():
    voicer = WhisperVoicer(amount=0.9, fallback_pitch=180.0)
    voicer.prepare(SAMPLE_RATE, 480)
    hiss = fricative(frames=4800)
    np.testing.assert_array_equal(stream(voicer, hiss), hiss)
    assert voicer._voiced is True
    quiet = np.zeros(4800, dtype=np.float32)
    np.testing.assert_array_equal(stream(voicer, quiet), quiet)


def test_an_explicit_flag_pins_the_detector():
    tone = voiced(frames=2400).reshape(-1, 1)
    voicer = WhisperVoicer(amount=0.8, fallback_pitch=180.0)
    voicer.prepare(SAMPLE_RATE, 2400)
    voicer.set_control(voiced=False)
    assert not np.array_equal(voicer.process(tone.copy(), SAMPLE_RATE), tone)
    voicer.reset()
    # Back to automatic: the same tone passes through untouched.
    assert np.array_equal(voicer.process(tone.copy(), SAMPLE_RATE), tone)
