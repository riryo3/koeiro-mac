"""Run the shipped window on the real screen, driven by real clicks, for the PV take.

OBS records this window. Two engine choices:

- ``--live`` runs the app's real audio route: this machine's own microphone in, the
  virtual cable out, the real AI worker loading the shipped voice. This is what a
  take uses, because a take whose status pill reads "エラー" is not a take.
- Without it, the audio engine is the test double the GUI tests use, so the meters,
  the relay and the state text move without opening a device. Never build the take
  on that path: its stream never ticks, the engine's two-second watchdog then stops
  a stream that never started, and the recording shows a device error it invented.

Either way the device names on the wiring cards are this machine's own names, read
with the app's own enumeration and its own selection rules, so the cards read like a
real setup.

Everything else is the shipped window, and every click is real OS input through
SendInput: the recording shows a window being operated, not a re-render of one.

    .venv/Scripts/python.exe tools/promo_run.py --route ai_voice --live \\
        --input "Senary Audio" --output "CABLE Input"

The window opens maximised and waits for a cue. That cue is the take's start
marker: start OBS on this window first, then press Space in the window, so the
take begins where the story does.

The sequence is scheduled by a Qt timer rather than sleep-looped, because a frozen
GUI thread would freeze the meters the recording exists to show. Do not move the
mouse during the take; the cursor is the performance.

Timeline and hotspots land in .freebuff/promo_run/ so the edit can align the cut and
the camera with what actually happened instead of with a guess.
"""
import argparse
import ctypes
import json
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QKeySequence, QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

# --- real OS input -----------------------------------------------------------------

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77

