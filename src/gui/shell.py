"""The shell: one bar, one stage, one voice list, two drawers.

The window has a single permanent surface. The bar carries the engine state, the two
drawer buttons and the window controls, and doubles as the title bar because the OS
frame is not drawn; the stage holds the live numbers, Start and the AI readiness at
its foot; the voice list sits on the right and folds away to zero width. Everything
else lives in a drawer that overlaps from the right, so the stage never gives up room
to a settings panel (DESIGN.md section 4). Every widget the rest of the application
already drives is still built by MainWindow; this module only owns the shell.
"""
from PySide6.QtCore import (QEvent, QLineF, QObject, QPoint, QRect, QRectF, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QCursor, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QComboBox,
                                QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

# Light TENTIAL-derived shell: a blue-tinted page, white cards carrying the
# content, near-black text, one navy accent. Neutrals do the structure work;
# navy marks live conversion, keyboard focus, the running state and the primary
# action. Text gray passes AA on the page, on cards and on pills (see below).
BG = '#eef2f7'
CARD = '#ffffff'
BORDER = '#d4dbe5'
BORDER_DARK = '#9fb0c7'
TEXT = '#18181b'
# Spec secondary #666666 misses AA on pills (4.40:1), so one step darker;
# still the same gray family, and AA everywhere it sits.
TEXT_MUTED = '#606060'
PRIMARY = '#284b7d'
PRIMARY_TEXT = '#ffffff'
LIVE = '#284b7d'
PILL = '#dde1f0'
TRACK = '#d4dbe5'
DANGER = '#dc2626'
# The fill red misses AA as words on the page (4.30:1), so error text uses the
# same hue one step darker, which passes on the page, on cards and on pills.
DANGER_TEXT = '#c51f1f'
# Spec amber #d97706 fails AA as small text, so the warning text is two darker
# amber steps instead; gold stays reserved for one-off badges, never for words.
WARN = '#a34a08'
# One brand navy names every surface (voice list, 調整, 実験, the guide): the
# reference design answers "where am I" with a single colour, and the four-way
# tint system is retired. Navy passes AA as text on the page, on cards and on
# pills (see test_ui_theme.py).
# The guide overlays the window with one thick navy stroke; the dim stays a dark
# veil so the lit control reads on the light page.
GUIDE_DIM = (11, 16, 32, 208)


class LevelBar(QWidget):
    """A 20-bar level meter drawn in-process; no audio work happens on this thread."""

    def __init__(self, parent=None, bars=20, vertical=False):
        super().__init__(parent)
        self.bars = bars
        self.vertical = vertical
        self._levels = [0.0]*bars
        self._peak = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._decay)
        self._timer.start()
        # A compact strip: enough to read a level at a glance, not a wall of bars.
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, value):
        """Feed a 0..1 amplitude.

        The strip shows the newest peak across its width rather than a per-bar history:
        the GUI thread samples at 30 Hz, so a fake per-bar walk would look like signal
        detail that was never measured.
        """
        level = max(0.0, min(1.0, float(value)))
        self._peak = max(self._peak, level)
        for index in range(len(self._levels)):
            self._levels[index] = level*(1.0-0.04*index)

    def set_levels(self, values):
        self._levels = [max(0.0, min(1.0, float(item))) for item in values][:self.bars]
        self.update()

    def _decay(self):
        self._peak *= 0.86
        if self._peak < 0.002:
            self._peak = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor(BG))
        count = len(self._levels) or 1
        gap = 2
        span = (rect.height()-gap*(count-1))/count
        bar_height = max(1, int(span))
        for index, level in enumerate(self._levels):
            y = int(index*(span+gap))
            filled = int(max(0.0, min(1.0, level))*rect.width())
            painter.fillRect(0, y, rect.width(), bar_height, QColor(TRACK))
            if filled:
                painter.fillRect(0, y, filled, bar_height, QColor(LIVE))
        # The newest peak is drawn across the strip so a single reading is visible even
        # though the per-bar history is not sampled at audio rate.
        peak_width = int(max(0.0, min(1.0, self._peak))*rect.width())
        if peak_width > 0:
            painter.fillRect(rect.width()-peak_width, 0, peak_width, rect.height(),
                             QColor('#ffffff'))


