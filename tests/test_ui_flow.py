"""The window shows only controls that can act, and each visible one does something.

The shell is one stage plus two drawers (DESIGN.md section 4): the stage is always
there, and a decision lives in the 調整 drawer with the rest of the settings. The
shipped standard voice is a MeanVC2 registration whose pitch, EQ, coding chunk and
prosody are fixed, so those controls are hidden instead of left greyed out. These
tests pin that behaviour, the stage's permanent contents, and the voice-panel link.
"""
import pytest

from tests.test_ai_gui import ai_window, pump  # noqa: F401  (ai_window is used as a fixture)
from src.gui.tutorial import PAGES


def test_the_stage_is_the_only_permanent_surface(ai_window):
    app, window, backend, bridge = ai_window
    pump(app, lambda: window.start_button.isEnabled())
    # No pages, no rail: the stage carries the live numbers and Start by itself.
    assert not hasattr(window, 'pages')
    assert not hasattr(window, 'sidebar')
    assert window.relay.isVisible() and window.input_bar.isVisible()
    assert window.start_button.isVisible() and window.stop_button.isVisible()
    assert window.latency_value.text().endswith('ms')
    assert window.transport_bar.isVisible()
    # Nothing has to be opened for the session to start.
    for drawer in window.drawers.values():
        assert not drawer.isVisible()


def test_the_window_is_frameless_and_the_bar_is_its_title_bar(ai_window):
    """No OS frame: one surface, and the controls in the bar all do something."""
    from PySide6.QtCore import Qt
    from src.gui.shell import WindowButton
    app, window, backend, bridge = ai_window
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    # It stays a real top-level window, so the taskbar and Alt+Tab still list it.
    assert window.windowFlags() & Qt.WindowType.Window
    assert window.header.maximize_button._glyph == WindowButton.MAXIMIZE
    window.header.maximize_button.click()
    pump(app, lambda: window.isMaximized())
    pump(app, lambda: window.header.maximize_button._glyph == WindowButton.RESTORE)
    window.header.maximize_button.click()
    pump(app, lambda: not window.isMaximized())
    pump(app, lambda: window.header.maximize_button._glyph == WindowButton.MAXIMIZE)
    window.header.minimize_button.click()
    pump(app, lambda: window.isMinimized())
    window.showNormal()
    pump(app, lambda: not window.isMinimized())


def test_the_stage_banner_states_the_ai_readiness_from_the_bridge(ai_window):
    """Five readiness states, each read off the worker rather than guessed."""
    app, window, backend, bridge = ai_window
    pump(app, lambda: bridge.status == 'Ready')
    window._tick()
    assert window.ai_banner.property('state') == 'ready'
    assert '準備完了' in window.ai_banner.text()
    # A reload in flight is stated as loading, not as ready.
    bridge.status = 'Loading'
    window._tick()
    assert window.ai_banner.property('state') == 'loading'
    bridge.status = 'Ready'
    window._tick()
    assert window.ai_banner.property('state') == 'ready'
    # Another sample rate means the AI route is not what will run.
    window.rate.setCurrentIndex(window.rate.findData(44100))
    window._tick()
    assert window.ai_banner.property('state') == 'fallback'
    window.rate.setCurrentIndex(window.rate.findData(48000))
    window._tick()
    assert window.ai_banner.property('state') == 'ready'
    bridge.status, bridge.error = 'Error', 'worker stopped'
    window._tick()
    assert window.ai_banner.property('state') == 'error'
    assert window.ai_banner_note.text() == 'worker stopped'
    bridge.status, bridge.error = 'Stopped', ''
    window._tick()
    assert window.ai_banner.property('state') == 'stopped'
    # The foot no longer repeats it: one wording of the same fact.
    assert not hasattr(window, 'ai_readiness')


def test_the_stage_repeats_the_ai_readiness_large(ai_window):
    """The same AI state gets one big line in the flow, not just the foot."""
    app, window, backend, bridge = ai_window
    assert window.ai_banner.isVisible()
    assert window.ai_banner_note.isVisible()
    font = window.ai_banner.font()
    # The size comes from the stylesheet in pixels, not points.
    assert font.pixelSize() >= 20 and font.bold()
    pump(app, lambda: bridge.status == 'Ready')
    window._tick()
    assert window.ai_banner.property('state') == 'ready'
    assert '準備完了' in window.ai_banner.text()
    assert '選んだ声に変換できます' in window.ai_banner_note.text()
    bridge.status = 'Loading'
    window._tick()
    assert window.ai_banner.property('state') == 'loading'
    assert '読み込み中' in window.ai_banner.text()
    bridge.status, bridge.error = 'Error', 'worker stopped'
    window._tick()
    assert window.ai_banner.property('state') == 'error'
    assert window.ai_banner_note.text() == 'worker stopped'


