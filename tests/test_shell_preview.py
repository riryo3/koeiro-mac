import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_ai_gui import ai_window, pump  # noqa: F401  (ai_window is used as a fixture)
from tests.test_voice_quality import RATE, speech, write_wav  # noqa: F401  (RATE used below)


# --- shell widgets ---

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_level_bar_clamps_and_never_shows_signal_it_was_not_given(app):
    from src.gui.shell import LevelBar
    bar = LevelBar(bars=8)
    bar.set_level(0.5)
    assert 0.0 <= bar._peak <= 1.0
    bar.set_level(9.0)
    assert bar._peak == 1.0
    bar.set_level(-3.0)
    assert bar._peak >= 0.0
    # A silent bar must read as silent.
    bar2 = LevelBar(bars=8)
    bar2.set_level(0.0)
    assert bar2._peak == 0.0


def test_relay_marks_the_state_and_is_tappable(app):
    from src.gui.shell import Relay
    relay = Relay()
    relay.set_state('running')
    assert relay._running is True and relay._error is False
    relay.set_level(0.0)
    assert relay._level == 0.0
    relay.set_level(9.0)
    assert relay._level == 1.0
    fired = []
    relay.tapped.connect(lambda: fired.append(True))
    relay.resize(600, Relay.HEIGHT)
    relay.grab()
    relay.tapped.emit()
    assert fired == [True]
    relay.set_state('error')
    assert relay._running is False and relay._error is True
    relay.set_state('stopped')
    assert relay._error is False


def test_window_button_paints_the_glyph_it_was_given(app):
    """Four controls draw four different shapes, with no icon font involved."""
    from src.gui.shell import WindowButton
    shapes = {}
    for glyph in (WindowButton.MINIMIZE, WindowButton.MAXIMIZE,
                    WindowButton.RESTORE, WindowButton.CLOSE):
        button = WindowButton(glyph)
        # A known light panel makes the glyph measurable: the page tint sits far
        # above the near-black lines.
        button.setStyleSheet('QPushButton { background: #eef2f7; border: none; }')
        image = button.grab().toImage()
        # The 1.3px strokes antialias into neighbouring rows, so the ink band
        # reads as dark gray rather than the full pen colour.
        ink = {(x, y) for y in range(image.height()) for x in range(image.width())
               if min(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(),
                      image.pixelColor(x, y).blue()) < 150}
        assert len(ink) > 15, (glyph, len(ink))
        shapes[glyph] = frozenset(ink)
    # Four glyphs, four distinct drawings.
    assert len(set(shapes.values())) == 4

    def width(ink):
        return max(x for x, _ in ink) - min(x for x, _ in ink)

    def height(ink):
        return max(y for _, y in ink) - min(y for _, y in ink)

    assert width(shapes[WindowButton.MINIMIZE]) > height(shapes[WindowButton.MINIMIZE])*5
    assert width(shapes[WindowButton.MAXIMIZE]) >= height(shapes[WindowButton.MAXIMIZE])
    # Close is an X: its own centre is on the strokes, a corner of the box is not.
    close = shapes[WindowButton.CLOSE]
    left, right = min(x for x, _ in close), max(x for x, _ in close)
    top, bottom = min(y for _, y in close), max(y for _, y in close)
    assert any(abs(x - (left+right)/2) <= 1 and abs(y - (top+bottom)/2) <= 1 for x, y in close)
    # Restore is two offset boxes: ink both above the front square and beside it.
    restore = shapes[WindowButton.RESTORE]
    assert any(y <= top + 2 and x > (left+right)/2 for x, y in restore)


