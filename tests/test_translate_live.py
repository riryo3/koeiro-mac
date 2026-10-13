"""Live translation voice: playback queue, router mode and driver orchestration."""
import threading
import time

import numpy as np
import pytest

from src.processors.translate_playback import TranslatePlayback, MAX_QUEUED
from src.processors.voice_router import VoiceRouter
from src.translate.live import TranslationDriver

SAMPLE_RATE = 48000


def tone(frames=4800, pitch=220.0, level=0.2):
    times = np.arange(frames) / SAMPLE_RATE
    return (np.sin(2 * np.pi * pitch * times) * level).astype(np.float32)


def test_playback_is_silent_until_speech_arrives():
    play = TranslatePlayback()
    out = np.zeros(960, dtype=np.float32)
    play.render_into(out)
    assert not out.any()
    assert play.queued_seconds == 0.0


def test_playback_rejects_garbage_and_caps_the_queue():
    play = TranslatePlayback()
    assert play.offer(np.zeros(0, dtype=np.float32)) is False
    assert play.offer(np.full(100, np.inf, dtype=np.float32)) is False
    assert play.offer(tone(frames=480)) is True
    for _ in range(MAX_QUEUED + 2):
        play.offer(tone(frames=480))
    assert play.dropped_utterances >= 1
    assert play.queued_seconds > 0


def test_playback_rises_and_settles_without_clicks():
    play = TranslatePlayback()
    play.offer(tone(frames=960))
    first = np.zeros(960, dtype=np.float32)
    play.render_into(first)
    assert abs(first[0]) < 0.05  # fades up out of silence instead of starting mid-wave
    assert abs(first[480] - tone(frames=960)[480]) < 1e-6  # past the rise: bit-exact
    tail = np.zeros(960, dtype=np.float32)
    play.render_into(tail)  # queue drains mid-render: the tail settles, not chops
    assert abs(tail[-1]) < 0.01
    assert play.played_utterances == 1


def test_router_translate_mode_never_passes_the_microphone():
    router = VoiceRouter(mode="translate")
    router.prepare(SAMPLE_RATE, 512)
    mic = (np.random.default_rng(0).normal(0, 0.3, (512, 1))).astype(np.float32)
    # The route switch itself crossfades (no clicks), so run past the fade:
    # the target is silence until translated speech arrives.
    for _ in range(6):
        out = router.process(mic.copy(), SAMPLE_RATE)
    np.testing.assert_array_equal(out, np.zeros_like(mic))
    speech = tone(frames=4800)
    router.translate_playback.offer(speech)
    heard = np.concatenate([router.process(np.zeros((512, 1), dtype=np.float32), SAMPLE_RATE)[:, 0]
                            for _ in range(12)])
    assert np.sqrt(np.mean(heard.astype(float) ** 2)) > 0.05


def test_router_rejects_unknown_modes_but_accepts_translate():
    with pytest.raises(ValueError):
        VoiceRouter(mode="karaoke")
    assert VoiceRouter(mode="translate").mode == "translate"


class FakeTap:
    def __init__(self):
        from src.audio.monitor import MonitorTap
        self.tap = MonitorTap(seconds=2.0)

    @property
    def active(self):
        return self.tap.active

    @active.setter
    def active(self, value):
        self.tap.active = value

    def reset(self):
        self.tap.reset()

    def read_into(self, destination):
        return self.tap.read_into(destination)

    def offer(self, audio):
        self.tap.offer(audio)


class FakeEngine:
    def __init__(self):
        self.translate_tap = FakeTap()


class FakeASRBridge:
    """An ASR worker that finalizes whatever it was fed, on demand."""

    def __init__(self, parameters, client_factory=None):
        self.status = "Stopped"
        self.final_text = ""
        self.partial_text = ""
        self.fed = 0

    def load(self):
        self.status = "Listening"

    def set_active(self, active):
        pass

    def submit(self, audio):
        self.fed += len(audio)

    def current(self):
        if self.final_text:
            return {"final_text": self.final_text, "audio_timestamp": time.monotonic()}
        if self.partial_text:
            return {"partial_text": self.partial_text, "audio_timestamp": time.monotonic()}
        return {}

    def stop(self):
        self.status = "Stopped"


class FakePipeline:
    def __init__(self):
        self.calls = []

    def process(self, text, source="ja", target="en", voice=""):
        self.calls.append(text)
        return f"<en>{text}", tone(frames=2400, pitch=330.0, level=0.25)


def run_driver(monkeypatch, final_text="konnichiwa"):
    import src.asr.bridge as asr_bridge_module
    monkeypatch.setattr(asr_bridge_module, "ASRBridge", FakeASRBridge)
    engine = FakeEngine()
    playback = TranslatePlayback()
    driver = TranslationDriver(engine, playback)
    pipeline = FakePipeline()

    from src.prosody.parameters import ProsodyParameters
    driver.start(ProsodyParameters(voice_commands=True), lambda: pipeline, voice="test")
    assert driver.alive
    # The driver pulls the tap itself; feed it continuously like a callback.
    universe = tone(frames=48000, pitch=150.0, level=0.15)
    asr = driver.asr
    asr.final_text = final_text
    deadline = time.monotonic() + 10
    while not driver.status["said"] and time.monotonic() < deadline:
        engine.translate_tap.offer(universe[:960])
        time.sleep(0.005)
    return driver, pipeline, playback