def test_the_drawer_marks_bands_cards_and_body_at_three_sizes(ai_window):
    """A 3700px drawer scans by size: band, card title, then body text."""
    from PySide6.QtWidgets import QFrame, QLabel
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    app.processEvents()
    band_title = window.band_wire.findChild(QLabel, 'bandTitle')
    assert band_title.font().pixelSize() == 19
    step_title = window.drawer_tune.findChild(QLabel, 'stepTitle')
    assert step_title is not None and step_title.font().pixelSize() == 16
    card = window.drawer_tune.findChild(QFrame, 'stepCard')
    body = card.findChild(QLabel, 'muted')
    assert body is not None and body.font().pixelSize() == 13


def test_the_finish_card_conditions_converted_output_only(ai_window):
    """The ② band's finishing card wires the chain's post stage and persists."""
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    assert window.finish_toggle.isVisible() and window.finish_toggle.isEnabled()
    assert window.controller.engine.chain.finish.enabled is False
    window.finish_toggle.setChecked(True)
    app.processEvents()
    assert window.controller.engine.chain.finish.enabled is True
    window._capture_settings()
    assert window.settings.finish is True
    window.finish_toggle.setChecked(False)
    app.processEvents()
    assert window.controller.engine.chain.finish.enabled is False


def test_the_ai_formant_card_lifts_only_the_ai_route(ai_window):
    """The ② band's formant card wires the native post stage and persists."""
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    chain = window.controller.engine.chain
    assert window.ai_formant_toggle.isVisible() and window.ai_formant_toggle.isEnabled()
    assert chain.ai_formant_enabled is False
    window.ai_formant_toggle.setChecked(True)
    window.ai_formant_amount.setValue(30)
    app.processEvents()
    assert chain.ai_formant_enabled is True
    assert chain.ai_formant_semitones == pytest.approx(3.0)
    window._capture_settings()
    assert window.settings.ai_formant_on is True
    assert window.settings.ai_formant == pytest.approx(3.0)
    window.ai_formant_toggle.setChecked(False)
    app.processEvents()
    assert chain.ai_formant_enabled is False


def test_the_auto_level_card_rides_the_input(ai_window):
    """The input card's leveller wires the chain head and persists."""
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    chain = window.controller.engine.chain
    assert window.auto_level_toggle.isVisible() and window.auto_level_toggle.isEnabled()
    assert chain.leveler.enabled is False
    window.auto_level_toggle.setChecked(True)
    app.processEvents()
    assert chain.leveler.enabled is True
    window._capture_settings()
    assert window.settings.auto_level is True


def test_the_translate_route_is_selectable_and_described(ai_window):
    """The 4th route names itself and leaves the DSP parameters valid."""
    app, window, backend, bridge = ai_window
    assert window.mode.findData('translate') >= 0
    window.mode.setCurrentIndex(window.mode.findData('translate'))
    app.processEvents()
    assert window._describe_output() == '同時通訳（English）'
    assert window._dsp_parameters().mode == 'original'
    # Parked while stopped: the driver never spends an ASR worker unasked.
    window._tick()
    assert not window.translate_driver.alive
    assert 'Start' in window.translate_live_status.text()


