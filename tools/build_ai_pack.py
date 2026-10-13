"""Build the AI voice pack installer: frozen worker + the files the route loads.

The app setup carries Koeiro.exe only; this pack is the second BOOTH/GitHub file and
installs beside it: KoeiroWorker.exe, its _internal_worker tree (torch), the MeanVC2
checkpoints the conversion actually loads, the LavaSR tree, and the shipped standard
voice. Nothing here needs Python on the customer's machine.

    .venv\\Scripts\\python tools\\build_ai_pack.py --tag v0.13.2
    vc_models\\meanvc2\\.venv\\Scripts\\python -m PyInstaller KoeiroWorker.spec --noconfirm

What is deliberately NOT in the pack:
* the worker virtualenv (2.2 GB of it) -- torch lives in _internal_worker instead
* the registration checkpoints (wavlm_large*.pt, ~2.4 GB) -- voice registration still
  needs tools/register_voice.py in an installed AI environment
* the vendored `encodec` package: its wheel metadata is CC BY-NC 4.0 and a paid
  distribution may not carry it. vocos imports EncodecModel at module level but this
  route never builds it, so the pack writes a raising stub of our own in its place
  (verified: the utterance+LavaSR conversion is bit-identical with the stub).

Outputs (into dist/ai-pack):
* ``koeiro-<tag>-ai-pack.exe`` (+ ``-2.bin`` ... when Inno spans disks at 1100 MB)
* ``koeiro-<tag>-ai-pack-checksums.txt`` -- sha256 of every part, sha256sum format
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from build_windows_setup import (BOOTH_FILE_LIMIT, SetupError, find_iscc, sha256_of,  # noqa: E402
                                 version_of)

DEFAULT_VOICE = "user_3b11387911244c6e9a013b42fa88a458"
VOICE_FILES = ("reference.wav", "fixed_embedding.npy", "runtime.json", "profile.json")
# The conversion path opens exactly these weights (src/vc/meanvc2.py, LavaSR).
MEANVC2_KEEP = (
    "ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors",
    "ckpts/vocos/vocos.pt",
    "preprocess/ckpts/fastu2pp_160ms.pt",
)
MEANVC2_CODE = ("src", "runtime", "preprocess", "defaults.ini", "default_config.yaml",
                "initialization.py", "README.md")
LAVASR_SKIP = ("vendor/encodec", "vendor/encodec-0.1.1.dist-info", "vendor/bin", ".venv",
               "repo/.git")
ENCODEC_STUB = '''"""Stand-in for the encodec package: importable, and any real use raises.

