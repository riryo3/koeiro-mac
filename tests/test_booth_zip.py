"""BOOTH 向け1 ZIP（tools/build_booth_zip.py）: 形・上限・sha256 照合の検査。

小さい作りの配布物で組み立て直し、買い手が解凍する形（フラット・無圧縮）を固定する。
実配布物（数百 MB）の SHA は `--check` で同じ関数を通す。
"""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from src.app_update import parse_checksums
from tools import build_booth_zip as booth

TAG = 'v9.9.9'


def digest(path):
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def build_tree(root, windows=('ok', ), linux='ok'):
    """dist/setup・dist/ai-pack・dist/linux と入手案内を並べる。"""
    setup, pack, lnx = root / 'setup', root / 'ai-pack', root / 'linux'
    setup.mkdir(parents=True, exist_ok=True)
    pack.mkdir(parents=True, exist_ok=True)
    lnx.mkdir(parents=True, exist_ok=True)
    guide_dir = root.parent / 'notes'
    guide_dir.mkdir(parents=True, exist_ok=True)

    files = {
        setup / f'koeiro-{TAG}-windows-setup.exe': b'setup',
        pack / f'koeiro-{TAG}-ai-pack.exe': b'aipack',
        pack / f'koeiro-{TAG}-ai-pack-1.bin': b'bin' * 40,
        lnx / f'koeiro-{TAG}-linux-app.tar.gz': b'app',
        lnx / f'koeiro-{TAG}-linux-ai-pack-1.tar.gz': b'one',
        lnx / f'koeiro-{TAG}-linux-ai-pack-2.tar.gz': b'two',
    }
    for path, payload in files.items():
        path.write_bytes(payload)

    (setup / f'koeiro-{TAG}-windows-checksums.txt').write_text(
        f"{digest(setup / f'koeiro-{TAG}-windows-setup.exe')}  koeiro-{TAG}-windows-setup.exe\n",
        'utf-8')
    (pack / f'koeiro-{TAG}-ai-pack-checksums.txt').write_text(
        '\n'.join(f"{digest(pack / name)}  {name}"
                  for name in (f'koeiro-{TAG}-ai-pack.exe', f'koeiro-{TAG}-ai-pack-1.bin')) + '\n',
        'utf-8')
    (lnx / f'koeiro-{TAG}-linux-checksums.txt').write_text(
        '\n'.join(f"{digest(lnx / name)}  {name}" for name in
                  (f'koeiro-{TAG}-linux-app.tar.gz', f'koeiro-{TAG}-linux-ai-pack-1.tar.gz',
                   f'koeiro-{TAG}-linux-ai-pack-2.tar.gz')) + '\n', 'utf-8')

    guide_windows = guide_dir / 'guide-windows.txt'
    guide_linux = guide_dir / 'guide-linux.txt'
    guide_windows.write_text('Windows 入手案内（実測範囲のみ）\n', 'utf-8')
    guide_linux.write_text('Linux 入手案内（実測範囲のみ）\n', 'utf-8')
    if windows == ('bad', ):
        (setup / f'koeiro-{TAG}-windows-setup.exe').write_bytes(b'tampered')
    return {'dist': root, 'guide_windows': guide_windows, 'guide_linux': guide_linux}


def invoke(tree, out, extra=()):
    return booth.main(['--tag', TAG, '--dist', str(tree['dist']), '--out', str(out),
                       '--guide-windows', str(tree['guide_windows']),
                       '--guide-linux', str(tree['guide_linux']), *extra])


def test_the_booth_zip_is_flat_stored_and_complete(tmp_path, capsys):
    tree = build_tree(tmp_path / 'dist')
    out = tmp_path / 'booth'
    assert invoke(tree, out) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'ok'

    windows = out / f'Koeiro_{TAG}_Windows.zip'
    linux = out / f'Koeiro_{TAG}_Linux.zip'
    assert windows.is_file() and linux.is_file()
    with zipfile.ZipFile(windows) as bundle:
        names = [info.filename for info in bundle.infolist()]
        assert names[0] == '入手案内.txt'  # the guide leads, or the buyer opens the wrong file
        assert all(info.compress_type == zipfile.ZIP_STORED for info in bundle.infolist())
        assert '入手案内.txt' in names
        assert not any('/' in name or '\\' in name for name in names)
        assert set(names) == {'入手案内.txt', f'koeiro-{TAG}-windows-setup.exe',
                              f'koeiro-{TAG}-windows-checksums.txt',
                              f'koeiro-{TAG}-ai-pack.exe', f'koeiro-{TAG}-ai-pack-1.bin',
                              f'koeiro-{TAG}-ai-pack-checksums.txt'}
    with zipfile.ZipFile(linux) as bundle:
        assert set(info.filename for info in bundle.infolist()) == {
            '入手案内.txt', f'koeiro-{TAG}-linux-app.tar.gz',
            f'koeiro-{TAG}-linux-ai-pack-1.tar.gz', f'koeiro-{TAG}-linux-ai-pack-2.tar.gz',
            f'koeiro-{TAG}-linux-checksums.txt'}

    recorded = parse_checksums((out / f'Koeiro_{TAG}_booth-checksums.txt').read_text('utf-8'))
    assert set(recorded) == {f'Koeiro_{TAG}_Windows.zip', f'Koeiro_{TAG}_Linux.zip'}
    assert recorded[f'Koeiro_{TAG}_Windows.zip'] == digest(windows)


def test_a_member_that_disagrees_with_its_checksums_stops_the_build(tmp_path, capsys):
    """Uploading a bundle whose inside no longer matches its own checksums is the
    most expensive mistake here: the buyer finds it, not us."""
    tree = build_tree(tmp_path / 'dist', windows=('bad', ))
    assert invoke(tree, tmp_path / 'booth') == 1
    assert 'sha256 が一致しません' in capsys.readouterr().err


def test_a_missing_artifact_is_named(tmp_path, capsys):
    tree = build_tree(tmp_path / 'dist')
    (tree['dist'] / 'linux' / f'koeiro-{TAG}-linux-ai-pack-2.tar.gz').unlink()
    assert invoke(tree, tmp_path / 'booth') == 1
    assert 'linux-ai-pack-2.tar.gz' in capsys.readouterr().err


def test_the_booth_file_limit_is_enforced_before_uploading(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(booth, 'BOOTH_FILE_LIMIT_BYTES', 20)
    tree = build_tree(tmp_path / 'dist')
    assert invoke(tree, tmp_path / 'booth') == 1
    assert '1ファイル上限' in capsys.readouterr().err


def test_check_accepts_the_shipped_shape_and_refuses_a_deflated_member(tmp_path, capsys):
    tree = build_tree(tmp_path / 'dist')
    out = tmp_path / 'booth'
    assert invoke(tree, out) == 0
    capsys.readouterr()
    assert invoke(tree, out, ('--check',)) == 0

    target = out / f'Koeiro_{TAG}_Windows.zip'
    with zipfile.ZipFile(target) as bundle:
        payload = {info.filename: bundle.read(info.filename) for info in bundle.infolist()}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, data in payload.items():
            bundle.writestr(name, data)
    capsys.readouterr()
    assert invoke(tree, out, ('--check',)) == 1
    assert 'stored' in capsys.readouterr().err