def test_the_translate_banner_names_the_next_step(ai_window):
    """The big line follows the translation driver, not the parked VC bridge."""
    from unittest import mock
    app, window, backend, bridge = ai_window
    window.mode.setCurrentIndex(window.mode.findData('translate'))
    app.processEvents()
    engine = window.controller.engine
    driver = window.translate_driver
    try:
        # Master switch off: a step, not a dead end.
        state, detail = window._translate_readiness()
        assert state == 'stopped' and '実験機能有効' in detail
        window.lab_enabled.setChecked(True)
        # Provider still off: again a step.
        state, detail = window._translate_readiness()
        assert state == 'stopped' and '合成' in detail
        window.translate_provider.setCurrentIndex(
            window.translate_provider.findData('kokoro'))
        app.processEvents()
        # Parked while stopped.
        state, detail = window._translate_readiness()
        assert state == 'stopped' and 'Start' in detail
        # Faking a running engine: the banner now tracks the driver.
        engine._stream = object()
        state, detail = window._translate_readiness()
        assert state == 'loading'
        thread = mock.Mock()
        thread.is_alive = lambda: True
        driver._thread = thread
        window._update_ai_readiness()
        assert window.ai_banner.property('state') == 'ready'
        assert '聞き取っています' in window.ai_banner_note.text()
        driver._status.update(heard='こんにちは', said='<en>konnichiwa')
        window._update_ai_readiness()
        assert 'こんにちは' in window.ai_banner_note.text()
        driver._status.update(error='boom', running=False)
        window._update_ai_readiness()
        assert window.ai_banner.property('state') == 'error'
        assert 'boom' in window.ai_banner_note.text()
    finally:
        engine._stream = None
        driver._thread = None


def test_the_stage_names_the_live_voice_and_route(ai_window):
    """The stage says what Start will use (or is using), not just the drawer card."""
    app, window, backend, bridge = ai_window
    assert window.stage_voice.isVisible()
    font = window.stage_voice.font()
    assert font.pixelSize() == 17 and font.bold()
    pump(app, lambda: bridge.status == 'Ready')
    window._tick()
    assert window.stage_voice.text() == '停止中'
    window.start_button.click()
    pump(app, lambda: window.stop_button.isEnabled())
    window._tick()
    live = window._describe_output()
    assert live != '停止中' and window.stage_voice.text() == live
    window.stop_button.click()
    pump(app, lambda: window.start_button.isEnabled())
    window._tick()
    assert window.stage_voice.text() == '停止中'


def test_the_stage_foot_fills_the_space_the_stage_left_empty(ai_window):
    """Bottom right names the app, stage never moves."""
    app, window, backend, bridge = ai_window
    window.resize(1520, 980)
    window.show()
    app.processEvents()
    foot = window.stage_foot.mapTo(window, window.stage_foot.rect().topLeft())
    assert foot.y() > window.height()/2
    assert foot.x() < window.width()/2
    nameplate = window.nameplate.mapTo(window, window.nameplate.rect().topLeft())
    assert nameplate.x() > foot.x() + window.width()/2
    # It belongs to the stage, so an open drawer never hides it.
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    assert window.nameplate.isVisible()
    window._open_drawer(None)
    # At the smallest window the app allows, the foot still fits the stage: no
    # clipping and no sideways scrolling of the live surface.
    window.resize(window.minimumWidth(), window.minimumHeight())
    app.processEvents()
    viewport = window.centre_scroll.viewport()
    nameplate = window.nameplate.mapTo(viewport, window.nameplate.rect().topLeft())
    assert nameplate.x() >= 0
    assert nameplate.x() + window.nameplate.width() <= viewport.width()
    assert not window.centre_scroll.horizontalScrollBar().isVisible()


