from .test_ai_gui import ai_window, pump


def test_ab_hotkey_toggles_original_and_last_route(ai_window):
    app, window, backend, bridge = ai_window
    pump(app, lambda: bridge.status == 'Ready')
    assert set(window.hotkeys) == {'Ctrl+1', 'Ctrl+2', 'Ctrl+3', 'Ctrl+D', 'Ctrl+F'}
    window.mode.setCurrentIndex(window.mode.findData('ai_voice'))
    pump(app, lambda: not window._pending and bridge.status == 'Ready')
    window._ab_toggle()
    assert window.mode.currentData() == 'original'
    window._ab_toggle()
    assert window.mode.currentData() == 'ai_voice'
    # Picking a non-Original route remembers it as the A side.
    window._select_mode('female_dsp')
    assert window.mode.currentData() == 'female_dsp' and window._ab_last == 'female_dsp'
    window._ab_toggle()
    assert window.mode.currentData() == 'original'
    window._ab_toggle()
    assert window.mode.currentData() == 'female_dsp'


def test_scene_save_apply_and_delete(ai_window):
    app, window, backend, bridge = ai_window
    pump(app, lambda: bridge.status == 'Ready')
    # Scene A: the untouched defaults.
    window.scene_name.setText('基本')
    window.scene_save.click()
    assert window.scene_combo.findText('基本') >= 0
    assert not window.denoise_toggle.isChecked()
    # Scene B: a distinctly different tone, saved on top.
    window.denoise_toggle.setChecked(True)
    window.denoise_strength.setValue(90)
    window.denoise_strength.valueChanged.emit(90)
    window.scene_name.setText('ノイズ除去')
    window.scene_save.click()
    assert window.scene_combo.count() == 2
    # Applying A turns the denoise stage back off...
    window.scene_combo.setCurrentText('基本')
    window.scene_load.click()
    assert not window.denoise_toggle.isChecked()
    # ...and applying B brings it back with its strength. A scene apply acknowledges
    # itself off the GUI thread, so let that settle before the next switch.
    pump(app, lambda: not window._pending)
    window.scene_combo.setCurrentText('ノイズ除去')
    window.scene_load.click()
    assert window.denoise_toggle.isChecked() and window.denoise_strength.value() == 90
    # Deleting removes it from the list.
    window.scene_delete.click()
    assert window.scene_combo.findText('ノイズ除去') < 0
    assert window.scene_combo.findText('基本') >= 0


def test_scene_apply_is_refused_while_running(ai_window):
    app, window, backend, bridge = ai_window
    pump(app, lambda: bridge.status == 'Ready')
    window.scene_name.setText('基本')
    window.scene_save.click()
    window.mode.setCurrentIndex(window.mode.findData('ai_voice'))
    pump(app, lambda: bridge.status == 'Ready')
    window.start_button.click()
    pump(app, lambda: window.stop_button.isEnabled())
    window.scene_combo.setCurrentText('基本')
    window.scene_load.click()
    assert '停止' in window.scene_status.text()
