"""Drive OBS over obs-websocket: one scene, one window, one output path we name.

The recorder for the PV take is OBS now, not Recordly. The takes that vanished were
lost to a post-recording AI pass (whisper-backed auto-zoom, never configured) that
cleaned up its own temp file when it failed; OBS records straight to a file and has
no such pass, so the footage exists the moment `stop` returns.

This script never launches OBS; it talks to the running instance, so the app stays a
normal window and the recording can be started and stopped from a terminal.

    .venv/Scripts/python.exe tools/obs_record.py check
    .venv/Scripts/python.exe tools/obs_record.py arm --window Koeiro
    .venv/Scripts/python.exe tools/obs_record.py start
    .venv/Scripts/python.exe tools/obs_record.py stop

`arm` is idempotent: it reuses the scene and source if a previous take made them, and
it re-resolves the window every time, because the window id OBS stores embeds the
process id and a stale id records nothing.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCENE = "Koeiro take"
SOURCE = "Koeiro window"
KIND = "window_capture"
WS_CONFIG = (pathlib.Path(os.environ["APPDATA"]) / "obs-studio" / "plugin_config"
             / "obs-websocket" / "config.json")


def connect():
    import obsws_python
    config = json.loads(WS_CONFIG.read_text(encoding="utf-8-sig"))
    if not config.get("server_enabled"):
        raise SystemExit("obs-websocket is disabled: turn it on in OBS under "
                         "Tools > WebSocket Server Settings")
    client = obsws_python.ReqClient(host="127.0.0.1", port=config["server_port"],
                                    password=config.get("server_password", ""), timeout=5)
    version = client.get_version()
    print(f"OBS {version.obs_version}, obs-websocket {version.obs_web_socket_version}")
    return client


def ensure_scene(client):
    scenes = [scene["sceneName"] for scene in client.get_scene_list().scenes]
    if SCENE not in scenes:
        client.create_scene(SCENE)
        print(f"created scene {SCENE!r}")


def ensure_source(client):
    """The window source, with the cursor drawn in and window audio left alone."""
    inputs = [item["inputName"] for item in client.get_input_list().inputs]
    if SOURCE not in inputs:
        client.create_input(sceneName=SCENE, inputName=SOURCE, inputKind=KIND,
                            inputSettings={"method": 0, "cursor": True, "capture_audio": False},
                            sceneItemEnabled=True)
        print(f"created source {SOURCE!r}")
    try:
        client.get_scene_item_id(SCENE, SOURCE)
    except Exception:
        client.create_scene_item(SCENE, SOURCE, enabled=True)
        print(f"added {SOURCE!r} to {SCENE!r}")


def resolve_window(client, hint):
    """Point the source at the window whose title contains `hint`.

    OBS hands out window ids as title/class/process strings; matching on a title
    substring keeps the take working across app restarts, and the id it returns is
    written verbatim so nothing here has to know its format.
    """
    items = client.get_input_properties_list_property_items(SOURCE, "window").property_items
    matches = [item for item in items if hint.lower() in str(item.get("itemName", "")).lower()]
    if not matches:
        raise SystemExit(f"no window matches {hint!r}: is it open? Try `check` for the list")
    chosen = matches[0]
    client.set_input_settings(SOURCE, {"window": chosen["itemValue"], "method": 0,
                                       "cursor": True, "client_area": False}, True)
    print(f"window: {chosen['itemName']}")
    return chosen


def arm(client, args):
    client.set_video_settings(numerator=args.fps, denominator=1, base_width=args.width,
                              base_height=args.height, out_width=args.width, out_height=args.height)
    client.set_profile_parameter("Output", "FilenameFormatting", "koeiro_%CCYY%MM%DD-%hh%mm%ss")
    client.set_profile_parameter("SimpleOutput", "RecFormat2", "hybrid_mp4")
    client.set_profile_parameter("SimpleOutput", "RecQuality", "HQ")
    # OBS resolves a relative path against its own working directory, so this must be absolute
    client.set_record_directory(str(pathlib.Path(args.dir).resolve()))
    ensure_scene(client)
    ensure_source(client)
    resolve_window(client, args.window)
    client.set_current_program_scene(SCENE)
    print(f"armed: {args.width}x{args.height} @ {args.fps} fps -> {args.dir}")


def status(client):
    state = client.get_record_status()
    print(f"recording {state.output_active}"
          + (f", {state.output_timecode} ({state.output_bytes / 2 ** 20:.1f} MiB)"
             if state.output_active else ""))


def shutdown_marker():
    """OBS's unclean-shutdown marker: its presence makes the next start ask about recovery."""
    return pathlib.Path(os.environ["APPDATA"]) / "obs-studio" / ".sentinel"


def clear_shutdown_marker():
    """Delete the marker so the next launch cannot open the recovery dialog.

    The dialog blocks OBS before obs-websocket comes up, which is worse for a take than
    any crash it is warning about, so the marker is cleared whenever we have stopped OBS.
    """
    marker = shutdown_marker()
    if marker.exists():
        shutil.rmtree(marker, ignore_errors=True)
        print(f"cleared {marker}")


def quit_obs(timeout=8.0):
    """Close OBS for real, then make sure the next launch will not stop on the dialog.

    A tray-resident OBS ignores WM_CLOSE (it is hidden by design), so the polite ask is
    followed by a forced stop when the process refuses to go; either way the marker is
    cleared, because a take needs the websocket, not a recovery prompt.
    """
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    found = []

    def visit(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value.startswith("OBS"):
                found.append((hwnd, title.value))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    for hwnd, title in found:
        print(f"asking OBS to close ({title})")
        user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
    deadline = time.monotonic() + timeout
    while found and time.monotonic() < deadline:
        time.sleep(0.5)
        running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                                 capture_output=True, text=True).stdout
        if "obs64.exe" not in running:
            break
    else:
        if found:
            print("OBS did not close; stopping it")
            subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], capture_output=True)
            time.sleep(1.0)
    clear_shutdown_marker()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("check", "arm", "start", "stop", "status", "quit"))
    parser.add_argument("--window", default="Koeiro", help="Title substring of the window to record")
    parser.add_argument("--dir", type=pathlib.Path, default=ROOT / "promo" / "public" / "raw")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1008)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()
    args.dir = args.dir if args.dir.is_absolute() else ROOT / args.dir
    args.dir.mkdir(parents=True, exist_ok=True)

    if args.action == "quit":
        quit_obs()
        return 0
    client = connect()
    if args.action == "check":
        scenes = [scene["sceneName"] for scene in client.get_scene_list().scenes]
        if SCENE in scenes:
            items = client.get_scene_item_list(SCENE).scene_items
            print("scene sources:", [item["sourceName"] for item in items])
        else:
            print("scene sources: no scene yet")
        if SOURCE in [item["inputName"] for item in client.get_input_list().inputs]:
            for item in client.get_input_properties_list_property_items(
                    SOURCE, "window").property_items:
                print("  window:", item.get("itemName"))
    elif args.action == "arm":
        arm(client, args)
    elif args.action == "start":
        client.start_record()
        time.sleep(1)
        status(client)
    elif args.action == "stop":
        response = client.stop_record()
        print("wrote:", getattr(response, "output_path", "(path unknown)"))
    else:
        status(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
