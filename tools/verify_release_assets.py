"""Check the assembled release set before a single byte is attached to GitHub.

Every tag presents the same set: two source trees, the Windows installer and its
checksums, the Windows AI pack and its checksums, the Linux app bundle and two AI
pack slices under one checksums sheet. This tool answers three questions about a
tree the builders have filled:

* is that set present, under the exact names ``src/app_update.py`` looks for
* does every checksums sheet still describe the bytes beside it
* can ``pick_asset`` select each install form from a release listing built from
  these very files, including the checksums an unattended update verifies against

Run it on the assembled ``dist/`` once every builder has finished. Exit 0 prints a
JSON report; any problem is a non-zero exit naming the file or the row.

    .venv\\Scripts\\python tools\\verify_release_assets.py --tag v1.2.3
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.app_update import (BUNDLE_ASSET, BUNDLE_CHECKSUMS_ASSET, CHECKSUMS_ASSET,  # noqa: E402
                            PLATFORM_ASSETS, SETUP_ASSET, parse_checksums, pick_asset,
                            sha256_of)


class VerifyError(RuntimeError):
    """The assembled tree is not something to publish."""


def source_asset(tag, platform):
    token, extension = PLATFORM_ASSETS[platform]
    return f"koeiro-{tag}-{token}{extension}"


def expected_files(dist, tag):
    """(path, what it is) for everything the release must carry."""
    dist = Path(dist)
    files = [
        (dist / source_asset(tag, "windows"), "Windows のソースツリー"),
        (dist / source_asset(tag, "linux"), "Linux のソースツリー"),
        (dist / "setup" / SETUP_ASSET.format(tag=tag), "実行ファイル版の installer"),
        (dist / "setup" / CHECKSUMS_ASSET.format(tag=tag), "installer の sha256"),
        (dist / "ai-pack" / f"koeiro-{tag}-ai-pack.exe", "AIパックの launcher"),
        (dist / "ai-pack" / f"koeiro-{tag}-ai-pack-checksums.txt", "AIパックの sha256"),
        (dist / "linux" / BUNDLE_ASSET.format(tag=tag), "Linux 凍結 GUI"),
        (dist / "linux" / BUNDLE_CHECKSUMS_ASSET.format(tag=tag), "Linux 版の sha256（更新が読む）"),
    ]
    slices = sorted((dist / "ai-pack").glob(f"koeiro-{tag}-ai-pack-*.bin"))
    if not slices:
        raise VerifyError(f"AIパックの分割物がありません: {dist / 'ai-pack'}")
    files += [(path, "AIパックの分割物") for path in slices]
    parts = sorted((dist / "linux").glob(f"koeiro-{tag}-linux-ai-pack-*.tar.gz"))
    if len(parts) != 2:
        found = ", ".join(path.name for path in parts) or "なし"
        raise VerifyError(f"Linux の AIパックは2分割のはずです: {found}")
    files += [(path, "Linux AIパックの分割") for path in parts]
    missing = [f"{path}（{label}）" for path, label in files if not path.is_file()]
    if missing:
        raise VerifyError("足りない資産: " + " / ".join(missing))
    return files


def check_checksums(dist, files):
    """Every sheet must match the file it names, wherever that file landed."""
    known = {path.name: path for path, _ in files}
    checked = 0
    for sheet in sorted(Path(dist).rglob("*checksums*.txt")):
        table = parse_checksums(sheet.read_text("utf-8"))
        if not table:
            raise VerifyError(f"checksums が空です: {sheet}")
        for name, expected in table.items():
            path = known.get(name)
            if path is None:
                path = next(Path(dist).rglob(name), None)
                if path is None:
                    raise VerifyError(f"{sheet.name} が指すファイルがありません: {name}")
            actual = sha256_of(path)
            if actual != expected:
                raise VerifyError(f"{sheet.name}: {name} の sha256 が違います"
                                  f"（{actual[:12]}… vs {expected[:12]}…）")
            checked += 1
    return checked


def check_linux_app_row(dist, tag):
    """The frozen Linux updater verifies the app bundle with this sheet's app row."""
    sheet = Path(dist) / "linux" / BUNDLE_CHECKSUMS_ASSET.format(tag=tag)
    table = parse_checksums(sheet.read_text("utf-8"))
    if BUNDLE_ASSET.format(tag=tag) not in table:
        raise VerifyError(f"{sheet.name} に app tar の行がありません"
                          "（Linux の自動更新が検証できません）")


def check_updater(files, tag):
    """A release listing made from these files must satisfy every install form."""
    assets = [{"name": path.name, "browser_download_url": "https://example.invalid/" + path.name,
               "size": path.stat().st_size} for path, _ in files]
    release = {"tag_name": tag, "assets": assets}
    wanted = {
        ("windows", "package"): source_asset(tag, "windows"),
        ("linux", "package"): source_asset(tag, "linux"),
        ("windows", "frozen"): SETUP_ASSET.format(tag=tag),
        ("linux", "frozen"): BUNDLE_ASSET.format(tag=tag),
    }
    picks = []
    for (platform, kind), name in wanted.items():
        picked = pick_asset(release, platform=platform, kind=kind)
        if not picked or picked.get("name") != name:
            raise VerifyError(f"更新が選べません: {platform}/{kind}（{name} を期待）")
        if kind == "frozen" and not picked.get("checksums_url"):
            raise VerifyError(f"更新が検証に使う checksums がありません: {platform}/{kind}")
        picks.append(f"{platform}/{kind}: {picked['name']}")
    return picks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="配布物の版（例: v1.2.3）")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist",
                        help="組み上がった dist の位置")
    args = parser.parse_args(argv)
    try:
        files = expected_files(args.dist, args.tag)
        rows = check_checksums(args.dist, files)
        check_linux_app_row(args.dist, args.tag)
        picks = check_updater(files, args.tag)
    except (VerifyError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "tag": args.tag, "files": len(files),
                      "bytes": sum(path.stat().st_size for path, _ in files),
                      "checksums_rows": rows, "updater": picks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