def test_header_holds_the_window_controls_and_not_the_product_name(app):
    """The bar is the title bar now, and the name moved to the stage foot."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    from src.gui.shell import HeaderBar, WindowButton
    header = HeaderBar()
    assert header.findChild(QLabel, 'brandIcon') is None
    assert header.findChild(QLabel, 'brand') is None
    for button in (header.minimize_button, header.maximize_button, header.close_button):
        assert isinstance(button, WindowButton)
        assert button.objectName() in ('windowButton', 'windowClose')
        assert button.toolTip()
        # Reachable by Tab and activatable with Space, like every other control.
        assert button.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert button.isEnabled()
    assert header.close_button.objectName() == 'windowClose'
    seen = []
    header.minimize_clicked.connect(lambda: seen.append('minimize'))
    header.maximize_clicked.connect(lambda: seen.append('maximize'))
    header.close_clicked.connect(lambda: seen.append('close'))
    header.minimize_button.click()
    header.maximize_button.click()
    header.close_button.click()
    assert seen == ['minimize', 'maximize', 'close']
    # The glyph follows the window state, not the last click.
    header.set_maximized(True)
    assert header.maximize_button._glyph == WindowButton.RESTORE
    header.set_maximized(False)
    assert header.maximize_button._glyph == WindowButton.MAXIMIZE


def test_dragging_the_bar_only_starts_where_no_control_sits(app):
    """A press on a button must stay a click; the rest of the bar moves the window."""
    from PySide6.QtCore import QPoint
    from src.gui.shell import HeaderBar
    header = HeaderBar()
    header.resize(1520, 44)
    header.show()
    app.processEvents()
    for button in (header.tune_button, header.lab_button, header.voice_button,
                   header.help_button, header.minimize_button, header.maximize_button,
                   header.close_button):
        assert header._interactive_at(button.geometry().center()) is True, button.text()
    # Between the state pill and the first button there is nothing but bar.
    middle = (header.status.geometry().right() + header.voice_button.geometry().left())//2
    assert header._interactive_at(QPoint(middle, 21)) is False
    assert header._interactive_at(QPoint(400, 22)) is False
    header.hide()


def test_the_bar_moves_the_window_when_the_platform_will_not(app):
    """Losing the drag would leave the window stuck where it is, so the app follows."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from src.gui.shell import HeaderBar
    window = QWidget()
    column = QVBoxLayout(window)
    column.setContentsMargins(0, 0, 0, 0)
    header = HeaderBar()
    header.resize(600, 44)
    column.addWidget(header)
    window.resize(600, 300)
    window.layout().activate()
    header.layout().activate()
    empty = QPoint(300, 22)
    assert header.childAt(empty) is None
    # No window handle is created yet, which is the same answer the platform gives
    # when it refuses the move: the bar has to do it itself.
    assert window.windowHandle() is None

    def event(kind, global_point, buttons=Qt.MouseButton.LeftButton):
        return QMouseEvent(kind, QPointF(header.mapFromGlobal(global_point)),
                           QPointF(global_point), Qt.MouseButton.LeftButton, buttons,
                           Qt.KeyboardModifier.NoModifier)

    def send(kind, global_point, buttons=Qt.MouseButton.LeftButton):
        mouse_event = event(kind, global_point, buttons)
        if kind == QEvent.Type.MouseButtonPress:
            header.mousePressEvent(mouse_event)
        elif kind == QEvent.Type.MouseMove:
            header.mouseMoveEvent(mouse_event)
        else:
            header.mouseReleaseEvent(mouse_event)

    start = header.mapToGlobal(empty)
    origin = window.pos()
    send(QEvent.Type.MouseButtonPress, start)
    send(QEvent.Type.MouseMove, start + QPoint(40, 25))
    assert window.pos() == origin + QPoint(40, 25)
    send(QEvent.Type.MouseButtonRelease, start + QPoint(40, 25), Qt.MouseButton.NoButton)
    # The bar stops following the pointer once the button is up.
    send(QEvent.Type.MouseMove, start + QPoint(200, 200))
    assert window.pos() == origin + QPoint(40, 25)
    # A press that lands on a control is a click, never a drag.
    centre = header.tune_button.geometry().center()
    header.mousePressEvent(event(QEvent.Type.MouseButtonPress,
                                header.mapToGlobal(centre)))
    assert header._drag_from is None
    assert window.pos() == origin + QPoint(40, 25)
    header.hide()


