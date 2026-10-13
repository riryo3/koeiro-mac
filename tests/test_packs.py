import json

import pytest

from src.packs.manager import MAX_MANIFEST_BYTES, PackManager, valid_id


def write_pack(root, folder, manifest):
    path = root / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def base_manifest(**overrides):
    data = {"id": "translate-ja-en", "name": "翻訳ボイス", "kind": "translation", "version": "0.1.0"}
    data.update(overrides)
    return data


def test_discovers_a_valid_pack(tmp_path):
    write_pack(tmp_path, "translate-ja-en", base_manifest(size_mb=3200, requires_device="cuda",
                                                          assets=["models/translator.bin"]))
    packs = PackManager(tmp_path).discover()
    assert set(packs) == {"translate-ja-en"}
    pack = packs["translate-ja-en"]
    assert pack.name == "翻訳ボイス" and pack.kind == "translation" and pack.size_mb == 3200
    assert pack.requires_device == "cuda" and pack.assets == ("models/translator.bin",)


def test_missing_and_malformed_manifests_are_ignored(tmp_path):
    (tmp_path / "empty").mkdir()
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "pack.json").write_text("{broken", encoding="utf-8")
    write_pack(tmp_path, "no-id", base_manifest(id=""))
    write_pack(tmp_path, "bad-kind", base_manifest(kind="magic"))
    write_pack(tmp_path, "bad-id", base_manifest(id="Not A Slug"))
    packs = PackManager(tmp_path).discover()
    assert packs == {}


def test_unknown_required_device_falls_back_to_any(tmp_path):
    write_pack(tmp_path, "p", base_manifest(requires_device="tpu"))
    assert PackManager(tmp_path).discover()["translate-ja-en"].requires_device == ""


def test_duplicate_id_keeps_the_first(tmp_path):
    write_pack(tmp_path, "a", base_manifest(name="first"))
    write_pack(tmp_path, "b", base_manifest(name="second"))
    packs = PackManager(tmp_path).discover()
    assert len(packs) == 1 and packs["translate-ja-en"].name == "first"


def test_installed_reflects_asset_presence(tmp_path):
    folder = write_pack(tmp_path, "translate-ja-en",
                        base_manifest(assets=["models/translator.bin", "models/tts.bin"]))
    pack = PackManager(tmp_path).discover()["translate-ja-en"]
    assert not pack.is_installed() and set(pack.missing_assets()) == {pack.assets[0], pack.assets[1]}
    (folder / "models").mkdir()
    (folder / "models" / "translator.bin").write_bytes(b"x")
    assert pack.missing_assets() == ["models/tts.bin"]
    (folder / "models" / "tts.bin").write_bytes(b"x")
    assert pack.is_installed()


def test_manifest_without_assets_is_not_installed(tmp_path):
    write_pack(tmp_path, "p", base_manifest())
    assert PackManager(tmp_path).discover()["translate-ja-en"].is_installed() is False


def test_oversized_manifest_is_ignored(tmp_path):
    folder = tmp_path / "big"
    folder.mkdir()
    (folder / "pack.json").write_text(" " * (MAX_MANIFEST_BYTES + 1), encoding="utf-8")
    assert PackManager(tmp_path).discover() == {}


def test_missing_root_is_empty(tmp_path):
    assert PackManager(tmp_path / "absent").discover() == {}


@pytest.mark.parametrize("value", ["", "UPPER", "with space", "slash/", 42, None, "a" * 49])
def test_valid_id(value):
    assert valid_id(value) is False


def test_shipped_translation_pack_manifest_is_valid():
    from src.runtime_paths import asset_root
    packs = PackManager(asset_root() / "models" / "packs").discover()
    assert "translate-ja-en" in packs
    pack = packs["translate-ja-en"]
    assert pack.kind == "translation" and pack.requires_device == "cuda"
    # The manifest ships, the models do not: it must report as not installed.
    assert pack.is_installed() is False
