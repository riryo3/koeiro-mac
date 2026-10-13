"""Build the Windows installer for a tag: dist/Koeiro -> koeiro-<tag>-windows-setup.exe.

Inno Setup (ISCC.exe) does the packing; this tool stages the frozen bundle, refuses
anything that still points at a development tree, runs the compiler, and writes the
checksums sidecar the in-app updater verifies.

Layout contract (see PUBLISHING.md and src/app_update.py):

* ``koeiro-<tag>-windows-setup.exe``      what a frozen install updates with, and what
  a BOOTH/GitHub customer double-clicks
* ``koeiro-<tag>-windows-checksums.txt``  ``<sha256>  <filename>`` lines, sha256sum format

Usage:

    .venv\\Scripts\\python tools\\build_windows_setup.py --tag v0.13.2
    .venv\\Scripts\\python tools\\build_windows_setup.py --tag v0.13.2 --rebuild
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BOOTH_FILE_LIMIT = 1200 * 1000 * 1000  # BOOTH: 1 file <= 1.2 GB
ISCC_NAMES = ("Inno Setup 6", "Inno Setup 7")
ROOT_FILE_NAME = "koeiro-root.txt"


class SetupError(Exception):
    pass


def version_of(tag):
    return tag[1:] if tag[:1] == "v" else tag


def asset_name(tag):
    return f"koeiro-{tag}-windows-setup.exe"


def checksums_name(tag):
    return f"koeiro-{tag}-windows-checksums.txt"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_iscc(explicit=None):
    """The Inno Setup compiler, or SetupError telling the user to install it."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    from_env = os.environ.get("ISCC")
    if from_env:
        candidates.append(Path(from_env))
    found = shutil.which("ISCC.exe")
    if found:
        candidates.append(Path(found))
    local = os.environ.get("LOCALAPPDATA")
    bases = [local, str(Path(local) / "Programs") if local else None,
             os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")]
    for base in bases:
        if not base:
            continue
        for name in ISCC_NAMES:
            candidates.append(Path(base) / name / "ISCC.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SetupError("ISCC.exe が見つかりません。Inno Setup 6 を導入するか --iscc でパスを指定してください "
                     "(winget install --id JRSoftware.InnoSetup -e --scope user)")


def stage_bundle(root, bundle_dir, stage_dir, keep_build_root=False):
    """Copy the frozen bundle plus the documents a distribution must carry.

    ``koeiro-root.txt`` records the folder the build was made in. Shipped to another
    PC it would point at a tree that does not exist there, which is why a
    distribution stage drops it: ``runtime_paths.install_root`` then falls back to the
    install folder itself, exactly where an AI pack belongs.
    """
    root, bundle_dir, stage_dir = Path(root), Path(bundle_dir), Path(stage_dir)
    if not (bundle_dir / "Koeiro.exe").is_file():
        raise SetupError(f"凍結バンドルがありません: {bundle_dir / 'Koeiro.exe'}")
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, stage_dir, symlinks=True)
    if not keep_build_root:
        target = stage_dir / "_internal" / ROOT_FILE_NAME
        if target.is_file():
            target.unlink()
        elif target.exists():
            raise SetupError(f"ビルド元記録を除去できません: {target}")
    for source_name, target_name in (("LICENSE", "LICENSE.txt"),
                                     ("README.md", "README.md"),
                                     ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")):
        source = root / source_name
        if not source.is_file():
            raise SetupError(f"同梱必須の文書がありません: {source_name}")
        shutil.copy2(source, stage_dir / target_name)
    return stage_dir


def check_stage(stage):
    """Fail on anything that must not leave this machine (PUBLISHING.md checklist)."""
    stage = Path(stage)
    problems = []
    if not (stage / "Koeiro.exe").is_file():
        problems.append("Koeiro.exe が無い")
    if not (stage / "_internal").is_dir():
        problems.append("_internal が無い")
    if not (stage / "LICENSE.txt").is_file():
        problems.append("LICENSE.txt が無い")
    for name in ("settings.json", "logs", "recordings", ROOT_FILE_NAME, "__pycache__"):
        if (stage / name).exists() or (stage / "_internal" / name).exists():
            problems.append(f"同梱してはいけない物がある: {name}")
    recorded = stage / "_internal" / ROOT_FILE_NAME
    if recorded.is_file():
        try:
            text = recorded.read_text("utf-8").strip()
        except OSError:
            text = "<読めない>"
        problems.append(f"ビルド元記録が残っている: {text}")
    if problems:
        raise SetupError("ステージ検査に失敗: " + " / ".join(problems))
    return stage


def newest_source(root):
    """Most recent mtime among the files a rebuild would pick up."""
    newest = 0.0
    for directory in ("src",):
        base = Path(root) / directory
        for path in base.rglob("*.py"):
            newest = max(newest, path.stat().st_mtime)
    app = Path(root) / "app.py"
    if app.is_file():
        newest = max(newest, app.stat().st_mtime)
    return newest


def check_fresh(root, bundle_exe, allow_stale=False):
    """Refuse to ship an exe older than the source, which would silently drop fixes."""
    if allow_stale:
        return
    stamp = Path(bundle_exe).stat().st_mtime
    source = newest_source(root)
    if source > stamp:
        raise SetupError("dist の exe より src の方が新しいです。--rebuild か、README の手順で "
                         "PyInstaller を実行し直してください（--allow-stale で回避）")


def run_pyinstaller(root, gui_python=None):
    """write_build_root.py + PyInstaller, i.e. the README build steps."""
    root = Path(root)
    interpreter = Path(gui_python) if gui_python else root / ".venv" / "Scripts" / "python.exe"
    if not interpreter.is_file():
        raise SetupError(f"ビルド用の Python がありません: {interpreter}")
    steps = [
        [str(interpreter), str(root / "tools" / "write_build_root.py")],
        [str(interpreter), "-m", "PyInstaller", str(root / "Koeiro.spec"), "--noconfirm"],
    ]
    for command in steps:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                   timeout=1800)
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-800:]
            raise SetupError(f"ビルドに失敗: {command[-1]} ... {tail}")
    return root / "dist" / "Koeiro"