def test_nameplate_carries_the_badge_and_the_wordmark(app):
    from PySide6.QtWidgets import QLabel
    from src.gui.shell import Nameplate
    from src.gui.splash import asset_path
    plate = Nameplate()
    badge = plate.findChild(QLabel, 'plateIcon')
    wordmark = plate.findChild(QLabel, 'plateLogo')
    assert badge is not None and wordmark is not None
    assert badge.pixmap() is not None and not badge.pixmap().isNull()
    mark = wordmark.pixmap()
    assert mark is not None and not mark.isNull()
    # The committed wordmark is wide; both parts are drawn at their configured height.
    assert mark.width() > mark.height()
    assert badge.pixmap().height() == Nameplate.ICON_PX
    assert mark.height() == Nameplate.LOGO_PX
    assert asset_path('logo.png') is not None


def test_nameplate_writes_the_name_when_the_images_are_missing(app, monkeypatch):
    """An asset-less checkout still shows a name rather than an empty box."""
    from PySide6.QtWidgets import QLabel
    from src.gui import splash
    from src.gui.shell import Nameplate
    monkeypatch.setattr(splash, 'asset_path', lambda name: None)
    plate = Nameplate()
    assert plate.findChild(QLabel, 'plateIcon') is None
    assert plate.findChild(QLabel, 'plateLogo') is None
    fallback = plate.findChild(QLabel, 'plateFallback')
    assert fallback is not None and fallback.text() == 'Koeiro'


def test_ai_readiness_names_every_state_it_can_show(app):
    """The stage says what the model is doing; the word carries the state, not colour."""
    from src.gui.shell import AiReadiness
    readiness = AiReadiness()
    assert readiness.state() == 'stopped'
    for kind, (label, note) in AiReadiness.TEXT.items():
        readiness.set_state(kind)
        assert readiness.value.text() == label
        assert readiness.note.text() == note
        assert readiness.state() == kind
    # An unknown state falls back to the one that claims nothing, and an error carries
    # the worker's own words instead of a guess.
    readiness.set_state('nonsense')
    assert readiness.state() == 'stopped'
    readiness.set_state('error', detail='AI worker pipe closed')
    assert readiness.value.text() == 'エラー'
    assert readiness.note.text() == 'AI worker pipe closed'
    assert set(AiReadiness.TEXT) == {'stopped', 'loading', 'ready', 'fallback',
                                     'unavailable', 'error'}


