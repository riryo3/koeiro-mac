"""First-run and on-demand guide: the window dims, one control stays lit.

Each step names the surface it belongs to and the control it talks about, and the guide
walks the real application: it opens that drawer (or the voice list) and draws a window
of light over just that control, with the explanation in one short block beside it. The
reader never has to match a paragraph in a centred dialog against the screen behind it.

Skipping closes the guide and it opens again on the next launch unless
"次回から表示しない" is ticked; the "？ 使い方ガイド" button in the header reopens it at
any time. The guide is a child of the window, so the splash owns the startup moment and
hands over to it when the window is actually visible (see MainWindow.
_schedule_first_run_tutorial).
"""
from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import shell as _shell
from .shell import GUIDE_DIM

# `drawer` is the drawer to open ('tune', 'lab', or None for the stage itself) and
# `target` is the MainWindow attribute to light up. `voice` unfolds the voice list
# first, because a step about picking a voice is useless with the list folded away.
# Each body stays inside three short lines: the ring says where to look, the text only
# says what to do there.
PAGES = (
    dict(title="Koeiro へようこそ",
         drawer=None, target="start_button",
         body="マイクの声を、選んだ声に変えて出力します。相手に届くのは変換後の声だけです。\n"
              "設定は画面中央の3列（配線・変換・詳細）にまとまっています。順に確かめます。"),
    dict(title="① マイクを選ぶ",
         drawer="tune", target="input_device",
         body="ふだん使っているマイクを選びます。足したときは「デバイス一覧を更新」を押します。\n"
              "左のレベルメーターが、話すと緑〜黄色で揺れていれば準備完了です。"),
    dict(title="② 声を選ぶ",
         drawer=None, voice=True, target="voice_panel",
         body="右の「声リスト」から、なりたい声を選びます。名前が分かるときは検索欄へ。\n"
              "自分の声を使うときは「＋ 声を追加」から登録します。"),
    dict(title="② 待つか、待たないか",
         drawer="tune", target="route_box",
         body="逐次は話しながら変換します（帯域復元なし）。一括は話し終えてから変換します。\n"
              "迷ったら一括のままで大丈夫です。あとから変えられます。"),
    dict(title="③ Start して話す",
         drawer=None, target="start_button",
         body="Start で変換を始め、Stop で止めます。右の流れ図（3つの点）を押しても同じです。\n"
              "変換中は「変換」の点だけがシアンになります。"),
    dict(title="困ったときは",
         drawer="tune", target="monitor_toggle",
         body="音が出ないときは Monitor でヘッドホンを選び、テスト音を鳴らします。\n"
              "音が切れるときは Buffer を大きく。分からないときは「推奨設定を適用」へ。"),
)


