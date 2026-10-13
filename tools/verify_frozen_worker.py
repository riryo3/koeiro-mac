"""Compare the frozen AI worker with the environment worker on stored WAVs.

Offline: the app-side protocol drives both workers over pipes on a file. No audio
devices are opened and nobody listens; the numbers say whether the two builds agree,
not whether the result sounds right.

    vc_models\\meanvc2\\.venv\\Scripts\\python.exe tools\\verify_frozen_worker.py
    python tools\\verify_frozen_worker.py --delivery streaming --quality low_latency

Both runs use the same torch (the bundle is built from that environment), the same
model tree and the same caches, so any difference is the packaging, not the math.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.vc.config import QUALITY_FACTORS  # noqa: E402
from src.vc.protocol import send, receive  # noqa: E402

RATE = 48000


def read_wav(path):
    with wave.open(str(path), "rb") as source:
        if source.getframerate() != RATE:
            raise ValueError(f"{path} must be {RATE} Hz, this tool does not resample")
        channels, frames = source.getnchannels(), source.getnframes()
        raw = np.frombuffer(source.readframes(frames), dtype="<i2")
    audio = raw.astype(np.float32) / 32768.0
    if channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)
    elif channels != 1:
        raise ValueError(f"{path} must be mono or stereo")
    return np.ascontiguousarray(audio)


def write_wav(path, audio):
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes((clipped * 32767.0).astype("<i2").tobytes())


def worker_env(extra=None):
    """The environment ServiceClient.start() builds for a MeanVC2 worker."""
    cache = ROOT / "vc_models" / "cache"
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "__PYVENV_LAUNCHER__"):
        environment.pop(key, None)
    for key, folder in (("TEMP", "temp"), ("TMP", "temp"), ("HF_HOME", "hf-home"),
                        ("HF_HUB_CACHE", "hf"), ("TORCH_HOME", "torch"),
                        ("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba")):
        target = cache / folder
        target.mkdir(parents=True, exist_ok=True)
        environment[key] = str(target)
    environment.update({"HF_HUB_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                        "CUDA_VISIBLE_DEVICES": ""})
    environment.update(extra or {})
    return environment


def build_command(kind, args, python, worker_exe):
    arguments = ["--factor", str(QUALITY_FACTORS[args.quality]), "--threads",
                 str(args.threads), "--device", "cpu", "--model", args.model,
                 "--delivery", args.delivery, "--enhancer", args.enhancer,
                 "--experiment", args.experiment]
    arguments.append("--lavasr-denoise" if args.lavasr_denoise else "--tune-combined")
    if kind == "environment":
        return [str(python), "-u", "-m", "src.vc.service"] + arguments
    return [str(worker_exe)] + arguments


def run_worker(command, env, audio, args, log_path, cwd):
    with open(log_path, "ab") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + args.load_timeout
        while time.monotonic() < deadline:
            header, _ = receive(process.stdout)
            if header["status"] == "Ready":
                break
            if header["status"] == "Error":
                raise RuntimeError(header.get("error", "worker failed to load"))
        else:
            raise RuntimeError("worker did not report Ready in time")
        header, output = None, None
        for _ in range(args.repeat):
            send(process.stdin, {"op": "utterance"}, audio)
            header, output = receive(process.stdout)
            if header["status"] == "Error":
                raise RuntimeError(header.get("error", "worker error"))
        return header, output
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass


def compare(first, second):
    report = {"samples": [int(len(first)), int(len(second))],
              "peak": [float(np.max(np.abs(first))), float(np.max(np.abs(second)))],
              "rms": [float(np.sqrt(np.mean(np.square(first)))),
                      float(np.sqrt(np.mean(np.square(second))))]}
    if len(first) != len(second):
        report["identical"] = False
        report["note"] = "length differs"
        return report
    difference = np.abs(np.asarray(first) - np.asarray(second))
    report["max_abs_diff"] = float(difference.max()) if difference.size else 0.0
    report["mean_abs_diff"] = float(difference.mean()) if difference.size else 0.0
    report["identical"] = bool(difference.size == 0 or difference.max() == 0.0)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, default=ROOT / "recordings" / "source_normal.wav")
    parser.add_argument("--model", default="user_3b11387911244c6e9a013b42fa88a458")
    parser.add_argument("--delivery", default="utterance", choices=("streaming", "utterance"))
    parser.add_argument("--enhancer", default="lavasr",
                        choices=("none", "flashsr", "mossformer", "voicefixer", "lavasr"))
    parser.add_argument("--experiment", default="natural")
    parser.add_argument("--quality", default="balanced")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--lavasr-denoise", action="store_true")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--load-timeout", type=float, default=300)
    parser.add_argument("--worker-exe", type=Path,
                        default=ROOT / "dist" / "KoeiroWorker" / "KoeiroWorker.exe")
    parser.add_argument("--tree", type=Path, default=None,
                        help="frozen run: the folder holding models/ and vc_models/ "
                             "(an installed AI pack), default this repository")
    parser.add_argument("--python", type=Path,
                        default=ROOT / "vc_models" / "meanvc2" / ".venv" / "Scripts" / "python.exe")
    parser.add_argument("--out", type=Path, default=ROOT / "validation" / "frozen_worker")
    parser.add_argument("--only", default="both", choices=("both", "environment", "frozen"),
                        help="run one worker only (the comparison needs both)")
    args = parser.parse_args(argv)

    audio = read_wav(args.wav)
    args.out.mkdir(parents=True, exist_ok=True)
    results = {"kind": "OFFLINE app<->worker WAV RPC on a stored file; no devices, no listening",
               "wav": str(args.wav), "model": args.model, "delivery": args.delivery,
               "enhancer": args.enhancer, "quality": args.quality, "threads": args.threads,
               "seconds": round(len(audio) / RATE, 3)}
    outputs = {}
    kinds = ("environment", "frozen") if args.only == "both" else (args.only,)
    for kind in kinds:
        if kind == "frozen" and not args.worker_exe.is_file():
            results["frozen"] = "missing " + str(args.worker_exe)
            continue
        command = build_command(kind, args, args.python, args.worker_exe)
        env = worker_env()
        cwd = ROOT
        if kind == "frozen":
            tree = Path(args.tree) if args.tree else ROOT
            cwd = tree
            env["KOEIRO_ROOT"] = str(tree)
            env["KOEIRO_ASSETS"] = str(tree)
        started = time.monotonic()
        header, output = run_worker(command, env, audio, args,
                                    args.out / f"{kind}-worker.log", cwd)
        outputs[kind] = np.asarray(output, dtype=np.float32).reshape(-1)
        results[kind] = {"seconds_wall": round(time.monotonic() - started, 2),
                         "header": {key: value for key, value in header.items()
                                    if key != "status"}}
        write_wav(args.out / f"{kind}.wav", outputs[kind])
    if len(outputs) == 2:
        results["compare"] = compare(outputs["environment"], outputs["frozen"])
    report = args.out / "report.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.only == "both":
        return 0 if "compare" in results else 1
    return 0 if outputs else 1


if __name__ == "__main__":
    sys.exit(main())