def test_the_window_border_answers_with_the_right_edge_and_pointer(ai_window):
    """The app owns the frame, so the app names the border the pointer is on."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    app, window, backend, bridge = ai_window
    window.resize(1280, 820)
    window.show()
    app.processEvents()
    edges_at = window.edge_resize.edges_at
    assert edges_at(QPoint(2, 400)) == Qt.Edge.LeftEdge
    assert edges_at(QPoint(1278, 400)) == Qt.Edge.RightEdge
    assert edges_at(QPoint(640, 818)) == Qt.Edge.BottomEdge
    assert edges_at(QPoint(640, 400)) == Qt.Edge(0)

    def move(local):
        point = QPointF(*local)
        global_point = QPointF(window.mapToGlobal(QPoint(*local)))
        event = QMouseEvent(QEvent.Type.MouseMove, point, global_point,
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        window.edge_resize.eventFilter(window, event)

    move((2, 400))
    assert window.cursor().shape() == Qt.CursorShape.SizeHorCursor
    move((640, 818))
    assert window.cursor().shape() == Qt.CursorShape.SizeVerCursor
    move((640, 400))
    assert window.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_drawers_open_one_at_a_time_and_can_be_closed(ai_window):
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    assert window._active_drawer == 'tune'
    assert window.input_device.isVisible()
    assert not window.drawer_lab.isVisible()
    window._open_drawer('lab')
    pump(app, lambda: window.drawer_lab.isVisible())
    assert not window.drawer_tune.isVisible()
    window.drawer_lab.close_button.click()
    pump(app, lambda: not window.drawer_lab.isVisible())
    assert window._active_drawer is None


def test_the_voice_list_folds_away_to_zero_width(ai_window):
    app, window, backend, bridge = ai_window
    assert window.voice_panel.isVisible()
    window.header.voice_button.click()
    pump(app, lambda: not window.voice_panel.isVisible())
    assert window.header.voice_button.isChecked() is False
    window.header.voice_button.click()
    pump(app, lambda: window.voice_panel.isVisible())
    assert window.header.voice_button.isChecked() is True


def test_standard_voice_hides_controls_that_cannot_apply(ai_window):
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    # MeanVC2 fixes the chunk, pitch and brightness; prosody stays off for it.
    for widget in (window.ai_quality, window.ai_brightness, window.ai_pitch, window.ai_wait):
        assert not window._container(widget).isVisible(), widget
    assert window.ai_threads.isVisible()
    assert not window.prosody_tab.isVisible()
    assert window.prosody_fixed_note.isVisible()


def test_control_visibility_follows_the_mode_and_route(ai_window):
    app, window, backend, bridge = ai_window
    # The tuning block lives in the 調整 drawer; the 一括変換 route uses it.
    window._open_drawer('tune')
    pump(app, lambda: window._container(window.tune_sib).isVisible())
    for widget in window._tune_widgets:
        assert window._container(widget).isVisible(), widget
    window.ai_delivery.setCurrentIndex(window.ai_delivery.findData('utterance_fastest'))
    pump(app, lambda: not window._container(window.tune_sib).isVisible())
    window.ai_delivery.setCurrentIndex(window.ai_delivery.findData('utterance_lavasr'))
    pump(app, lambda: window._container(window.tune_sib).isVisible())
    # Committing an unspoken utterance exists only on the utterance route.
    pump(app, lambda: window.finish_phrase.isVisible())
    window.ai_delivery.setCurrentIndex(window.ai_delivery.findData('streaming'))
    pump(app, lambda: not window.finish_phrase.isVisible())
    window.ai_delivery.setCurrentIndex(window.ai_delivery.findData('utterance_lavasr'))
    pump(app, lambda: window.finish_phrase.isVisible())


def test_dsp_controls_are_visible_and_drivable_only_on_the_dsp_path(ai_window):
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    # AI Voice is the active mode, so the section explains itself instead of showing
    # controls that would do nothing.
    pump(app, lambda: not window.pitch_display.isVisible())
    assert window.dsp_notice.text().startswith('いまは「AI Voice」です。')
    assert window.dsp_switch.isVisible()
    window.dsp_switch.click()
    pump(app, lambda: window.mode.currentData() == 'female_dsp'
         and window.pitch_display.isVisible())
    assert window.pitch.isVisible() and window.formant.isVisible()
    assert not window.dsp_switch.isVisible()
    assert window.dsp_notice.text() == ''


def test_quick_voice_picker_and_library_combo_stay_in_step(ai_window):
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.voice_quick.isVisible())
    assert [window.voice_quick.itemData(i) for i in range(window.voice_quick.count())] == \
        [window.ai_model.itemData(i) for i in range(window.ai_model.count())]
    assert window.voice_quick.currentData() == window.ai_model.currentData()
    # Choosing in the panel updates the drawer picker without re-sending a load.
    window.ai_model.setCurrentIndex(window.ai_model.count() - 1)
    pump(app, lambda: window.voice_quick.currentData() == window.ai_model.currentData())
    window.mode.setCurrentIndex(window.mode.findData('original'))
    pump(app, lambda: not window.voice_quick.isVisible())


def test_panel_jump_focuses_the_voice_search(ai_window):
    app, window, backend, bridge = ai_window
    window.show()
    window.panel_jump.click()
    pump(app, lambda: window.voice_panel.search.hasFocus())
    assert window.voice_panel.search.hasFocus()


def test_guide_steps_point_at_widgets_inside_the_surface_they_open(ai_window):
    """Every step names a control that exists, in the surface the step opens."""
    from src.gui.tutorial import TutorialOverlay
    app, window, backend, bridge = ai_window
    persistent = ('voice_panel', 'start_button')
    overlay = TutorialOverlay(window.centralWidget(), on_page=window._guide_page)
    for spec in PAGES:
        window._guide_page(spec, overlay)
        target = spec.get('target')
        if not target:
            continue
        widget = getattr(window, target, None)
        assert widget is not None, f'{spec["title"]} points at {target}'
        if target in persistent:
            # The voice list and the stage are always on screen by design.
            continue
        drawer = window.drawers[spec['drawer']]
        assert drawer.isVisible(), spec['title']
        # The guide must never point outside the surface it just opened.
        ancestor = widget
        while ancestor is not None and ancestor is not drawer.scroll.widget():
            ancestor = ancestor.parentWidget()
        assert ancestor is drawer.scroll.widget(), f'{target} is not in the {spec["drawer"]} drawer'
    overlay.deleteLater()


def _card_headings(band):
    """The card headings inside one band, in the order they are shown."""
    from PySide6.QtWidgets import QLabel
    headings = []
    for index in range(band.body.count()):
        widget = band.body.itemAt(index).widget()
        if widget is None:
            continue
        for label in widget.findChildren(QLabel):
            if label.objectName() in ('stepTitle', 'sectionTitle'):
                headings.append(label.text())
                break
    return headings


def _visible_titles(drawer):
    from PySide6.QtWidgets import QLabel
    titles = []
    for _group, cards in drawer.groups():
        for card in cards:
            if card.isVisible():
                titles.append(next((label.text() for label in card.findChildren(QLabel)
                                    if label.objectName() in ('stepTitle', 'sectionTitle')),
                                   card.objectName()))
    return titles


def test_the_drawer_search_keeps_only_what_matches(ai_window):
    app, window, backend, bridge = ai_window
    drawer = window.drawer_tune
    window._open_drawer('tune')
    pump(app, lambda: drawer.isVisible())
    assert len(_visible_titles(drawer)) == 15
    drawer.search.setText('モニター')
    app.processEvents()
    assert _visible_titles(drawer) == ['モニター（変換後の音を自分の耳で確認）']
    # A band with nothing left in it goes away with its card.
    bands = [group for group, _cards in drawer.groups()]
    assert [band.isVisible() for band in bands] == [True, False, False]
    assert not drawer.search_empty.isVisible()
    drawer.search.setText('そんな設定はない')
    app.processEvents()
    assert _visible_titles(drawer) == []
    assert drawer.search_empty.isVisible()
    assert not any(button.isEnabled() for button, _g in drawer.index_buttons)
    # Emptying the box brings the whole surface back.
    drawer.search.clear()
    app.processEvents()
    assert len(_visible_titles(drawer)) == 15
    assert all(band.isVisible() for band in bands)
    assert not drawer.search_empty.isVisible()


def test_the_search_reads_control_labels_not_only_headings(ai_window):
    app, window, backend, bridge = ai_window
    drawer = window.drawer_tune
    window._open_drawer('tune')
    pump(app, lambda: drawer.isVisible())
    drawer.search.setText('WASAPI')
    app.processEvents()
    titles = _visible_titles(drawer)
    assert 'マイクを選ぶ' in titles or '出力先を選ぶ' in titles
    assert 'シーン（設定プロファイル）' not in titles


def test_a_filter_never_unhides_a_control_the_mode_hid(ai_window):
    """Searching works on whole cards; the mode rules still own the cards' insides."""
    app, window, backend, bridge = ai_window
    drawer = window.drawer_tune
    window._open_drawer('tune')
    pump(app, lambda: drawer.isVisible())
    hidden = window._container(window.ai_brightness)
    assert not hidden.isVisible()
    drawer.search.setText('AI')
    app.processEvents()
    assert _card(window, '声の微調整（一括変換）').isVisible()
    assert not hidden.isVisible()
    drawer.search.clear()
    app.processEvents()
    assert not hidden.isVisible()


