from dataclasses import asdict, replace
import json

import pytest

from src.lab.parameters import LabParameters
from src.settings.manager import AppSettings, SettingsManager


def test_defaults_are_the_conservative_ones():
    lab = LabParameters()
    # The governor only reports, and no stage that touches the audio route is on.
    assert lab.governor is True and lab.governor_auto is False
    assert lab.whisper is False and lab.remote is False and lab.diarization is False
    assert lab.translation_provider == 'off' and lab.translate_preserve is True


def test_construction_validates_every_field():
    for field, value in (('whisper', 'yes'), ('translation_provider', 'google'),
                         ('whisper_amount', 2), ('remote_port', 0),
                         ('diarization_speakers', 5), ('remote_host', 'x' * 300),
                         ('translate_reference', 'x' * 100)):
        with pytest.raises(ValueError):
            LabParameters(**{field: value})


def test_a_hand_edited_file_degrades_to_defaults():
    lab = LabParameters.from_dict({
        'whisper': 'yes', 'remote_port': 99999, 'translation_provider': 'nope',
        'diarization_speakers': 99, 'governor': None,
        'remote_host': 12, 'translate_voice': ['x']})
    assert lab == LabParameters()


def test_valid_values_survive_a_load():
    lab = LabParameters.from_dict({
        'governor': False, 'governor_auto': True, 'translation_provider': 'kokoro',
        'translate_voice': 'af_heart', 'translate_preserve': False, 'whisper': True,
        'whisper_amount': 0.25, 'whisper_pitch': 260, 'remote': True,
        'remote_host': 'gpu-box.local', 'remote_port': 9000, 'translate_reference': 'user_a',
        'diarization': True, 'diarization_speakers': 3})
    assert lab.remote_port == 9000 and lab.diarization_speakers == 3
    assert lab.whisper_pitch == 260 and lab.translate_reference == 'user_a'
    assert LabParameters.from_dict(asdict(lab)) == lab


def test_a_json_number_that_should_be_an_int_is_accepted():
    # JSON has one number type, so a port written as 9000.0 is still a port.
    lab = LabParameters.from_dict({'remote_port': 9000.0, 'diarization_speakers': 3.0})
    assert (lab.remote_port, lab.diarization_speakers) == (9000, 3)


def test_settings_carry_the_lab_object(tmp_path):
    manager = SettingsManager(tmp_path / 'settings.json')
    settings = replace(AppSettings(), lab=asdict(LabParameters(whisper=True, whisper_amount=0.4,
                                                               remote_port=9100)))
    assert manager.save(settings)
    assert manager.load() == settings
    assert manager.load().lab_parameters().whisper_amount == 0.4


def test_settings_without_a_lab_object_get_the_defaults(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'gain_db': 1.0}), encoding='utf-8')
    loaded = SettingsManager(path).load()
    assert loaded.lab_parameters() == LabParameters()
    assert loaded.gain_db == 1.0


def test_a_broken_lab_object_never_breaks_the_rest_of_the_settings(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'gain_db': 2.5, 'lab': {'whisper': 'yes'}}), encoding='utf-8')
    loaded = SettingsManager(path).load()
    assert loaded.gain_db == 2.5
    assert loaded.lab_parameters().whisper is False


def test_unknown_lab_keys_are_ignored():
    lab = LabParameters.from_dict({'a_feature_from_the_future': 3, 'whisper': True})
    assert lab.whisper is True and not hasattr(lab, 'a_feature_from_the_future')