def compile_setup(iscc, script, stage, out_dir, tag, timeout=1200):
    """Run ISCC. Returns the produced setup path."""
    iscc, script, stage, out_dir = Path(iscc), Path(script), Path(stage), Path(out_dir)
    if not script.is_file():
        raise SetupError(f"インストーラスクリプトがありません: {script}")
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [str(iscc),
               f"/DMyAppVersion={version_of(tag)}",
               f"/DMyTag={tag}",
               f"/DStageDir={stage}",
               f"/DOutDir={out_dir}",
               str(script)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise SetupError("ISCC に失敗:\n" + output.strip()[-2000:])
    target = out_dir / asset_name(tag)
    if not target.is_file():
        raise SetupError(f"setup.exe が作られませんでした:\n{output.strip()[-800:]}")
    return target, output


def write_checksums(out_dir, tag, entries):
    """`<sha256>  <filename>` lines, in the format sha256sum -c reads."""
    path = Path(out_dir) / checksums_name(tag)
    lines = [f"{digest}  {name}" for name, digest in sorted(entries.items())]
    path.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return path


def build_setup(root, tag, out_dir=None, stage_dir=None, bundle_dir=None, iscc=None,
                rebuild=False, allow_stale=False, keep_build_root=False, gui_python=None):
    """Stage, compile and hash. Returns (setup_path, sha256, checksums_path)."""
    root = Path(root)
    out_dir = Path(out_dir or root / "dist" / "setup")
    bundle_dir = Path(bundle_dir or root / "dist" / "Koeiro")
    stage_dir = Path(stage_dir or root / "build" / "setup-stage" / "Koeiro")
    if rebuild:
        bundle_dir = run_pyinstaller(root, gui_python)
    check_fresh(root, bundle_dir / "Koeiro.exe", allow_stale=allow_stale)
    stage = stage_bundle(root, bundle_dir, stage_dir, keep_build_root=keep_build_root)
    check_stage(stage)
    compiler = find_iscc(iscc)
    target, _ = compile_setup(compiler, root / "installer" / "Koeiro.iss", stage, out_dir, tag)
    digest = sha256_of(target)
    entries = {target.name: digest}
    source_zip = out_dir / f"koeiro-{tag}-windows.zip"
    if source_zip.is_file():
        entries[source_zip.name] = sha256_of(source_zip)
    checksums = write_checksums(out_dir, tag, entries)
    if target.stat().st_size > BOOTH_FILE_LIMIT:
        raise SetupError(f"setup.exe が {BOOTH_FILE_LIMIT} バイト超: BOOTH の1ファイル上限を超えます")
    return target, digest, checksums


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="例: v0.13.2")
    parser.add_argument("--root", default=".", help="リポジトリの場所")
    parser.add_argument("--out", default=None, help="setup.exe の出力先（既定: dist/setup）")
    parser.add_argument("--bundle", default=None, help="凍結バンドルの場所（既定: dist/Koeiro）")
    parser.add_argument("--stage", default=None, help="ステージング先（既定: build/setup-stage/Koeiro）")
    parser.add_argument("--iscc", default=None, help="ISCC.exe のパス")
    parser.add_argument("--rebuild", action="store_true", help="PyInstaller から作り直す")
    parser.add_argument("--gui-python", default=None, help="--rebuild が使う venv Python")
    parser.add_argument("--allow-stale", action="store_true",
                        help="src より古い exe でも止めない")
    parser.add_argument("--keep-build-root", action="store_true",
                        help="ビルド元記録を残す（このPCで試すときだけ。配布物では必須除去）")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="APP_VERSION とタグの一致検査を省略")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if not args.allow_dirty:
            check_version_tag(root, args.tag)
        target, digest, checksums = build_setup(
            root, args.tag, out_dir=args.out, stage_dir=args.stage, bundle_dir=args.bundle,
            iscc=args.iscc, rebuild=args.rebuild, allow_stale=args.allow_stale,
            keep_build_root=args.keep_build_root, gui_python=args.gui_python)
    except SetupError as error:
        print(f"error: {error}")
        return 1
    print(f"setup: {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"sha256: {digest}")
    print(f"checksums: {checksums}")
    print("次のリリースへの添付: gh release upload " + args.tag + " "
          f'"{target}" "{checksums}" --clobber')
    return 0


def read_app_version(root):
    """APP_VERSION as written in src/version.py, without importing it."""
    path = Path(root) / "src" / "version.py"
    try:
        text = path.read_text("utf-8")
    except OSError as error:
        raise SetupError(f"src/version.py が読めません: {error}") from error
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise SetupError("src/version.py から APP_VERSION を読めません")
    return match.group(1)


def check_version_tag(root, tag):
    """The build must report the release it came from, or the updater loops forever."""
    current = read_app_version(root)
    if version_of(tag) != current:
        raise SetupError(f"src/version.py の APP_VERSION={current} がタグ {tag} と違います。"
                         "更新し忘れると自動更新が無限に通知します")


if __name__ == "__main__":
    sys.exit(main())
