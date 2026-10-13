"""The splash video renderer: the timeline it drives, and the frames it writes.

The tool is not the splash, so this does not re-test the splash widget -- it tests
that the capture of it is real. Both halves matter: an off timeline makes a video
that never matches the app, and a grab that ignores the opacity effect makes a
video of a still frame. The frames are read back as pixels here, because the
widget's own state cannot tell those two failures apart. The frame rate is low
on purpose: the timeline is what is under test, not the smoothness of the fade.
"""
import shutil
import time

import pytest
from PySide6.QtWidgets import QApplication

from src.gui.splash import FADE_IN_MS, HOLD_MS, SPLASH_MS
from tools.render_splash import build_window, opacity_at, render_frames, verify_frames

FPS = 10


def test_timeline_is_the_shipped_fade():
    """Same breakpoints and direction as the overlay's own animations."""
    assert opacity_at(0) == 0.0
    assert opacity_at(FADE_IN_MS - 1) < 1.0
    assert opacity_at(FADE_IN_MS) == 1.0
    assert opacity_at(FADE_IN_MS + HOLD_MS - 1) == 1.0
    assert opacity_at(SPLASH_MS) == 0.0
    steps = [opacity_at(t) for t in range(0, SPLASH_MS + 1, 50)]
    rising = steps[:FADE_IN_MS // 50 + 1]
    falling = steps[(FADE_IN_MS + HOLD_MS) // 50:]
    assert rising == sorted(rising), rising
    assert falling == sorted(falling, reverse=True), falling


@pytest.fixture(scope="module")
def frames(tmp_path_factory):
    """One render for both frame checks; a broken frame is what the copy is for."""
    app = QApplication.instance() or QApplication([])
    window, controller, _bridge = build_window(app, 640, 360)
    try:
        return render_frames(app, window, tmp_path_factory.mktemp("splash") / "frames",
                             fps=FPS, width=640, height=360)
    finally:
        window.close()
        until = time.monotonic() + 5
        while time.monotonic() < until and controller.alive:
            app.processEvents()
            time.sleep(0.005)


def test_every_frame_tracks_the_fade(frames):
    """One frame per timeline step, each matching the fade in its pixels."""
    assert len(frames) == round(SPLASH_MS / 1000 * FPS)
    verify_frames(frames, FPS)  # raises SystemExit when a frame leaves the timeline


def test_a_frame_off_the_timeline_is_rejected(frames, tmp_path):
    """The check above must fail on a wrong frame, or it proves nothing."""
    copies = [shutil.copyfile(path, tmp_path / path.name) for path in frames]
    shutil.copyfile(copies[len(copies) // 2], copies[5])  # a hold frame in the fade-in
    try:
        verify_frames(copies, FPS)
    except SystemExit as error:
        assert "frame 5" in str(error), error
    else:
        raise AssertionError("a frame from the hold passed as a fade frame")