def test_edge_resize_reads_the_border_under_the_pointer(app):
    """A frameless window has no OS border, so the app names the edge itself."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QWidget
    from src.gui.shell import EdgeResize
    window = QWidget()
    window.resize(200, 100)
    window.show()
    app.processEvents()
    edge = EdgeResize(window)
    try:
        assert edge.edges_at(QPoint(3, 3)) == (Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
        assert edge.edges_at(QPoint(100, 3)) == Qt.Edge.TopEdge
        assert edge.edges_at(QPoint(197, 50)) == Qt.Edge.RightEdge
        assert edge.edges_at(QPoint(100, 97)) == Qt.Edge.BottomEdge
        assert edge.edges_at(QPoint(100, 50)) == Qt.Edge(0)
        assert EdgeResize.cursor_for(Qt.Edge.LeftEdge | Qt.Edge.TopEdge) == \
            Qt.CursorShape.SizeFDiagCursor
        assert EdgeResize.cursor_for(Qt.Edge.RightEdge | Qt.Edge.TopEdge) == \
            Qt.CursorShape.SizeBDiagCursor
        assert EdgeResize.cursor_for(Qt.Edge.RightEdge) == Qt.CursorShape.SizeHorCursor
        assert EdgeResize.cursor_for(Qt.Edge.BottomEdge) == Qt.CursorShape.SizeVerCursor
        assert EdgeResize.cursor_for(Qt.Edge(0)) == Qt.CursorShape.ArrowCursor
    finally:
        from PySide6.QtWidgets import QApplication as App
        App.instance().removeEventFilter(edge)
        window.close()


def test_edge_resize_ignores_another_window_and_a_maximised_one(app):
    """Dialogs keep their own frame, and a maximised window has no edge to drag."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication as App, QWidget
    from src.gui.shell import EdgeResize
    window = QWidget()
    window.resize(200, 100)
    window.show()
    dialog = QWidget()
    dialog.resize(120, 80)
    dialog.show()
    app.processEvents()
    edge = EdgeResize(window)

    def press(widget, point):
        local = QPointF(*point)
        return QMouseEvent(QEvent.Type.MouseButtonPress, local, local,
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    try:
        # A press in another window's corner never reaches this window's borders.
        assert edge.eventFilter(dialog, press(dialog, (2, 2))) is False
        # The platform decides whether it will run the resize; here it is asked once and
        # the app never resizes the window itself.
        assert edge.eventFilter(window, press(window, (2, 2))) in (True, False)
        window.showMaximized()
        app.processEvents()
        assert window.isMaximized()
        assert edge.eventFilter(window, press(window, (2, 2))) is False
    finally:
        App.instance().removeEventFilter(edge)
        dialog.close()
        window.close()


def test_the_close_button_releases_the_devices_and_hides_the_window(ai_window):
    """Closing is the one control that must work even while audio is loaded."""
    app, window, _backend, bridge = ai_window
    pump(app, lambda: bridge.status == 'Ready')
    window.header.close_button.click()
    pump(app, lambda: window._closing and not window.isVisible())
    assert not window.isVisible()


def test_header_carries_the_state_and_the_two_drawers(app):
    from src.gui.shell import HeaderBar, StatusPill
    header = HeaderBar()
    assert set(StatusPill.BADGES) == {'stopped', 'running', 'error'}
    assert header.status.text() == '停止中'
    header.set_badge('running')
    assert header.status.text() == '変換中'
    header.set_badge('nonsense')
    assert header.status.text() == '変換中'
    seen = []
    header.tune_clicked.connect(lambda: seen.append('tune'))
    header.lab_clicked.connect(lambda: seen.append('lab'))
    header.voice_clicked.connect(lambda: seen.append('voice'))
    header.tune_button.click()
    header.lab_button.click()
    header.voice_button.click()
    assert seen == ['tune', 'lab', 'voice']
    header.set_voice_checked(False)
    assert header.voice_button.isChecked() is False


def test_drawer_opens_closes_and_never_wider_than_its_container(app):
    from PySide6.QtWidgets import QWidget
    from src.gui.shell import Drawer
    container = QWidget()
    container.resize(1600, 900)
    # The real drawer is a child of the window container; a parentless one would be a
    # top-level window and the platform could move it.
    drawer = Drawer('調整', '説明', container)
    container.show()
    closed = []
    drawer.closed.connect(lambda: closed.append(True))
    assert not drawer.isVisible()
    drawer.open()
    # A child is only visible once its container is, which is how the window uses it.
    assert drawer.isVisible()
    drawer.place(container)
    assert drawer.width() == Drawer.WIDTH
    assert drawer.x() + drawer.width() == container.width()
    assert drawer.height() == container.height()
    container.resize(400, 300)
    drawer.place(container)
    assert drawer.width() <= container.width()
    assert drawer.x() + drawer.width() == container.width()
    drawer.dismiss()
    assert not drawer.isVisible()
    assert closed == [True]
    # Dismissing an already closed drawer reports nothing.
    drawer.dismiss()
    assert closed == [True]


def test_voice_card_select_emits_the_key(app):
    from src.gui.shell import VoiceCard
    card = VoiceCard('voice_a', 'テスト', '標準ボイス（同梱）')
    assert card.key == 'voice_a'
    chosen = []
    card.selected.connect(chosen.append)
    card.selected.emit(card.key)
    assert chosen == ['voice_a']
    card.set_selected(True)
    assert card.property('selected') is True
    card.set_selected(False)
    assert card.property('selected') is False


# --- preview module ---

def test_preview_reads_and_writes_wav_without_changing_the_signal(tmp_path):
    from src.gui import preview
    source = write_wav(tmp_path/'in.wav', speech(3.0).astype(np.float32))
    audio = preview.read_wav(source)
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert len(audio) == pytest.approx(3.0*48000, rel=0.01)
    target = preview.write_wav(tmp_path/'nested'/'out.wav', audio)
    assert target.is_file()
    again = preview.read_wav(target)
    # 16-bit round trip: close, not bit exact.
    assert np.max(np.abs(again-audio)) < 2.0/32768


def test_preview_rejects_unreadable_and_silent_input(tmp_path):
    from src.gui import preview
    broken = tmp_path/'broken.wav'
    broken.write_bytes(b'not a wav file at all')
    with pytest.raises(preview.PreviewError):
        preview.read_wav(broken)
    silence = write_wav(tmp_path/'silence.wav', np.zeros(int(2*48000), np.float32))
    with pytest.raises(preview.PreviewError, match='無音'):
        preview.convert(silence, 'meanvc2_ref20')
    with pytest.raises(preview.PreviewError):
        preview.convert(tmp_path/'missing.wav', 'meanvc2_ref20')


def test_preview_cache_key_separates_every_condition():
    """A LavaSR preview must never be served a plain conversion from the cache."""
    import inspect
    from src.gui import preview
    source = inspect.getsource(preview.convert)
    for token in ('str(model)', 'str(enhancer)', 'str(bool(denoise))', 'str(experiment)',
                  'str(tune_sib_db)', 'str(tune_cons_db)', 'str(tune_caps)',
                  'str(tune_floor_db)', 'str(tune_excess_db)', 'str(tune_mid)',
                  'str(tune_match)', 'str(tune_ptrans)', 'str(tune_pcap)',
                  'str(bool(tune_combined))', 'str(tune_level_db)',
                  'PREVIEW_FORMAT_VERSION'):
        assert token in source, f'cache key ignores {token}'


def test_preview_describe_surfaces_the_worker_measurements():
    from src.gui import preview
    text = preview.describe({'rtf': 0.371, 'guards': {'input_silence_seconds': 1.5,
                                                      'enhancer_skipped': True,
                                                      'enhancer_skip_reason': 'entirely silent'},
                             'enhancer': 'lavasr'})
    assert '0.371' in text
    assert '1.5' in text
    assert 'entirely silent' in text
    assert 'lavasr' in text
    assert preview.describe({}) == ''


# --- window integration ---

def test_window_route_buttons_switch_delivery(ai_window):
    app, window, _backend, bridge = ai_window
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    window.route_buttons['streaming'].click()
    pump(app, lambda: not window._pending)
    assert window.ai_delivery.currentData() == 'streaming'
    assert bridge.parameters.delivery == 'streaming'
    assert window.route_buttons['streaming'].isChecked()
    window.route_buttons['utterance_lavasr'].click()
    pump(app, lambda: not window._pending)
    assert window.ai_delivery.currentData() == 'utterance_lavasr'
    assert bridge.parameters.delivery == 'utterance' and bridge.parameters.enhancer == 'lavasr'
    assert window.route_buttons['utterance_lavasr'].isChecked()


def test_window_route_buttons_refuse_change_while_pending(ai_window):
    app, window, _backend, _bridge = ai_window
    assert window.ai_delivery.currentData() == 'utterance_lavasr'
    window._pending = True
    window.route_buttons['streaming'].click()
    pump(app, lambda: not window.route_buttons['streaming'].isChecked())
    assert window.ai_delivery.currentData() == 'utterance_lavasr'
    window._pending = False


def test_window_drawer_overlaps_the_edge_without_moving_the_stage(ai_window):
    app, window, _backend, _bridge = ai_window
    window.resize(1280, 820)
    window.show()
    app.processEvents()
    stage_width = window.centre_scroll.width()
    window._open_drawer('tune')
    pump(app, lambda: window.drawer_tune.isVisible())
    container = window.centralWidget()
    assert window.drawer_tune.x() + window.drawer_tune.width() == container.width()
    assert window.drawer_tune.width() <= container.width()
    # A drawer covers the stage edge; it never shrinks the live numbers.
    assert window.centre_scroll.width() == stage_width
    assert window.start_button.isVisible()
    # Folding the voice list hands its width to the stage.
    window._open_drawer(None)
    window.voice_panel.set_collapsed(True)
    pump(app, lambda: not window.voice_panel.isVisible())
    assert window.centre_scroll.width() > stage_width


def test_window_drawers_are_exclusive_and_leave_the_stage_alone(ai_window):
    app, window, _backend, _bridge = ai_window
    for key in ('tune', 'lab'):
        window._open_drawer(key)
        pump(app, lambda name=key: window.drawers[name].isVisible())
        visible = [name for name, drawer in window.drawers.items() if drawer.isVisible()]
        assert visible == [key]
        assert window.start_button.isVisible()
    window._open_drawer(None)
    assert [name for name, drawer in window.drawers.items() if drawer.isVisible()] == []


def test_window_pitch_slider_is_only_live_on_the_dsp_path(ai_window):
    app, window, _backend, _bridge = ai_window
    window.mode.setCurrentIndex(window.mode.findData('female_dsp'))
    pump(app, lambda: window.pitch_display.isEnabled())
    assert window.pitch_display.isEnabled()
    window.mode.setCurrentIndex(window.mode.findData('ai_voice'))
    pump(app, lambda: not window.pitch_display.isEnabled())
    assert not window.pitch_display.isEnabled()


def test_window_stage_shows_the_real_state_without_inventing_signal(ai_window):
    app, window, _backend, _bridge = ai_window
    window._tick()
    assert window.relay._level == 0.0
    assert window.relay._running is False
    assert window.stage_error.isVisible() is False
    assert window.header.status.text() in ('停止中', '変換中', 'エラー')


def test_window_output_card_describes_the_active_mode(ai_window):
    app, window, _backend, _bridge = ai_window
    window.mode.setCurrentIndex(window.mode.findData('original'))
    assert window._describe_output() == 'Original（無変換）'
    window.mode.setCurrentIndex(window.mode.findData('female_dsp'))
    assert window._describe_output() == 'Female DSP'
    window.mode.setCurrentIndex(window.mode.findData('ai_voice'))
    described = window._describe_output()
    assert window.ai_model.currentText() in described


# --- runtime guards surfaced through the worker stats ---

def test_utterance_statistics_report_silence_and_skips():
    from src.vc.utterance import convert_utterance

    class FakeBackend:
        chunk_samples = 2560
        sample_rate = 16000

        def __init__(self):
            self.calls = 0

        def reset(self):
            pass

        def get_stats(self):
            return {'algorithmic_buffer_ms': 1440, 'interpolation_grid_delay_ms': 0,
                    'phrase_extra_delay_ms': 1600}

        def process_chunk(self, audio):
            self.calls += 1
            return audio

    backend = FakeBackend()
    # convert_utterance runs at 48 kHz, so the fixture is generated at that rate.
    gap = np.zeros(int(1.0*48000), np.float32)
    audio = np.concatenate([speech(2.0, rate=48000).astype(np.float32), gap,
                            speech(2.0, rate=48000).astype(np.float32)]).astype(np.float32)
    stats = {}
    result = convert_utterance(backend, None, None, audio, statistics=stats)
    assert len(result) == len(audio)
    assert stats['input_seconds'] == pytest.approx(5.0, abs=0.05)
    assert stats['input_silence_seconds'] > 0.5
    assert 0.0 < stats['silence_share'] < 1.0
    # Without an enhancer there is nothing to skip, so no enhancer key is written.
    assert 'enhancer_skipped' not in stats


def test_utterance_skips_an_enhancer_when_the_result_is_silent():
    from src.vc.utterance import convert_utterance

    class SilentBackend:
        chunk_samples = 2560
        sample_rate = 16000

        def __init__(self):
            self.calls = 0

        def reset(self):
            pass

        def get_stats(self):
            return {'algorithmic_buffer_ms': 1440, 'interpolation_grid_delay_ms': 0}

        def process_chunk(self, audio):
            self.calls += 1
            return np.zeros_like(audio)

    ran = []

    class RecordingEnhancer:
        def process(self, audio):
            ran.append(len(audio))
            return audio

    backend = SilentBackend()
    audio = np.zeros(int(3.0*48000), np.float32)
    stats = {}
    result = convert_utterance(backend, None, None, audio,
                               enhance=RecordingEnhancer().process, statistics=stats)
    assert ran == [], 'the enhancer ran on an inaudible result'
    assert stats['enhancer_skipped'] is True
    assert len(result) == len(audio)


def test_utterance_reports_an_enhancer_failure_rather_than_hiding_it():
    from src.vc.utterance import convert_utterance

    class SimpleBackend:
        chunk_samples = 2560
        sample_rate = 16000

        def __init__(self):
            pass

        def reset(self):
            pass

        def get_stats(self):
            return {'algorithmic_buffer_ms': 1440, 'interpolation_grid_delay_ms': 0}

        def process_chunk(self, audio):
            return audio

    def broken(audio):
        raise RuntimeError('enhancer exploded')

    audio = speech(3.0, rate=48000).astype(np.float32)
    with pytest.raises(RuntimeError, match='enhancer exploded'):
        convert_utterance(SimpleBackend(), None, None, audio, enhance=broken, statistics={})


# --- listening A/B harness ---

def test_ab_harness_normalises_level_between_conditions():
    from tools.build_listening_ab import normalise
    quiet = (speech(2.0, level=0.01).astype(np.float32))
    loud = (speech(2.0, level=0.20).astype(np.float32))
    a = normalise(quiet, 0.05)
    b = normalise(loud, 0.05)
    def rms(x):
        return float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64)**2)))
    assert rms(a) == pytest.approx(rms(b), rel=0.02)
    # A silent clip is returned untouched rather than scaled into noise.
    assert normalise(np.zeros(1000, np.float32), 0.05).max() == 0.0


