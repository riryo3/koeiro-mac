"""The update offer: a scrollable note, and buttons that stay on screen.

v0.13.0's release body is about 6,000 characters. A QMessageBox grew with the whole
of it and pushed 「更新して再起動」 below the visible area, so the one action the dialog
exists for could not be clicked. Here the note is a bounded scroll area and the three
buttons live in the dialog's own layout, which is the arrangement the voice
registration dialog already uses for the same reason.

The note arrives as GitHub release markdown. It is rendered as plain text on purpose:
the markers that survive (``#``, ``**``, ``[label](url)``) are the ugly parts, and a
rich-text renderer would fetch remote images the body can reference.
"""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

NOTES_LIMIT = 2000
# 0.4 of the screen, so the title, the note and the button row all fit with room left.
NOTES_SCREEN_FRACTION = 0.4
NOTES_MIN_HEIGHT = 160
NOTES_MAX_HEIGHT = 420

_LINK = re.compile(r'\[([^\]]*)\]\([^)]*\)')
_BR = re.compile(r'<br\s*/?>', re.I)
_TAG = re.compile(r'</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?>')
_HEADING = re.compile(r'^\s{0,3}#{1,6}\s*', re.M)
_BULLET = re.compile(r'^(\s*)[*+-]\s+', re.M)
# Single underscores are left alone: release notes name settings keys and files
# (`ai_formant_on`, `meanvc2_ref20`) far more often than they emphasise with them.
_EMPHASIS = re.compile(r'\*\*|\*|__|`')
_RULE = re.compile(r'^\s*([-*_])\s*(?:\1\s*){2,}$', re.M)
_BLANK = re.compile(r'\n{3,}')


def plain_notes(text, limit=NOTES_LIMIT):
    """Release markdown to readable plain text, capped at ``limit`` characters."""
    body = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    body = _LINK.sub(lambda match: match.group(1), body)
    body = _BR.sub('\n', body)
    body = _TAG.sub('', body)
    body = _RULE.sub('', body)
    body = _HEADING.sub('', body)
    body = _BULLET.sub(lambda match: f'{match.group(1)}・ ', body)
    body = _EMPHASIS.sub('', body)
    body = _BLANK.sub('\n\n', body).strip()
    if len(body) > limit:
        body = body[:limit].rstrip() + '…'
    return body


def notes_height(parent=None):
    """How tall the note may grow on this screen, in pixels."""
    try:
        screen = parent.screen() if parent is not None else QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height()
    except (AttributeError, RuntimeError):
        available = 0
    if available <= 0:
        available = 1080
    return max(NOTES_MIN_HEIGHT, min(NOTES_MAX_HEIGHT, int(available * NOTES_SCREEN_FRACTION)))


class UpdateOfferDialog(QDialog):
    """Update now, ignore this version, or decide later. The buttons never hide."""

    def __init__(self, parent=None, tag='', notes='', url=''):
        super().__init__(parent)
        self.setWindowTitle('アプリの更新')
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setMinimumWidth(520)
        self.action = 'later'
        layout = QVBoxLayout(self)
        heading = QLabel(f'新しいバージョンがあります：{tag}' if tag else '新しいバージョンがあります')
        heading.setObjectName('sectionTitle')
        layout.addWidget(heading)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumHeight(notes_height(self))
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel(plain_notes(notes) or '（リリースノートなし）')
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_layout.addWidget(note)
        if url:
            link = QLabel(f'全文: {url}')
            link.setObjectName('muted')
            link.setWordWrap(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body_layout.addWidget(link)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        # Outside the scroll area: whatever the note says, this row is where it always is.
        row = QHBoxLayout()
        self.update_button = QPushButton('更新して再起動')
        self.update_button.setToolTip('配布ファイルをダウンロードして、更新を適用し再起動します。')
        self.update_button.clicked.connect(lambda: self._choose('update', self.update_button))
        self.ignore_button = QPushButton('このバージョンは無視')
        self.ignore_button.setToolTip('次回以降この版を通知しません。設定に保存されます。')
        self.ignore_button.clicked.connect(lambda: self._choose('ignore', self.ignore_button))
        self.later_button = QPushButton('後で')
        self.later_button.clicked.connect(lambda: self._choose('later', self.later_button))
        row.addWidget(self.update_button)
        row.addWidget(self.ignore_button)
        row.addWidget(self.later_button)
        layout.addLayout(row)

    def _choose(self, action, button):
        self.action = action
        self.accept()

    def keyPressEvent(self, event):
        """Esc means later: the decision is not made by closing the window."""
        if event.key() == Qt.Key.Key_Escape:
            self.action = 'later'
        super().keyPressEvent(event)
