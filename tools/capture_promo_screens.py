"""Capture the real screens the promo video is built from.

The PV uses the shipped UI, not a redrawn mock: each state is reached by driving
the real MainWindow through its own code paths (Start, the two drawers, the saved
route), then grabbed off-screen at 1920x1080 with mock audio devices. No hardware
is opened, so this is a capture, not an audio trial.

Alongside each PNG it writes a hotspot sidecar: where the controls actually are in
that state, in pixels. The video's cursor then lands on the real button instead of
on coordinates guessed from a screenshot, which is what makes "operating the app"
read as true.

Every step is verified before the shutter: a state that silently failed to change
would otherwise be captured as the previous screen, which is exactly the kind of
near-miss a promo must not ship.

    .venv/Scripts/python.exe tools/capture_promo_screens.py --out promo/public/screens
"""
import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

# The mock microphone level the meters are shown at, and how many callback ticks
# to feed. The FakeBackend sends a constant buffer, so the amplitude is chosen
# here; the meter, the relay and the state text are the app's own.
MOCK_INPUT = 0.46
TICKS = 40


def build_window(application, width, height, route=None):
    """The shipped window with mock audio, as the GUI tests and render tools build it.

    `route` is written to the settings before the window is built, so the app wakes
    up on that route the way it does for a returning user. Switching live would test
    the switch, not the screen.

    Discord presence, the update check and the first-run guide stay off in those
    settings: a capture must not talk to the network, and the guide's scrim would
    cover the screen being photographed.
    """
    from src.audio.controller import AudioController
    from src.audio.engine import AudioEngine
    from src.gui.main_window import MainWindow
    from src.processors.ai_voice import AIVoiceProcessor
    from src.processors.chain import ProcessorChain
    from src.processors.voice_router import VoiceRouter
    from src.settings.manager import AppSettings, SettingsManager
    from src.vc.bridge import AIBridge
    from tests.fakes import FakeBackend
    from tests.test_ai_voice import FakeClient

    bridge = AIBridge(client_factory=FakeClient)
    router = VoiceRouter(ai=AIVoiceProcessor(bridge=bridge))
    backend = FakeBackend()
    controller = AudioController(AudioEngine(ProcessorChain(router), backend))
    settings_dir = Path(tempfile.mkdtemp(prefix="koeiro-promo-"))
    manager = SettingsManager(settings_dir / "settings.json")
    settings = replace(AppSettings(), discord_presence=False, app_update_check=False,
                       tutorial_seen=True)
    if route is not None:
        settings = replace(settings, voice_mode=route)
    manager.save(settings)
    window = MainWindow(manager, controller)
    window.show()
    requirement = "the window never became ready"
    if not _pump(application, lambda: window.start_button.isEnabled()):
        raise SystemExit(requirement)
    window.resize(width, height)
    application.processEvents()
    return window, controller, backend, bridge


def _pump(application, predicate, seconds=5.0):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        application.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _require(condition, message):
    """A capture is worthless if the state never arrived, so refuse it loudly."""
    if not condition:
        raise SystemExit(message)


def _run_stream(application, backend, ticks=TICKS):
    """Feed the mock microphone through the running engine so the meters move."""
    for _ in range(ticks):
        stream = backend.streams[-1]
        stream.indata[:] = MOCK_INPUT
        stream.tick()
        application.processEvents()
        time.sleep(0.012)


def _rect(window, widget):
    """The widget's rectangle in window pixels, or None when it is not on screen.

    A control inside a scrolled-away part of a drawer is visible() but not shown,
    so the rectangle must lie inside the window rather than merely exist.
    """
    if widget is None or not widget.isVisibleTo(window):
        return None
    top_left = widget.mapTo(window, QPoint(0, 0))
    x, y, w, h = top_left.x(), top_left.y(), widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return None
    if x < 0 or y < 0 or x + w > window.width() or y + h > window.height():
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def hotspots(window, extra=None):
    """Where the controls are, by name, for the state being captured."""
    widgets = {
        "start": window.start_button,
        "stop": window.stop_button,
        "mode": window.mode,
        "status": window.header.status,
        "voiceList": window.header.voice_button,
        "tune": window.header.tune_button,
        "lab": window.header.lab_button,
        "help": window.header.help_button,
        "relay": window.relay,
        "nameplate": window.nameplate,
        "pitch": window.pitch,
        "voicePanel": window.voice_panel,
        "voiceSearch": window.voice_panel.search,
    }
    widgets.update(extra or {})
    found = {}
    for name, widget in widgets.items():
        rect = _rect(window, widget)
        if rect is not None:
            found[name] = rect
    return found


def capture(application, window, path, action, extra=None):
    """Run the action that reaches the state, then grab the window."""
    action()
    application.processEvents()
    window.grab().save(str(path))
    return hotspots(window, extra=extra)


def drawer_boxes(window, name):
    drawer = window.drawers[name]
    return {"drawer": drawer, "drawerSearch": drawer.search, "drawerIndex": drawer.index_box}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "promo" / "public" / "screens")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    states = {}
    size = [args.width, args.height]

    # The shipped route: stopped, then running, then one drawer at a time. The same
    # window throughout, so the four screens read as one session with the reader.
    window, controller, backend, _bridge = build_window(application, args.width, args.height)
    try:
        states["stage"] = capture(application, window, out_dir / "stage.png", lambda: None)
        _require(not window.stop_button.isEnabled(), "the engine was already running")

        def start():
            window.start_button.click()
            _require(_pump(application, lambda: window.stop_button.isEnabled()),
                     "Start never turned the engine on")
            _run_stream(application, backend)

        states["running"] = capture(application, window, out_dir / "running.png", start)

        def open_tune():
            window._open_drawer("tune")
            application.processEvents()
            _require(window.drawers["tune"].isVisible(), "the tuning drawer did not open")

        states["tune"] = capture(application, window, out_dir / "tune.png", open_tune,
                                 extra=drawer_boxes(window, "tune"))

        def open_lab():
            window._open_drawer("lab")
            application.processEvents()
            _require(window.drawers["lab"].isVisible(), "the experiments drawer did not open")

        states["lab"] = capture(application, window, out_dir / "lab.png", open_lab,
                                extra=drawer_boxes(window, "lab"))
    finally:
        window.close()
        _pump(application, lambda: not controller.alive)

    # The registered voice route, launched on it rather than switched into it.
    window, controller, backend, _bridge = build_window(application, args.width, args.height,
                                                        route="ai_voice")
    try:
        _require(window.mode.currentData() == "ai_voice", "the window did not launch on AI Voice")

        def start_ai():
            window.start_button.click()
            _require(_pump(application, lambda: window.stop_button.isEnabled()),
                     "Start never turned the engine on in AI Voice")
            _require(_pump(application, lambda: window.voice_panel.cards_layout.count() > 0),
                     "the voice list never filled")
            _run_stream(application, backend)

        states["ai_voice"] = capture(application, window, out_dir / "ai_voice.png", start_ai)
    finally:
        window.close()
        _pump(application, lambda: not controller.alive)

    sidecar = out_dir / "hotspots.json"
    sidecar.write_text(json.dumps({"size": size, "states": states}, ensure_ascii=False,
                                  indent=2) + "\n", encoding="utf-8")
    for name, boxes in states.items():
        print(name, sorted(boxes))
    print(f"wrote {len(states)} screens and {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
