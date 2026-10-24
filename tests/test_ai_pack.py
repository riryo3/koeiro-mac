"""AI voice pack staging: only the weights the route loads, no venv, no CC BY-NC encodec."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

from tools import build_ai_pack
from tools.build_ai_pack import SetupError, DEFAULT_VOICE as VOICE


def _touch(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fake_source(tmp_path):
    root = tmp_path / "repo"
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        _touch(root / name, "doc")
    repo = root / "vc_models/meanvc2/repo"
    _touch(repo / "src/infer/infer_e2e.py")
    _touch(repo / "src/model/cfm.py")
    _touch(repo / "preprocess/audio.py")
    _touch(repo / "preprocess/models/ecapa_tdnn.py")
    for name in ("fastu2pp_160ms.pt", "fastu2pp_80ms.pt", "wavlm_large.pt",
                 "wavlm_large_finetune.pth"):
        _touch(repo / "preprocess/ckpts" / name)
    _touch(repo / "ckpts/vocos/vocos.pt")
    _touch(repo / "ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors")
    _touch(repo / "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors")
    _touch(repo / "figs/diagram.png")
    _touch(repo / "defaults.ini")
    _touch(repo / "default_config.yaml")
    lavasr = root / "vc_models/post_lavasr"
    _touch(lavasr / "repo/LavaSR/model.py")
    _touch(lavasr / "weights/lavasr.pt")
    _touch(lavasr / "vendor/vocos/feature_extractors.py")
    _touch(lavasr / "vendor/encodec/__init__.py")
    _touch(lavasr / "vendor/encodec/model.py")
    _touch(lavasr / "vendor/encodec-0.1.1.dist-info/METADATA")
    _touch(lavasr / "vendor/bin/encodec.exe")
    voice_dir = root / "models/user_voices" / VOICE
    _touch(voice_dir / "reference.wav")
    _touch(voice_dir / "fixed_embedding.npy")
    _touch(voice_dir / "profile.json")
    entries = [
        {"path": "vc_models/meanvc2/repo/preprocess/ckpts/fastu2pp_160ms.pt"},
        {"path": "vc_models/meanvc2/repo/ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors"},
        {"path": "vc_models/meanvc2/repo/ckpts/vocos/vocos.pt"},
        {"path": f"models/user_voices/{VOICE}/reference.wav"},
        {"path": f"models/user_voices/{VOICE}/fixed_embedding.npy"},
    ]
    for entry in entries:
        entry["sha256"] = hashlib.sha256(b"x").hexdigest()
    (voice_dir / "runtime.json").write_text(json.dumps(
        {"backend": "meanvc2", "assets": entries}, ensure_ascii=False), "utf-8")
    _touch(root / "models/user_voices/user_other/reference.wav")
    worker = tmp_path / "dist/KoeiroWorker"
    _touch(worker / "KoeiroWorker.exe", "MZ")
    _touch(worker / "_internal_worker/torch/libtorch_cpu.dll", "dll")
    _touch(worker / "_internal_worker/src/vc/service.py", "code")
    return root, worker


def test_stage_pack_ships_the_route_weights_and_nothing_else(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    assert (stage / "KoeiroWorker.exe").is_file()
    assert (stage / "_internal_worker/torch/libtorch_cpu.dll").is_file()
    kept = "vc_models/meanvc2/repo/"
    assert (stage / (kept + "preprocess/ckpts/fastu2pp_160ms.pt")).is_file()
    assert (stage / (kept + "ckpts/vocos/vocos.pt")).is_file()
    assert (stage / (kept + "src/infer/infer_e2e.py")).is_file()
    for absent in (kept + "preprocess/ckpts/wavlm_large.pt",
                   kept + "preprocess/ckpts/wavlm_large_finetune.pth",
                   kept + "preprocess/ckpts/fastu2pp_80ms.pt",
                   kept + "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors",
                   kept + "figs/diagram.png",
                   "vc_models/post_lavasr/vendor/bin/encodec.exe",
                   "models/user_voices/user_other/reference.wav"):
        assert not (stage / absent).exists(), absent
    assert count >= 15


def test_stage_pack_replaces_encodec_with_a_raising_stub(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    stub = stage / "vc_models/post_lavasr/vendor/encodec/__init__.py"
    assert stub.is_file()
    assert "encodec is not distributed with Koeiro" in stub.read_text("utf-8")
    assert not (stage / "vc_models/post_lavasr/vendor/encodec/model.py").exists()
    assert not (stage / "vc_models/post_lavasr/vendor/encodec-0.1.1.dist-info").exists()
    build_ai_pack.check_stage(stage)


def test_encodec_stub_imports_like_a_package_and_refuses_use(tmp_path):
    """vocos does `from encodec import EncodecModel`, so the stand-in must import."""
    import importlib
    import sys

    package = tmp_path / "encodec"
    package.mkdir()
    (package / "__init__.py").write_text(build_ai_pack.ENCODEC_STUB, "utf-8")
    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("encodec", None)
    try:
        module = importlib.import_module("encodec")
        assert [str(Path(item)) for item in module.__path__] == [str(package)]
        with pytest.raises(NotImplementedError):
            module.EncodecModel()
        with pytest.raises(NotImplementedError):
            module.EncodecModel.encodec_model_24khz()
        with pytest.raises(AttributeError):
            module.some_unknown_name
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("encodec", None)


def test_manifest_records_the_pack_contract(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    manifest = build_ai_pack.write_manifest(stage, "v9.9.9", "a" * 64)
    build_ai_pack.check_stage(stage)
    on_disk = json.loads((stage / "koeiro-ai-pack.json").read_text("utf-8"))
    assert on_disk == manifest
    assert on_disk["version"] == "9.9.9"
    assert on_disk["requires"]["app_asset"] == "koeiro-v9.9.9-windows-setup.exe"
    assert on_disk["worker_sha256"] == "a" * 64
    assert any("encodec" in item for item in on_disk["excluded"])


def test_a_tampered_checkpoint_stops_the_pack(tmp_path):
    """runtime.json pins the weights; a pack that does not match them must not build."""
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    build_ai_pack.check_stage(stage)
    victim = stage / "vc_models/meanvc2/repo/ckpts/vocos/vocos.pt"
    victim.write_text("tampered", "utf-8")
    with pytest.raises(SetupError) as caught:
        build_ai_pack.check_stage(stage)
    assert "sha256" in str(caught.value)


def test_check_stage_refuses_a_real_encodec_and_a_build_root(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    _touch(stage / "vc_models/post_lavasr/vendor/encodec/model.py")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)
    _touch(stage / "_internal_worker/koeiro-root.txt", "D:/dev")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)


def test_check_stage_refuses_a_missing_torch_or_worker(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    shutil.rmtree(stage / "_internal_worker/torch")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)
    with pytest.raises(SetupError):
        build_ai_pack.stage_pack(root, tmp_path / "absent", tmp_path / "stage2")


def test_the_linux_manifest_names_the_linux_artifacts(tmp_path):
    """The same staging builds the Linux pack, so the manifest has to follow."""
    root, worker = _fake_source(tmp_path)
    (worker / "KoeiroWorker").write_bytes(b"\x7fELF")
    stage, _count, _total = build_ai_pack.stage_pack(
        root, worker, tmp_path / "stage", tag="v9.9.9",
        worker_exe="KoeiroWorker", contents_dir="_internal_worker")
    build_ai_pack.check_stage(stage, worker_exe="KoeiroWorker")
    manifest = json.loads((stage / "koeiro-ai-pack.json").read_text("utf-8"))
    assert manifest["worker"] == "KoeiroWorker"
    assert manifest["requires"]["app_asset"] == "koeiro-v9.9.9-linux-app.tar.gz"
    assert manifest["contents"][0] == "KoeiroWorker"
    assert build_ai_pack.app_asset("v1.2.3", "KoeiroWorker.exe") == \
        "koeiro-v1.2.3-windows-setup.exe"


def test_pack_asset_names():
    assert build_ai_pack.pack_name("v1.2.3") == "koeiro-v1.2.3-ai-pack-checksums.txt"


def test_linux_build_script_is_the_same_for_docker_and_a_bare_host():
    """One script text, two transports: stdout tar in a container, a file path on CI."""
    from tools import build_linux_bundles

    app = build_linux_bundles._script("app", root="/work", apt=True)
    assert "cd /work" in app
    assert "Koeiro.spec" in app
    assert "tar -C /tmp/dist -czf - Koeiro" in app
    # The container is root, so it carries its own runtime libraries; a CI runner
    # installs the same list in its own step and the script must not try to run apt.
    assert " ".join(build_linux_bundles.RUNTIME_APT) in app
    local = build_linux_bundles._script("app", root="/work")
    assert "apt-get" not in local
    worker = build_linux_bundles._script("worker", root="/repo", tar="/out/worker.tar.gz")
    assert "cd /repo" in worker
    assert "KoeiroWorker.spec" in worker
    assert "requirements.lock.txt" in worker and "--extra-index-url" in worker
    assert "tar -C /tmp/dist -czf /out/worker.tar.gz KoeiroWorker" in worker
    # Every step but the tar stays off stdout, or the gzip stream corrupts.
    assert "--workpath /tmp/pb 1>&2" in worker


def test_the_extracted_worker_tar_is_staged_from_its_inner_folder(tmp_path, monkeypatch):
    """The tar has one top folder, so the staged worker dir is one level down."""
    from src.version import APP_VERSION
    from tools import build_linux_bundles as bundles

    seen = {}

    def fake_build_bundle(kind, root, out_path, timeout, engine):
        Path(out_path).write_bytes(b"\x1f\x8b fake")

    monkeypatch.setattr(bundles, "require_docker", lambda root: None)
    monkeypatch.setattr(bundles, "build_bundle", fake_build_bundle)
    monkeypatch.setattr(bundles, "extract",
                        lambda tar_path, destination: Path(destination))
    monkeypatch.setattr(bundles, "build_pack",
                        lambda root, tag, bundle, out_dir, stage_dir:
                        seen.update(bundle=Path(bundle)) or ([], {"files": 0, "raw_bytes": 0}))
    code = bundles.main(["--tag", "v" + APP_VERSION, "--kind", "worker", "--engine", "docker",
                         "--root", str(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 0
    assert seen["bundle"] == tmp_path / "build" / "linux-worker" / "KoeiroWorker"
    assert seen["bundle"].name == "KoeiroWorker"  # stage_pack wants the folder holding the exe


@pytest.mark.skipif(not (shutil.which("sh") and shutil.which("sha256sum") and shutil.which("tar")),
                    reason="sh / sha256sum / tar が無い環境（Windows の CI など）では飛ぶ")
def test_install_ai_pack_verifies_only_the_pack_files_it_has(tmp_path):
    """A buyer who keeps every download in one folder must still pass the checksum check."""
    from tools import build_linux_bundles as bundles

    app = tmp_path / "Koeiro"
    app.mkdir()
    (app / "Koeiro").write_text("#!/bin/sh\n", "utf-8")
    pack = tmp_path / "downloads"
    pack.mkdir()
    for number, member in ((1, "KoeiroWorker"), (2, "vc_models")):
        name = f"koeiro-v9.9.9-linux-ai-pack-{number}.tar.gz"
        inner = tmp_path / f"payload-{number}"
        inner.mkdir()
        (inner / member).write_text(f"content {member}\n", "utf-8")
        with tarfile.open(pack / name, "w:gz") as bundle:
            bundle.add(inner / member, arcname=member)  # the real parts unpack at the root
    lines = [f"{hashlib.sha256((pack / name).read_bytes()).hexdigest()}  {name}"
             for name in ("koeiro-v9.9.9-linux-ai-pack-1.tar.gz",
                          "koeiro-v9.9.9-linux-ai-pack-2.tar.gz")]
    lines.append("0" * 64 + "  koeiro-v9.9.9-linux-app.tar.gz")  # not in this folder
    (pack / "koeiro-v9.9.9-linux-checksums.txt").write_text("\n".join(lines) + "\n", "ascii")
    # Two checksums files in one folder is the normal CI shape (app job and pack job
    # each write their own); grep must not prefix matches with the file name.
    (pack / "koeiro-v9.9.9-linux-ai-pack-checksums.txt").write_text("\n".join(lines[:2]) + "\n",
                                                                   "ascii")
    script = pack / "install-ai-pack.sh"
    script.write_text(bundles.INSTALL_SCRIPT, "utf-8", newline="\n")

    # Git Bash's tar takes the target as a forward-slash path; backslashes come out mangled
    done = subprocess.run(["sh", str(script), app.as_posix()], cwd=pack, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (app / "KoeiroWorker").read_text("utf-8") == "content KoeiroWorker\n"
    assert (app / "vc_models").read_text("utf-8") == "content vc_models\n"


def test_only_a_set_with_the_app_bundle_may_write_the_bundle_checksums():
    """CI uploads from two jobs into one release; the pack job must not clobber the app line."""
    from tools import build_linux_bundles as bundles

    pack = [Path("koeiro-v1.2.3-linux-ai-pack-1.tar.gz"),
            Path("koeiro-v1.2.3-linux-ai-pack-2.tar.gz")]
    assert bundles.checksums_name("v1.2.3", pack) == "koeiro-v1.2.3-linux-ai-pack-checksums.txt"
    with_app = pack + [Path("koeiro-v1.2.3-linux-app.tar.gz")]
    assert bundles.checksums_name("v1.2.3", with_app) == "koeiro-v1.2.3-linux-checksums.txt"


def test_the_pack_tar_keeps_the_worker_executable(tmp_path):
    """NTFS records no exec bit, so the pack must restate it or the buyer can't start it."""
    from tools import build_linux_bundles as bundles

    stage = tmp_path / "stage"
    (stage / "_internal_worker").mkdir(parents=True)
    for name in ("KoeiroWorker", "install-ai-pack.sh", "README.md"):
        (stage / name).write_text("x\n", "utf-8")
    (stage / "_internal_worker" / "base.so").write_text("x\n", "utf-8")
    tar = tmp_path / "koeiro-v9.9.9-linux-ai-pack-1.tar.gz"
    bundles.tar_stream(tar, stage, ".", members=("KoeiroWorker", "install-ai-pack.sh",
                                                 "README.md", "_internal_worker"))
    with tarfile.open(tar, "r:gz") as bundle:
        modes = {member.name: member.mode & 0o111 for member in bundle.getmembers()
                 if member.isfile()}
    assert modes["KoeiroWorker"] == 0o111
    assert modes["install-ai-pack.sh"] == 0o111
    assert modes["README.md"] == 0
    assert modes["_internal_worker/base.so"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows では Docker 以外選べない")
def test_local_engine_refuses_to_run_on_windows(tmp_path):
    from tools import build_linux_bundles
    with pytest.raises(SetupError):
        build_linux_bundles.build_local("app", tmp_path, tmp_path / "out.tar.gz", 60)


def test_the_linux_runtime_library_list_has_one_source():
    """The apt list is `RUNTIME_APT`; the CI job and the README used to copy it.

    The verification container had the seven package names written out a second time
    (the file's own comment warns that one of the two then goes stale), and the
    README's Linux source-tree install omitted the Qt libraries entirely, so a clean
    Debian box followed the doc and PySide6 refused to start.
    """
    from tools import build_linux_bundles
    root = Path(__file__).resolve().parents[1]
    packages = set(build_linux_bundles.RUNTIME_APT)
    # Every workflow file is read: merging or renaming them must not drop the guard.
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    assert workflows, ".github/workflows にワークフローがありません"
    combined = "\n".join(path.read_text("utf-8") for path in workflows)
    assert "steps.runtime-apt.outputs.packages" in combined
    for package in packages:
        assert combined.count(package) <= 1, f"{package} copied into the workflow again"

    readme = (root / "README.md").read_text("utf-8").splitlines()
    command = []
    continuation = chr(92)  # the shell line-continuation the README command uses
    for line_number, line in enumerate(readme):
        if line.strip().startswith("sudo apt install"):
            command, cursor = [], line_number
            while True:
                command.append(readme[cursor].strip().rstrip(continuation))
                if not readme[cursor].rstrip().endswith(continuation):
                    break
                cursor += 1
            break
    assert command, "the README no longer shows a Linux apt install command"
    joined = " ".join(command)
    missing = sorted(package for package in packages if package not in joined)
    assert not missing, f"README Linux setup is missing {missing}"


def test_checksums_mode_merges_the_three_linux_parts(tmp_path, capsys):
    """The app job and the pack job run apart, so the shipping sheet is written here.

    Both consumers exist: the in-app updater reads the app row out of
    `koeiro-<tag>-linux-checksums.txt`, and install-ai-pack.sh greps the pack rows
    out of the sheet it finds. A pack-only sheet would leave the packs unverified
    at install time.
    """
    from tools import build_linux_bundles as bundles
    out = tmp_path / "linux"
    out.mkdir()
    parts = ["koeiro-v9.9.9-linux-app.tar.gz", "koeiro-v9.9.9-linux-ai-pack-1.tar.gz",
             "koeiro-v9.9.9-linux-ai-pack-2.tar.gz"]
    for name in parts:
        (out / name).write_bytes(name.encode("utf-8"))
    (out / "koeiro-v9.9.9-linux-ai-pack-checksums.txt").write_text("x\n", "utf-8")
    assert bundles.main(["--tag", "v9.9.9", "--kind", "checksums",
                         "--out", str(out), "--root", str(tmp_path)]) == 0
    sheet = out / "koeiro-v9.9.9-linux-checksums.txt"
    rows = [line.split("  ", 1)[1] for line in sheet.read_text("utf-8").splitlines()]
    assert rows == parts
    assert not (out / "koeiro-v9.9.9-linux-ai-pack-checksums.txt").exists()
    assert "checksums" in capsys.readouterr().out


def test_checksums_mode_names_the_parts_that_are_missing(tmp_path, capsys):
    from tools import build_linux_bundles as bundles
    out = tmp_path / "linux"
    out.mkdir()
    (out / "koeiro-v9.9.9-linux-app.tar.gz").write_bytes(b"app")
    assert bundles.main(["--tag", "v9.9.9", "--kind", "checksums",
                         "--out", str(out), "--root", str(tmp_path)]) == 1
    assert "linux-ai-pack-1.tar.gz" in capsys.readouterr().out
