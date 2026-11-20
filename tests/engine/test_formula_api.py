"""Formula candidate detection never replaces the original PDF source."""

import base64
import hashlib

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.core import KnowledgeError
from researchgraph.formula_api import (
    detect_formula_candidates,
    formula_candidate_id,
    persist_formula_recognition,
    register_formula_api,
)
from researchgraph.models import AttachmentRevision, Base, Paper, PaperSource, Project
from researchgraph.structure_models import DocumentParse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def formula_document():
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((200, 160), "x_u^(l) = ReLU(W_self x_u^(l-1) + sum_i w_ui)", fontsize=14)
    page.insert_text((220, 260), "This ordinary sentence contains a = b but is prose.", fontsize=11)
    return document


def test_detect_formula_candidates_keeps_source_text_and_no_latex():
    with formula_document() as document:
        candidates = detect_formula_candidates(document, "revision")
    assert candidates
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.page == 1
    assert candidate.source_text_hash == hashlib.sha256(candidate.source_text.encode()).hexdigest()
    assert candidate.latex is None
    assert candidate.status == "latex_unavailable"
    assert candidate.bbox[2] > candidate.bbox[0]


def test_formula_routes_require_same_sha_source_and_render_original_crop(tmp_path):
    with formula_document() as document:
        content = document.tobytes()
    source = tmp_path / "source.pdf"
    source.write_bytes(content)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    digest = hashlib.sha256(content).hexdigest()
    with Session(engine) as session, session.begin():
        session.add(Project(id="project", name="Synthetic", description="", created_at="now"))
        session.add(Paper(id="paper", project_id="project", title="Synthetic", created_at="now"))
        session.add(
            AttachmentRevision(
                id="revision",
                paper_id="paper",
                sha256=digest,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="now",
            )
        )
        session.add(
            PaperSource(
                id="source",
                paper_id="paper",
                revision_id="revision",
                path=str(source),
                mode="reference",
                managed_path=None,
                generation=1,
                last_check=None,
            )
        )
    app = FastAPI()
    register_formula_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    listed = client.get("/api/v1/revisions/revision/formulas")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["source_sha256"] == digest
    assert payload["items"]
    assert payload["items"][0]["latex"] is None
    formula_id = payload["items"][0]["id"]
    image = client.get(f"/api/v1/revisions/revision/formulas/{formula_id}/image")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content.startswith(b"\x89PNG")
    preview = client.get(f"/api/v1/revisions/revision/formulas/{formula_id}/preview")
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["mime_type"] == "image/png"
    assert preview_payload["formula_id"] == formula_id
    assert preview_payload["revision_id"] == "revision"
    assert preview_payload["source_text_hash"] == payload["items"][0]["source_text_hash"]
    assert base64.b64decode(preview_payload["data_base64"]).startswith(b"\x89PNG")
    recognition = client.post(
        "/api/v1/revisions/revision/formulas/recognize",
        json={},
    )
    assert recognition.status_code == 200, recognition.text
    recognition_payload = recognition.json()
    assert recognition_payload["status"] == "unavailable"
    assert recognition_payload["model_calls"] == 0
    assert recognition_payload["items"][0]["error_code"] == "FORMULA_RECOGNIZER_UNAVAILABLE"
    assert recognition_payload["reading_document_refresh_required"] is False
    engine.dispose()