class MeterStrip(QWidget):
    """Vertical dB peak meters (input and output) with a scale and peak hold.

    The old strip drew the amplitude on a linear scale, so a healthy -20 dBFS looked
    like an almost empty bar. This one is calibrated in dBFS (-60..0): green is a
    comfortable level, yellow is loud, red is close to clipping. The thin line is the
    peak hold of the last second.
    """

    DB_MIN = -60.0
    TICKS = (0, -6, -12, -18, -24, -36, -48, -60)
    GREEN_TO = -18.0
    YELLOW_TO = -6.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = [0.0, 0.0]
        self._shown = [0.0, 0.0]
        self._hold = [0.0, 0.0]
        self._hold_age = [0, 0]
        self._gate_db = None
        self._out_gate_db = None
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.setMinimumWidth(170)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def _fraction(self, amplitude):
        import math
        amplitude = max(1e-6, float(amplitude))
        decibels = 20.0*math.log10(amplitude)
        return max(0.0, min(1.0, (decibels - self.DB_MIN)/(0.0 - self.DB_MIN)))

    def set_level(self, amplitude):
        self._target[0] = self._fraction(amplitude)

    def set_output_level(self, amplitude):
        self._target[1] = self._fraction(amplitude)

    def set_gate_db(self, decibels):
        """Noise Gate threshold: the input bar below this level is greyed out."""
        self._gate_db = float(decibels)
        self.update()

    def set_output_gate_db(self, decibels):
        """Output gate threshold (None or <= -70: off): the output bar is greyed below it."""
        self._out_gate_db = None if decibels is None or decibels <= -70 else float(decibels)
        self.update()

    def _tick(self):
        for i in (0, 1):
            self._shown[i] = max(self._target[i], self._shown[i] - 0.03)
            if self._target[i] >= self._hold[i]:
                self._hold[i] = self._target[i]
                self._hold_age[i] = 0
            else:
                self._hold_age[i] += 1
                if self._hold_age[i] > 25:
                    self._hold[i] = max(self._target[i], self._hold[i] - 0.02)
        self.update()

    def _y(self, fraction, top, height):
        return int(top + height*(1.0 - fraction))

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        top, bottom = 8, 8
        height = max(10, self.height() - top - bottom)
        scale_width, bar_width, gap = 34, 28, 10
        xs = (scale_width + 6, scale_width + 6 + bar_width + gap)
        green, yellow, red = QColor('#2f9e6f'), QColor('#d9a21b'), QColor(DANGER)
        zones = ((0.0, (self.GREEN_TO - self.DB_MIN)/-self.DB_MIN, green),
                 ((self.GREEN_TO - self.DB_MIN)/-self.DB_MIN,
                  (self.YELLOW_TO - self.DB_MIN)/-self.DB_MIN, yellow),
                 ((self.YELLOW_TO - self.DB_MIN)/-self.DB_MIN, 1.0, red))
        for i, x in enumerate(xs):
            painter.fillRect(x, top, bar_width, height, QColor(TRACK))
            level = self._shown[i]
            for low, high, colour in zones:
                if level <= low:
                    continue
                upper = min(level, high)
                y_top = self._y(upper, top, height)
                y_bottom = self._y(low, top, height)
                painter.fillRect(x, y_top, bar_width, max(1, y_bottom - y_top), colour)
            hold_y = self._y(self._hold[i], top, height)
            if self._hold[i] > 0.0:
                painter.fillRect(x, hold_y, bar_width, 2, QColor(TEXT))
        used_label_y = []
        for index, (gate_db, name) in enumerate(((self._gate_db, '入力ゲート'),
                                                 (self._out_gate_db, '出力ゲート'))):
            if gate_db is None:
                continue
            fraction = max(0.0, min(1.0, (gate_db - self.DB_MIN)/-self.DB_MIN))
            gate_y = self._y(fraction, top, height)
            # Below the threshold the gate keeps the sound out (input) or mutes it (output).
            painter.fillRect(xs[index], gate_y, bar_width, top + height - gate_y,
                             QColor(120, 128, 140, 150))
            painter.fillRect(xs[index], gate_y, bar_width, 1, QColor(TEXT_MUTED))
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawLine(xs[1] + bar_width + 2, gate_y, xs[1] + bar_width + 8, gate_y)
            small = painter.font()
            small.setPointSize(8)
            painter.setFont(small)
            label_y = gate_y - 15
            while any(abs(label_y - other) < 28 for other in used_label_y):
                label_y += 28
            used_label_y.append(label_y)
            painter.drawText(QRect(xs[1] + bar_width + 8, label_y, 70, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            painter.drawText(QRect(xs[1] + bar_width + 8, label_y + 12, 70, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f'{gate_db:.0f}')
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(TEXT_MUTED))
        for tick in self.TICKS:
            y = self._y((tick - self.DB_MIN)/-self.DB_MIN, top, height)
            painter.drawLine(scale_width, y, scale_width + 4, y)
            painter.drawText(QRect(0, y - 7, scale_width - 2, 14),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(tick))


STATUS_BADGES = {
    'stopped': ('停止中', 'stopped'),
    'running': ('変換中', 'running'),
    'error': ('エラー', 'error'),
}


class StatusPill(QLabel):
    """The one mark for the engine state; its colour changes only with the state."""

    BADGES = STATUS_BADGES

    def __init__(self, parent=None):
        super().__init__('停止中', parent)
        self.setObjectName('statusPill')
        self.setProperty('badge', 'stopped')

    def set_badge(self, kind):
        """kind: 'stopped', 'running' or 'error'. Unknown kinds keep the old pill."""
        label, _ = self.BADGES.get(kind, (None, None))
        if label is None:
            return
        self.setText(label)
        self.setProperty('badge', kind)
        self.style().unpolish(self)
        self.style().polish(self)


class WindowButton(QPushButton):
    """A minimise, maximise, restore or close control drawn by this app.

    The glyph is painted instead of typed, so no icon font has to exist on the host:
    the same four shapes appear on Windows and Linux. Hover, focus ring and the close
    button's red hover still come from the shared stylesheet, because the panel is
    drawn by the base class before the lines go on top.
    """

    MINIMIZE = 'minimize'
    MAXIMIZE = 'maximize'
    RESTORE = 'restore'
    CLOSE = 'close'

    WIDTH, HEIGHT = 42, 32

    def __init__(self, glyph, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_glyph(self, glyph):
        if glyph == self._glyph:
            return
        self._glyph = glyph
        self.update()

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(TEXT), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width()/2.0, self.height()/2.0
        if self._glyph == self.MINIMIZE:
            painter.drawLine(QLineF(cx-6, cy, cx+6, cy))
        elif self._glyph == self.MAXIMIZE:
            painter.drawRect(QRectF(cx-6, cy-6, 12, 12))
        elif self._glyph == self.RESTORE:
            painter.drawRect(QRectF(cx-6, cy-3, 9, 9))
            painter.drawLine(QLineF(cx-3, cy-6, cx+6, cy-6))
            painter.drawLine(QLineF(cx+6, cy-6, cx+6, cy+3))
        elif self._glyph == self.CLOSE:
            painter.drawLine(QLineF(cx-5, cy-5, cx+5, cy+5))
            painter.drawLine(QLineF(cx+5, cy-5, cx-5, cy+5))


class HeaderBar(QFrame):
    """Engine state, the two drawers, the guide and the window controls.

    One row, always visible: the state is readable without opening anything, and both
    drawers are one click away from wherever the reader is. The bar doubles as the
    window's title bar, and the product mark lives at the foot of the stage
    (Nameplate), so the first thing on this row is the state, not the logo.
    """

    tune_clicked = Signal()
    lab_clicked = Signal()
    voice_clicked = Signal()
    help_clicked = Signal()
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('headerBar')
        self._drag_from = None
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 6, 6)
        row.setSpacing(8)
        self.status = StatusPill()
        row.addWidget(self.status)
        row.addStretch(1)
        self.voice_button = QPushButton('声リスト')
        self.voice_button.setCheckable(True)
        self.voice_button.setChecked(True)
        self.voice_button.setToolTip('右の声リストを畳みます。畳むとステージが広がります。')
        self.tune_button = QPushButton('調整')
        self.tune_button.setToolTip('マイク・話し方・音量・加工・診断を開きます。')
        self.lab_button = QPushButton('実験')
        self.lab_button.setToolTip('追加機能を開きます（すべて既定OFF）。')
        self.help_button = QPushButton('？ 使い方ガイド')
        self.help_button.setToolTip('使い方ガイドを開きます（何度でも開けます）。')
        # Each button names its surface in the stylesheet, so the bar shows which
        # surface is on screen by tinting just that one button.
        self.voice_button.setObjectName('headerVoice')
        self.tune_button.setObjectName('headerTune')
        self.lab_button.setObjectName('headerLab')
        self.help_button.setObjectName('headerHelp')
        for button in (self.voice_button, self.tune_button, self.lab_button, self.help_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(32)
            row.addWidget(button)
        self.voice_button.clicked.connect(lambda _=False: self.voice_clicked.emit())
        self.tune_button.clicked.connect(lambda _=False: self.tune_clicked.emit())
        self.lab_button.clicked.connect(lambda _=False: self.lab_clicked.emit())
        self.help_button.clicked.connect(lambda _=False: self.help_clicked.emit())
        # The window controls sit last, where the platform puts them: the buttons
        # above them are this app's, the three at the edge belong to the window.
        divider = QFrame()
        divider.setObjectName('headerDivider')
        divider.setFixedSize(1, 20)
        row.addWidget(divider)
        self.minimize_button = WindowButton(WindowButton.MINIMIZE)
        self.minimize_button.setObjectName('windowButton')
        self.minimize_button.setToolTip('最小化します。')
        self.maximize_button = WindowButton(WindowButton.MAXIMIZE)
        self.maximize_button.setObjectName('windowButton')
        self.maximize_button.setToolTip('最大化します。もう一度押すと元のサイズに戻ります。')
        self.close_button = WindowButton(WindowButton.CLOSE)
        self.close_button.setObjectName('windowClose')
        self.close_button.setToolTip('アプリを閉じます（音声デバイスを解放してから終了します）。')
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            row.addWidget(button)
        self.minimize_button.clicked.connect(lambda _=False: self.minimize_clicked.emit())
        self.maximize_button.clicked.connect(lambda _=False: self.maximize_clicked.emit())
        self.close_button.clicked.connect(lambda _=False: self.close_clicked.emit())

    def set_badge(self, kind):
        self.status.set_badge(kind)

    def set_surface_active(self, surface, active):
        """Tint one bar button while its surface is the one on screen.

        `surface` is 'voice', 'tune', 'lab' or 'guide'. Only the active button takes a
        tint, which is why a property is set at all: the surface colours mark where the
        reader is, not what the bar contains.
        """
        buttons = {'voice': self.voice_button, 'tune': self.tune_button,
                   'lab': self.lab_button, 'guide': self.help_button}
        button = buttons.get(surface)
        if button is None:
            return
        if button.property('active') == bool(active):
            return
        button.setProperty('active', bool(active))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def set_voice_checked(self, checked):
        """Mirror the voice list state without re-emitting the click."""
        self.voice_button.blockSignals(True)
        self.voice_button.setChecked(bool(checked))
        self.voice_button.blockSignals(False)

    def set_maximized(self, maximized):
        """Show the glyph that matches the window state, not the last click."""
        self.maximize_button.set_glyph(WindowButton.RESTORE if maximized
                                      else WindowButton.MAXIMIZE)

    def _interactive_at(self, point):
        """True when this point belongs to a control rather than the bar itself."""
        widget = self.childAt(point)
        while widget is not None and widget is not self:
            if isinstance(widget, (QAbstractButton, QLineEdit)):
                return True
            widget = widget.parentWidget()
        return False

    def _start_move(self, event):
        """Ask the platform to move the window, so snapping still works.

        The OS frame is gone, so nothing moves the window on its own any more;
        startSystemMove hands the drag to the platform instead of repositioning the
        window from mouse deltas, which keeps edge snapping and multi-monitor
        behaviour identical to a framed window.
        """
        handle = self.window().windowHandle()
        if handle is None or not handle.startSystemMove():
            return False
        event.accept()
        return True

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._interactive_at(event.position().toPoint())):
            if self._start_move(event):
                return
            # A compositor can refuse the platform move. Losing the drag entirely
            # would leave the window unstuck in place, so follow the pointer instead.
            self._drag_from = (event.globalPosition().toPoint()
                               - self.window().frameGeometry().topLeft())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_from)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_from = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """A double click anywhere on the bar toggles maximise, as the frame did."""
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._interactive_at(event.position().toPoint())):
            self.maximize_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class Relay(QWidget):
    """The three-point relay: input, conversion, output.

    The same three points answer "where is it stuck" everywhere in the app, and only
    one of them is ever emphasised: navy on the conversion point while the engine
    runs, red on the same point when it failed, grey while nothing is measured. The
    input point fills with the measured level; no other part of the shape moves.
    """

    tapped = Signal()
    LABELS = (('入力', 'マイク'), ('変換', 'Koeiro'), ('出力', '通話先'))
    HEIGHT = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('relay')
        self._running = False
        self._error = False
        self._level = 0.0
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('クリックすると Start / Stop を切り替えます。')

    def set_state(self, kind):
        """kind: 'stopped', 'running' or 'error'."""
        self._running = kind == 'running'
        self._error = kind == 'error'
        self.update()

    def set_level(self, value):
        """Feed a 0..1 measured level; only the input point's fill follows it."""
        self._level = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        margin = 44
        radius = 7
        step = ((rect.width() - 2*margin)/(len(self.LABELS) - 1)
                if rect.width() > 2*margin else 0)
        centres = [QPoint(int(margin + index*step), rect.height()//2 - 12)
                   for index in range(len(self.LABELS))]
        painter.setPen(QPen(QColor(TRACK), 2))
        for left, right in zip(centres, centres[1:]):
            painter.drawLine(left, right)
        for index, (label, sub) in enumerate(self.LABELS):
            centre = centres[index]
            if index == 1 and self._error:
                colour = QColor(DANGER)
            elif index == 1 and self._running:
                colour = QColor(LIVE)
            else:
                colour = QColor(TEXT_MUTED)
            filled = index == 1 and (self._running or self._error)
            painter.setBrush(colour if filled else QColor(BG))
            painter.setPen(QPen(colour, 2))
            painter.drawEllipse(centre, radius, radius)
            if index == 0 and self._level > 0:
                painter.setBrush(QColor(LIVE))
                painter.setPen(Qt.PenStyle.NoPen)
                inner = max(1, int(radius*self._level))
                painter.drawEllipse(centre, inner, inner)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        for index, (label, sub) in enumerate(self.LABELS):
            centre = centres[index]
            painter.setPen(QColor(TEXT if index == 1 else TEXT_MUTED))
            painter.drawText(QRect(centre.x()-44, centre.y()+radius+2, 88, 18),
                             Qt.AlignmentFlag.AlignCenter, f'{label}  {sub}')

    def mousePressEvent(self, event):
        self.tapped.emit()
        super().mousePressEvent(event)


class Drawer(QFrame):
    """A surface that overlaps from the right; the caller fills its body.

    A drawer covers the stage edge instead of pushing it aside, so the live numbers
    stay where they were while a setting is being changed. One drawer is open at a
    time; placing it is the owner's job, because only the window knows its own size.

    The drawer finds its own contents: a search box and a jump index are built from
    the groups the caller added, so a surface that grew past one screen can still be
    used without reading all of it. Both work on whole cards, never on the controls
    inside a card, so a filter can never uncover something the current mode hid.
    """

    closed = Signal()
    WIDTH = 520
    MIN_WIDTH = 320
    MAX_INDEX_LABEL = 16

    def __init__(self, title, purpose, parent=None, surface=None):
        super().__init__(parent)
        self.setObjectName('drawer')
        self.setVisible(False)
        self.surface = surface
        self.index_buttons = []
        self._filter_hidden = []
        self._index_linked = False
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        top = QFrame()
        top.setObjectName('drawerTop')
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(18, 12, 14, 12)
        top_row.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName('drawerTitle')
        if surface:
            heading.setProperty('surface', surface)
        top_row.addWidget(heading)
        top_row.addStretch(1)
        self.close_button = QPushButton('閉じる')
        self.close_button.setObjectName('drawerClose')
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip('この引き出しを閉じます。')
        self.close_button.clicked.connect(self.dismiss)
        top_row.addWidget(self.close_button)
        column.addWidget(top)
        head = QWidget()
        head_row = QVBoxLayout(head)
        head_row.setContentsMargins(18, 10, 18, 10)
        head_row.setSpacing(8)
        self.purpose = QLabel(purpose)
        self.purpose.setObjectName('muted')
        self.purpose.setWordWrap(True)
        head_row.addWidget(self.purpose)
        self.search = QLineEdit()
        self.search.setObjectName('drawerSearch')
        self.search.setPlaceholderText('この中を検索（Ctrl+F）')
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip('カードの見出しと中の文字で絞り込みます。空にすると元に戻ります。')
        self.search.textChanged.connect(self.apply_filter)
        head_row.addWidget(self.search)
        self.index_box = QWidget()
        self.index_box.setObjectName('segmentBox')
        # Three across, then wrapping: five long feature names in one row force
        # the whole drawer wider than the window (the lab drawer clipped its
        # right edge for exactly this reason). A grid keeps every name on one
        # tappable chip while the drawer stays 520 px wide.
        self.index_row = QGridLayout(self.index_box)
        self.index_row.setContentsMargins(4, 3, 4, 3)
        self.index_row.setSpacing(2)
        self.INDEX_COLUMNS = 3
        self.index_group = QButtonGroup(self)
        self.index_group.setExclusive(True)
        head_row.addWidget(self.index_box)
        self.search_empty = QLabel('見つかりません。別の言葉で試すか、検索を空にしてください。')
        self.search_empty.setObjectName('muted')
        self.search_empty.setWordWrap(True)
        self.search_empty.setVisible(False)
        head_row.addWidget(self.search_empty)
        column.addWidget(head)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(18, 12, 18, 18)
        self.body.setSpacing(10)
        scroll.setWidget(body)
        column.addWidget(scroll, 1)
        self.scroll = scroll

    def open(self):
        self.setVisible(True)
        self.raise_()

    def as_popup(self, title, width=560, height=820):
        """Open as a window of its own instead of overlapping the main window."""
        self.popup = True
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setVisible(False)

    def closeEvent(self, event):
        # Closed with the window's own button: tell the owner, like dismiss() does.
        if getattr(self, 'popup', False) and self.isVisible():
            self.search.clear()
            self.closed.emit()
        super().closeEvent(event)

    def dock(self, width=440):
        """Become a permanent side panel inside a layout instead of an overlay."""
        self.docked = True
        self.close_button.hide()
        self.purpose.hide()
        self.setFixedWidth(width)
        self.setVisible(True)

    def groups(self):
        """The drawer's named groups in the order shown, each with its cards.

        Body items without a heading (the 実験 master switch, its summary) are not
        groups: the index has no name to show for them and a filter has no card to
        hide, so they stay where they are.
        """
        found = []
        for index in range(self.body.count()):
            widget = self.body.itemAt(index).widget()
            if widget is None or not self._heading_of(widget):
                continue
            if isinstance(widget, Band):
                cards = [widget.body.itemAt(i).widget() for i in range(widget.body.count())]
                found.append([widget, [card for card in cards if card is not None]])
            else:
                found.append([widget, [widget]])
        return found

    @staticmethod
    def _heading_of(widget):
        """The name a group or card shows, which is what the index and search read."""
        for label in widget.findChildren(QLabel):
            if label.objectName() in ('bandTitle', 'stepTitle', 'sectionTitle'):
                if label.parentWidget() is widget or label.parentWidget() is None:
                    return label.text()
        for label in widget.findChildren(QLabel):
            if label.objectName() in ('bandTitle', 'stepTitle', 'sectionTitle'):
                return label.text()
        return ''

    @classmethod
    def _short_label(cls, text):
        """The index shows the group's own name, cut before its explanation."""
        head = text.split('（')[0].split('(')[0].strip()
        if len(head) > cls.MAX_INDEX_LABEL:
            head = head[:cls.MAX_INDEX_LABEL - 1].rstrip() + '…'
        return head

    @staticmethod
    def _card_text(card):
        """Everything a reader can read inside a card, for the search box."""
        parts = [label.text() for label in card.findChildren(QLabel)]
        for combo in card.findChildren(QComboBox):
            parts.extend(combo.itemText(i) for i in range(combo.count()))
            parts.append(combo.currentText())
        return '\n'.join(parts).lower()

    def build_index(self):
        """One jump button per group, plus the scroll link that follows the reader.

        Called by the owner after the drawer is filled: the index is built from what is
        actually there, so a card added later can never be missing from it.
        """
        for button, _group in self.index_buttons:
            self.index_group.removeButton(button)
            self.index_row.removeWidget(button)
            button.deleteLater()
        self.index_buttons = []
        for position, (group, _cards) in enumerate(self.groups()):
            label = self._short_label(self._heading_of(group))
            button = QPushButton(label)
            button.setObjectName('indexJump')
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f'{self._heading_of(group)} へ移動します。')
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(1)
            button.clicked.connect(lambda _checked=False, target=group: self.jump_to(target))
            self.index_group.addButton(button)
            self.index_row.addWidget(button, position // self.INDEX_COLUMNS,
                                     position % self.INDEX_COLUMNS)
            self.index_buttons.append((button, group))
        self.index_box.setVisible(len(self.index_buttons) > 1)
        if not self._index_linked:
            self.scroll.verticalScrollBar().valueChanged.connect(self._sync_index)
            self._index_linked = True
        self._sync_index()

    def _shown(self, widget):
        """True when the drawer itself shows this group.

        `isVisible()` also asks the ancestors, so every button would read as hidden
        while the drawer is closed; `isVisibleTo` asks only about this surface's own
        rules, which is what the filter and the feature switches change.
        """
        return widget.isVisibleTo(self)

    def jump_to(self, group):
        """Scroll so the group's heading sits at the top of the visible area."""
        bar = self.scroll.verticalScrollBar()
        bar.setValue(max(bar.minimum(), min(bar.maximum(), group.y())))

    def _sync_index(self, *_):
        """Mark the group in view, and grey out the ones a filter has taken away."""
        if not self.index_buttons:
            return
        position = self.scroll.verticalScrollBar().value()
        current = 0
        for index, (button, group) in enumerate(self.index_buttons):
            button.setEnabled(self._shown(group))
            if group.y() <= position + 8 and self._shown(group):
                current = index
        for index, (button, _group) in enumerate(self.index_buttons):
            button.setChecked(index == current)

    def apply_filter(self, text):
        """Keep the cards the query matches; a group left with none of them goes away.

        The filter only ever hides. A card this surface already hid (the mode rules, a
        feature switch) is left exactly as it was, so searching can never uncover a
        control the reader's current setup took away.
        """
        query = text.strip().lower()
        for widget in self._filter_hidden:
            widget.setVisible(True)
        self._filter_hidden = []
        if not query:
            self.search_empty.setVisible(False)
            self._sync_index()
            return
        shown = 0
        for group, cards in self.groups():
            if not self._shown(group):
                continue
            named = query in self._heading_of(group).lower()
            keeps = named
            for card in cards:
                if not self._shown(card):
                    continue
                if named or query in self._card_text(card):
                    keeps = True
                else:
                    card.setVisible(False)
                    self._filter_hidden.append(card)
            if keeps:
                shown += len(cards)
            else:
                group.setVisible(False)
                self._filter_hidden.append(group)
        self.search_empty.setVisible(shown == 0)
        self._sync_index()

    def focus_search(self):
        """Keyboard route to the search box (Ctrl+F while this drawer is open)."""
        self.search.setFocus()
        self.search.selectAll()

    def dismiss(self):
        if not self.isVisible():
            return
        # A closed drawer always reopens whole: a filter left behind would hide the
        # setting the reader comes back for.
        self.search.clear()
        self.setVisible(False)
        self.closed.emit()

    def place(self, container):
        """Sit against the container's right edge, never wider than the container."""
        width = min(self.WIDTH, max(self.MIN_WIDTH, container.width()))
        self.setGeometry(container.width() - width, 0, width, container.height())


