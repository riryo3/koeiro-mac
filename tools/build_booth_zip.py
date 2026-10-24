"""BOOTH 向けの「OSごとに1 ZIP」を、配布物から作り直す（PUBLISHING.md の BOOTH 節）。

買い手が ZIP を解いたフォルダで `ai-pack.exe` が `ai-pack-1.bin` を、
`install-ai-pack.sh` が2つの tar と checksums を同じフォルダで探すため、
アーカイブのルートは **フラット**でなければなりません。中身はすでに gzip / Inno で
圧縮済みなので **無圧縮(stored)** にします（deflate は CPU を溶くだけで大きくはならない）。

BOOTH の上限（1ファイル 1.2GB・1商品あたり合計 10GB）はこの場で検査します。
超限の ZIP をアップロードしてから気づくのが一番高い失敗だからです。

使い方は PUBLISHING.md にあります:
    .venv\\Scripts\\python tools\\build_booth_zip.py --tag v1.0.0 --guide-windows notes\\... --guide-linux notes\\...
    .venv\\Scripts\\python tools\\build_booth_zip.py --tag v1.0.0 --check     # 出来た ZIP の点検だけ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.app_update import parse_checksums, sha256_of  # noqa: E402

# booth.pixiv.help のアップロード容量制限（2026-03-09 時点）。
BOOTH_FILE_LIMIT_BYTES = 1_200_000_000
BOOTH_PRODUCT_LIMIT_BYTES = 10_000_000_000

# ZIP に入れるファイル（`{tag}` は展開する）。入手案内.txt は持ち主が書いたものだけ使う
# ので、このツールは中身を創作せず必ずパスで受け取る。
WINDOWS_MEMBERS = ("koeiro-{tag}-windows-setup.exe",
                   "koeiro-{tag}-windows-checksums.txt",
                   "koeiro-{tag}-ai-pack.exe",
                   "koeiro-{tag}-ai-pack-1.bin",
                   "koeiro-{tag}-ai-pack-checksums.txt")
LINUX_MEMBERS = ("koeiro-{tag}-linux-app.tar.gz",
                 "koeiro-{tag}-linux-ai-pack-1.tar.gz",
                 "koeiro-{tag}-linux-ai-pack-2.tar.gz",
                 "koeiro-{tag}-linux-checksums.txt")
GUIDE_NAME = "入手案内.txt"
# どのメンバーがどの checksums ファイルで検証できるか（無いものは照合しない）。
COVERAGE = ("koeiro-{tag}-windows-checksums.txt", "koeiro-{tag}-ai-pack-checksums.txt",
            "koeiro-{tag}-linux-checksums.txt")


class BoothError(RuntimeError):
    """配布物として出せない、という意思表示。"""


def source_dirs(dist):
    """dist/ の下の、配布物が出来上がっている場所."""
    dist = Path(dist)
    return {"windows": dist / "setup", "ai-pack": dist / "ai-pack", "linux": dist / "linux"}


def _locate(name, directories):
    for folder in directories.values():
        candidate = folder / name
        if candidate.is_file():
            return candidate
    raise BoothError(f"配布物が見つかりません: {name}")


def _has(name, directories):
    return any((folder / name).is_file() for folder in directories.values())


def os_plan(tag, platform, guide, directories):
    """One product: the guide, that OS's artifacts, each verified where possible."""
    if platform not in ("windows", "linux"):
        raise BoothError(f"対応していない OS です: {platform}")
    names = WINDOWS_MEMBERS if platform == "windows" else LINUX_MEMBERS
    paths = [name.format(tag=tag) for name in names]
    missing = [name for name in paths if not _has(name, directories)]
    if missing:
        raise BoothError(f"{platform} の配布物が揃っていません: {', '.join(missing)}")
    guide_path = Path(guide)
    if not guide_path.is_file():
        raise BoothError(f"入手案内.txt を作ってください（実測した範囲のことだけ書きます）: {guide_path}")
    members = [(GUIDE_NAME, guide_path)] + [(name, _locate(name, directories)) for name in paths]
    verify(tag, platform, members, directories)
    return members


