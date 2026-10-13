# PV take: recording with OBS

The first two takes were recorded with Recordly and lost: its post-recording pass
(whisper-backed auto-zoom, never configured) failed and cleaned up its own temp file
before the take could be saved. OBS records straight to a file we name, so there is no
pass that can eat the take.

## What an OBS take needs (each of these cost a take to find)

1. **The cursor is in the file only while the captured window owns the foreground
   window.** `plugins/win-capture/window-capture.c` computes
   `cursor_hidden = foreground pid != target pid` and stops drawing the cursor when the
   app is not in front, which is invisible in the OBS UI. The driver focuses the window
   before recording and never takes focus back.
2. **The record output does not start when `StartRecord` returns** (encoder init, ~0.7 s
   on this machine). The cue's position in the file is read from
   `GetRecordStatus().output_duration` at the moment Space is pressed, so no fixed delay
   is assumed. A take's marks are cue-relative; add `cue_offset_s` from `take.json` to
   get file times.
3. **The record directory must be absolute**: OBS resolves a relative path against its
   own install directory and then fails the output with "bad output path".
4. **Preview off** (`user.ini`: `PreviewEnabled=false`) took lagged frames from 8 % to
   0.5 % at 1920x1008@60 on this machine's N150.
5. **OBS's global audio devices are set to `Disabled`** (mic and desktop audio), so the
   take is silent and no hardware input is opened.
6. **A tray-resident OBS ignores `WM_CLOSE`.** `tools/obs_record.py quit` therefore asks
   once, stops the process if it refuses, and clears `%APPDATA%\obs-studio\.sentinel`;
   leaving the marker means the next start stops on a crash-recovery dialog that blocks
   obs-websocket (`first_load`/`ConfirmOnExit` are also off in the profile).

## Commands

    # one take, end to end (launches the window, records it, cues it, stops it)
    .venv/Scripts/python.exe tools/pv_take.py --route ai_voice

    # the pieces, when a take needs to be driven by hand
    .venv/Scripts/python.exe tools/obs_record.py check|arm|start|stop|status|quit

    # the recorded file, as the edit sees it
    .freebuff/promo_run/take.json          file, cue_offset_s, the 18 marks
    .freebuff/promo_run/hotspots.json      widget boxes and click aims
    .freebuff/promo_run/cursor_track.json  cursor position every 0.25 s
    .freebuff/promo_run/promo_run.log      the window's own log for the take

## Verified takes

    promo/public/raw/koeiro_20261012-141304.mp4   driver take, 40.0 s, cue at 1.15 s
    promo/public/raw/koeiro_20261012-140311.mp4   hand take,   39.1 s, cue ~0.52 s (frame-scanned)

Both are 1920x1008 at 60 fps with the cursor in frame (the parked cursor shows as a
~200 px dark outline over the relay card) and both hold the full 18-mark sequence with no
errors; the driver take carries the measured cue offset. Test clips that were only used
to prove the pipeline are in `.freebuff/promo_run/tests/`.

## What is still open

The edit itself is not started: `take.json` + `hotspots.json` + `cursor_track.json` are
what a Remotion composition needs to place the camera, and the drawer buttons
(`tuneClose`, `labClose`) are measured only by `promo_run.py --dry-run`, so their boxes
are not in the live take's hotspots yet.
