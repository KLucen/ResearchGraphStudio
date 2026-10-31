import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from researchgraph import ingest
from researchgraph.workspaces import MARKER, clean_workspace, create_workspace, recover_workspaces
from test_engine import client, post
from test_ingest import FIXTURES, queue, wait_job


def test_recovery_only_reclaims_owned_flat_temporary_files(tmp_path):
    work = create_workspace(tmp_path)
    (work / "snapshot.pdf").write_bytes(b"temporary PDF")
    (work / "result.json").write_text("{}")
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    for name in ("historical.pdf", "current.pdf", "shared.pdf"):
        (attachments / name).write_bytes(b"keep attachment")
    original = tmp_path / "original.pdf"
    original.write_bytes(b"keep original")
    legacy = work.parent / str(uuid4())
    legacy.mkdir()
    (legacy / "snapshot.pdf").write_bytes(b"unknown ownership")
    unknown = create_workspace(tmp_path)
    (unknown / "private.txt").write_bytes(b"keep unknown content")
    with client(tmp_path) as api:
        report = api.get("/api/v1/health").json()["temporary_files"]
        assert report == {"removed": 1, "busy": 0, "retained": 2, "errors": 0}
        assert not work.exists()
        assert original.read_bytes() == b"keep original"
        assert all(p.read_bytes() == b"keep attachment" for p in attachments.iterdir())
        assert (legacy / "snapshot.pdf").read_bytes() == b"unknown ownership"
        assert (unknown / "private.txt").read_bytes() == b"keep unknown content"
    assert recover_workspaces(tmp_path).removed == 0


def test_live_child_lease_survives_engine_recovery_then_is_reclaimed(tmp_path):
    work = create_workspace(tmp_path)
    script = (
        "import sys,time; from pathlib import Path; "
        "from researchgraph.workspaces import worker_workspace,report_stage; "
        "work=Path(sys.argv[1]); "
        "\nwith worker_workspace(work):\n report_stage(work,'parsing'); time.sleep(60)\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "services/engine")}
    child = subprocess.Popen([sys.executable, "-c", script, str(work)], env=environment)
    try:
        deadline = time.monotonic() + 5
        while not (work / "stage.json").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (work / "stage.json").exists()
        with client(tmp_path) as api:
            assert api.get("/api/v1/health").json()["temporary_files"]["busy"] == 1
            assert work.exists()
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert recover_workspaces(tmp_path).removed == 1
    late = subprocess.run(
        [sys.executable, "-c", script, str(work)], env=environment, capture_output=True
    )
    assert late.returncode != 0 and not work.exists()


def junction(link: Path, target: Path):
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("location", ["root", "workspace", "inside"])
def test_directory_links_never_delete_external_files(tmp_path, location):
    data, outside = tmp_path / "data", tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    (outside / "result.json").write_bytes(b"external content")
    if location == "root":
        junction(data / "import-work", outside)
    elif location == "workspace":
        (data / "import-work").mkdir()
        junction(data / "import-work" / str(uuid4()), outside)
    else:
        work = create_workspace(data)
        junction(work / "snapshot.pdf", outside)
    assert recover_workspaces(data).retained == 1
    assert (outside / "result.json").read_bytes() == b"external content"


def test_lease_link_never_touches_external_file(tmp_path):
    work = create_workspace(tmp_path)
    outside = tmp_path / "outside.lock-target"
    outside.write_bytes(b"external content")
    lock = work.with_suffix(".lock")
    try:
        lock.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("file symlinks are unavailable")
    assert clean_workspace(work) == "errors"
    assert outside.read_bytes() == b"external content"
    assert (work / MARKER).exists()


def test_lease_hardlink_never_touches_external_file(tmp_path):
    work = create_workspace(tmp_path)
    outside = tmp_path / "outside.hardlink-target"
    outside.write_bytes(b"external content")
    lock = work.with_suffix(".lock")
    try:
        os.link(outside, lock)
    except OSError:
        pytest.skip("hard links are unavailable")
    assert clean_workspace(work) == "errors"
    assert outside.read_bytes() == b"external content"
    assert (work / MARKER).exists()


@pytest.mark.parametrize("operation", ["unlink", "rmdir"])
def test_cleanup_permission_failure_keeps_marker_for_retry(tmp_path, monkeypatch, operation):
    work = create_workspace(tmp_path)
    snapshot = work / "snapshot.pdf"
    snapshot.write_bytes(b"temporary")
    original = getattr(Path, operation)

    def denied(path, *args, **kwargs):
        if path == (snapshot if operation == "unlink" else work):
            raise PermissionError("injected permission denial")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, denied)
    assert clean_workspace(work) == "errors"
    assert (work / MARKER).exists()
    monkeypatch.undo()
    assert clean_workspace(work) == "removed"


def test_cleanup_failure_does_not_change_success_and_restart_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "clean_workspace", lambda _work: "errors")
    with client(tmp_path, worker=True) as api:
        project = post(api, "/projects", {"name": "cleanup after commit"}).json()["id"]
        job = wait_job(
            api, queue(api, project, FIXTURES / "two-pages.pdf", "cleanup-error", "managed")
        )
        assert job["status"] == "succeeded" and job["stage"] == "saving"
        paper = api.get(f"/api/v1/papers/{job['result']['paper_id']}").json()
    with client(tmp_path) as api:
        assert api.get("/api/v1/health").json()["temporary_files"]["removed"] == 1
        assert api.get(f"/api/v1/papers/{job['result']['paper_id']}").json() == paper
        assert api.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"
    assert len(list((tmp_path / "attachments").glob("*.pdf"))) == 1


def test_progress_file_sharing_failure_does_not_fail_pdf_parsing(tmp_path, monkeypatch):
    replace = Path.replace

    def deny_progress(path, target):
        if Path(target).name == "stage.json":
            raise PermissionError("progress file temporarily busy")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", deny_progress)
    ingest.parse_pdf(str(FIXTURES / "two-pages.pdf"), str(tmp_path))
    assert (tmp_path / "result.json").is_file()
    assert not (tmp_path / "error.txt").exists()
