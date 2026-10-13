import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from src.gui.tutorial import PAGES, TutorialOverlay
from tests.test_ai_gui import ai_window, pump  # noqa: F401  (ai_window is used as a fixture)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _overlay(window):
    """A guide attached to the real window, as the app builds it."""
    overlay = TutorialOverlay(window.centralWidget(), on_page=window._guide_page)
    overlay.start()
    window.show()
    for _ in range(20):
        QApplication.processEvents()
    return overlay


def _settle(app, window):
    pump(app, lambda: window.isVisible())
    for _ in range(20):
        app.processEvents()


def test_guide_has_six_short_steps(qapp):
    assert len(PAGES) == 6
    for spec in PAGES:
        lines = [line for line in spec['body'].split('\n') if line.strip()]
        # The ring says where to look; the text only says what to do there.
        assert 0 < len(lines) <= 3, (spec['title'], lines)
        assert len(spec['title']) <= 20, spec['title']


def test_the_guide_dims_everything_except_the_control_it_names(ai_window):
    app, window, backend, bridge = ai_window
    _settle(app, window)
    overlay = _overlay(window)
    try:
        lit = overlay.target_rect
        assert lit is not None and lit.width() > 40 and lit.height() > 10
        image = overlay.grab().toImage()
        # Inside the lit window the app shows through untouched.
        inside = image.pixelColor(lit.center())
        assert inside.alpha() == 0, inside.alpha()
        # Away from it the window is dimmed, not covered.
        corner = image.pixelColor(QPoint(4, overlay.height() - 4))
        assert corner.alpha() > 150, corner.alpha()
        assert corner.alpha() < 255
    finally:
        overlay.skip()
        window.close()


def test_the_note_sits_beside_the_control_and_never_on_top_of_it(ai_window):
    app, window, backend, bridge = ai_window
    _settle(app, window)
    overlay = _overlay(window)
    try:
        for _index, _spec in enumerate(PAGES):
            lit = overlay.target_rect
            card = overlay.card.geometry()
            assert overlay.rect().contains(card), card
            if lit is not None:
                assert not card.intersects(lit), (card, lit)
            overlay.next_button.click()
            app.processEvents()
    finally:
        overlay.skip()
        window.close()


def _widget_rect(widget, overlay):
    """The widget's rectangle in the overlay's coordinates."""
    from PySide6.QtCore import QRect
    return QRect(widget.mapTo(overlay, QPoint(0, 0)), widget.size())


def test_guide_walks_the_window_and_lights_each_control(ai_window):
    app, window, backend, bridge = ai_window
    _settle(app, window)
    overlay = _overlay(window)
    try:
        for index, spec in enumerate(PAGES):
            while overlay.page < index:
                overlay.next_button.click()
                app.processEvents()
            expected = spec.get('drawer')
            assert window._active_drawer == expected, spec['title']
            for key, drawer in window.drawers.items():
                assert drawer.isVisible() == (key == expected), spec['title']
            target = spec.get('target')
            if target and getattr(window, target).isVisible():
                lit = overlay.target_rect
                widget = getattr(window, target)
                assert lit is not None, spec['title']
                assert lit.contains(_widget_rect(widget, overlay)), spec['title']
    finally:
        overlay.skip()
        window.close()


def test_navigation_buttons_and_skip(ai_window):
    app, window, backend, bridge = ai_window
    _settle(app, window)
    finished = []
    overlay = _overlay(window)
    overlay.finished.connect(finished.append)
    try:
        assert overlay.page == 0
        assert not overlay.back_button.isEnabled()
        assert overlay.next_button.text() == '次へ'
        overlay.next_button.click()
        app.processEvents()
        assert overlay.page == 1
        overlay.back_button.click()
        app.processEvents()
        assert overlay.page == 0
        assert not finished
        # Skip closes without remembering, and the signal carries the choice.
        overlay.skip_button.click()
        app.processEvents()
        assert finished == [False]
        assert not overlay.isVisible()
    finally:
        overlay.deleteLater()
        window.close()


