"""Text-to-speech provider: Kokoro-82M through kokoro-onnx.

Kokoro-82M's weights are Apache-2.0 and kokoro-onnx is MIT, so shipping this backend
changes nothing about Koeiro's MIT distribution: the weights are downloaded by the
user's own setup (``tools/install_tts.py``), never bundled into this repository.

The heavy import is deferred to construction. A missing model file or a missing
runtime raises :class:`TtsUnavailable`, which callers turn into "feature absent", so
an uninstalled TTS never affects the voice route. Synthesis runs off the audio
callback; nothing here is touched from the PortAudio callback.
"""
import json
import math
import os
from pathlib import Path

import numpy as np

# The quantized int8 weights (~110 MB) plus the voices file (~28 MB): the lightest
# Kokoro build that still sounds right, chosen for low-spec machines.
MODEL_DIR = Path("models") / "tts" / "kokoro"
MODEL_FILE = "kokoro-v1.0.int8.onnx"
VOICES_FILE = "voices-v1.0.bin"
METADATA_FILE = "metadata.json"
# A female American English voice: the strongest grade in the model card and the
# target language of the ja -> en translation pack.
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "en-us"
NATIVE_SAMPLE_RATE = 24000


class TtsUnavailable(RuntimeError):
    """The model files or the kokoro-onnx runtime are not installed."""


def model_dir(root):
    return Path(root) / MODEL_DIR


def model_paths(root):
    base = model_dir(root)
    return base / MODEL_FILE, base / VOICES_FILE


def available(root):
    """True when both model files are on disk. Says nothing about the runtime."""
    model, voices = model_paths(root)
    return model.is_file() and voices.is_file()


def metadata(root):
    """The install-time metadata, or an empty dict when it is missing or unreadable."""
    try:
        data = json.loads((model_dir(root) / METADATA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resample(samples, source_rate, target_rate):
    """Linear resample to ``target_rate``. Bounded work, no scipy dependency."""
    samples = np.asarray(samples, dtype=np.float32)
    if target_rate == source_rate or samples.size == 0:
        return samples
    length = max(1, round(samples.size * target_rate / source_rate))
    index = np.linspace(0, samples.size - 1, length)
    return np.interp(index, np.arange(samples.size), samples).astype(np.float32)


class KokoroProvider:
    """A SpeechSynth-compatible Kokoro backend.

    ``synthesize(text, voice, sample_rate)`` returns mono float32 at ``sample_rate``
    (Kokoro generates 24 kHz and it is resampled here). Construction imports
    kokoro-onnx and loads the ONNX session, so it must run off the audio callback.
    """

    def __init__(self, root, voice=DEFAULT_VOICE, lang=DEFAULT_LANG, speed=1.0):
        if not available(root):
            raise TtsUnavailable(f"Kokoro model files are not installed under {model_dir(root)}")
        try:
            from kokoro_onnx import Kokoro
        except ImportError as error:
            raise TtsUnavailable("kokoro-onnx is not installed") from error
        model, voices = model_paths(root)
        self.voice = voice
        self.lang = lang
        self.speed = float(speed)
        self.sample_rate = NATIVE_SAMPLE_RATE
        self._kokoro = Kokoro(str(model), str(voices), espeak_config=_espeak_config())

    def synthesize(self, text, voice="", sample_rate=NATIVE_SAMPLE_RATE):
        text = (text or "").strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        samples, rate = self._kokoro.create(text, voice=voice or self.voice,
                                            speed=self.speed, lang=self.lang)
        return _resample(samples, rate, sample_rate or NATIVE_SAMPLE_RATE)


def _espeak_config():
    """An espeak configuration that works even under a non-ASCII install path.

    espeak-ng opens its data files with the narrow C API, so on Windows it cannot
    read them under a path with non-ASCII characters (a repository under a Japanese
    folder name is the common case) and fails with an opaque byte-sequence error.
    When the bundled data directory is not ASCII, it is mirrored once to an ASCII
    location under the OS temp directory and the library is pointed there.

    Returns None when ``espeakng_loader`` is not importable, so kokoro-onnx can try
    its own defaults instead.
    """
    try:
        import espeakng_loader
        from kokoro_onnx.config import EspeakConfig
    except ImportError:
        return None
    data = str(espeakng_loader.get_data_path())
    library = str(espeakng_loader.get_library_path())
    if not data.isascii():
        data = _mirror_ascii(data)
    os.environ.setdefault("ESPEAK_DATA_PATH", data)
    return EspeakConfig(lib_path=library, data_path=data)


def _mirror_ascii(source):
    """Copy a data directory to an ASCII path under the temp dir, once."""
    import shutil
    import tempfile
    target = Path(tempfile.gettempdir()) / "koeiro-espeak" / Path(source).name
    try:
        if not target.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        return str(target)
    except OSError:
        # Give up on the mirror and let espeak surface its own error rather than
        # masking it; a non-ASCII temp dir has no better fallback either.
        return source


def build_provider(root, **kwargs):
    """A ready provider, or None when nothing can synthesize.

    Returning None rather than raising keeps "TTS is optional" a caller-side branch,
    never an exception in the middle of a request. The model files are looked for
    first, then the two ways they can be spoken through: this process (a user who
    installed kokoro-onnx into the app's own environment) and, when that import is
    absent, the dedicated TTS environment through :mod:`src.tts.client`.
    """
    if not available(root):
        return None
    try:
        return KokoroProvider(root, **kwargs)
    except TtsUnavailable:
        pass
    from src.tts.client import KokoroClient, worker_available
    if not worker_available(root):
        return None
    try:
        return KokoroClient(root, **kwargs)
    except TtsUnavailable:
        return None
