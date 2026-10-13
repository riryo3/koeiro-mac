import numpy as np
import pytest

from src.audio.controller import AudioController
from src.audio.engine import AudioEngine
from src.audio.performance import TimingSnapshot
from src.gui.main_window import MainWindow
from src.processors.chain import ProcessorChain
from src.processors.voice_router import VoiceRouter
from src.processors.whisper import WhisperVoicer
from src.settings.manager import SettingsManager
from tests.fakes import FakeBackend
from tests.test_gui import pump, qapp  # noqa: F401  (fixtures)

SAMPLE_RATE = 48000


@pytest.fixture
def lab_window(qapp, tmp_path):
    backend = FakeBackend()
    whisper = WhisperVoicer(0.0, 150.0)
    chain = ProcessorChain(VoiceRouter(), whisper=whisper)
    controller = AudioController(AudioEngine(chain=chain, backend=backend))
    window = MainWindow(SettingsManager(tmp_path / 'settings.json'), controller)
    window.show()
    pump(qapp, lambda: window.start_button.isEnabled())
    window._open_drawer('lab')
    yield qapp, window, chain, whisper
    window.close()
    pump(qapp, lambda: not controller.alive)
    qapp.processEvents()


def test_the_lab_drawer_keeps_every_switch_reachable(lab_window):
    qapp, window, _chain, _whisper = lab_window
    assert window._active_drawer == 'lab' and window.drawer_lab.isVisible()
    for attribute in ('governor_on', 'governor_status', 'translate_provider', 'translate_test_button',
                      'translate_live_status',
                      'translate_reference', 'whisper_on', 'whisper_amount', 'whisper_pitch',
                      'remote_enabled', 'remote_host', 'remote_port', 'remote_test_button',
                      'diarization_on', 'diarization_speakers',
                      'speaker_a', 'speaker_b', 'speaker_test_button'):
        assert hasattr(window, attribute), attribute
    # Master switch off: the heads and their ON/OFF stay put, only the bodies hide,
    # so a running feature always has a visible way to stop it.
    assert window.lab_enabled.isChecked() is False
    assert window.lab_summary.isVisible()
    for key, (card, body, switch) in window.lab_rows.items():
        assert card.isVisible(), key
        assert switch.isVisible() and switch.isEnabled(), key
        assert not body.isVisible(), key
    window.lab_enabled.setChecked(True)
    qapp.processEvents()
    assert not window.lab_summary.isVisible()
    for key, (card, body, switch) in window.lab_rows.items():
        assert card.isVisible(), key
        # Only the features this reader turned on open their settings.
        assert body.isVisible() == switch.isChecked(), key


def test_the_master_switch_gates_effect_not_the_choice(lab_window):
    """Armed while the master is OFF means saved but inert, never half-running."""
    qapp, window, chain, whisper = lab_window
    assert chain.pre_processors[0] is whisper
    window.whisper_on.setChecked(True)
    window.whisper_amount.setValue(70)
    qapp.processEvents()
    assert whisper.amount == 0.0  # master OFF: the switch is remembered, not applied
    assert '無効' in window.whisper_note.text()
    window.lab_enabled.setChecked(True)
    qapp.processEvents()
    assert whisper.amount == pytest.approx(0.7)
    assert '無効' not in window.whisper_note.text()
    window.lab_enabled.setChecked(False)
    qapp.processEvents()
    assert whisper.amount == 0.0