def test_the_last_step_finishes_and_the_newer_keys_work(ai_window):
    app, window, backend, bridge = ai_window
    _settle(app, window)
    finished = []
    overlay = _overlay(window)
    overlay.finished.connect(finished.append)
    try:
        for _ in range(len(PAGES) - 1):
            overlay.next_button.click()
            app.processEvents()
        assert overlay.page == len(PAGES) - 1
        assert overlay.next_button.text() == 'はじめる'
        # Escape skips, the arrow keys move: no mouse needed.
        overlay.next_button.click()
        app.processEvents()
        assert finished == [True]
    finally:
        overlay.deleteLater()
        window.close()

    overlay = _overlay(window)
    try:
        overlay.keyPressEvent(_key_event(Qt.Key.Key_Right))
        assert overlay.page == 1
        overlay.keyPressEvent(_key_event(Qt.Key.Key_Left))
        assert overlay.page == 0
        overlay.keyPressEvent(_key_event(Qt.Key.Key_Escape))
        assert not overlay.isVisible()
    finally:
        overlay.deleteLater()
        window.close()


def _key_event(key):
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def test_next_is_the_bright_one_and_back_is_plain(ai_window):
    """The two buttons are told apart by fill, not only by label."""
    from PySide6.QtGui import QColor
    from src.gui.shell import PILL, PRIMARY
    from tests.fakes import dominant_colour
    app, window, backend, bridge = ai_window
    _settle(app, window)
    overlay = _overlay(window)
    try:
        forward = QColor(dominant_colour(overlay.next_button.grab().toImage()))
        back = QColor(dominant_colour(overlay.back_button.grab().toImage()))
        assert forward.name().lower() == PRIMARY.lower(), forward.name()
        assert back.name().lower() == PILL.lower(), back.name()
        # Navy fill against a light pill: told apart by lightness either way.
        assert back.lightness() - forward.lightness() > 100
    finally:
        overlay.skip()
        window.close()


def test_tutorial_seen_roundtrip():
    from src.settings.manager import AppSettings
    assert AppSettings().tutorial_seen is False
    assert AppSettings.from_dict({"tutorial_seen": True}).tutorial_seen is True
    assert AppSettings.from_dict({"tutorial_seen": "yes"}).tutorial_seen is False


def test_monitor_settings_roundtrip():
    from src.settings.manager import AppSettings
    assert AppSettings().monitor is False
    assert AppSettings().monitor_device is None
    assert AppSettings().monitor_volume_db == 0.0
    values = AppSettings.from_dict({"monitor": True, "monitor_volume_db": -9.5,
                                    "monitor_device": {"name": "HP", "host_api": "X"}})
    assert values.monitor is True
    assert values.monitor_device == {"name": "HP", "host_api": "X"}
    assert values.monitor_volume_db == -9.5
    assert AppSettings.from_dict({"monitor": "yes"}).monitor is False
    assert AppSettings.from_dict({"monitor_volume_db": 99}).monitor_volume_db == 0.0
    assert AppSettings.from_dict({"monitor_volume_db": "loud"}).monitor_volume_db == 0.0
    params = values.ai_parameters()
    assert params is not None


def test_first_run_tutorial_marks_seen(ai_window, monkeypatch):
    """A reader who finishes (or hides) the guide does not see it again."""
    from src.gui import tutorial as tutorial_module
    app, window, backend, bridge = ai_window
    calls = []
    real = tutorial_module.TutorialOverlay

    class StubOverlay(real):
        def __init__(self, host, on_page=None, parent=None):
            calls.append(host)
            super().__init__(host, on_page=on_page, parent=parent)
            self.hide_box.setChecked(True)

        def start(self):
            super().start()
            self._close(True)

    monkeypatch.setattr(tutorial_module, "TutorialOverlay", StubOverlay)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert window.settings.tutorial_seen is False
    window._maybe_show_tutorial()
    assert calls
    assert window.settings.tutorial_seen is True
    assert window._guide_open is False