def test_the_lab_search_never_unhides_a_feature_that_is_switched_off(ai_window):
    """Heads are always offered; bodies still need the master and the switch."""
    app, window, backend, bridge = ai_window
    drawer = window.drawer_lab
    window._open_drawer('lab')
    pump(app, lambda: drawer.isVisible())
    assert not window.lab_enabled.isChecked()
    # The heads and their switches stay reachable with the master off, but no
    # body opens: searching finds the head without unlocking its settings.
    drawer.search.setText('囁き')
    app.processEvents()
    assert not drawer.search_empty.isVisible()
    assert window.whisper_on.isVisibleTo(drawer)
    assert not window.whisper_amount.isVisibleTo(drawer)
    drawer.search.clear()
    app.processEvents()
    assert window.governor_on.isVisibleTo(drawer)
    # The master switch brings the bodies back; a feature's own switch is what
    # reveals its contents.
    window.lab_enabled.setChecked(True)
    pump(app, lambda: window.governor_on.isVisibleTo(drawer))
    assert not window.translate_test_button.isVisibleTo(drawer)
    drawer.search.setText('ガバナ')
    app.processEvents()
    assert not drawer.search_empty.isVisible()
    assert not window.translate_test_button.isVisibleTo(drawer)
    drawer.search.clear()
    window.translate_on.setChecked(True)
    pump(app, lambda: window.translate_test_button.isVisibleTo(drawer))


