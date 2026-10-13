"""One command per PV take: open the window, record it with OBS, cue it, stop, report.

    .venv/Scripts/python.exe tools/pv_take.py --route ai_voice --live \\
        --input "Senary Audio" --output "CABLE Input"

The take is the shipped window over promo_run, recorded by OBS through its window
capture. ``--live`` runs the real route (this machine's microphone into the virtual
cable); without it the engine is the GUI test double, whose stream never ticks, so the
engine watchdogs it into a device error a few seconds into the take. Three machine
facts are baked in, because the recording depends on
them and all three were found the hard way:

- OBS draws the cursor only while the captured window's process owns the foreground
  window (window-capture.c hides it otherwise), so the driver brings the window to the
  front and keeps it there for the whole take.
- The record output does not start when StartRecord returns, so the cue's position inside
  the file is measured from GetRecordStatus().output_duration at the moment Space is
  pressed, not from an assumed delay.
- OBS resolves a relative record path against its own directory, so the path is absolute.

After stopping it reads the file back and writes .freebuff/promo_run/take.json with the
file, the measured cue offset, the marks, and a 0.25 s cursor track for the edit.

OBS must be running with obs-websocket enabled; the driver launches OBS itself if the
socket is not answering (OBS_PATH overrides the default install path).
"""
import argparse
import ctypes
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import obs_record  # noqa: E402
from promo_run import ScreenInput  # noqa: E402

OBS_PATH = pathlib.Path(os.environ.get("OBS_PATH", r"D:\OBS\obs-studio\bin\64bit\obs64.exe"))
OUT = ROOT / ".freebuff" / "promo_run"
CURSOR_ONLY_MAX = 6000      # a diff this small between 0.25 s samples is cursor-only
TITLE = "Koeiro"