def verify(tag, platform, members, directories):
    """BOOTH の上限と、同梱 checksums との突き合わせ。壊れた配布物を出さないため。"""
    names = {arcname for arcname, _ in members}
    tables = {}
    for name in {path.name for _, path in members if "checksums" in path.name}:
        for folder in directories.values():
            candidate = folder / name
            if candidate.is_file():
                tables[name] = parse_checksums(candidate.read_text("utf-8"))
    total = 0
    for arcname, path in members:
        if "/" in arcname or "\\" in arcname or ":" in arcname:
            raise BoothError(f"ルートがフラットでないメンバー: {arcname}")
        size = path.stat().st_size
        if size > BOOTH_FILE_LIMIT_BYTES:
            raise BoothError(f"1ファイル上限（{BOOTH_FILE_LIMIT_BYTES} byte）超過: {arcname} {size} byte")
        total += size
        for checksum_name, table in tables.items():
            expected = table.get(arcname)
            if not expected:
                continue
            actual = sha256_of(path)
            if actual != expected.lower():
                raise BoothError(f"{checksum_name} と {arcname} の sha256 が一致しません"
                                 f"（{actual[:12]}… vs {expected[:12]}…）")
    if total > BOOTH_PRODUCT_LIMIT_BYTES:
        raise BoothError(f"1商品の上限（{BOOTH_PRODUCT_LIMIT_BYTES} byte）超過: {platform} {total} byte")
    return total


def build(tag, platform, members, out):
    """stored・フラットで1 ZIP。ZIP 自体の sha256 は呼び出し側が checksums へ出す。"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"Koeiro_{tag}_{platform.capitalize()}.zip"
    target = out / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED, compresslevel=0) as bundle:
        seen = set()
        for arcname, path in members:
            if arcname in seen:
                raise BoothError(f"メンバーが重複しています: {arcname}")
            seen.add(arcname)
            bundle.write(path, arcname)
    return target


def booth_checksum_line(path):
    return f"{sha256_of(path)}  {path.name}"


def check(target, tag, platform, directories):
    """出来た ZIP が形として正しいか（フラット・stored・中身の名前・破損）。"""
    expected = {GUIDE_NAME} | {name.format(tag=tag) for name in
                               (WINDOWS_MEMBERS if platform == "windows" else LINUX_MEMBERS)}
    with zipfile.ZipFile(target) as bundle:
        if bundle.testzip() is not None:
            raise BoothError(f"ZIP が壊れています: {target.name}")
        problems = []
        for info in bundle.infolist():
            if info.compress_type != zipfile.ZIP_STORED:
                problems.append(f"{info.filename} が stored でない")
            if info.filename not in expected or "/" in info.filename:
                problems.append(f"想定にないメンバー: {info.filename}")
        missing = expected - {info.filename for info in bundle.infolist()}
        if missing:
            problems.append(f"足りないメンバー: {', '.join(sorted(missing))}")
    if problems:
        raise BoothError("; ".join(problems))
    return sorted(expected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="配布物の版（v1.0.0）")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist",
                        help="setup / ai-pack / linux がある dist の位置")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "booth")
    parser.add_argument("--guide-windows", type=Path, default=None)
    parser.add_argument("--guide-linux", type=Path, default=None)
    parser.add_argument("--check", action="store_true",
                        help="作り直さず、出来ている ZIP を点検する")
    args = parser.parse_args(argv)
    directories = source_dirs(args.dist)
    report = {}
    try:
        for platform, guide in (("windows", args.guide_windows), ("linux", args.guide_linux)):
            target = args.out / f"Koeiro_{args.tag}_{platform.capitalize()}.zip"
            if args.check:
                if not target.is_file():
                    raise BoothError(f"ZIP がありません: {target}")
                check(target, args.tag, platform, directories)
                report[platform] = {"zip": target.name, "checked": True}
                continue
            members = os_plan(args.tag, platform, guide, directories)
            total = verify(args.tag, platform, members, directories)
            written = build(args.tag, platform, members, args.out)
            report[platform] = {"zip": written.name, "bytes": written.stat().st_size,
                                "members": len(members), "payload_bytes": total}
    except (BoothError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        return 1
    if not args.check:
        lines = [booth_checksum_line(args.out / entry["zip"]) for entry in report.values()]
        (args.out / f"Koeiro_{args.tag}_booth-checksums.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        report["checksums"] = f"Koeiro_{args.tag}_booth-checksums.txt"
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