def _title_of(window, key):
    from PySide6.QtWidgets import QLabel
    return window.drawers[key].findChild(QLabel, 'drawerTitle')


def test_the_bar_and_the_surface_header_name_where_the_reader_is(ai_window):
    """One button takes the brand navy, so the bar answers "where am I"."""
    from src.gui.shell import LIVE
    from tests.fakes import pixel_colours
    app, window, backend, bridge = ai_window
    window.resize(1400, 900)
    window.show()
    app.processEvents()
    header = window.header
    assert header.tune_button.property('active') is not True
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    assert header.tune_button.property('active') is True
    assert header.lab_button.property('active') is not True
    # The open surface's own name is written in navy; a closed surface borrows none.
    tuned = pixel_colours(_title_of(window, 'tune').grab().toImage())
    assert LIVE.lower() in tuned, sorted(tuned)
    assert LIVE.lower() in pixel_colours(header.tune_button.grab().toImage())
    assert LIVE.lower() not in pixel_colours(header.lab_button.grab().toImage())
    assert _title_of(window, 'lab').property('surface') == 'lab'
    window._open_drawer('lab')
    pump(app, lambda: window.drawer_lab.isVisible())
    assert header.lab_button.property('active') is True
    assert header.tune_button.property('active') is not True
    opened = pixel_colours(_title_of(window, 'lab').grab().toImage())
    assert LIVE.lower() in opened, sorted(opened)
    assert LIVE.lower() in pixel_colours(header.lab_button.grab().toImage())


def test_ctrl_f_finds_the_search_box_of_the_open_drawer(ai_window):
    app, window, backend, bridge = ai_window
    window.show()
    app.processEvents()
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    window.hotkeys['Ctrl+F'].activated.emit()
    pump(app, lambda: window.drawer_tune.search.hasFocus())
    assert window.drawer_tune.search.hasFocus()
    # A closed drawer has no search box to send the reader to.
    window._open_drawer(None)
    pump(app, lambda: not window.drawer_tune.isVisible())
    window._focus_drawer_search()
    assert not window.drawer_lab.search.hasFocus()


def test_the_jump_row_lists_the_groups_and_scrolls_to_them(ai_window):
    from PySide6.QtWidgets import QLabel
    app, window, backend, bridge = ai_window
    drawer = window.drawer_tune
    window._open_drawer('tune')
    pump(app, lambda: drawer.isVisible())
    labels = [button.text() for button, _group in drawer.index_buttons]
    # One glyph ahead of each group's number: in a 3700px drawer the shape is what
    # the eye finds first, and the number still says where it sits in the session.
    assert labels == ['🔌 ① 配線', '🎛 ② 変換', '⚙️ ③ アプリ']
    assert drawer.index_box.isVisible()
    # The list is short enough for the index to name it as it is.
    lab = [button.text() for button, _group in window.drawer_lab.index_buttons]
    assert lab and all(len(name) <= drawer.MAX_INDEX_LABEL for name in lab)
    # The five features keep their order even though each label now leads with a glyph.
    assert [next(ch for ch in name if ch in '①②③④⑤') for name in lab] == list('①②③④⑤')
    third, group = drawer.index_buttons[-1]
    # The drawer scrolls, so it needs a laid-out range before a jump means anything.
    pump(app, lambda: drawer.scroll.verticalScrollBar().maximum() > 0)
    bar = drawer.scroll.verticalScrollBar()
    third.click()
    pump(app, lambda: bar.value() > 0)
    # The jump lands on the group's own line (clamped by the end of the drawer).
    assert bar.value() == max(bar.minimum(), min(bar.maximum(), group.y()))
    assert bar.value() == min(bar.maximum(), group.y())
    assert third.isChecked()
    assert sum(1 for button, _g in drawer.index_buttons if button.isChecked()) == 1
    assert drawer.search.placeholderText().startswith('この中を検索')
    assert any(label.objectName() == 'muted' for label in drawer.findChildren(QLabel))


