"""AI formant finish: brighter AI output, pitch untouched, converted routes only."""
import numpy as np
import pytest

from src.processors.chain import ProcessorChain
from src.processors.dsp_parameters import DSPParameters
from src.processors.female_dsp import FemaleDSPProcessor
from src.processors.passthrough import PassthroughProcessor

SAMPLE_RATE = 48000


def speechy_vowel(frames=24000, seed=9):
    rng = np.random.default_rng(seed)
    t = np.arange(frames) / SAMPLE_RATE
    harmonics = sum(np.sin(2 * np.pi * 130 * k * t) / k for k in range(1, 21))
    spec = np.fft.rfft(harmonics)
    freqs = np.fft.rfftfreq(frames, 1 / SAMPLE_RATE)
    envelope = (np.exp(-((freqs - 500) / 60) ** 2)
                + 0.7 * np.exp(-((freqs - 1500) / 90) ** 2)
                + 0.4 * np.exp(-((freqs - 2500) / 120) ** 2) + 0.01)
    shaped = np.fft.irfft(spec * envelope, frames)
    wobble = 1.0 + 0.01 * np.sin(2 * np.pi * 5 * t)
    breath = rng.normal(0, 1, frames) * 0.02
    out = shaped * wobble + breath * np.sqrt(np.mean(shaped ** 2))
    return (out / np.max(np.abs(out)) * 0.3).astype(np.float32)


def sine(frames=4800, pitch=200.0, level=0.2):
    t = np.arange(frames) / SAMPLE_RATE
    return (np.sin(2 * np.pi * pitch * t) * level).astype(np.float32)


def centroid(audio):
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio)))) ** 2 + 1e-12
    freqs = np.fft.rfftfreq(len(audio), 1 / SAMPLE_RATE)
    return float(np.sum(freqs * spec) / np.sum(spec))


def run_stage(formant, signal, block=480):
    from src.vc.voice_quality import estimate_f0  # noqa (kept local: heavy import)
    dsp = FemaleDSPProcessor(DSPParameters(mode='female_dsp', pitch=0.0, formant=formant,
                                           brightness=50.0, low_cut=False, limiter=False,
                                           wet=1.0, quality='low_latency'))
    dsp.prepare(SAMPLE_RATE, block)
    out = np.empty_like(signal)
    for start in range(0, len(signal), block):
        chunk = signal[start:start + block].reshape(-1, 1).copy()
        out[start:start + len(chunk)] = dsp.process(chunk, SAMPLE_RATE)[:, 0]
    return out


def native_or_skip():
    try:
        dsp = FemaleDSPProcessor(DSPParameters(mode='female_dsp', pitch=0.0, formant=0.0,
                                              brightness=50.0, low_cut=False, limiter=False,
                                              wet=1.0, quality='low_latency'))
        dsp.prepare(SAMPLE_RATE, 480)
    except (OSError, RuntimeError):
        pytest.skip('Female DSP native library unavailable')
    return dsp


def test_formant_lift_brightens_without_moving_pitch():
    native_or_skip()
    voice = speechy_vowel()
    lifted = run_stage(4.0, voice)[4096:-4096]
    plain = run_stage(0.0, voice)[4096:-4096]
    assert centroid(lifted) > centroid(plain)
    from src.vc.voice_quality import estimate_f0
    probe = sine(frames=24000)
    before, _ = estimate_f0(probe, SAMPLE_RATE)
    after, _ = estimate_f0(run_stage(3.0, probe)[4096:-4096], SAMPLE_RATE)
    voiced_before = before[before > 0]
    voiced_after = after[after > 0]
    assert voiced_before.size and voiced_after.size
    assert abs(float(np.median(voiced_after)) - float(np.median(voiced_before))) / float(
        np.median(voiced_before)) < 0.02


def test_formant_stage_keeps_level_within_bounds():
    native_or_skip()
    voice = speechy_vowel()
    out = run_stage(4.0, voice)
    rms = lambda x: float(np.sqrt(np.mean(x.astype(float) ** 2)))
    assert abs(20 * np.log10(rms(out) / rms(voice))) < 6.0
    assert np.isfinite(out).all()


def test_formant_bypass_and_validation():
    assert DSPParameters(mode='original', pitch=0.0, formant=0.0, brightness=50.0,
                         low_cut=False, limiter=False, wet=1.0).mode == 'original'
    with pytest.raises(ValueError):
        DSPParameters(mode='karaoke', pitch=0.0, formant=0.0, brightness=50.0,
                      low_cut=False, limiter=False, wet=1.0)


class ModeStub(PassthroughProcessor):
    def __init__(self, mode):
        self.mode = mode


def test_chain_arms_the_formant_finish_for_ai_voice_only():
    native_or_skip()
    chain = ProcessorChain(main_processor=ModeStub('original'))
    chain.prepare(SAMPLE_RATE, 480)
    assert chain.ai_formant_enabled is False
    voice = speechy_vowel()
    out = np.concatenate([chain.process(voice[i:i + 480].reshape(-1, 1).copy(), SAMPLE_RATE)[:, 0]
                          for i in range(0, len(voice), 480)])
    assert abs(20 * np.log10(np.sqrt(np.mean(out.astype(float) ** 2)) + 1e-9)
               - 20 * np.log10(np.sqrt(np.mean(voice.astype(float) ** 2)) + 1e-9)) < 0.5
    chain.ai_formant_enabled = True
    chain.ai_formant_semitones = 4.0
    chain.main_processor.mode = 'ai_voice'
    shifted = np.concatenate([chain.process(voice[i:i + 480].reshape(-1, 1).copy(), SAMPLE_RATE)[:, 0]
                              for i in range(0, len(voice), 480)])
    assert centroid(shifted[4096:-4096]) > centroid(voice[4096:-4096])