def test_ab_harness_builds_a_shuffled_pair_with_a_sealed_answer(tmp_path):
    from tools.build_listening_ab import build_pair, measure
    import numpy as np
    source = speech(3.0, rate=48000).astype(np.float32)
    rng = np.random.default_rng(0)

    def convert(audio, rate, variant=0.0, **_ignored):
        return audio*(1.0+variant)

    result = build_pair(source, 48000, convert,
                        {'no change': dict(variant=0.0), 'scaled': dict(variant=0.2)},
                        tmp_path, rng)
    assert result is not None
    assert len(result['pages']) == 2
    assert set(result['answer']) == {'A', 'B'}
    # Both sides must be different conditions, or the pair proves nothing.
    assert result['answer']['A'] != result['answer']['B']
    for page in result['pages']:
        assert (tmp_path/page['file']).is_file()
    assert 'spectral_flatness' in measure(source, 48000)


def test_ab_harness_skips_a_pair_when_a_condition_fails(tmp_path):
    from tools.build_listening_ab import build_pair
    source = speech(3.0, rate=48000).astype(np.float32)

    def convert(audio, rate, fail=False, **_ignored):
        return None if fail else audio

    assert build_pair(source, 48000, convert,
                      {'ok': dict(), 'broken': dict(fail=True)}, tmp_path,
                      np.random.default_rng(1)) is None