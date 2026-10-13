"""Render the startup splash as a video (MP4, for promo material).

This is not a screen recording of a live launch: the real MainWindow and the real
show_splash overlay are built exactly as app.py builds them, then each frame is
rendered off-screen with the overlay's opacity set from a fixed timeline. The
result is deterministic and repeatable, which a wall-clock capture of a 3-second
fade is not.

The timeline read here is the splash module's own -- same durations, same ease,
and each frame is one grab of the real widget tree, so the pixel content is the
shipped art rather than a redrawing of it.

    .venv/Scripts/python.exe tools/render_splash.py --out renders/splash.mp4

Frames can be kept with --frames-dir when the material needs to be re-cut.
ffmpeg must be on PATH; it is the only encoder used.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Chosen before Qt is imported: the render must never need a display or audio.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QTimer  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.gui.splash import (BACKGROUND, FADE_IN_MS, FADE_OUT_MS, HOLD_MS,  # noqa: E402
                            SPLASH_MS, show_splash)


def build_window(application, width, height):
    """The shipped main window with mock audio, the way the GUI tests build it.

    Discord presence, the background update check and the first-run guide are
    switched off in the temporary settings: an unattended render must not talk to
    Discord or GitHub, and the guide -- whose scrim would cover the splash a few
    seconds in -- belongs to a real launch, not to this capture.
    """
    from dataclasses import replace

    from src.audio.controller import AudioController
    from src.audio.engine import AudioEngine
    from src.gui.main_window import MainWindow
    from src.processors.ai_voice import AIVoiceProcessor
    from src.processors.chain import ProcessorChain
    from src.processors.voice_router import VoiceRouter
    from src.settings.manager import SettingsManager
    from src.vc.bridge import AIBridge
    from tests.fakes import FakeBackend
    from tests.test_ai_voice import FakeClient

    bridge = AIBridge(client_factory=FakeClient)
    router = VoiceRouter(ai=AIVoiceProcessor(bridge=bridge))
    controller = AudioController(AudioEngine(ProcessorChain(router), FakeBackend()))
    settings_dir = Path(tempfile.mkdtemp(prefix="koeiro-splash-"))
    window = MainWindow(SettingsManager(settings_dir / "settings.json"), controller)
    window.settings = replace(window.settings, discord_presence=False,
                             app_update_check=False, tutorial_seen=True)
    window.show()
    until = time.monotonic() + 5
    while time.monotonic() < until and not window.start_button.isEnabled():
        application.processEvents()
        time.sleep(0.005)
    # A launched window fills the monitor; the render matches that, so the splash
    # covers the frame exactly. The taskbar and title bar are not part of it.
    window.resize(width, height)
    application.processEvents()
    return window, controller, bridge


def opacity_at(t_ms, easing=None):
    """The overlay content's opacity at a point on the splash timeline.

    Mirrors the animations started in show_splash (fade in, hold, fade out) using
    the same easing curve object they use, so the video is the app's own fade and
    not an approximation of it.
    """
    easing = easing or QEasingCurve(QEasingCurve.Type.InOutQuad)

    def ramp(start, end, duration, elapsed):
        progress = min(max(elapsed / duration, 0.0), 1.0)
        return start + (end - start) * easing.valueForProgress(progress)

    if t_ms < FADE_IN_MS:
        return ramp(0.0, 1.0, FADE_IN_MS, t_ms)
    if t_ms < FADE_IN_MS + HOLD_MS:
        return 1.0
    return ramp(1.0, 0.0, FADE_OUT_MS, t_ms - FADE_IN_MS - HOLD_MS)


def render_frames(application, window, frames_dir, fps, width, height):
    """Grab one frame per timeline step; return the frame paths.

    show_splash is called without when_revealed: the first-run guide belongs to a
    real launch, and it would open a second window over the animation here.
    """
    overlay = show_splash(window)
    if overlay is None:
        raise SystemExit("brand art is missing: assets/icon.png and assets/logo.png are required")
    if overlay.size() != window.size():
        print(f"note: overlay is {overlay.size().width()}x{overlay.size().height()}, "
              f"window is {window.size().width()}x{window.size().height()}")
    # The overlay drives itself from the wall clock. Stop every timer and
    # animation it owns and hold the opacity by hand: the clock is the only part
    # that must not be real, and nothing here may advance on its own mid-render.
    for animation in overlay.findChildren(QAbstractAnimation):
        animation.stop()
    for timer in overlay.findChildren(QTimer):
        timer.stop()
    content = overlay.findChild(QWidget, "splashContent")
    if content is None:
        raise SystemExit("splashContent is missing from the overlay")
    effect = content.graphicsEffect()
    if effect is None:
        raise SystemExit("the overlay has no opacity effect to drive")

    frames_dir.mkdir(parents=True, exist_ok=True)
    count = round(SPLASH_MS / 1000 * fps)
    paths = []
    for index in range(count):
        t_ms = index * 1000 / fps
        effect.setOpacity(opacity_at(t_ms))
        application.processEvents()
        path = frames_dir / f"frame_{index:04d}.png"
        # The window, not the overlay: what the screen shows on a launch.
        window.grab().save(str(path))
        paths.append(path)
    return paths


def verify_frames(paths, fps):
    """Check every frame against the timeline it was rendered from, in pixels.

    A grab that ignores the opacity effect still produces frames, and a widget
    that appears mid-render still produces frames: both are caught here instead of
    in the deliverable. Frame 0 must be flat brand background, and the strongest
    pixel difference from it must track the fade -- rising to the hold, then
    falling back -- to within 8-bit rounding, no matter what the widget state says.
    """
    background = QColor(BACKGROUND).getRgb()[:3]
    with Image.open(paths[0]).convert("RGB") as first:
        histogram = first.getcolors(maxcolors=1 << 22)
        if histogram is None:
            raise SystemExit(f"{paths[0].name} has too many colors to read back")
        if len(histogram) != 1 or histogram[0][1] != background:
            busiest = max(histogram, key=lambda entry: entry[0])[1]
            raise SystemExit(
                f"frame 0 is not the flat brand background {background}, it is {busiest}")
        base = np.asarray(first, dtype=np.int16)
    deltas = []
    for path in paths:
        with Image.open(path).convert("RGB") as frame:
            deltas.append(int(np.abs(np.asarray(frame, dtype=np.int16) - base).max()))
    peak = max(deltas)
    if peak < 40:
        raise SystemExit(f"the art never becomes visible (peak delta {peak}/255)")
    for index, delta in enumerate(deltas):
        expected = round(opacity_at(index * 1000 / fps) * peak)
        if abs(delta - expected) > 3:
            raise SystemExit(f"frame {index} shows {delta}/255 where the splash timeline "
                             f"says {expected}/255")
    print(f"checked frames: background {background}; art peak {peak}/255; "
          f"first/middle/last delta {deltas[0]}/{deltas[len(deltas) // 2]}/{deltas[-1]}/255")


def encode(frames_dir, out_path, fps, crf, silence):
    """Encode the frames with ffmpeg; report its own exit status, never mask it."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit(f"ffmpeg is not on PATH; the rendered frames remain in {frames_dir}")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-framerate", str(fps), "-start_number", "0",
               "-i", str(frames_dir / "frame_%04d.png")]
    if silence:
        command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-shortest"]
    command += ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    command += [] if silence else ["-an"]
    command += [str(out_path)]
    result = subprocess.run(command)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg exited with {result.returncode}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "renders" / "splash.mp4")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=60,
                        help="Frame rate; the splash runs %d ms" % SPLASH_MS)
    parser.add_argument("--crf", type=int, default=18, help="x264 quality (lower is better)")
    parser.add_argument("--frames-dir", type=Path, default=None,
                        help="Keep the PNG frames here instead of a temporary directory")
    parser.add_argument("--with-silence", action="store_true",
                        help="Add a silent stereo track, for editors that want one")
    args = parser.parse_args()
    if args.width % 2 or args.height % 2:
        parser.error("width and height must be even for yuv420p")
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = args.frames_dir or Path(tempfile.mkdtemp(prefix="koeiro-splash-frames-"))

    application = QApplication.instance() or QApplication([])
    window, controller, _bridge = build_window(application, args.width, args.height)
    try:
        paths = render_frames(application, window, frames_dir, args.fps, args.width, args.height)
        verify_frames(paths, args.fps)
    finally:
        window.close()
        until = time.monotonic() + 5
        while time.monotonic() < until and controller.alive:
            application.processEvents()
            time.sleep(0.005)
    encode(frames_dir, out_path, args.fps, args.crf, args.with_silence)
    size = out_path.stat().st_size
    print(f"saved {out_path} ({size:,} bytes, {len(paths)} frames, "
          f"{args.fps} fps, {SPLASH_MS / 1000:.1f} s, {args.width}x{args.height})")
    if args.frames_dir:
        print(f"frames: {frames_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