def test_driver_turns_a_final_transcript_into_queued_speech(monkeypatch):
    driver, pipeline, playback = run_driver(monkeypatch)
    try:
        assert pipeline.calls == ["konnichiwa"]
        status = driver.status
        assert status["heard"] == "konnichiwa"
        assert status["said"] == "<en>konnichiwa"
        assert status["spoken"] == 1
        assert playback.queued_seconds > 0
    finally:
        driver.stop()
    assert not driver.alive


def test_driver_repeats_a_sentence_after_a_pause(monkeypatch):
    driver, pipeline, playback = run_driver(monkeypatch, final_text="ohayo")
    try:
        assert pipeline.calls == ["ohayo"]
        # Same words again without a pause in between: not spoken twice.
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            time.sleep(0.05)
        assert pipeline.calls == ["ohayo"]
    finally:
        driver.stop()


def test_driver_without_playback_reports_honestly(monkeypatch):
    import src.asr.bridge as asr_bridge_module
    monkeypatch.setattr(asr_bridge_module, "ASRBridge", FakeASRBridge)
    from src.prosody.parameters import ProsodyParameters
    driver = TranslationDriver(FakeEngine(), None)
    driver.start(ProsodyParameters(voice_commands=True), lambda: FakePipeline())
    assert not driver.alive
    assert "使えません" in driver.status["error"]


def test_translate_survives_settings_roundtrip():
    from src.settings.manager import AppSettings
    saved = AppSettings.from_dict({"voice_mode": "translate"})
    assert saved.voice_mode == "translate"
    assert AppSettings.from_dict({"voice_mode": "karaoke"}).voice_mode == "ai_voice"


def test_driver_flags_a_silent_microphone(monkeypatch):
    import src.asr.bridge as asr_bridge_module
    monkeypatch.setattr(asr_bridge_module, "ASRBridge", FakeASRBridge)
    from src.prosody.parameters import ProsodyParameters
    engine, playback = FakeEngine(), TranslatePlayback()
    from src.translate.live import TranslationDriver
    driver = TranslationDriver(engine, playback)
    driver.start(ProsodyParameters(voice_commands=True), lambda: FakePipeline())
    try:
        for _ in range(40):
            engine.translate_tap.offer(np.zeros(960, dtype=np.float32))
            time.sleep(0.02)
        assert driver.status["mic_silent"] is True
        engine.translate_tap.offer(tone(frames=960, level=0.2))
        deadline = time.monotonic() + 2
        while driver.status["mic_silent"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert driver.status["mic_silent"] is False
    finally:
        driver.stop()


def test_driver_speaks_a_stable_partial_without_a_pause(monkeypatch):
    """Long monologues never finalize: a steady partial still goes out, once."""
    import src.asr.bridge as asr_bridge_module
    monkeypatch.setattr(asr_bridge_module, "ASRBridge", FakeASRBridge)
    from src.prosody.parameters import ProsodyParameters
    engine, playback = FakeEngine(), TranslatePlayback()
    from src.translate.live import TranslationDriver
    driver = TranslationDriver(engine, playback)
    driver.stable_speak_seconds = 0.2
    pipeline = FakePipeline()
    driver.start(ProsodyParameters(voice_commands=True), lambda: pipeline)
    try:
        driver.asr.partial_text = "konnichiwa"
        deadline = time.monotonic() + 5
        while not pipeline.calls and time.monotonic() < deadline:
            engine.translate_tap.offer(tone(frames=960, level=0.1))
            time.sleep(0.01)
        assert pipeline.calls == ["konnichiwa"]
        # It stays steady: still only spoken once.
        time.sleep(0.5)
        assert pipeline.calls == ["konnichiwa"]
        # It grows: only the new words go out next.
        driver.asr.partial_text = "konnichiwa sekai"
        deadline = time.monotonic() + 5
        while len(pipeline.calls) < 2 and time.monotonic() < deadline:
            engine.translate_tap.offer(tone(frames=960, level=0.1))
            time.sleep(0.01)
        assert pipeline.calls == ["konnichiwa", "sekai"]
    finally:
        driver.stop()


def test_translated_speech_reaches_chain_output_while_mic_does_not():
    """The Discord wire carries the TTS, never the untranslated microphone."""
    from src.processors.chain import ProcessorChain
    from src.processors.voice_router import VoiceRouter
    mic = (np.sin(2 * np.pi * 300 * np.arange(4800) / SAMPLE_RATE) * 0.3).astype(np.float32)
    tts = (np.sin(2 * np.pi * 440 * np.arange(4800) / SAMPLE_RATE) * 0.25).astype(np.float32)
    chain = ProcessorChain(main_processor=VoiceRouter(mode="translate"))
    chain.prepare(SAMPLE_RATE, 480)
    chain.main_processor.translate_playback.offer(tts)
    out = np.concatenate([chain.process(mic[i:i + 480].reshape(-1, 1).copy(), SAMPLE_RATE)[:, 0]
                          for i in range(0, len(mic), 480)])
    # Past the route-switch crossfade and before the utterance tail settle,
    # the output is the offered speech bit-exactly, not the microphone.
    np.testing.assert_array_equal(out[960:4608], tts[960:4608])
    assert not np.allclose(out[960:4608], mic[960:4608])
