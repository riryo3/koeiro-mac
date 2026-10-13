"""Discover and validate installable extension packs ("DLC").

The base install stays small: heavy optional features -- the realtime translation
voice among them -- ship as a pack, a folder under ``models/packs/<id>`` holding a
``pack.json`` manifest and, once the user has downloaded them, the pack's assets.

This module only reads and validates. It never downloads, never imports pack code
and never touches the audio callback, so a malformed or half-installed pack degrades
to "not available" rather than breaking the app. Whether a pack's assets are present
is reported separately from whether its manifest is well formed, because a manifest
can be shipped while a multi-gigabyte model still is not.
"""
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MANIFEST = "pack.json"
# A manifest is metadata, never a model or audio, so the same ceiling the settings
# loader uses is generous here.
MAX_MANIFEST_BYTES = 64 * 1024
KINDS = ("translation", "voice", "enhancer")
DEVICES = ("cpu", "cuda", "")
_REQUIRED = ("id", "name", "kind", "version")
_ID_OK = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def valid_id(value):
    """Pack ids are lowercase slugs so they are safe as a folder name and a key."""
    return (isinstance(value, str) and 1 <= len(value) <= 48
            and all(character in _ID_OK for character in value))


@dataclass(frozen=True)
class Pack:
    """One installable pack, as declared by its manifest."""

    id: str
    name: str
    kind: str
    version: str
    description: str = ""
    requires_device: str = ""
    size_mb: float = 0.0
    assets: tuple = ()
    entry: dict = field(default_factory=dict)
    root: str = ""

    def missing_assets(self):
        """Declared asset paths that are not on disk yet (relative to the pack)."""
        base = Path(self.root)
        return [asset for asset in self.assets if not (base / asset).exists()]

    def is_installed(self):
        """True when the manifest declares assets and every one of them is present."""
        return bool(self.assets) and not self.missing_assets()


class PackManager:
    """Reads the packs under a root directory. Read-only and side-effect free."""

    def __init__(self, root):
        self.root = Path(root)

    def discover(self):
        """Every valid pack keyed by id. A broken manifest is skipped, not fatal."""
        found = {}
        if not self.root.is_dir():
            return found
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir():
                continue
            pack = self._read(folder)
            if pack is None:
                continue
            if pack.id in found:
                log.warning("Duplicate pack id %s; keeping %s", pack.id, found[pack.id].root)
                continue
            found[pack.id] = pack
        return found

    def get(self, pack_id):
        return self.discover().get(pack_id)

    def _read(self, folder):
        data = self._manifest(folder / MANIFEST)
        if data is None:
            log.warning("Ignoring pack with an unreadable manifest: %s", folder)
            return None
        missing = [key for key in _REQUIRED if not isinstance(data.get(key), str) or not data[key]]
        if missing or not valid_id(data.get("id")):
            log.warning("Ignoring pack %s: invalid fields %s", folder, missing)
            return None
        if data["kind"] not in KINDS:
            log.warning("Ignoring pack %s: unknown kind %r", folder, data["kind"])
            return None
        device = data.get("requires_device", "")
        if device not in DEVICES:
            device = ""
        assets = data.get("assets") or []
        assets = tuple(str(asset) for asset in assets) if isinstance(assets, list) else ()
        entry = data.get("entry") if isinstance(data.get("entry"), dict) else {}
        size = data.get("size_mb", 0.0)
        size = float(size) if type(size) in (int, float) and size >= 0 else 0.0
        return Pack(id=data["id"], name=data["name"], kind=data["kind"], version=data["version"],
                    description=str(data.get("description", ""))[:400],
                    requires_device=device, size_mb=size, assets=assets, entry=entry,
                    root=str(folder))

    @staticmethod
    def _manifest(path):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if len(raw.encode("utf-8")) > MAX_MANIFEST_BYTES:
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            return None
        return data if isinstance(data, dict) else None
