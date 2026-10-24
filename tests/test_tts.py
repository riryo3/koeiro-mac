import sys
import types

import numpy as np
import pytest

from src.tts import provider as tts


def make_files(root):
    base = tts.model_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    (base / tts.MODEL_FILE).write_bytes(b"x")
    (base / tts.VOICES_FILE).write_bytes(b"x")
    return base


def test_missing_model_reports_unavailable_and_absent_provider(tmp_path):
    assert tts.available(tmp_path) is False
    assert tts.build_provider(tmp_path) is None
    with pytest.raises(tts.TtsUnavailable):
        tts.KokoroProvider(tmp_path)


def test_available_only_when_both_files_present(tmp_path):
    base = tts.model_dir(tmp_path)
    base.mkdir(parents=True)
    (base / tts.MODEL_FILE).write_bytes(b"x")
    assert tts.available(tmp_path) is False
    (base / tts.VOICES_FILE).write_bytes(b"x")
    assert tts.available(tmp_path) is True


def test_files_present_but_runtime_missing_raises_unavailable(tmp_path):
    make_files(tmp_path)
    # kokoro-onnx is not part of the GUI environment, so this is the real path here:
    # the manifest is shipped, the runtime is not, and that is a clean "not available".
    with pytest.raises(tts.TtsUnavailable):
        tts.KokoroProvider(tmp_path)
    assert tts.build_provider(tmp_path) is None


def test_metadata_is_read_when_valid(tmp_path):
    base = tts.model_dir(tmp_path)
    base.mkdir(parents=True)
    (base / tts.METADATA_FILE).write_text('{"license": "Apache-2.0"}', encoding="utf-8")
    assert tts.metadata(tmp_path) == {"license": "Apache-2.0"}
    (base / tts.METADATA_FILE).write_text("{broken", encoding="utf-8")
    assert tts.metadata(tmp_path) == {}
    # "Unreadable" includes a document nested past the parser's depth limit: the json
    # scanner raises RecursionError there, not ValueError.
    (base / tts.METADATA_FILE).write_text('[' * 30000 + ']' * 30000, encoding="utf-8")
    assert tts.metadata(tmp_path) == {}


def test_resample_length_and_dtype():
    x = np.linspace(-1, 1, 24000, dtype=np.float32)
    same = tts._resample(x, 24000, 24000)
    assert same.dtype == np.float32 and np.array_equal(same, x)
    up = tts._resample(x, 24000, 48000)
    assert up.dtype == np.float32 and len(up) == 48000


def test_kokoro_provider_fills_the_pipelines_speech_synth_seam(tmp_path, monkeypatch):
    from src.translate.pipeline import TranslationPipeline

    class FakeKokoro:
        def __init__(self, model, voices, espeak_config=None):
            self.paths = (model, voices)
            self.espeak_config = espeak_config

        def create(self, text, voice, speed, lang):
            return np.full(480, 0.5, dtype=np.float32), 24000

    make_files(tmp_path)
    module = types.ModuleType("kokoro_onnx")
    module.Kokoro = FakeKokoro
    monkeypatch.setitem(sys.modules, "kokoro_onnx", module)

    provider = tts.KokoroProvider(tmp_path, voice="af_heart")
    pipeline = TranslationPipeline(synthesizer=provider, sample_rate=16000)
    audio = pipeline.speak("hello world")
    # 480 samples at 24 kHz become 320 at the pipeline's 16 kHz.
    assert isinstance(audio, np.ndarray) and audio.dtype == np.float32 and len(audio) == 320
    assert len(pipeline.speak("")) == 0
