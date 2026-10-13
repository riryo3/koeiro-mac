"""Optional text-to-speech, shipped as a light weight model the user installs."""
from .client import KokoroClient, launcher, venv_dir, worker_available
from .provider import (DEFAULT_LANG, DEFAULT_VOICE, KokoroProvider, TtsUnavailable,
                       available, build_provider, metadata, model_dir, model_paths)

__all__ = ("DEFAULT_LANG", "DEFAULT_VOICE", "KokoroClient", "KokoroProvider",
           "TtsUnavailable", "available", "build_provider", "launcher", "metadata",
           "model_dir", "model_paths", "venv_dir", "worker_available")