def test_the_translation_row_switch_and_the_provider_are_one_decision(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    window.translate_on.setChecked(True)
    qapp.processEvents()
    assert window.translate_provider.currentData() == 'kokoro'
    assert window.lab_rows['translate'][1].isVisible()
    window.translate_provider.setCurrentIndex(window.translate_provider.findData('off'))
    qapp.processEvents()
    assert not window.lab_rows['translate'][1].isVisible()


def test_defaults_are_off_and_the_governor_only_reports(lab_window):
    _qapp, window, _chain, _whisper = lab_window
    assert window.whisper_on.isChecked() is False
    assert window.diarization_on.isChecked() is False
    assert window.remote_enabled.isChecked() is False
    assert window.governor_on.isChecked() is True
    assert window.governor_auto.isChecked() is False
    assert window.translate_provider.currentData() == 'off'


def test_turning_whisper_on_sets_the_stage_the_chain_really_runs(lab_window):
    qapp, window, chain, whisper = lab_window
    assert chain.pre_processors[0] is whisper
    assert whisper.amount == 0.0
    window.lab_enabled.setChecked(True)
    window.whisper_on.setChecked(True)
    window.whisper_amount.setValue(70)
    window.whisper_pitch.setValue(180)
    qapp.processEvents()
    assert whisper.amount == pytest.approx(0.7)
    assert whisper._pitch == 180
    window.whisper_on.setChecked(False)
    assert whisper.amount == 0.0


def test_the_lab_settings_are_captured_and_saved(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    window.whisper_on.setChecked(True)
    window.whisper_amount.setValue(40)
    window.remote_enabled.setChecked(True)
    window.remote_host.setText('gpu-box.local')
    window.remote_port.setValue(9100)
    window.diarization_speakers.setValue(3)
    window.translate_provider.setCurrentIndex(window.translate_provider.findData('kokoro'))
    qapp.processEvents()
    window._capture_settings()
    saved = window.settings.lab
    assert saved['whisper'] is True and saved['whisper_amount'] == pytest.approx(0.4)
    assert saved['remote_host'] == 'gpu-box.local' and saved['remote_port'] == 9100
    assert saved['diarization_speakers'] == 3
    assert saved['translation_provider'] == 'kokoro'
    assert saved['enabled'] is True
    # And the same values come back through the settings loader.
    assert window.settings.lab_parameters().remote_port == 9100
    assert window.settings.lab_parameters().enabled is True


def test_the_governor_reads_the_callback_counters(lab_window):
    qapp, window, chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    for _ in range(60):
        chain.performance.record(9_000_000, 256, SAMPLE_RATE)
    window._lab_governor_tick()
    assert 'p99' in window.governor_status.text()
    assert '推奨' in window.governor_status.text()


def test_the_governor_can_drop_and_raise_the_quality_profiles(lab_window):
    qapp, window, chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    window.governor_auto.setChecked(True)
    for _ in range(60):
        chain.performance.record(9_000_000, 256, SAMPLE_RATE)
    window.governor.observe(TimingSnapshot(60, 9.0, 9.0, 9.0, 0, 8.0, 9.0, 9.0))
    window._lab_apply_governor()
    assert window.ai_quality.currentData() == 'low_latency'
    # Three clean windows raise the suggestion, and applying it moves both routes.
    for count in (100, 200, 300):
        window.governor.observe(TimingSnapshot(count, 5.0, 5.0, 5.0, 0, 4.0, 5.0, 5.0))
    assert window.governor.profile == 'balanced'
    window._lab_apply_governor()
    assert window.ai_quality.currentData() == 'balanced'
    assert window.quality.currentData() == 'balanced'


def test_the_governor_refuses_to_change_quality_while_running(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    window.start_button.click()
    pump(qapp, lambda: window.stop_button.isEnabled())
    window._lab_governor_tick()
    window.governor.profile = 'balanced'
    window._lab_apply_governor()
    assert '停止' in window.governor_status.text()
    window.stop_button.click()
    pump(qapp, lambda: window.start_button.isEnabled())


def test_speaker_test_needs_two_registered_voices(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window._lab_speaker_test()
    assert '登録ボイス' in window.speaker_status.text()


def test_background_results_land_in_the_labels(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window.files.results['lab_remote'] = 'gpu-box に接続しました（protocol 1）'
    window.files.results['lab_speakers'] = 'ERROR: 参照音声が読めません'
    window._lab_results()
    assert 'gpu-box' in window.remote_status.text()
    assert window.speaker_status.text() == '参照音声が読めません'


def test_the_translation_test_asks_for_a_voice_first(lab_window):
    qapp, window, _chain, _whisper = lab_window
    window.translate_provider.setCurrentIndex(window.translate_provider.findData('kokoro'))
    window.translate_preserve.setChecked(True)
    window._lab_translate_test()
    # The shipped voice is not a user registration, so there is no reference to borrow.
    assert '登録ボイス' in window.translate_status.text()


def test_nothing_in_the_lab_drawer_overflows_its_right_edge(lab_window):
    """Every card fits the drawer: the horizontal bar stays off for a reason.

    The index row and the long feature headings once forced the body wider
    than the viewport, clipping switches and combos on the right with no way
    to scroll to them.
    """
    from PySide6.QtWidgets import QWidget
    qapp, window, _chain, _whisper = lab_window
    window.lab_enabled.setChecked(True)
    for _key, (_card, _body, switch) in window.lab_rows.items():
        switch.setChecked(True)
    qapp.processEvents()
    viewport = window.drawer_lab.scroll.viewport()
    body = window.drawer_lab.scroll.widget()
    assert body.layout().minimumSize().width() <= viewport.width()
    for widget in body.findChildren(QWidget):
        if widget.parentWidget() is not body or widget.geometry().width() <= 0:
            continue
        assert widget.geometry().right() <= viewport.width(), (
            type(widget).__name__, widget.objectName(), widget.geometry().getRect())


def test_the_index_wraps_instead_of_widening_the_drawer(lab_window):
    from PySide6.QtWidgets import QGridLayout
    qapp, window, _chain, _whisper = lab_window
    assert isinstance(window.drawer_lab.index_row, QGridLayout)
    assert window.drawer_lab.INDEX_COLUMNS == 3
    rows = {window.drawer_lab.index_row.getItemPosition(index)[0]
            for index in range(window.drawer_lab.index_row.count())}
    assert rows == {0, 1}  # five features over two wrapped rows