class VoicePanel(QFrame):
    """Right-hand voice list. Folds away to zero width when the reader asks.

    Picking a voice is the second decision of every session, so the list and its search
    stay one glance away; folding it (header button) hands the whole window to the
    stage for someone who has already chosen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('voicePanel')
        self.setFixedWidth(330)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(10)
        title = QLabel('声リスト')
        title.setObjectName('railTitle')
        layout.addWidget(title)
        search_caption = QLabel('名前で絞り込む')
        search_caption.setObjectName('muted')
        layout.addWidget(search_caption)
        self.search = QLineEdit()
        self.search.setObjectName('voiceSearch')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tabs = {}
        segment = QWidget()
        segment.setObjectName('segmentBox')
        segment_layout = QHBoxLayout(segment)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(2)
        for key, label in (('all', 'すべて'), ('standard', '標準ボイス'),
                           ('user', '追加した声')):
            button = QPushButton(label)
            button.setObjectName('filterTab')
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button)
            segment_layout.addWidget(button)
            self.tabs[key] = button
        self.tabs['all'].setChecked(True)
        tabs.addWidget(segment, 1)
        layout.addLayout(tabs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.cards_layout = QVBoxLayout(body)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.actions_layout = QVBoxLayout()
        self.actions_layout.setSpacing(8)
        layout.addLayout(self.actions_layout)

    def set_collapsed(self, collapsed):
        """Fold to zero width (hidden) so the stage can take the space back."""
        self.setVisible(not collapsed)


class VoiceCard(QFrame):
    """One voice: avatar initial, name, kind and select."""

    selected = Signal(str)

    def __init__(self, key, name, sub, parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName('voiceCard')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        avatar = QLabel((name or '?')[:1])
        avatar.setObjectName('voiceAvatar')
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(avatar)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(name)
        title.setObjectName('presetName')
        caption = QLabel(sub)
        caption.setObjectName('presetDetail')
        caption.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(caption)
        row.addLayout(text, 1)
        choose = QPushButton('選択')
        choose.setObjectName('cardChoose')
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(lambda: self.selected.emit(self.key))
        row.addWidget(choose)
        self.set_selected(False)

    def set_selected(self, selected):
        self.setProperty('selected', bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.selected.emit(self.key)
        super().mousePressEvent(event)


class Band(QFrame):
    """A named group of cards inside a drawer, and the layout those cards go into.

    The three bands of 調整 are asked in the order a session happens: where the sound
    enters and leaves, what it becomes, and what the app remembers. A rule above the
    name keeps the cards below it in one group without giving the band a card of its
    own, so the drawer still reads as a single surface (DESIGN.md section 4).

    The band owns ``body``, the layout its cards are added to. The drawer used to add
    every card to one layout and rely on the build order matching the headings; a card
    built later landed above the heading it belonged to, which read as the app saying
    one thing and showing another. Cards now nest under their own heading and cannot
    drift away from it.
    """

    def __init__(self, number, name, purpose, parent=None, glyph=''):
        super().__init__(parent)
        self.setObjectName('band')
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 26, 0, 4)
        column.setSpacing(6)
        # One glyph per band, ahead of the number: in a 3700px drawer the shape is
        # what the eye lands on first, and the number is what says where it sits in
        # the session (DESIGN.md section 4 A-2).
        title = QLabel(f'{glyph}{number} {name}'.strip() if glyph else f'{number} {name}')
        title.setObjectName('bandTitle')
        column.addWidget(title)
        note = QLabel(purpose)
        note.setObjectName('muted')
        note.setWordWrap(True)
        column.addWidget(note)
        # The drawer's own card rhythm, so a band reads as part of the same surface.
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        column.addLayout(self.body)


class Nameplate(QWidget):
    """The product mark at the foot of the stage: badge, wordmark, nothing else.

    The header no longer carries the name, so identity sits in the room the stage
    leaves over: out of the way of the live numbers, and still there while a drawer is
    open. Both images are committed brand files; when they are missing (a source
    checkout without assets) the name is written out rather than showing an empty box.
    """

    ICON_PX = 34
    LOGO_PX = 36

    @staticmethod
    def _cropped_art(path, pad=4, threshold=24):
        """The wordmark art without its transparent margins.

        The committed file carries wide empty margins (and a soft halo) for
        large print use; at foot size those margins shrink the letters to a
        smudge. Cutting to the alpha bounding box keeps the halo, drops the
        empty surround, and roughly doubles the letter height. Returns None
        when the file has nothing visible in it.
        """
        image = QPixmap(str(path)).toImage()
        # The box is searched on a small copy (a full-res Python pixel walk
        # costs seconds) and mapped back; the pad absorbs the rounding.
        probe = image.scaledToWidth(min(400, image.width()), Qt.TransformationMode.FastTransformation)
        scale = image.width() / probe.width()
        left, top, right, bottom = probe.width(), probe.height(), -1, -1
        for y in range(probe.height()):
            for x in range(probe.width()):
                if probe.pixelColor(x, y).alpha() >= threshold:
                    if x < left:
                        left = x
                    if x > right:
                        right = x
                    if y < top:
                        top = y
                    if y > bottom:
                        bottom = y
        if right < left or bottom < top:
            return None
        left = max(0, int(left * scale) - pad)
        top = max(0, int(top * scale) - pad)
        right = min(image.width() - 1, int((right + 1) * scale) + pad)
        bottom = min(image.height() - 1, int((bottom + 1) * scale) + pad)
        return QPixmap.fromImage(image.copy(left, top, right - left + 1, bottom - top + 1))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('nameplate')
        from .splash import asset_path
        icon_file, logo_file = asset_path('icon.png'), asset_path('logo.png')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        if icon_file is None and logo_file is None:
            fallback = QLabel('Koeiro')
            fallback.setObjectName('plateFallback')
            row.addWidget(fallback)
            return
        if icon_file is not None:
            badge = QLabel()
            badge.setObjectName('plateIcon')
            badge.setPixmap(QPixmap(str(icon_file)).scaledToHeight(
                self.ICON_PX, Qt.TransformationMode.SmoothTransformation))
            row.addWidget(badge)
        if logo_file is not None:
            wordmark = QLabel()
            wordmark.setObjectName('plateLogo')
            art = self._cropped_art(logo_file)
            if art is None:
                art = QPixmap(str(logo_file))
            wordmark.setPixmap(art.scaledToHeight(
                self.LOGO_PX, Qt.TransformationMode.SmoothTransformation))
            row.addWidget(wordmark)


class AiReadiness(QFrame):
    """Whether the AI voice model is ready, stated on the stage itself.

    The words are the shared vocabulary: the window renders them in the big
    stage line, and this frame (kept for the wording and its unit tests) is no
    longer placed anywhere. Every value comes from the bridge, so nothing here
    is a timed animation or an invented percentage: a bar that was not measured
    would be a claim the app cannot back. The words name the state and the
    colour only repeats them, so the state is still readable without colour
    vision.
    """

    TEXT = {
        'stopped': ('未起動', 'Startを押すとモデルを読み込みます。'),
        'loading': ('読み込み中', 'モデルを準備しています。この間は Original で変換します。'),
        'ready': ('準備完了', '選んだ声に変換できます。'),
        'fallback': ('48000 Hz以外', 'Original で動作します。Sample Rateを48000 Hzにしてください。'),
        'unavailable': ('利用できません',
                        'このPCではモデルを読み込めません。Original と Female DSP は使えます。'),
        'error': ('エラー', '「調整」の AI Voice から再読み込みしてください。'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('aiReadiness')
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        caption = QLabel('AIの準備状況')
        caption.setObjectName('muted')
        column.addWidget(caption)
        self.value = QLabel()
        self.value.setObjectName('aiValue')
        column.addWidget(self.value)
        self.note = QLabel()
        self.note.setObjectName('muted')
        self.note.setWordWrap(True)
        # Room for a full sentence on one or two lines; the block stays narrow enough
        # for the smallest window the app allows.
        self.note.setMinimumWidth(320)
        column.addWidget(self.note)
        self.set_state('stopped')

    def state(self):
        return self.value.property('state')

    def set_state(self, kind, detail=None):
        """kind: one of TEXT's keys. ``detail`` replaces that state's note line."""
        if kind not in self.TEXT:
            kind = 'stopped'
        label, note = self.TEXT[kind]
        self.value.setText(label)
        self.note.setText(note if detail is None else detail)
        self.value.setProperty('state', kind)
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


class EdgeResize(QObject):
    """The resize borders and pointer for a window the OS no longer frames.

    With no frame, nothing marks the edge and nothing starts a resize, so this filter
    watches this window's own widgets: near a border it shows the matching pointer, and
    a press there asks the platform to resize, which keeps snapping and multi-monitor
    handling the same as a framed window. Another window's events are never touched, so
    a dialog keeps its own borders, and a maximised window has none to drag.
    """

    MARGIN = 6

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._window.setMouseTracking(True)
        for child in window.findChildren(QWidget):
            # Hover only reaches a widget with tracking on. Widgets built later are
            # switched on at their first Enter event (see eventFilter).
            child.setMouseTracking(True)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

    def edges_at(self, point):
        """Which borders a window-local point is on, as startSystemResize wants them."""
        edges = Qt.Edge(0)
        if point.x() <= self.MARGIN:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self._window.width() - self.MARGIN:
            edges |= Qt.Edge.RightEdge
        if point.y() <= self.MARGIN:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self._window.height() - self.MARGIN:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def cursor_for(edges):
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)
        bottom = bool(edges & Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _edges_under(self, global_point):
        local = self._window.mapFromGlobal(global_point)
        if not self._window.rect().contains(local):
            return Qt.Edge(0)
        return self.edges_at(local)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Enter and isinstance(watched, QWidget):
            watched.setMouseTracking(True)
            return False
        if kind == QEvent.Type.Leave:
            if self._window.rect().contains(self._window.mapFromGlobal(QCursor.pos())):
                return False
            self._window.unsetCursor()
            return False
        if kind not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return False
        if not isinstance(watched, QWidget) or watched.window() is not self._window:
            return False
        try:
            if self._window.isMaximized() or not self._window.isVisible():
                return False
            edges = self._edges_under(event.globalPosition().toPoint())
            if kind == QEvent.Type.MouseMove:
                self._window.setCursor(self.cursor_for(edges))
                return False
            if edges == Qt.Edge(0) or event.button() != Qt.MouseButton.LeftButton:
                return False
            handle = self._window.windowHandle()
            if handle is None or not handle.startSystemResize(edges):
                return False
        except RuntimeError:
            # The window was destroyed while the filter was still installed.
            return False
        return True


def stylesheet(asset_dir):
    """Shared dark-navy theme for the shell; widget-level tweaks stay in main_window."""
    import pathlib
    arrow = (pathlib.Path(asset_dir)/'chevron_dark.svg').as_posix()
    return """
        QWidget { background: %(bg)s; color: %(text)s;
                  font-family: Helvetica, 'neue-haas-grotesk-display', 'Noto Sans JP',
                  YuGothic, 'Yu Gothic', 'Hiragino Kaku Gothic ProN', 'Yu Gothic UI',
                  'Segoe UI', sans-serif; font-size: 13px; font-weight: 500; }
        QLabel, QCheckBox, QWidget#plainRow { background: transparent; }
        /* Headings and buttons speak first (din-2014 where installed, Noto Sans
           JP below it); body text stays in the Helvetica stack. */
        QLabel#drawerTitle, QLabel#bandTitle, QLabel#railTitle, QLabel#presetName,
        QLabel#sectionTitle, QLabel#stepTitle, QLabel#latencyValue, QLabel#aiBanner,
        QLabel#stageVoice, QLabel#guideTitle, QLabel#statusPill, QLabel#title,
        QLabel#plateFallback, QLabel#voiceAvatar, QPushButton {
                  font-family: din-2014, 'Noto Sans JP', YuGothic, 'Yu Gothic',
                  'Hiragino Kaku Gothic ProN', 'Yu Gothic UI', 'Segoe UI', sans-serif; }
        QFrame#headerBar { background: %(card)s; border-bottom: 1px solid %(edge)s; }
        QFrame#headerDivider { background: %(border)s; }
        QPushButton#windowButton, QPushButton#windowClose {
            background: transparent; border: none; border-radius: 6px; padding: 0px; }
        QPushButton#windowButton:hover, QPushButton#windowClose:hover { background: %(pill)s; }
        QPushButton#windowClose:hover { background: %(danger)s; }
        /* After the hover rules on purpose: the id selector would otherwise win and
           hide the keyboard focus ring that every other button gets. */
        QPushButton#windowButton:focus, QPushButton#windowClose:focus {
            background: %(pill)s; border: 1px solid %(live)s; }
        QFrame#stageFoot, QFrame#aiReadiness, QWidget#nameplate { background: transparent; }
        /* A band is a group heading, not a card: the rule above the name is what
           separates it, so a band never looks like one more surface. */
        QFrame#band { background: transparent; border-top: 1px solid %(border)s; }
        QLabel#bandTitle { font-size: 19px; font-weight: 600; color: %(text)s; }
        QLabel#plateFallback { font-size: 15px; font-weight: 600; color: %(muted)s; }
        /* The wordmark is white art for dark grounds: on the light foot it sits
           on a navy chip instead of vanishing into the page. */
        QLabel#plateLogo { background: %(live)s; border-radius: 6px; padding: 2px 6px; }
        /* The stage repeats the same AI state large. Same tokens as the foot's
           readout, one size step up from the card headings, so the state reads
           across the room without inventing a colour. */
        QLabel#aiBanner { font-size: 16px; font-weight: 600; color: %(muted)s; }
        QLabel#aiBanner[state="loading"] { color: %(live)s; }
        QLabel#aiBanner[state="ready"] { color: %(text)s; }
        QLabel#aiBanner[state="fallback"], QLabel#aiBanner[state="unavailable"] {
            color: %(warn)s; }
        QLabel#aiBanner[state="error"] { color: %(danger_text)s; }
        /* The live voice and route on the stage: one step below the AI banner so
           the two never compete, same text token, nothing else. */
        QLabel#stageVoice { font-size: 14px; font-weight: 600; color: %(text)s; }
        QFrame#drawer { background: %(card)s; border-left: 2px solid %(border)s; }
        QFrame#drawerTop { background: %(card)s; border-bottom: 1px solid %(border)s; }
        QLabel#drawerTitle { font-size: 17px; font-weight: 600; color: %(live)s; }
        QPushButton#drawerClose { padding: 6px 12px; }
        /* The header button borrows the brand navy only while that surface is the
           one on screen, so the bar never turns into a row of colours. */
        QPushButton#headerVoice[active="true"] { color: %(live)s; border-color: %(live)s; }
        QPushButton#headerTune[active="true"] { color: %(live)s; border-color: %(live)s; }
        QPushButton#headerLab[active="true"] { color: %(live)s; border-color: %(live)s; }
        QPushButton#headerHelp[active="true"] { color: %(live)s; border-color: %(live)s; }
        /* The guide paints its own dim, so the overlay must not paint a page behind it. */
        QWidget#guideOverlay { background: transparent; }
        QFrame#guideCard { background: %(card)s; border: 1px solid %(live)s;
                           border-radius: 12px; }
        QLabel#guideTitle { font-size: 15px; font-weight: 600; color: %(live)s; }
        QLabel#guideBody { font-size: 13px; color: %(text)s; }
        QPushButton#guideNext { background: %(primary)s; border-color: %(primary)s;
                                color: %(primary_text)s; font-weight: 600; padding: 8px 22px;
                                border-radius: 20px; }
        QPushButton#guideNext:focus { border-color: %(live)s; }
        QPushButton#guideBack { padding: 8px 16px; }
        QPushButton#guideSkip { background: transparent; border: none; color: %(muted)s;
                                padding: 6px 8px; }
        QPushButton#guideSkip:hover { color: %(text)s; }
        QLineEdit#drawerSearch { font-size: 12px; padding: 6px 8px; border-radius: 4px; }
        QPushButton#indexJump { background: transparent; border: none; border-radius: 7px;
                                padding: 6px 8px; color: %(muted)s; font-size: 12px; }
        QPushButton#indexJump:hover { color: %(text)s; }
        QPushButton#indexJump:checked { background: %(live)s; color: #ffffff; font-weight: 600; }
        QPushButton#indexJump:disabled { color: %(border_dark)s; }
        QLabel#latencyValue { font-size: 18px; font-weight: 600; color: %(text)s; }
        QLabel#stageError { color: %(warn)s; font-size: 12px; }
        QFrame#emptyState { background: %(card)s; border: 1px solid %(border)s;
                            border-radius: 12px; }
        QLabel#statusPill { font-size: 12px; font-weight: 600; padding: 5px 12px;
                            border-radius: 11px; }
        QLabel#statusPill[badge="stopped"] { background: %(pill)s; color: %(muted)s; }
        QLabel#statusPill[badge="running"] { background: %(live)s; color: %(bg)s; }
        QLabel#statusPill[badge="error"] { background: %(danger)s; color: #ffffff; }
        QFrame#voicePanel { background: %(bg)s; border-left: 1px solid %(edge)s; }
        QLabel#railTitle { font-size: 17px; font-weight: 600; color: %(live)s; }
        QLineEdit#voiceSearch { font-size: 13px; border-radius: 4px; }
        QWidget#segmentBox { background: %(pill)s; border-radius: 10px; }
        QPushButton#filterTab { background: transparent; border: none;
                                border-radius: 7px; padding: 6px 4px; color: %(muted)s; font-size: 12px; }
        QPushButton#filterTab:hover { color: %(text)s; }
        QPushButton#filterTab:checked { background: %(live)s; color: #ffffff; font-weight: 600; }
        QFrame#voiceCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 12px; }
        QFrame#voiceCard:hover { border-color: %(border_dark)s; }
        QFrame#voiceCard[selected="true"] { border: 2px solid %(live)s; }
        QLabel#voiceAvatar { background: %(pill)s; border-radius: 20px; font-size: 18px;
                             font-weight: 600; color: %(muted)s; }
        QPushButton#cardChoose { padding: 8px 12px; }
        QLabel#presetName { font-size: 14px; font-weight: 600; }
        QLabel#presetDetail { color: %(muted)s; font-size: 11px; }
        QPushButton#routeButton { background: transparent; border: none;
                                  border-radius: 7px; padding: 10px 6px; font-weight: 600;
                                  color: %(muted)s; }
        QPushButton#routeButton:hover { color: %(text)s; }
        QPushButton#routeButton:checked { background: %(live)s; color: #ffffff; }
        QLabel#muted { color: %(muted)s; font-size: 12px; }
        QLabel#title { font-size: 22px; font-weight: 600; }
        QLabel#sectionTitle { font-size: 16px; font-weight: 600; color: %(text)s; }
        QFrame#outputCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 12px; }
        QFrame#pitchRow { background: transparent; }
        QFrame#transportBar { background: %(bg)s; border-top: 1px solid %(edge)s; }
        QLineEdit { background: #f6fafe; border: 1px solid %(border_dark)s; border-radius: 8px; padding: 8px; }
        QComboBox, QPushButton { background: %(pill)s; border: 1px solid %(border_dark)s;
                                 border-radius: 8px; padding: 7px; color: %(text)s; }
        QComboBox { padding-right: 26px; }
        QComboBox::drop-down { width: 22px; border: none; }
        QComboBox::down-arrow { image: url(__ARROW__); width: 12px; height: 8px; }
        QComboBox QAbstractItemView { background: %(card)s; border: 1px solid %(border_dark)s;
                                      selection-background-color: %(pill)s; selection-color: %(text)s; }
        QPushButton:hover { border-color: %(live)s; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus { border-color: %(live)s; }
        QCheckBox { spacing: 8px; color: %(text)s; border: 1px solid transparent; border-radius: 4px; }
        QCheckBox:focus { border-color: %(live)s; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(border_dark)s;
                               border-radius: 4px; background: %(bg)s; }
        QCheckBox::indicator:checked { background: %(live)s; border-color: %(live)s; }
        QSlider { border: 1px solid transparent; border-radius: 4px; }
        QSlider:focus { border-color: %(live)s; }
        QPushButton#start { background: %(primary)s; border-color: %(primary)s; color: %(primary_text)s;
                            font-weight: 600; padding: 10px 26px; border-radius: 8px; }
        QPushButton#start:focus { border-color: %(live)s; }
        QPushButton#start:disabled { background: %(pill)s; color: #9aa3b2; border-color: %(pill)s; }
        /* Anything that cannot be used right now is washed out, not just a bit lighter. */
        QPushButton:disabled { background: #f3f5f8; color: #b4bcc9; border-color: #e3e8ef; }
        QComboBox:disabled { background: #f3f5f8; color: #b4bcc9; border-color: #e3e8ef; }
        QLineEdit:disabled { background: #f3f5f8; color: #b4bcc9; border-color: #e3e8ef; }
        QCheckBox:disabled { color: #b4bcc9; }
        QSlider::groove:horizontal:disabled { background: #e8ecf2; }
        QSlider::handle:horizontal:disabled { background: #f3f5f8; border-color: #e3e8ef; }
        QPushButton#scrollHint { background: %(card)s; color: %(live)s; border: 1px solid %(live)s;
                                 border-radius: 16px; padding: 0px; font-size: 16px; font-weight: 600; }
        QPushButton#scrollHint:hover { background: %(live)s; color: #ffffff; }
        QPushButton#stop { padding: 10px 22px; border-radius: 8px; }
        QLabel#warningText { color: %(warn)s; font-size: 12px; }
        QLabel#stepTitle { color: %(text)s; font-size: 16px; font-weight: 600; }
        /* Long explanations inside drawer cards read at body size, not caption
           size: the 12px muted stays for one-line captions outside cards. */
        QFrame#stepCard QLabel#muted, QFrame#outputCard QLabel#muted { font-size: 13px; }
        QFrame#stepCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 12px; }
        *[guide="true"] { border: 2px solid %(live)s; border-radius: 8px; }
        QTabWidget::pane { border: 1px solid %(border)s; border-radius: 10px; background: %(card)s; }
        QTabBar::tab { padding: 8px 12px; color: %(muted)s; }
        QTabBar::tab:selected { color: %(text)s; background: %(card)s; }
        QSlider::groove:horizontal { background: %(track)s; height: 5px; border-radius: 2px; }
        QSlider::handle:horizontal { background: #ffffff; border: 1px solid %(border_dark)s;
                                     width: 16px; margin: -6px 0; border-radius: 8px; }
        QProgressBar { border: none; background: %(track)s; border-radius: 4px; height: 10px; }
        QProgressBar::chunk { background: %(live)s; border-radius: 4px; }
        QCheckBox { spacing: 8px; color: %(text)s; }
        QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
        QScrollBar::handle:vertical { background: %(border_dark)s; border-radius: 4px; min-height: 30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
        QScrollBar::handle:horizontal { background: %(border_dark)s; border-radius: 4px; min-width: 30px; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QToolTip { background: %(primary)s; color: %(primary_text)s; border: none; padding: 5px; }
    """.replace('__ARROW__', arrow) % {
        'bg': BG, 'edge': BORDER, 'text': TEXT, 'muted': TEXT_MUTED,
        'primary': PRIMARY, 'primary_text': PRIMARY_TEXT, 'live': LIVE,
        'pill': PILL, 'track': TRACK, 'card': CARD, 'border': BORDER,
        'border_dark': BORDER_DARK, 'danger': DANGER, 'danger_text': DANGER_TEXT,
        'warn': WARN}


class ErrorDialog(QFrame):
    """Error details in a window of their own: selectable text and a copy button.

    The old red line sat at the top of the stage, pushed the gauges down and could
    not be selected. This is a separate, non-modal window, so the stage keeps its
    shape and the whole text (cause, fix, device and setting details) can be copied.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout
        self.setWindowTitle('エラー')
        self.resize(640, 420)
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(10)
        title = QLabel('エラーが発生しました')
        title.setObjectName('sectionTitle')
        column.addWidget(title)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        column.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton('すべてコピー')
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        close = QPushButton('閉じる')
        close.clicked.connect(self.close)
        row.addWidget(close)
        column.addLayout(row)

    def _copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_button.setText('コピーしました')
        QTimer.singleShot(1500, lambda: self.copy_button.setText('すべてコピー'))

    def show_text(self, text):
        self.text.setPlainText(text)
        self.copy_button.setText('すべてコピー')
        self.show()
        self.raise_()


class ScrollHints(QObject):
    """Round ↑ / ↓ buttons over a scroll area when more content lies out of view.

    A tall column can run past the bottom of a small screen without any sign of it.
    The arrows appear only while there is something above or below, and a click
    scrolls by most of a page.
    """

    def __init__(self, scroll_area):
        super().__init__(scroll_area)
        from PySide6.QtWidgets import QPushButton
        self.area = scroll_area
        viewport = scroll_area.viewport()
        self.up = QPushButton('↑', viewport)
        self.down = QPushButton('↓', viewport)
        for button, step in ((self.up, -1), (self.down, 1)):
            button.setObjectName('scrollHint')
            button.setFixedSize(32, 32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip('まだ上に項目があります。' if step < 0 else 'まだ下に項目があります。')
            button.clicked.connect(lambda _=False, s=step: self._page(s))
            button.hide()
        bar = scroll_area.verticalScrollBar()
        bar.valueChanged.connect(self.refresh)
        bar.rangeChanged.connect(self.refresh)
        viewport.installEventFilter(self)
        QTimer.singleShot(0, self.refresh)

    def _page(self, direction):
        bar = self.area.verticalScrollBar()
        bar.setValue(bar.value() + direction*int(self.area.viewport().height()*0.8))

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.refresh()
        return False

    def refresh(self, *_):
        bar = self.area.verticalScrollBar()
        viewport = self.area.viewport()
        width, height = viewport.width(), viewport.height()
        x = (width - 32)//2
        self.up.move(x, 8)
        self.down.move(x, max(0, height - 32 - 8))
        self.up.setVisible(bar.maximum() > 0 and bar.value() > bar.minimum() + 4)
        self.down.setVisible(bar.maximum() > 0 and bar.value() < bar.maximum() - 4)
        self.up.raise_()
        self.down.raise_()

