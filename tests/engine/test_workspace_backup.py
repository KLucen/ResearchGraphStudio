import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from researchgraph.knowledge_connection_models import KnowledgeAnalysisEvent
from researchgraph.knowledge_library import ensure_library
from researchgraph.models import AttachmentRevision, Paper, PaperSource, now
from researchgraph.workspace_backup import (
    WorkspaceBackupError,
    backup_file_path,
    export_workspace,
    restore_workspace,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post


def test_complete_backup_restores_pdf_and_disables_automatic_dispatch(tmp_path):
    original = tmp_path / "original"
    export_root = tmp_path / "backup root"
    export_root.mkdir()
    pdf = (Path(__file__).parent.parent / "fixtures" / "pdf" / "two-pages.pdf").read_bytes()
    sha = hashlib.sha256(pdf).hexdigest()
    paper_id, revision_id, event_id = (str(uuid4()) for _ in range(3))
    with client(original) as api:
        project_id = post(api, "/projects", {"name": "Anonymous project"}).json()["id"]
        attached = original / "attachments" / f"{sha}.pdf"
        attached.parent.mkdir()
        attached.write_bytes(pdf)
        with Session(api.app.state.engine) as db, db.begin():
            library = ensure_library(db)
            library.settings_json = {"auto_connect": True, "allow_network": True}
            db.add(KnowledgeAnalysisEvent(version_id=event_id, state="pending"))
            db.add(
                Paper(id=paper_id, project_id=project_id, title="Anonymous paper", created_at=now())
            )
            db.flush()
            db.add(
                AttachmentRevision(
                    id=revision_id,
                    paper_id=paper_id,
                    sha256=sha,
                    parser_version="fixture",
                    page_count=2,
                    warnings=[],
                    created_at=now(),
                )
            )
            db.flush()
            for mode, managed_path in (("managed", str(attached)), ("reference", None)):
                db.add(
                    PaperSource(
                        id=str(uuid4()),
                        paper_id=paper_id,
                        revision_id=revision_id,
                        path=str(tmp_path / f"external-{mode}.pdf"),
                        mode=mode,
                        managed_path=managed_path,
                    )
                )
        with pytest.raises(WorkspaceBackupError, match="仍在运行"):
            export_workspace(original, export_root)

    made = export_workspace(original, export_root)
    backup = Path(made["path"])
    assert made["managed_files"] == made["external_sources"] == 1
    assert backup_file_path(backup / "attachments" / attached.name).read_bytes() == pdf
    assert (
        json.loads((backup / "workspace-backup.json").read_text(encoding="utf-8"))["format_version"]
        == 1
    )
    restored = tmp_path / "restored research"
    result = restore_workspace(backup, restored)
    assert result["managed_files"] == 1
    with client(restored) as api:
        assert api.get(f"/api/v1/papers/{paper_id}").json()["paper"]["title"] == "Anonymous paper"
        with Session(api.app.state.engine) as db:
            assert not ensure_library(db).settings_json["allow_network"]
            assert db.get(KnowledgeAnalysisEvent, event_id).state == "revoked"
            restored_source = db.scalar(select(PaperSource).where(PaperSource.mode == "managed"))
            assert Path(restored_source.managed_path) == restored / "attachments" / attached.name
            assert Path(restored_source.managed_path).read_bytes() == pdf
        assert len(api.get("/api/v1/jobs").json()) == 0

    assert attached.read_bytes() == pdf
    tampered = backup_file_path(backup / "attachments" / attached.name)
    tampered.write_bytes(b"!" + pdf[1:])
    refused = tmp_path / "rejected"
    with pytest.raises(WorkspaceBackupError, match="PDF 指纹"):
        restore_workspace(backup, refused)
    assert not refused.exists()
    assert not list(tmp_path.glob(".researchgraph-restoring-*"))
