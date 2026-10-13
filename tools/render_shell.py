"""Headless render of the new shell so the layout can be inspected as an image.

Qt paints widgets without a visible window when `grab()` is called on an unshown widget,
so this produces a real render of the current stylesheet and geometry rather than a
redrawing of the design by hand.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--width', type=int, default=1520)
    parser.add_argument('--height', type=int, default=980)
    args = parser.parse_args()

    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])

    from src.gui import shell

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

    style = shell.stylesheet(ROOT/'src/gui/assets')
    # Standalone shell render: the header and the stage exactly as the window uses them.
    header = shell.HeaderBar()
    header.setStyleSheet(style)
    header.resize(args.width, 54)
    header.set_badge('running')
    header.grab().save(args.out)
    print('header:', args.out)

    stage = QWidget()
    stage.setStyleSheet(style)
    column = QVBoxLayout(stage)
    column.setContentsMargins(28, 18, 28, 18)
    column.setSpacing(12)
    level = shell.LevelBar(bars=1)
    level.set_level(0.62)
    level_caption = QLabel('入力レベル')
    level_caption.setObjectName('muted')
    column.addWidget(level_caption)
    column.addWidget(level)
    relay = shell.Relay()
    relay.set_state('running')
    relay.set_level(0.62)
    column.addWidget(relay)
    latency = QLabel('26 ms')
    latency.setObjectName('latencyValue')
    column.addWidget(latency)
    stage.resize(args.width, 280)
    stage_path = str(Path(args.out).with_name(Path(args.out).stem+'_stage.png'))
    stage.grab().save(stage_path)
    print('stage:', stage_path)

    rail = shell.VoicePanel()
    rail.setStyleSheet(style)
    rail.resize(330, 620)
    from src.gui.shell import VoiceCard
    for key, name, sub in (('seiren', 'セイレーン', '標準ボイス（同梱）'),
                           ('runa', 'ルナ', '追加した声'),
                           ('kaito', 'カイト', '追加した声')):
        card = VoiceCard(key, name, sub)
        card.set_selected(key == 'seiren')
        rail.cards_layout.addWidget(card)
    rail_path = str(Path(args.out).with_name(Path(args.out).stem+'_panel.png'))
    rail.grab().save(rail_path)
    print('panel:', rail_path)

    # The stage foot: the readiness block on the left, the product mark on the right.
    foot = QWidget()
    foot.setStyleSheet(style)
    foot_row = QHBoxLayout(foot)
    foot_row.setContentsMargins(28, 18, 28, 18)
    readiness = shell.AiReadiness()
    readiness.set_state('loading')
    foot_row.addWidget(readiness, 0, Qt.AlignmentFlag.AlignBottom)
    foot_row.addStretch(1)
    foot_row.addWidget(shell.Nameplate(), 0, Qt.AlignmentFlag.AlignBottom)
    foot.resize(args.width, 120)
    foot_path = str(Path(args.out).with_name(Path(args.out).stem+'_foot.png'))
    foot.grab().save(foot_path)
    print('foot:', foot_path)

    drawer = shell.Drawer('調整', 'マイク、話し方、音量、加工、診断。変更はこの面の中で完結します。')
    drawer.setStyleSheet(style)
    drawer.resize(shell.Drawer.WIDTH, 620)
    drawer.body.addWidget(QLabel('ドロワーの中身は MainWindow が入れる。'))
    drawer.open()
    drawer_path = str(Path(args.out).with_name(Path(args.out).stem+'_drawer.png'))
    drawer.grab().save(drawer_path)
    print('drawer:', drawer_path)


if __name__ == '__main__':
    main()