class TutorialOverlay(QWidget):
    """A dim over the window with one lit control and a short note beside it.

    The overlay is a child of the window's central widget, not a dialog of its own:
    it travels with the application, can never end up over another program, and the
    surface it describes is the surface the reader is looking at. It covers the window
    while it runs (the splash does the same), so a first run cannot start audio by
    accident while the guide talks.
    """

    finished = Signal(bool)
    CARD_WIDTH = 380
    MARGIN = 18
    RING = 3
    PAD = 6

    def __init__(self, host, on_page=None, parent=None):
        super().__init__(parent if parent is not None else host)
        self.host = host
        self.on_page = on_page
        self.setObjectName('guideOverlay')
        self.setVisible(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._index = 0
        self._target = None
        self._target_rect = None
        card = QFrame(self)
        card.setObjectName('guideCard')
        column = QVBoxLayout(card)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName('guideTitle')
        self.title.setWordWrap(True)
        self.body = QLabel()
        self.body.setObjectName('guideBody')
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.title)
        column.addWidget(self.body)
        self.position = QLabel()
        self.position.setObjectName('muted')
        self.position.setWordWrap(True)
        column.addWidget(self.position)   # its own line: beside the buttons it was cut off
        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch(1)
        self.back_button = QPushButton('戻る')
        self.back_button.setObjectName('guideBack')
        self.next_button = QPushButton('次へ')
        self.next_button.setObjectName('guideNext')
        foot.addWidget(self.back_button)
        foot.addWidget(self.next_button)
        column.addLayout(foot)
        tail = QHBoxLayout()
        tail.setSpacing(8)
        self.hide_box = QCheckBox('次回から表示しない')
        tail.addWidget(self.hide_box)
        tail.addStretch(1)
        self.skip_button = QPushButton('スキップ')
        self.skip_button.setObjectName('guideSkip')
        self.skip_button.setToolTip('案内を閉じます。次回の起動でもう一度表示されます。')
        tail.addWidget(self.skip_button)
        column.addLayout(tail)
        card.setFixedWidth(self.CARD_WIDTH)
        self.card = card
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        self.skip_button.clicked.connect(self.skip)

    # --- state the window and the tests read ---

    @property
    def page(self):
        return self._index

    @property
    def pages(self):
        return len(PAGES)

    @property
    def hide_next_time(self):
        return self.hide_box.isChecked()

    @property
    def target_rect(self):
        """The lit rectangle, in this overlay's coordinates (None on a bare step)."""
        return QRect(self._target_rect) if self._target_rect is not None else None

    def light(self, widget):
        """Light one widget of the application and move the note beside it."""
        self._target = widget
        if widget is not None:
            self._scroll_into_view(widget)
        self._reposition()

    @staticmethod
    def _scroll_into_view(widget):
        """Put the control on screen before the ring is placed around it.

        A control inside a drawer scrolls inside that drawer rather than inside the
        stage, so every scrollable ancestor gets a say instead of one named area. A
        ring drawn around an off-screen rectangle lights nothing.
        """
        ancestor = widget.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(widget, 24, 24)
            ancestor = ancestor.parentWidget()

    # --- running the guide ---

    def start(self):
        """Fill the window, light the first control, and take focus."""
        self.setGeometry(self.host.rect())
        self.host.installEventFilter(self)
        self.show()
        self.raise_()
        self.setFocus()
        self._show_page(0)

    def skip(self):
        """Headless/test helper with the same semantics as the Skip button."""
        self._close(False)

    def _show_page(self, index):
        self._index = max(0, min(index, len(PAGES) - 1))
        spec = PAGES[self._index]
        self.title.setText(spec['title'])
        self.body.setText(spec['body'])
        self.position.setText(f'{self._index + 1} / {len(PAGES)}　Enterで次へ・Escで閉じる')
        self.back_button.setEnabled(self._index > 0)
        self.next_button.setText('はじめる' if self._index == len(PAGES) - 1 else '次へ')
        self._target = None
        if callable(self.on_page):
            # The host opens the surface first: the ring can only be placed once the
            # drawer exists at its final geometry, so the host lights the control.
            self.on_page(spec, self)
        # Opening a drawer raises it above everything, including this overlay, so
        # the dim and the note would end up behind the surface they describe.
        # The hole still reveals the control beneath (it is just unpainted space),
        # but only when the overlay paints last.
        self.raise_()
        self._reposition()
        self.update()

    def _reposition(self):
        """Place the ring now, and again while the layout settles, then paint.

        The window can still be resizing (maximise, splash hand-over) when a page opens,
        so one late placement measured a rectangle that moved afterwards; a few
        staggered passes keep the ring on the control.
        """
        self._place()
        for delay in (0, 200, 600):
            QTimer.singleShot(delay, self._place_settled)

    def _place_settled(self):
        if self.isVisible():
            self._place()
            self.update()

    def _place(self):
        host_rect = self.rect()
        target = self._target
        rect = None
        if target is not None and target.isVisible():
            # The overlay is a sibling of the controls, not their ancestor, so mapTo()
            # would answer in the top-level window's frame of reference (off by the
            # title bar on macOS). Go through screen coordinates instead.
            rect = QRect(self.mapFromGlobal(target.mapToGlobal(QPoint(0, 0))), target.size())
        self._target_rect = rect
        card = self.card
        # A word-wrapped label only reports its real height for a given width, so ask the
        # layout for the height at the card's width; adjustSize() alone left the last
        # lines of the text cut off.
        card.setFixedHeight(card.layout().totalHeightForWidth(card.width()))
        card.adjustSize()
        # The card's width is fixed, so its laid-out width is the one to keep clear of
        # the lit rectangle; the hint can be narrower and would overlap it.
        size = card.sizeHint()
        size.setWidth(max(size.width(), card.width()))
        if rect is None:
            x = (host_rect.width() - size.width()) // 2
            y = (host_rect.height() - size.height()) // 2
        else:
            right = rect.right() + self.MARGIN + self.PAD
            left = rect.left() - self.MARGIN - self.PAD - size.width()
            below = rect.bottom() + self.MARGIN + self.PAD
            above = rect.top() - self.MARGIN - self.PAD - size.height()
            if right + size.width() <= host_rect.width() - self.MARGIN:
                x, y = right, rect.top()
            elif left >= self.MARGIN:
                x, y = left, rect.top()
            elif below + size.height() <= host_rect.height() - self.MARGIN:
                x = min(rect.left(), host_rect.width() - size.width() - self.MARGIN)
                x, y = max(self.MARGIN, x), below
            else:
                x, y = rect.left(), above
        x = max(self.MARGIN, min(x, host_rect.width() - size.width() - self.MARGIN))
        y = max(self.MARGIN, min(y, host_rect.height() - size.height() - self.MARGIN))
        card.move(x, y)

    def _close(self, completed):
        self.host.removeEventFilter(self)
        self.hide()
        self.finished.emit(bool(completed))

    def _back(self):
        if self._index > 0:
            self._show_page(self._index - 1)

    def _next(self):
        if self._index >= len(PAGES) - 1:
            self._close(True)
            return
        self._show_page(self._index + 1)

    # --- events ---

    def eventFilter(self, watched, event):
        if watched is self.host and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.host.rect())
            # The window's children are laid out after the resize event, so the
            # control has not moved yet: measure again once they have.
            self._reposition()
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.skip()
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._next()
            return
        if key == Qt.Key.Key_Left:
            self._back()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Everything outside the card belongs to the explanation, not to the app:
        # swallowing the click keeps a first run from switching a setting by accident.
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        lit = self._target_rect
        dim = QColor(*GUIDE_DIM)
        if lit is None:
            painter.fillRect(self.rect(), dim)
            return
        window = QRectF(lit.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD))
        shape = QPainterPath()
        shape.addRect(QRectF(self.rect()))
        cut = QPainterPath()
        cut.addRoundedRect(window, 10, 10)
        painter.fillPath(shape.subtracted(cut), dim)
        pen = QPen(QColor(_shell.LIVE))
        pen.setWidth(self.RING)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(window, 10, 10)
