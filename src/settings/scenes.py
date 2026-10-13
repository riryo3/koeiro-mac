"""Named settings profiles -- "scenes" -- saved beside settings.json.

A scene is a complete, validated :class:`AppSettings` snapshot under a name. Loading
goes through ``AppSettings.from_dict``, the same validator the settings file uses, so
a hand-edited or stale scene can never introduce a value the app would reject -- an
unknown key or an out-of-range number falls back field by field instead.

The store is deliberately small and bounded: one JSON file, a capped number of scenes
and a size ceiling, so nothing a user saves can grow without limit.
"""
from dataclasses import asdict
import json
import logging
from pathlib import Path

from .manager import AppSettings

log = logging.getLogger(__name__)

MAX_SCENES = 64
MAX_NAME_CHARS = 40
# Larger than settings.json (64 KiB) because it holds several snapshots, but still
# far too small to be a stream of audio or a model.
MAX_FILE_BYTES = 256 * 1024
_FORBIDDEN = set('/\\"')


def valid_name(name):
    """The trimmed name, or None when it is not something we will store."""
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not 1 <= len(name) <= MAX_NAME_CHARS:
        return None
    if any(ord(character) < 32 or character in _FORBIDDEN for character in name):
        return None
    return name


class SceneStore:
    """Reads and writes named :class:`AppSettings` snapshots."""

    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            if self.path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Scenes file too large")
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, RecursionError):
            log.warning("Invalid/unreadable scenes; starting empty", exc_info=True)
            return {}
        scenes = data.get("scenes") if isinstance(data, dict) else None
        if not isinstance(scenes, dict):
            return {}
        # Only keep entries that carry a dict, and cap what we accept on read rather
        # than trusting a hand-written file.
        return {name: value for name, value in list(scenes.items())[:MAX_SCENES]
                if valid_name(name) and isinstance(value, dict)}

    def _write(self, scenes):
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"version": 1, "scenes": scenes},
                           ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8")
            temporary.replace(self.path)
            return True
        except (OSError, ValueError, TypeError):
            log.exception("Failed to save scenes: %s", self.path)
            return False

    def names(self):
        """Saved scene names, sorted for a stable list."""
        return sorted(self._read())

    def save(self, name, settings):
        """Store the current settings under ``name``; validates before writing."""
        name = valid_name(name)
        if name is None:
            raise ValueError("Invalid scene name")
        scenes = self._read()
        if name not in scenes and len(scenes) >= MAX_SCENES:
            raise ValueError("Too many scenes")
        # Round-trip through the validator so a scene holds only accepted values.
        scenes[name] = asdict(AppSettings.from_dict(asdict(settings)))
        return self._write(scenes)

    def load(self, name):
        """Return the stored :class:`AppSettings`, or raise ``KeyError``."""
        name = valid_name(name)
        scenes = self._read()
        if name is None or name not in scenes:
            raise KeyError("Unknown scene")
        return AppSettings.from_dict(scenes[name])

    def delete(self, name):
        name = valid_name(name)
        scenes = self._read()
        if name not in scenes:
            return False
        del scenes[name]
        return self._write(scenes)