def test_every_group_leads_with_a_glyph_that_names_it(ai_window):
    """The drawer is scanned by shape first, so every group carries one glyph.

    A group is what a reader hunts for in a 3700px list, and the glyph is the part
    that can be recognised without reading it. Cards keep their headings as plain
    text: a glyph per card is the clutter the group glyphs are meant to cut through
    (DESIGN.md section 4 A-2).
    """
    from src.gui.shell import Drawer
    app, window, backend, bridge = ai_window
    expected = {'tune': ('🔌', '🎛', '⚙️'),
                'lab': ('⏱️', '🌐', '🤫', '📡', '👥')}
    glyphs = {glyph for names in expected.values() for glyph in names}
    for key, names in expected.items():
        drawer = window.drawers[key]
        chips = [button.text() for button, _group in drawer.index_buttons]
        assert len(chips) == len(names), (key, chips)
        for glyph, chip in zip(names, chips):
            assert chip.startswith(glyph), (key, chip)
            # The glyph is a prefix, never a replacement: the name is still there,
            # and still short enough to read in the row.
            assert len(chip) <= drawer.MAX_INDEX_LABEL, chip
    for drawer in (window.drawer_tune, window.drawer_lab):
        for group, cards in drawer.groups():
            for card in cards:
                if card is group:
                    # In the lab drawer a feature card *is* its own group, so its
                    # heading is a group name and the glyph belongs to it.
                    continue
                heading = Drawer._heading_of(card)
                assert not heading.startswith(tuple(glyphs)), heading


def test_every_card_sits_under_the_band_that_names_it(ai_window):
    """A band owns its cards, so a heading never promises another band's controls.

    The drawer used to be one flat layout filled in build order, so what a heading
    named and what sat under it could disagree: the 更新 card was read under "① 配線"
    and the monitor and audio-format cards under "② 変換".
    """
    from src.gui.shell import Band
    app, window, backend, bridge = ai_window
    body = window.drawer_tune.body
    bands = [body.itemAt(i).widget() for i in range(body.count())]
    # Three headings and nothing loose between them.
    assert all(isinstance(band, Band) for band in bands), bands
    assert [band.body.count() > 0 for band in bands] == [True, True, True]
    assert _card_headings(bands[0]) == [
        'マイクを選ぶ', '出力先を選ぶ', 'モニター（変換後の音を自分の耳で確認）',
        '音の規格（Sample Rate / Buffer）']
    assert _card_headings(bands[1]) == [
        '入力の整え（音量とノイズ）', '声と話し方を選ぶ', '声の加工（Female DSP）',
        '声の微調整（一括変換）', '抑揚補正（Prosody）', '出力の仕上げ（自然さ）',
        'AI出力のフォルマント']
    assert _card_headings(bands[2]) == [
        'シーン（設定プロファイル）', 'アプリの更新', 'Discordのアクティビティ表示',
        '診断（実測値）']
    # The controls a heading names really are inside that heading's group.
    wired, converted, app_band = bands
    for widget in (window.input_device, window.output_device, window.monitor_toggle,
                   window.rate, window.buffer):
        assert wired.isAncestorOf(widget), widget
    # The voice combo in the card is the visible face of the choice; `ai_model` is a
    # hidden data owner shared with the worker and the voice panel, so it has no parent.
    for widget in (window.gain, window.voice_quick, window.mode, window.route_box,
                   window.ai_pitch, window.ai_fade, window.prosody_on,
                   window.prosody_advanced_box):
        assert converted.isAncestorOf(widget), widget
    assert window.ai_model.parentWidget() is None
    for widget in (window.update_auto, window.discord_toggle, window.latency_detail,
                   window.debug_snapshot):
        assert app_band.isAncestorOf(widget), widget


