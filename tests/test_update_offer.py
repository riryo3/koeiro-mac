"""The update offer dialog: the note may be long, the buttons may not be lost.

The bug was a QMessageBox that grew with the release body and pushed the update
button below the screen. These tests hold the two halves of the fix: the note area
is bounded by the screen and scrolls, and the button row belongs to the dialog
rather than to the scrolling body. The markdown cleaning is tested next to it
because the note the dialog shows is the release body itself.
"""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QScrollArea

from src.gui.update_offer import (NOTES_LIMIT, UpdateOfferDialog, notes_height,
                                  plain_notes)

LONG_BODY = "# Koeiro v0.13.0: 声の作り込み\n\n## 🌟 ハイライト\n\n" + \
    "\n\n".join(f"* **機能{i}**\n  本文の説明テキスト。`code` と [リンク](https://example.com/a) を含む。"
                for i in range(120))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_plain_notes_drops_the_markers_keeps_the_words():
    text = plain_notes("# 見出し\n\n**太字** と `コード`\n\n* 箇条書き\n\n"
                       "[GitHub](https://github.com/heynegix/koeiro)\n\n<details>\n<summary>詳細</summary>\n本文\n</details>")
    assert text == '見出し\n\n太字 と コード\n\n・ 箇条書き\n\nGitHub\n\n詳細\n本文'


def test_plain_notes_closes_at_the_limit():
    assert plain_notes('あ' * (NOTES_LIMIT + 500)).endswith('…')
    assert len(plain_notes('あ' * (NOTES_LIMIT + 500))) <= NOTES_LIMIT + 1
    assert plain_notes('') == ''


def test_plain_notes_maps_windows_line_endings():
    assert plain_notes("1行目\r\n2行目\r\n\r\n\r\n3行目") == '1行目\n2行目\n\n3行目'


def test_note_area_is_bounded_by_the_screen(app):
    available = QGuiApplication.primaryScreen().availableGeometry().height()
    dialog = UpdateOfferDialog(tag='v0.13.0', notes=LONG_BODY)
    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None
    assert notes_height(dialog) == scroll.maximumHeight()
    assert scroll.maximumHeight() <= available


def test_buttons_stay_inside_the_dialog_with_a_long_note(app):
    dialog = UpdateOfferDialog(tag='v0.13.0', notes=LONG_BODY,
                               url='https://github.com/heynegix/koeiro/releases/tag/v0.13.0')
    dialog.resize(dialog.sizeHint())
    dialog.show()
    app.processEvents()
    scroll = dialog.findChild(QScrollArea)
    for button in (dialog.update_button, dialog.ignore_button, dialog.later_button):
        top = button.mapTo(dialog, QPoint(0, 0)).y()
        assert 0 <= top, button.text()
        assert top + button.height() <= dialog.height(), button.text()
        # In the dialog's layout, not in the scrolling body the note fills.
        parent = button.parent()
        while parent is not None and parent is not dialog:
            assert not isinstance(parent, QScrollArea), button.text()
            parent = parent.parent()
    available = QGuiApplication.primaryScreen().availableGeometry().height()
    assert dialog.height() <= available
    assert scroll.height() <= scroll.maximumHeight()
    dialog.close()


@pytest.mark.parametrize('pressed,action', [('update', 'update'), ('ignore', 'ignore'),
                                            ('later', 'later')])
def test_each_button_records_its_action(app, pressed, action):
    dialog = UpdateOfferDialog(tag='v0.13.0', notes='本文')

    def decide():  # the click handler runs, but nothing is downloaded or saved
        dialog._choose(action, getattr(dialog, f'{pressed}_button'))

    getattr(dialog, f'{pressed}_button').clicked.connect(decide)
    getattr(dialog, f'{pressed}_button').click()
    assert dialog.action == action


def test_escape_is_later(app):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    dialog = UpdateOfferDialog(tag='v0.13.0', notes='本文')
    dialog.action = 'update'  # a stale choice must not survive Esc
    dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                   Qt.KeyboardModifier.NoModifier))
    assert dialog.action == 'later'


def test_plain_notes_keeps_the_names_it_should(app):
    """Settings keys and paths are identifiers, not emphasis."""
    assert plain_notes('`ai_formant_on` と `models/meanvc2_ref20/runtime.json`') == \
        'ai_formant_on と models/meanvc2_ref20/runtime.json'


def test_missing_notes_say_so(app):
    dialog = UpdateOfferDialog(tag='v0.13.0', notes='')
    from PySide6.QtWidgets import QLabel

    labels = dialog.findChildren(QLabel)
    assert any('（リリースノートなし）' == label.text() for label in labels)
