from dataclasses import replace

import pytest

from src.settings.manager import AppSettings
from src.settings.scenes import MAX_SCENES, SceneStore, valid_name


def test_save_load_roundtrip(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    scene = AppSettings(voice_mode="female_dsp", pitch_semitones=4.5, preset="Female Bright",
                        denoise=True, denoise_strength=0.4)
    assert store.save("配信用", scene)
    assert store.names() == ["配信用"]
    loaded = store.load("配信用")
    assert loaded.voice_mode == "female_dsp" and loaded.pitch_semitones == 4.5
    assert loaded.denoise is True and loaded.denoise_strength == pytest.approx(0.4)


def test_missing_and_corrupt_file_start_empty(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    assert store.names() == []
    with pytest.raises(KeyError):
        store.load("nope")
    store.path.write_text("{broken", encoding="utf-8")
    assert store.names() == []
    store.path.write_text("[]", encoding="utf-8")
    assert store.names() == []


def test_delete(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    store.save("A", AppSettings())
    assert store.delete("A") is True
    assert store.delete("A") is False and store.names() == []


@pytest.mark.parametrize("name", ["", "   ", "a" * 41, 7, None, "bad/name", 'q"uote', "line\nbreak"])
def test_invalid_names(name):
    assert valid_name(name) is None


def test_save_rejects_invalid_name(tmp_path):
    with pytest.raises(ValueError):
        SceneStore(tmp_path / "scenes.json").save("", AppSettings())


def test_saved_values_are_validated(tmp_path):
    # An out-of-range field is stored as its fallback, never as the raw value.
    store = SceneStore(tmp_path / "scenes.json")
    store.save("odd", replace(AppSettings(), gain_db=999.0))
    assert store.load("odd").gain_db == 0.0


def test_scene_count_is_capped(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    for index in range(MAX_SCENES):
        assert store.save(f"s{index}", AppSettings())
    with pytest.raises(ValueError):
        store.save("one-too-many", AppSettings())
    # Overwriting an existing name is still allowed at the cap.
    assert store.save("s0", AppSettings(gain_db=1.0))
    assert store.load("s0").gain_db == 1.0