def test_no_tutorial_when_already_seen(ai_window, monkeypatch):
    from dataclasses import replace
    from src.gui import tutorial as tutorial_module
    app, window, backend, bridge = ai_window
    window.settings = replace(window.settings, tutorial_seen=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("tutorial must not open")

    monkeypatch.setattr(tutorial_module, "TutorialOverlay", forbidden)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    window._maybe_show_tutorial()


def test_first_run_guide_skip_keeps_it_for_the_next_launch(ai_window, monkeypatch):
    """Skipping closes the guide without remembering it; hiding remembers it."""
    from src.gui import tutorial as tutorial_module
    app, window, backend, bridge = ai_window
    real = tutorial_module.TutorialOverlay

    class StubOverlay(real):
        def start(self):
            super().start()
            self.skip()

    monkeypatch.setattr(tutorial_module, "TutorialOverlay", StubOverlay)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    window._maybe_show_tutorial()
    assert window.settings.tutorial_seen is False
    assert window._guide_open is False


def test_the_guide_button_lives_in_the_header(ai_window):
    from PySide6.QtWidgets import QPushButton
    app, window, backend, bridge = ai_window
    window.resize(1200, 820)
    window.show()
    app.processEvents()
    button = window.help_button
    assert button is window.header.help_button
    assert button.isEnabled() and button.isVisible()
    # No floating corner button any more: the header is the one entry point.
    assert window.centralWidget().findChild(QPushButton, 'helpFab') is None


def test_closing_the_guide_clears_the_overlay_and_keeps_it_for_next_launch(ai_window, monkeypatch):
    from src.gui import tutorial as tutorial_module
    app, window, backend, bridge = ai_window
    real = tutorial_module.TutorialOverlay

    class Scripted(real):
        """A reader who turns three pages and then closes the guide."""

        def start(self):
            super().start()
            for _ in range(4):
                self.next_button.click()
                QApplication.processEvents()
            self.skip()

    monkeypatch.setattr(tutorial_module, 'TutorialOverlay', Scripted)
    window._show_tutorial()
    assert window._guide_open is False
    assert getattr(window, '_guide_overlay', None) is None
    assert window.settings.tutorial_seen is False
    # The bar stops marking the guide as the surface on screen.
    assert window.header.help_button.property('active') is not True


def test_default_voice_shows_as_the_app_standard(ai_window):
    from src.vc.voice_library import DEFAULT_VOICE_ID, DEFAULT_VOICE_NAME
    app, window, backend, bridge = ai_window
    assert window.ai_model.itemData(0) == DEFAULT_VOICE_ID
    window.ai_model.setCurrentIndex(0)
    window._update_voice_info()
    assert DEFAULT_VOICE_NAME in window.voice_hint.text()
    assert "アプリ標準の声" in window.voice_hint.text()
    assert "登録済み" not in window.voice_hint.text()
    # Thread count still applies to the standard voice; the fixed processing chunk does not.
    assert window.ai_threads.isEnabled()
    assert not window.ai_quality.isEnabled()


def _near(first, second, tolerance=10):
    return all(abs(first[i] - second[i]) <= tolerance for i in range(3))


def test_the_note_stays_above_the_drawer_it_describes(ai_window):
    """A drawer step must not bury the guide: the card paints last.

    Opening a drawer raises it above everything, including the guide overlay,
    so the dim and the note ended up behind the surface they describe. The
    overlay now re-raises itself after each page: the card's navy edge must be
    visible in the composited window on every step, drawer steps included.
    """
    from PySide6.QtGui import QColor
    app, window, backend, bridge = ai_window
    _settle(app, window)
    overlay = _overlay(window)
    try:
        edge = QColor('#284b7d')
        for index, spec in enumerate(PAGES):
            while overlay.page < index:
                overlay.next_button.click()
                app.processEvents()
            app.processEvents()
            image = window.grab().toImage()
            card = overlay.card.geometry()
            left = card.left() + card.width() // 4
            right = card.left() + card.width() * 3 // 4
            found = False
            for dx in range(left, right + 1):
                for dy in (card.top() - 1, card.top(), card.top() + 1):
                    point = overlay.mapTo(window, QPoint(dx, dy))
                    if not image.rect().contains(point):
                        continue
                    pixel = image.pixelColor(point)
                    if _near((pixel.red(), pixel.green(), pixel.blue()),
                             (edge.red(), edge.green(), edge.blue())):
                        found = True
                        break
                if found:
                    break
            assert found, (spec['title'], card)
    finally:
        overlay.skip()
        window.close()