def test_the_bands_do_not_interleave_down_the_drawer(ai_window):
    """On screen the groups are contiguous: no band's card lands inside another's run."""
    from PySide6.QtWidgets import QLabel
    app, window, backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    for _ in range(20):
        app.processEvents()
    from PySide6.QtCore import QRect
    body = window.drawer_tune.scroll.widget()
    seen = []
    for index in range(window.drawer_tune.body.count()):
        band = window.drawer_tune.body.itemAt(index).widget()
        for position in range(band.body.count()):
            card = band.body.itemAt(position).widget()
            # `card.geometry()` is in band coordinates; both rectangles are compared
            # in the drawer body's own coordinates.
            in_body = QRect(band.mapTo(body, card.geometry().topLeft()), card.size())
            assert band.geometry().contains(in_body), _heading_of(card)
            seen.append((in_body.top(), index, card))
    # Reading down the drawer, the bands never alternate: every card of a band comes
    # before any card of the next one.
    tops = [top for top, _index, _card in sorted(seen, key=lambda item: item[1])]
    assert tops == sorted(tops), tops
    assert len({id(card) for _top, _index, card in seen}) == len(seen)
    # Every card still shows a heading, so no band swallowed another's label.
    assert all(_heading_of(card) for _top, _index, card in seen)
    assert all(card.findChildren(QLabel) for _top, _index, card in seen)


def _heading_of(card):
    from PySide6.QtWidgets import QLabel
    return next((label.text() for label in card.findChildren(QLabel)
                 if label.objectName() in ('stepTitle', 'sectionTitle')), card.objectName())


def _card(window, title):
    """The card whose own heading is `title`."""
    from PySide6.QtWidgets import QFrame, QLabel
    for card in window.drawer_tune.scroll.widget().findChildren(QFrame):
        for label in card.findChildren(QLabel):
            if label.parentWidget() is card and label.text() == title:
                return card
    raise AssertionError(f'no card titled {title}')


def test_a_card_holds_the_decision_it_names(ai_window):
    """The prosody controls sit in the prosody card, and 診断 holds measurements only."""
    app, window, backend, bridge = ai_window
    prosody = _card(window, '抑揚補正（Prosody）')
    assert prosody.isAncestorOf(window.prosody_advanced_box)
    assert prosody.isAncestorOf(window.prosody_preset)
    assert prosody.isAncestorOf(window.prosody_on)
    tuning = _card(window, '声の微調整（一括変換）')
    for widget in (window.ai_quality, window.ai_brightness, window.ai_pitch,
                   window.ai_wait, window.ai_fade):
        assert tuning.isAncestorOf(widget), widget
    diagnostics = _card(window, '診断（実測値）')
    for widget in (window.latency_detail, window.xruns, window.health):
        assert diagnostics.isAncestorOf(widget), widget
    # Nothing in 診断 is a setting that changes the sound.
    for widget in (window.ai_pitch, window.ai_wait, window.prosody_advanced_box):
        assert not diagnostics.isAncestorOf(widget), widget


def test_the_stage_keeps_the_caveat_and_diagnostics_keeps_the_breakdown(ai_window):
    """One number and one caveat on the stage; the working behind it in 診断."""
    app, window, backend, bridge = ai_window
    assert window.latency_value.text().endswith('ms')
    assert window.latency.text() == 'いずれもエンドツーエンドの実測値ではありません。'
    detail = window.latency_detail.text()
    assert '48000 Hz' in detail and 'Buffer latency' in detail
    # Neither line is the other's label, and the working is not on the stage.
    assert window.latency is not window.latency_detail
    assert not window.drawer_tune.isAncestorOf(window.latency)
    assert window.drawer_tune.isAncestorOf(window.latency_detail)


def test_the_preroll_caption_reads_as_a_setting_and_not_a_measurement(ai_window, monkeypatch):
    """The pre-roll caption has one source, and it never claims a measured delay.

    It was spelled out at every place that touched the slider, and the MeanVC2 route
    reached for a caption helper that did not exist.
    """
    app, window, backend, bridge = ai_window
    caption = window._preroll_text()
    assert caption.startswith(f'{window.ai_wait.value()} ms')
    assert '実測遅延ではありません' in caption
    assert '実測遅延ではありません' in window.ai_wait_label.text()
    # A voice the route does not fix reads the reader's own value.
    monkeypatch.setattr('src.gui.main_window.is_meanvc2', lambda *_args: False)
    window.ai_wait.setValue(77)
    window._update_meanvc_controls()
    assert window.ai_wait_label.text() == window._preroll_text()
    assert window.ai_wait_label.text().startswith('77 ms')