GLIDE_STEPS = 34


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class ScreenInput:
    """The real cursor, driven the way a hand would drive it.

    A wrong structure size makes SendInput fail silently, and a take with a missing
    click looks like a take where the app ignored the user, so both the size and
    every call's return value are checked.
    """

    INPUT_MOUSE = 0

    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT),
                                          ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT
        if ctypes.sizeof(INPUT) != 40:
            raise SystemExit(f"INPUT is {ctypes.sizeof(INPUT)} bytes, not the 40 Windows expects")
        self.origin = (self.user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
                       self.user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        self.span = (self.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
                     self.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    def _send(self, *events):
        array = (INPUT * len(events))(*events)
        sent = self.user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
        if sent != len(events):
            raise RuntimeError(f"SendInput delivered {sent} of {len(events)} events "
                               f"(error {ctypes.get_last_error()})")

    def _absolute(self, flags, x, y, data=0):
        event = INPUT(type=self.INPUT_MOUSE)
        event.u.mi = MOUSEINPUT(
            dx=round((x - self.origin[0]) * 65535 / max(self.span[0] - 1, 1)),
            dy=round((y - self.origin[1]) * 65535 / max(self.span[1] - 1, 1)),
            mouseData=data, dwFlags=flags | MOUSEEVENTF_ABSOLUTE, time=0, dwExtraInfo=None)
        return event

    def cursor_position(self):
        point = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def move_one(self, x, y):
        self._send(self._absolute(MOUSEEVENTF_MOVE, x, y))

    def click(self):
        self._send(self._absolute(MOUSEEVENTF_LEFTDOWN, 0, 0))
        time.sleep(0.06)
        self._send(self._absolute(MOUSEEVENTF_LEFTUP, 0, 0))

    def wheel(self, notches):
        self._send(self._absolute(MOUSEEVENTF_WHEEL, 0, 0, data=int(notches) * 120))


# --- the window --------------------------------------------------------------------

def device_by_name(devices, fragment, kind):
    """The Windows WASAPI device a name fragment picks, in one direction only.

    A name that matches nothing must stop the take rather than silently fall back
    to some other microphone: the recording is the proof of the wiring, and a
    take wired to the wrong device proves the wrong thing.
    """
    matches = [d for d in devices
               if fragment.lower() in d.name.lower()
               and getattr(d, f"max_{kind}_channels") > 0
               and "wasapi" in d.host_api.lower()]
    if not matches:
        raise SystemExit(f"no WASAPI {kind} device matches {fragment!r}")
    return matches[0]


def pick_devices(input_name=None, output_name=None):
    """This machine's input and output, chosen the way the window chooses them.

    Enumeration only: listing a device does not open one. A named fragment wins;
    otherwise the app's own ``choose_device`` decides (the default microphone and,
    for the output, a virtual cable), so an unconfigured take still wires itself
    the way a launch would.
    """
    from src.audio.devices import choose_device, enumerate_devices
    devices = enumerate_devices()
    source = (device_by_name(devices, input_name, "input") if input_name
              else choose_device(devices, "input"))
    target = (device_by_name(devices, output_name, "output") if output_name
              else choose_device(devices, "output",
                                 preferred_api=source.host_api if source else None))
    if source is None or target is None:
        raise SystemExit("this machine has no usable input/output pair")
    if source.host_api != target.host_api:
        raise SystemExit(f"input and output must share a host API "
                         f"({source.host_api} / {target.host_api})")
    print(f"devices: {source.label} -> {target.label}")
    return source, target


def build_window(route, live=False, input_name=None, output_name=None, data_dir=None):
    """The shipped window on the real display, over the real engine or the mock."""
    from src.audio.controller import AudioController
    from src.audio.engine import AudioEngine
    from src.gui.main_window import MainWindow
    from src.processors.ai_voice import AIVoiceProcessor
    from src.processors.chain import ProcessorChain
    from src.processors.voice_router import VoiceRouter
    from src.settings.manager import AppSettings, SettingsManager
    from src.vc.bridge import AIBridge

    source, target = pick_devices(input_name, output_name)
    if live:
        bridge = AIBridge()
        backend = None
    else:
        from tests.fakes import FakeBackend
        from tests.test_ai_voice import FakeClient

        class PromoBackend(FakeBackend):
            """The test double, wearing this machine's device names."""

            def query_devices(self, index=None):
                devices = [dict(name=source.name, hostapi=0, max_input_channels=2,
                                max_output_channels=0),
                           dict(name=target.name, hostapi=0, max_input_channels=0,
                                max_output_channels=2)]
                return devices if index is None else devices[index]

        bridge = AIBridge(client_factory=FakeClient)
        backend = PromoBackend()

    router = VoiceRouter(ai=AIVoiceProcessor(bridge=bridge))
    engine = (AudioEngine(ProcessorChain(router)) if backend is None
              else AudioEngine(ProcessorChain(router), backend))
    controller = AudioController(engine)
    settings_dir = Path(data_dir or tempfile.mkdtemp(prefix="koeiro-promo-run-"))
    manager = SettingsManager(settings_dir / "settings.json")
    # The saved identities are the enumerated ones, so the window's own
    # choose_device resolves exactly these two devices on either path.
    manager.save(replace(AppSettings(), voice_mode=route, discord_presence=False,
                         app_update_check=False, tutorial_seen=True,
                         input_device=source.identity, output_device=target.identity))
    window = MainWindow(manager, controller)
    window.showMaximized()
    until = time.monotonic() + 8
    while time.monotonic() < until and not window.start_button.isEnabled():
        QApplication.processEvents()
        time.sleep(0.005)
    QApplication.processEvents()
    return window, controller, engine


def widget_box(window, widget):
    """A widget's rectangle in window pixels, plus its normalised copy.

    The normalised copy is what the video edit zooms with: it survives the
    recording being scaled, so the camera aims at the control the cursor did.
    """
    if widget is None or not widget.isVisibleTo(window):
        return None
    top_left = widget.mapTo(window, QPoint(0, 0))
    box = {"x": top_left.x(), "y": top_left.y(),
           "w": widget.width(), "h": widget.height()}
    box.update({"nx": box["x"] / window.width(), "ny": box["y"] / window.height(),
                "nw": box["w"] / window.width(), "nh": box["h"] / window.height()})
    return box


def physical_center(window, box, offset=(0, 0)):
    """The screen pixel for a window-pixel box, DPI scaling included.

    Qt hands out logical pixels and SendInput takes physical ones, so the window's
    own device pixel ratio is the conversion, not a guess.
    """
    scale = window.devicePixelRatio()
    origin = window.mapToGlobal(QPoint(0, 0))
    return (round((origin.x() + box["x"] + box["w"] / 2 + offset[0]) * scale),
            round((origin.y() + box["y"] + box["h"] / 2 + offset[1]) * scale))


def plan_steps(await_ai=False):
    """The story, at the pace a person would do it, with room for the camera.

    Spelled out as primitives rather than compound actions: which pixel is aimed
    at, and what it is called in the timeline, are then both readable here -- the
    timeline is what the edit cuts on. Each wait lets a click's zoom arrive and
    settle before the next beat, so there is something to cut between.
    """
    return [
        ("mark", "take begins"), ("wait", 1.4),
        ("glide", "start", "center", 0.85), ("wait", 0.35),
        ("mark", "click Start"), ("click",), ("wait", 0.5),
        ("mark", "engine running"),
        *((("await_ai", 120), ("wait", 1.0)) if await_ai else (("wait", 4.4),)),
        ("glide", "tune", "center", 0.85), ("wait", 0.35),
        ("mark", "click 調整"), ("click",), ("wait", 0.5),
        ("mark", "tuning drawer open"), ("wait", 2.2),
        ("glide", "voicePanel", "lower", 0.8), ("mark", "read the drawer"), ("wait", 0.5),
        ("wheel", -3), ("mark", "scroll down"), ("wait", 1.5),
        ("wheel", -3), ("mark", "scroll further"), ("wait", 1.5),
        ("wheel", 6), ("mark", "scroll back"), ("wait", 1.1),
        ("glide_widget", "tuneClose", 0.8), ("wait", 0.3),
        ("mark", "click 閉じる"), ("click",), ("wait", 0.6),
        ("mark", "drawer closed"), ("wait", 1.3),
        ("glide", "lab", "center", 0.85), ("wait", 0.35),
        ("mark", "click 実験"), ("click",), ("wait", 0.5),
        ("mark", "experiments open"), ("wait", 2.2),
        ("glide", "voicePanel", "lower", 0.8), ("mark", "read the cards"), ("wait", 2.6),
        ("glide_widget", "labClose", 0.8), ("wait", 0.3),
        ("mark", "click 閉じる"), ("click",), ("wait", 0.6),
        ("mark", "back to the stage"), ("wait", 1.6),
        ("glide", "relay", "center", 0.9),
        ("mark", "hold on the stage"), ("wait", 3.2),
        ("mark", "take ends"),
    ]


class Sequence(QObject):
    """Plays the plan on the GUI thread, one timed step at a time.

    Every wait is a QTimer interval, never a sleep: the engine's meters animate on
    this same thread, and a take where the meters stutter is a take thrown away.
    """

    finished = Signal(list)

    def __init__(self, screen, window, aims, widgets, readiness=None):
        super().__init__()
        self.screen = screen
        self.window = window
        self.aims = aims
        self.widgets = widgets
        # The route's own live state, so the take waits for the model instead of
        # assuming it and marks the fact it actually observed.
        self.readiness = readiness
        self.timeline = []
        self.plan = plan_steps(await_ai=readiness is not None)
        self.index = 0
        self.glide = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)

    def start(self):
        self.started_at = time.monotonic()
        self.index = 0
        self.timeline = []
        self._advance()

    def _mark(self, name):
        self.timeline.append({"step": name, "ms": round((time.monotonic() - self.started_at) * 1000)})
        print(f"  t+{self.timeline[-1]['ms'] / 1000:5.1f}s  {name}", flush=True)

    def _point(self, name, spot="center"):
        box = widget_box(self.window, self.widgets[name]())
        if box is None:
            raise RuntimeError(f"{name} is not on screen for this beat")
        return physical_center(self.window, box, (0, 150) if spot == "lower" else (0, 0))

    def _advance(self):
        if self.glide is not None:
            self.glide["step"] += 1
            t = self.glide["step"] / GLIDE_STEPS
            eased = t * t * (3 - 2 * t)
            x = round(self.glide["from"][0] + (self.glide["to"][0] - self.glide["from"][0]) * eased)
            y = round(self.glide["from"][1] + (self.glide["to"][1] - self.glide["from"][1]) * eased)
            self.screen.move_one(x, y)
            if self.glide["step"] < GLIDE_STEPS:
                self.timer.start(self.glide["interval_ms"])
                return
            self.glide = None
        while self.index < len(self.plan):
            step = self.plan[self.index]
            if step[0] == "await_ai":
                status = self.readiness() if self.readiness else "Ready"
                if status == "Ready":
                    self.index += 1
                    self._mark("AI ready")
                    continue
                if time.monotonic() - self.started_at > step[1]:
                    self.index += 1
                    self._mark(f"AI not ready: {status}")
                    continue
                self.timer.start(250)
                return
            self.index += 1
            kind = step[0]
            try:
                if kind == "mark":
                    self._mark(step[1])
                elif kind == "wait":
                    self.timer.start(round(step[1] * 1000))
                    return
                elif kind in ("glide", "glide_widget"):
                    if kind == "glide":
                        target, seconds = self._point(step[1], step[2]), step[3]
                    else:
                        target, seconds = self._point(step[1]), step[2]
                    self.glide = {"from": self.screen.cursor_position(), "to": target,
                                  "step": 0,
                                  "interval_ms": max(1, round(seconds * 1000 / GLIDE_STEPS))}
                    self.timer.start(0)
                    return
                elif kind == "click":
                    self.screen.click()
                elif kind == "wheel":
                    self.screen.wheel(step[1])
            except Exception as error:  # a failed input must be reported, not swallowed
                self.timeline.append({"step": f"ERROR: {error}", "error": True})
                print(f"input failed: {error}", flush=True)
                break
        self.finished.emit(self.timeline)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--route", default="ai_voice",
                        choices=("original", "female_dsp", "ai_voice"))
    parser.add_argument("--live", action="store_true",
                        help="Run the real audio route on this machine's devices; without it the "
                             "engine is the GUI test double and no device is opened")
    parser.add_argument("--input", metavar="FRAGMENT", default=None,
                        help="Input device name fragment (default: the app's own choice)")
    parser.add_argument("--output", metavar="FRAGMENT", default=None,
                        help="Output device name fragment (default: the app's own choice)")
    parser.add_argument("--out", type=Path, default=ROOT / ".freebuff" / "promo_run")
    parser.add_argument("--auto-after", type=float, default=0.0,
                        help="Begin without a cue after this many seconds (0 waits for one)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the resolved coordinates, click nothing")
    args = parser.parse_args()
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    application.setApplicationName("Koeiro")
    data_dir = Path(tempfile.mkdtemp(prefix="koeiro-promo-run-"))
    if args.live:
        # The take's own evidence: selected devices, AI model status, xruns. It is
        # read back when the take is verified, so it lives beside the settings.
        from src.utils.logging import configure_logging
        configure_logging(data_dir / "logs")
    window, controller, engine = build_window(args.route, args.live, args.input, args.output,
                                              data_dir)
    print(f"engine: {'live' if args.live else 'test double'}")

    widgets = {
        "start": lambda: window.start_button,
        "stop": lambda: window.stop_button,
        "tune": lambda: window.header.tune_button,
        "lab": lambda: window.header.lab_button,
        "relay": lambda: window.relay,
        "nameplate": lambda: window.nameplate,
        "voicePanel": lambda: window.voice_panel,
        "mode": lambda: window.mode,
    }
    aims = {}
    for name, getter in widgets.items():
        box = widget_box(window, getter())
        if box is not None:
            aims[name] = {"center": physical_center(window, box),
                          "lower": physical_center(window, box, (0, 150))}
    boxes = {name: box for name, getter in widgets.items()
             if (box := widget_box(window, getter())) is not None}
    drawer_closes = {"tuneClose": lambda: window.drawers["tune"].close_button,
                     "labClose": lambda: window.drawers["lab"].close_button}
    live_inputs = dict(widgets, **drawer_closes)
    print(f"window {window.width()}x{window.height()} logical, dpr {window.devicePixelRatio()}, "
          f"origin {window.mapToGlobal(QPoint(0, 0))}")
    for name, spots in aims.items():
        print(f"  {name:10s} centre {spots['center']}  lower {spots['lower']}")
    if args.dry_run:
        (out_dir / "hotspots.json").write_text(
            json.dumps({"size": [window.width(), window.height()],
                        "device_pixel_ratio": window.devicePixelRatio(),
                        "boxes": boxes, "aims": aims}, ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")
        for drawer, name in (("tune", "tuneClose"), ("lab", "labClose")):
            window._open_drawer(drawer)
            application.processEvents()
            box = widget_box(window, drawer_closes[name]())
            print(f"  {name:10s} {box}")
            window._open_drawer(None)
            application.processEvents()
        print("dry run: nothing was clicked")
        return 0

    sequence = Sequence(ScreenInput(), window, aims, live_inputs,
                        (lambda: window.router.ai.bridge.status) if args.live else None)

    def finish(timeline):
        (out_dir / "timeline.json").write_text(
            json.dumps({"route": args.route, "live": args.live, "data_dir": str(data_dir),
                        "timeline": timeline}, ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")
        (out_dir / "hotspots.json").write_text(
            json.dumps({"size": [window.width(), window.height()],
                        "device_pixel_ratio": window.devicePixelRatio(),
                        "boxes": boxes, "aims": aims}, ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_dir / 'timeline.json'}", flush=True)
        print("stop the recording now; the window stays open", flush=True)

    sequence.finished.connect(finish)

    def play():
        if sequence.timeline:
            return
        print("take starting", flush=True)
        sequence.start()

    if args.auto_after:
        QTimer.singleShot(int(args.auto_after * 1000), play)
        print(f"starting automatically in {args.auto_after:.0f}s")
    else:
        cue = QShortcut(QKeySequence(Qt.Key.Key_Space), window)
        cue.activated.connect(play)
        print("start Recordly on this window, then press Space here to begin the take")
    application.exec()
    window.close()
    until = time.monotonic() + 5
    while time.monotonic() < until and controller.alive:
        application.processEvents()
        time.sleep(0.005)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