def test_formula_recognition_persists_in_versioned_structure_and_is_reused(tmp_path):
    with formula_document() as document:
        content = document.tobytes()
        candidates = detect_formula_candidates(document, "revision")
    source = tmp_path / "source.pdf"
    source.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    candidate = candidates[0]
    with Session(engine) as session, session.begin():
        session.add(Project(id="project", name="Synthetic", description="", created_at="now"))
        session.add(Paper(id="paper", project_id="project", title="Synthetic", created_at="now"))
        session.add(
            AttachmentRevision(
                id="revision",
                paper_id="paper",
                sha256=digest,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="now",
            )
        )
        session.add(
            PaperSource(
                id="source",
                paper_id="paper",
                revision_id="revision",
                path=str(source),
                mode="reference",
                managed_path=None,
                generation=1,
                last_check=None,
            )
        )
        session.add(
            DocumentParse(
                id="parse",
                document_version_id="revision",
                parser_version="synthetic;structure-v2",
                source_sha256=digest,
                data={
                    "schema_version": "pdf-structure-1",
                    "parser_version": "synthetic;structure-v2",
                    "sections": [],
                    "blocks": [],
                    "formulas": [
                        {
                            "id": "formula-unbound",
                            "formula_id": "formula-unbound",
                            "page_index": candidate.page - 1,
                            "bbox": candidate.bbox,
                            "text": candidate.source_text,
                            "source_text_hash": candidate.source_text_hash,
                            "confidence": candidate.confidence,
                            "status": "latex_unavailable",
                        }
                    ],
                },
                created_at="now",
            )
        )
        saved = persist_formula_recognition(
            session,
            "revision",
            formula_candidate_id(
                "revision", candidate.page - 1, candidate.bbox, candidate.source_text
            ),
            latex=r"x_u^{(l)} = \\operatorname{ReLU}(W_{self}x_u^{(l-1)})",
            status="recognized",
            confidence="high",
            recognizer="synthetic-formula-ocr",
            recognizer_config_hash="config-hash",
        )
        assert saved["status"] == "recognized"
        assert saved["recognition_source_sha256"] == digest
        assert saved["recognition_source_text_hash"] == candidate.source_text_hash

    class FakeRecognizer:
        name = "synthetic-formula-ocr"
        config_hash = "config-hash"

        def __call__(self, _image, _candidate):
            from researchgraph.formula_api import LocalRecognition

            return LocalRecognition(
                status="recognized",
                latex=r"x_u^{(l)} = \\operatorname{ReLU}(W_{self}x_u^{(l-1)})",
                recognizer=self.name,
                message="synthetic",
            )

    app = FastAPI()
    register_formula_api(app, lambda: engine, tmp_path, FakeRecognizer())
    client = TestClient(app)
    rerun = client.post(
        "/api/v1/revisions/revision/formulas/recognize",
        json={"force": True},
    )
    assert rerun.status_code == 200, rerun.text
    rerun_payload = rerun.json()
    assert rerun_payload["status"] == "completed"
    assert rerun_payload["model_calls"] == 0
    assert rerun_payload["reading_document_refresh_required"] is True
    listed = client.get("/api/v1/revisions/revision/formulas")
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["status"] == "recognized"
    assert item["latex"].startswith("x_u")
    assert item["recognizer"] == "synthetic-formula-ocr"
    assert item["recognizer_config_hash"] == "config-hash"
    engine.dispose()


def test_formula_recognition_rejects_stale_revision_or_missing_formula(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Project(id="project", name="Synthetic", description="", created_at="now"))
        session.add(Paper(id="paper", project_id="project", title="Synthetic", created_at="now"))
        session.add(
            AttachmentRevision(
                id="revision",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="now",
            )
        )
        session.add(
            DocumentParse(
                id="parse",
                document_version_id="revision",
                parser_version="synthetic;structure-v2",
                source_sha256="a" * 64,
                data={"formulas": []},
                created_at="now",
            )
        )
        with pytest.raises(KnowledgeError) as error:
            persist_formula_recognition(
                session,
                "revision",
                "formula-missing",
                latex="x",
                status="recognized",
                confidence="high",
                recognizer="synthetic",
            )
        assert error.value.code == "FORMULA_NOT_FOUND"
        revision = session.get(AttachmentRevision, "revision")
        assert revision is not None
        revision.sha256 = "b" * 64
        with pytest.raises(KnowledgeError) as stale:
            persist_formula_recognition(
                session,
                "revision",
                "formula-missing",
                latex="x",
                status="recognized",
                confidence="high",
                recognizer="synthetic",
            )
        assert stale.value.code == "FORMULA_STRUCTURE_UNAVAILABLE"
    engine.dispose()