def windows_with_title():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    hits = []

    def visit(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value.startswith(TITLE):
                hits.append((hwnd, title.value))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return hits


def focus(hwnd):
    """Bring the window forward, which is also what makes OBS draw the cursor."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if user32.GetForegroundWindow() == hwnd:
        return True
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(foreground_thread, target_thread, True)
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.keybd_event(0x12, 0, 0, 0)   # ALT down: lets a background process set the foreground
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.AttachThreadInput(foreground_thread, target_thread, False)
    time.sleep(0.4)
    return user32.GetForegroundWindow() == hwnd


def ensure_obs(timeout=90):
    """Connect to OBS, starting the app first if its websocket is not answering."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return obs_record.connect()
        except Exception as error:
            if time.monotonic() > deadline or not OBS_PATH.exists():
                raise SystemExit(f"OBS websocket unreachable ({error}); start OBS and enable "
                                 f"Tools > WebSocket Server Settings")
            if not any("obs64" in name.lower() for name in subprocess.run(
                    ["tasklist"], capture_output=True, text=True).stdout.split()):
                print(f"starting OBS from {OBS_PATH}")
                obs_record.clear_shutdown_marker()   # never start into the recovery dialog
                subprocess.Popen([str(OBS_PATH), "--minimize-to-tray", "--disable-shutdown-check"],
                                 cwd=str(OBS_PATH.parent))
            time.sleep(2)


def frame_reader(path, width, height):
    import numpy as np

    def frame(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3).astype("int16")

    return frame


def cursor_track(path, duration, width, height):
    """Where the cursor was, sampled every 0.25 s: the only small moving thing on screen.

    The window's own meters animate too, so a sample counts as a cursor sample only when
    the changed pixels stay under a threshold; the centroid is then the cursor.
    """
    import numpy as np
    frame = frame_reader(path, width, height)
    samples = [round(0.5 + 0.25 * i, 2) for i in range(int((duration - 0.5) / 0.25))]
    track, previous = [], frame(samples[0])
    for t in samples[1:]:
        current = frame(t)
        delta = np.abs(current - previous).max(axis=2) > 24
        total = int(delta.sum())
        entry = {"t": t, "changed": total}
        if 0 < total < CURSOR_ONLY_MAX:
            ys, xs = np.nonzero(delta)
            entry["cursor"] = [int(xs.mean()), int(ys.mean()), int(xs.min()), int(ys.min()),
                               int(xs.max()), int(ys.max())]
        track.append(entry)
        previous = current
    return track


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--route", default="ai_voice",
                        choices=("original", "female_dsp", "ai_voice"))
    parser.add_argument("--live", action="store_true",
                        help="Record the shipped window on the real audio route")
    parser.add_argument("--input", metavar="FRAGMENT", default=None,
                        help="Input device name fragment (default: the app's own choice)")
    parser.add_argument("--output", metavar="FRAGMENT", default=None,
                        help="Output device name fragment (default: the app's own choice)")
    parser.add_argument("--title", default=TITLE)
    parser.add_argument("--cue-delay", type=float, default=1.2,
                        help="Seconds of lead-in recorded before the cue is pressed")
    parser.add_argument("--tail", type=float, default=2.0,
                        help="Seconds recorded after the last mark")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    existing = windows_with_title()
    if existing:
        raise SystemExit(f"a {TITLE} window is already open ({existing}); close it first")

    print("opening the window")
    log = open(OUT / "promo_run.log", "w", encoding="utf-8")
    command = [sys.executable, "-u", str(ROOT / "tools" / "promo_run.py"),
               "--route", args.route, "--out", str(OUT)]
    if args.live:
        command.append("--live")
    for flag, value in (("--input", args.input), ("--output", args.output)):
        if value:
            command += [flag, value]
    print("running " + " ".join(repr(part) if " " in part else part for part in command))
    app = subprocess.Popen(command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)

    client = ensure_obs()
    hits = []
    for _ in range(45):
        hits = windows_with_title()
        if hits:
            break
        time.sleep(1)
    if not hits:
        app.terminate()
        raise SystemExit("the window never appeared; see .freebuff/promo_run/promo_run.log")
    hwnd, title = hits[0]
    print(f"window: {title}")

    class Args:
        window, width, height, fps = args.title, 1920, 1008, 60
        dir = (ROOT / "promo" / "public" / "raw").resolve()
    obs_record.arm(client, Args())
    if not focus(hwnd):
        print("warning: could not confirm the window is the foreground window")

    timeline = OUT / "timeline.json"
    timeline.unlink(missing_ok=True)
    before = {path.name for path in Args.dir.glob("*.mp4")}

    client.start_record()
    for _ in range(50):                      # the output only starts once the encoder is up
        if client.get_record_status().output_active:
            break
        time.sleep(0.1)
    time.sleep(args.cue_delay)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.keybd_event(0x20, 0, 0, 0)        # SPACE: the take's cue
    time.sleep(0.05)
    user32.keybd_event(0x20, 0, 2, 0)
    cue_offset = client.get_record_status().output_duration / 1000
    print(f"take cued; it sits at {cue_offset:.2f} s in the file")

    started = time.monotonic()
    while time.monotonic() - started < args.timeout and not timeline.exists():
        time.sleep(0.25)
    if not timeline.exists():
        client.stop_record()
        raise SystemExit("the take never finished; the file was stopped anyway")
    print(f"take finished after {time.monotonic() - started:.1f} s")
    time.sleep(args.tail)

    response = client.stop_record()
    time.sleep(1.5)
    new = sorted({path.name for path in Args.dir.glob("*.mp4")} - before)
    if not new:
        raise SystemExit("no recording appeared")
    path = Args.dir / new[-1]

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate,nb_frames,duration",
                            "-of", "json", str(path)], capture_output=True, text=True, check=True)
    stream = json.loads(probe.stdout)["streams"][0]
    duration = float(stream["duration"])
    print(f"reading {path.name} back for the cursor track")
    track = cursor_track(path, duration, int(stream["width"]), int(stream["height"]))
    (OUT / "cursor_track.json").write_text(json.dumps(track, indent=1), encoding="utf-8")

    take = {
        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "route": args.route,
        "window": {"width": int(stream["width"]), "height": int(stream["height"]),
                   "fps": stream["r_frame_rate"], "title": title},
        "duration_s": duration,
        "frames": int(stream["nb_frames"]),
        "cue_offset_s": round(cue_offset, 2),
        "cue_offset_note": "file time = cue time + this; measured from the record output's "
                           "own duration when the cue was pressed",
        "timeline": json.loads(timeline.read_text(encoding="utf-8"))["timeline"],
        "artifacts": {"hotspots": ".freebuff/promo_run/hotspots.json",
                      "cursor_track": ".freebuff/promo_run/cursor_track.json",
                      "output_path": getattr(response, "output_path", None)},
        "live": args.live,
        "recorded_by": ("OBS window capture, preview off; the shipped window on this machine's "
                        "own microphone and virtual cable (no audio is captured into the file)"
                        if args.live else
                        "OBS window capture, preview off, audio devices disabled; the engine is "
                        "the GUI test double"),
    }
    (OUT / "take.json").write_text(json.dumps(take, ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
    print(f"wrote {path} ({duration:.1f} s) and .freebuff/promo_run/take.json")
    print("the window and OBS stay open; close them with tools/obs_record.py quit when done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