The vendored encodec wheel is CC BY-NC 4.0, so this distribution carries no encodec
code. vocos/feature_extractors.py imports EncodecModel at module level and only builds
it for the EncodecFeatures extractor, which the LavaSR checkpoint this app uses does
not select. Verified bit-identical output against the real package.
"""


class EncodecModel:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("encodec is not distributed with Koeiro")

    @classmethod
    def encodec_model_24khz(cls, *args, **kwargs):
        raise NotImplementedError("encodec is not distributed with Koeiro")

    @classmethod
    def encodec_model_48khz(cls, *args, **kwargs):
        raise NotImplementedError("encodec is not distributed with Koeiro")


def __getattr__(name):
    raise AttributeError("encodec is not distributed with Koeiro: " + str(name))
'''


def copy_tree(source, destination, keep=None, skip=()):
    """Copy a tree, keeping only listed relative paths and honouring skip prefixes."""
    source, destination = Path(source), Path(destination)
    if not source.is_dir():
        raise SetupError(f"同梱元がありません: {source}")
    keep = set(keep) if keep is not None else None
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source).as_posix()
        if any(relative == name or relative.startswith(name + "/") for name in skip):
            continue
        if keep is not None and relative not in keep:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def stage_pack(root, worker_dir, stage, voice=DEFAULT_VOICE, tag="0.0.0",
               worker_exe="KoeiroWorker.exe", contents_dir="_internal_worker"):
    """Assemble exactly what ships. Returns (stage, file_count, total_bytes)."""
    root, worker_dir, stage = Path(root), Path(worker_dir), Path(stage)
    if not (worker_dir / worker_exe).is_file():
        raise SetupError(f"凍結ワーカーがありません: {worker_dir / worker_exe}"
                         "（AI環境の Python で KoeiroWorker.spec をビルド）")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(worker_dir, stage / "worker", symlinks=True)
    shutil.move(str(stage / "worker" / worker_exe), str(stage / worker_exe))
    shutil.move(str(stage / "worker" / contents_dir), str(stage / contents_dir))
    shutil.rmtree(stage / "worker")
    (stage / "vc_models" / "meanvc2" / "repo").mkdir(parents=True)
    for name in MEANVC2_CODE:
        source = root / "vc_models/meanvc2/repo" / name
        if source.is_dir():
            copy_tree(source, stage / "vc_models/meanvc2/repo" / name,
                      skip=("ckpts",))
        elif source.is_file():
            target = stage / "vc_models/meanvc2/repo" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    copy_tree(root / "vc_models/meanvc2/repo", stage / "vc_models/meanvc2/repo",
              keep=MEANVC2_KEEP)
    copy_tree(root / "vc_models/post_lavasr", stage / "vc_models/post_lavasr",
              skip=LAVASR_SKIP)
    voice_source = root / "models/user_voices" / voice
    for name in VOICE_FILES:
        source = voice_source / name
        if not source.is_file():
            raise SetupError(f"既定声の同梱物がありません: {voice}/{name}")
        target = stage / "models/user_voices" / voice / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    stub = stage / "vc_models/post_lavasr/vendor/encodec/__init__.py"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(ENCODEC_STUB, "utf-8", newline="\n")
    for name, source in (("LICENSE.txt", "LICENSE"), ("README.md", "README.md"),
                         ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")):
        if not (root / source).is_file():
            raise SetupError(f"同梱必須の文書がありません: {source}")
        shutil.copy2(root / source, stage / name)
    write_manifest(stage, tag, sha256_of(stage / worker_exe), worker_exe, contents_dir)
    files = [path for path in stage.rglob("*") if path.is_file()]
    return stage, len(files), sum(path.stat().st_size for path in files)


def check_stage(stage, voice=DEFAULT_VOICE, worker_exe="KoeiroWorker.exe",
                contents_dir="_internal_worker"):
    """The pack must not smuggle a development tree, a venv, or CC BY-NC encodec."""
    stage = Path(stage)
    problems = []
    for name in (worker_exe, contents_dir, "LICENSE.txt",
                 "koeiro-ai-pack.json", "models/user_voices/" + voice + "/reference.wav"):
        if not (stage / name).exists():
            problems.append("無い: " + name)
    # The shipped voice names the weights it needs and pins their sha256; the pack must
    # carry exactly those bytes, so a wrong or half-copied checkpoint never ships.
    try:
        runtime = json.loads((stage / "models/user_voices" / voice / "runtime.json")
                             .read_text("utf-8"))
        for item in runtime.get("assets") or []:
            asset = item["path"] if isinstance(item, dict) else str(item)
            path = stage / asset
            if not path.is_file():
                problems.append("runtime.json が要求する資産が無い: " + str(asset))
                continue
            expected = str(item.get("sha256") or "").lower() if isinstance(item, dict) else ""
            if expected and sha256_of(path) != expected:
                problems.append("資産の sha256 が runtime.json と違います: " + str(asset))
    except (OSError, ValueError, TypeError, KeyError) as error:
        problems.append(f"runtime.json を読めません: {error}")
    for name in ("koeiro-root.txt", "settings.json", ".venv", ".venv-ai", ".venv-prosody"):
        if any(stage.rglob(name)):
            problems.append("同梱不可: " + name)
    for name in ("logs", "recordings", "vc_models/meanvc2/.venv",
                 "vc_models/post_lavasr/vendor/bin", "vc_models/post_lavasr/.venv",
                 "vc_models/meanvc2/repo/figs", "vc_models/meanvc2/repo/preprocess/ckpts/wavlm_large.pt"):
        if (stage / name).exists():
            problems.append("同梱不可: " + name)
    if not (stage / contents_dir / "torch").is_dir():
        problems.append(f"torch が凍結されていない（{contents_dir}/torch が無い）")
    encodec = stage / "vc_models/post_lavasr/vendor/encodec"
    if (encodec / "model.py").is_file() or (encodec / "modules").is_dir():
        problems.append("encodec の実体が残っている（CC BY-NC 4.0）")
    if not (encodec / "__init__.py").is_file():
        problems.append("encodec の代替スタブが無い")
    if problems:
        raise SetupError("AIパックの検査に失敗: " + " / ".join(problems))
    return stage


def app_asset(tag, worker_exe):
    """The app artifact this pack belongs to: the Windows setup or the Linux bundle."""
    return (f"koeiro-{tag}-windows-setup.exe" if worker_exe.endswith(".exe")
            else f"koeiro-{tag}-linux-app.tar.gz")


def write_manifest(stage, tag, worker_sha256, worker_exe="KoeiroWorker.exe",
                   contents_dir="_internal_worker"):
    manifest = {
        "app": "Koeiro AI Voice Pack",
        "version": version_of(tag),
        "tag": tag,
        "requires": {"app_asset": app_asset(tag, worker_exe)},
        "worker": worker_exe,
        "worker_sha256": worker_sha256,
        "voice": DEFAULT_VOICE,
        "contents": [worker_exe, contents_dir, "vc_models/meanvc2/repo",
                     "vc_models/post_lavasr", "models/user_voices", "LICENSE.txt",
                     "README.md", "THIRD_PARTY_NOTICES.md"],
        "excluded": ["encodec (CC BY-NC 4.0: raising stub instead)",
                     "wavlm_large*.pt (voice registration only)",
                     f"the AI virtualenv (frozen into {contents_dir})"],
    }
    (Path(stage) / "koeiro-ai-pack.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n")
    return manifest


def compile_pack(iscc, script, stage, out_dir, tag, repo_root, timeout=3600):
    iscc, stage, out_dir = Path(iscc), Path(stage), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [str(iscc),
               f"/DMyAppVersion={version_of(tag)}",
               f"/DMyTag={tag}",
               f"/DStageDir={stage}",
               f"/DOutDir={out_dir}",
               f"/DRepoRoot={repo_root}",
               str(script)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise SetupError("ISCC に失敗:\n" + output.strip()[-2500:])
    # Inno writes one launcher plus N1050MB slices; the slices sort before the .exe by
    # name, so the launcher is found by path, not by taking parts[0].
    launcher = out_dir / f"koeiro-{tag}-ai-pack.exe"
    found = sorted(path for path in out_dir.glob(f"koeiro-{tag}-ai-pack*")
                   if path.suffix.lower() in (".exe", ".bin"))
    if not launcher.is_file():
        raise SetupError("AIパックの出力が見つかりません:\n" + output.strip()[-800:])
    return [launcher] + [path for path in found if path != launcher], output


def pack_name(tag):
    return f"koeiro-{tag}-ai-pack-checksums.txt"


def build_pack(root, tag, out_dir=None, stage_dir=None, worker_dir=None, iscc=None,
               voice=DEFAULT_VOICE):
    """Stage, check, compile and hash.

    Returns (parts, checksums_path, {"files": staged file count, "raw_bytes": staged
    size before compression}).
    """
    root = Path(root)
    out_dir = Path(out_dir or root / "dist" / "ai-pack")
    worker_dir = Path(worker_dir or root / "dist" / "KoeiroWorker")
    stage_dir = Path(stage_dir or root / "build" / "ai-pack-stage" / "Koeiro")
    stage, count, total = stage_pack(root, worker_dir, stage_dir, voice=voice, tag=tag)
    check_stage(stage, voice=voice)
    parts, _ = compile_pack(find_iscc(iscc), root / "installer" / "KoeiroAIPack.iss",
                           stage, out_dir, tag, root)
    entries = {path.name: sha256_of(path) for path in parts}
    checksums = out_dir / pack_name(tag)
    lines = [f"{entries[path.name]}  {path.name}" for path in parts]
    checksums.write_text("\n".join(lines) + "\n", "ascii", newline="\n")
    oversized = [path.name for path in parts if path.stat().st_size > BOOTH_FILE_LIMIT]
    if oversized:
        raise SetupError("BOOTH の1ファイル上限 1.2GB を超えた分割物があります: "
                         + ", ".join(oversized))
    return parts, checksums, {"files": count, "raw_bytes": total}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="例: v0.13.2")
    parser.add_argument("--root", default=".", help="リポジトリの場所")
    parser.add_argument("--out", default=None, help="出力先（既定: dist/ai-pack）")
    parser.add_argument("--stage", default=None, help="ステージング先")
    parser.add_argument("--worker", default=None, help="凍結ワーカーの場所（既定: dist/KoeiroWorker）")
    parser.add_argument("--iscc", default=None, help="ISCC.exe のパス")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="同梱する既定声の id")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        sys.path.insert(0, str(root))
        from src.version import APP_VERSION
        if version_of(args.tag) != APP_VERSION:
            raise SetupError(f"APP_VERSION={APP_VERSION} がタグ {args.tag} と違います")
        parts, checksums, staged = build_pack(root, args.tag, out_dir=args.out,
                                             stage_dir=args.stage, worker_dir=args.worker,
                                             iscc=args.iscc, voice=args.voice)
    except SetupError as error:
        print(f"error: {error}")
        return 1
    for path in parts:
        print(f"part: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"staged: {staged['files']} files, {staged['raw_bytes'] / 1024 / 1024:.1f} MB")
    print(f"checksums: {checksums}")
    print(f"BOOTH への添付対象: {len(parts)} 物（同じフォルダに全て置いて part1 を実行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
