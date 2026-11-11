import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.core import KnowledgeError, digest
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import record_usage
from researchgraph.model_settings import ModelConnection, ModelProfile
from researchgraph.models import (
    AttachmentRevision,
    Base,
    Chunk,
    Job,
    Paper,
    PaperSource,
    Project,
    now,
)
from researchgraph.translation_api import (
    _identity,
    _save_outputs,
    cancel_translation_job,
    execute_translation,
    recover_translations,
    register_translation_api,
)
from researchgraph.translation_contracts import TranslationHealth
from researchgraph.translation_models import PDFTranslation, PDFTranslationSettings
from researchgraph.translation_proxy import TranslationProxy as RealTranslationProxy
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

HTTP_CLIENT = httpx.AsyncClient


def pdf_bytes() -> bytes:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "A synthetic paper for translation tests.")
        return document.tobytes()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, source_id, connection_id, profile_id = (
        str(uuid4()) for _ in range(6)
    )
    source = tmp_path / "synthetic.pdf"
    content = pdf_bytes()
    source.write_bytes(content)
    with Session(engine) as session, session.begin():
        session.add(
            Project(id=project_id, name="translation", description="test", created_at=now())
        )
        session.add(Paper(id=paper_id, project_id=project_id, title="Synthetic", created_at=now()))
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256=hashlib.sha256(content).hexdigest(),
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.add(
            PaperSource(
                id=source_id,
                paper_id=paper_id,
                revision_id=revision_id,
                path=str(source),
                mode="reference",
                generation=1,
                managed_path=None,
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="A synthetic paper.",
                bbox=[0, 0, 100, 100],
            )
        )
        session.add(
            ModelConnection(
                id=connection_id,
                project_id=None,
                name="test",
                provider="compatible",
                base_url="https://example.invalid/v1",
                credential_ref=None,
                secret_refs=[],
                active=True,
                updated_at=now(),
            )
        )
        session.add(
            ModelProfile(
                id=profile_id,
                project_id=None,
                connection_id=connection_id,
                name="model",
                provider="compatible",
                base_url="https://example.invalid/v1",
                model="test-model",
                parameters={"temperature": 0},
                credential_ref=None,
                secret_refs=[],
                active=True,
                updated_at=now(),
            )
        )
        session.add(
            PDFTranslationSettings(
                id="global",
                enabled=True,
                service_url="http://127.0.0.1:8890",
                launch_mode="manual",
            )
        )

    class FakeBridge:
        instances = []
        submissions = 0
        busy = False
        invalid_pdf = False
        before_poll = None
        names_bad = False
        zero_usage = False
        downloads = []
        missing_output = False

        def __init__(
            self, service_url, *, before_request=None, service_token=None, expected_version="4.1.8"
        ):
            self.service_url = service_url
            self.before_request = before_request
            self.service_token = service_token
            self.expected_version = expected_version
            type(self).instances.append(self)

        async def guard(self):
            if self.before_request is not None:
                await self.before_request()

        async def check(self):
            await self.guard()
            return TranslationHealth(
                available=True,
                status="ready",
                version=self.expected_version,
                active_tasks=int(self.busy),
                message="ready",
            )

        async def submit(self, payload, stem, proxy_url, proxy_token, model, *, output_mode="both"):
            await self.guard()
            assert payload == content
            assert proxy_token == "task-only-token"
            assert proxy_url.startswith("http://127.0.0.1:")
            type(self).submissions += 1
            if not self.zero_usage:
                with Session(engine) as session, session.begin():
                    record_usage(
                        session,
                        project_id=project_id,
                        paper_id=paper_id,
                        document_version_id=revision_id,
                        task_kind="pdf_translation",
                        task_run_id=stem.removeprefix("rg-"),
                        status="succeeded",
                        input_tokens=10,
                        output_tokens=20,
                        total_tokens=30,
                        usage_source="provider",
                    )
            self.stem = stem
            self.output_mode = output_mode
            return {"status": "accepted", "taskId": "external-synthetic"}

        async def poll(self, task_id):
            await self.guard()
            if type(self).before_poll:
                type(self).before_poll()
            names = [
                f"{self.stem}.no_watermark.zh-CN.mono.pdf",
                f"{self.stem}.no_watermark.zh-CN.LR_dual.pdf",
            ]
            if self.output_mode == "dual":
                names = names[1:]
            elif self.output_mode == "mono":
                names = names[:1]
            return {
                "status": "success",
                "active": False,
                "finished": True,
                "fileList": (
                    []
                    if self.missing_output
                    else ["../../outside.pdf"]
                    if self.names_bad
                    else names
                ),
            }

        async def download(self, filename):
            await self.guard()
            type(self).downloads.append(filename)
            return b"%PDF-not-a-pdf" if self.invalid_pdf else pdf_bytes()

    class FakeProxy:
        instances = 0
        forwarded_parameters = []
        snapshots = []
        error_code = None
        cancelled = False
        base_url = "http://127.0.0.1:12345/v1"
        token = "task-only-token"

        def __init__(self, *args):
            type(self).instances += 1
            self.forward_parameters = True
            type(self).snapshots.append(json.loads(json.dumps(args[3])))

        async def __aenter__(self):
            type(self).forwarded_parameters.append(self.forward_parameters)
            return self

        async def __aexit__(self, *_args):
            self.cancelled = True

        async def cancel(self):
            self.cancelled = True

    monkeypatch.setattr("researchgraph.translation_api.TranslationBridge", FakeBridge)
    monkeypatch.setattr("researchgraph.translation_proxy.TranslationProxy", FakeProxy)
    app = FastAPI()
    register_translation_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    body = {"document_version_id": revision_id, "profile_id": profile_id}
    yield engine, client, tmp_path, paper_id, body, source, FakeBridge, FakeProxy
    client.close()
    engine.dispose()


def prepared(client, paper_id, body):
    response = client.post(f"/api/v1/papers/{paper_id}/translations/prepare", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def create(client, paper_id, body, **extra):
    preview = prepared(client, paper_id, body)
    return client.post(
        f"/api/v1/papers/{paper_id}/translations",
        json={
            **body,
            "expected_fingerprint": preview["prepare_fingerprint"],
            "allow_network": True,
            "exclusive_service": True,
            **extra,
        },
    )


def test_prepare_is_zero_model_and_requires_explicit_consent(workspace):
    engine, client, _root, paper, body, _source, bridge, proxy = workspace
    preview = prepared(client, paper, body)
    assert preview["source_characters"] > 0
    assert preview["page_start"] == preview["page_end"] == 1
    assert preview["estimate_is_limit"] is False
    response = client.post(
        f"/api/v1/papers/{paper}/translations",
        json={**body, "expected_fingerprint": preview["prepare_fingerprint"]},
    )
    assert response.status_code == 409
    assert bridge.submissions == proxy.instances == 0
    with Session(engine) as session:
        assert session.scalars(select(LiteTokenUsage)).all() == []
        assert session.scalars(select(Job)).all() == []


def test_success_managed_artifacts_cache_and_original_unchanged(workspace):
    engine, client, root, paper, body, source, bridge, proxy = workspace
    original = source.read_bytes()
    response = create(client, paper, body)
    assert response.status_code == 200, response.text
    queued = response.json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED"
    assert result["progress"] == 100
    assert {item["kind"] for item in result["artifacts"]} == {"mono", "dual"}
    assert source.read_bytes() == original
    assert "path" not in str(result["artifacts"])
    artifact = client.get(f"/api/v1/translations/{result['id']}/artifacts/mono")
    assert artifact.status_code == 200
    assert Path(artifact.json()["path"]) == root / "translations" / result["id"] / "mono.pdf"
    cached = create(client, paper, body, allow_network=False, exclusive_service=False)
    assert cached.status_code == 200
    assert cached.json()["cache_hit"] is True
    assert cached.json()["usage"]["calls"] == 0
    assert bridge.submissions == proxy.instances == 1
    with Session(engine) as session:
        rows = session.scalars(select(LiteTokenUsage)).all()
        assert len(rows) == 2 and sum(row.cache_hit for row in rows) == 1


def test_preflight_fingerprint_rejects_model_or_budget_drift(workspace):
    engine, client, _root, paper, body, _source, bridge, proxy = workspace
    preview = prepared(client, paper, body)
    with Session(engine) as session, session.begin():
        profile = session.get(ModelProfile, body["profile_id"])
        profile.model = "changed-model"
    response = client.post(
        f"/api/v1/papers/{paper}/translations",
        json={
            **body,
            "expected_fingerprint": preview["prepare_fingerprint"],
            "allow_network": True,
            "exclusive_service": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TRANSLATION_PREPARE_CHANGED"
    assert bridge.submissions == proxy.instances == 0


def test_source_changed_after_queue_never_submits(workspace):
    engine, client, root, paper, body, source, bridge, proxy = workspace
    queued = create(client, paper, body).json()
    source.write_bytes(pdf_bytes())
    # A new serializable PDF is allowed to coincide except its document IDs;
    # force a byte change independent of PyMuPDF metadata generation timing.
    source.write_bytes(source.read_bytes() + b"\nchanged")
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_SOURCE_UNAVAILABLE"
    assert bridge.submissions == proxy.instances == 0


def test_busy_service_never_uploads_or_opens_proxy(workspace):
    engine, client, root, paper, body, _source, bridge, proxy = workspace
    queued = create(client, paper, body).json()
    bridge.busy = True
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["error_code"] == "TRANSLATION_SERVICE_BUSY"
    assert bridge.submissions == proxy.instances == 0


@pytest.mark.parametrize("invalid_pdf,names_bad", [(True, False), (False, True)])
def test_unsafe_or_invalid_outputs_never_publish(workspace, invalid_pdf, names_bad):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    bridge.invalid_pdf, bridge.names_bad = invalid_pdf, names_bad
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["artifacts"] == []


def test_cancel_and_restart_preserve_history_without_replay(workspace):
    engine, client, root, paper, body, _source, bridge, proxy = workspace
    queued = create(client, paper, body).json()
    cancelled = client.post(f"/api/v1/papers/{paper}/translations/{queued['id']}/cancel")
    assert cancelled.json()["status"] == "CANCELLED"
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    assert bridge.submissions == proxy.instances == 0
    second = create(client, paper, body).json()
    assert second["id"] != queued["id"]
    assert recover_translations(engine) == 1
    assert recover_translations(engine) == 0
    asyncio.run(execute_translation(engine, second["job_id"], root))
    assert (
        client.get(f"/api/v1/papers/{paper}/translations/{second['id']}").json()["status"]
        == "INTERRUPTED"
    )
    assert bridge.submissions == proxy.instances == 0


def test_cancel_after_external_acceptance_keeps_unknown_and_no_publish(workspace):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    queued = create(client, paper, body).json()

    def cancel():
        with Session(engine) as session, session.begin():
            job = session.get(Job, queued["job_id"])
            cancel_translation_job(session, job)

    bridge.before_poll = cancel
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "CANCELLED"
    assert result["external_state"] == "unknown"
    assert result["artifacts"] == []


def test_tampered_artifact_does_not_pass_cache_or_open(workspace):
    engine, client, root, paper, body, _source, _bridge, _proxy = workspace
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    (root / "translations" / queued["id"] / "mono.pdf").write_bytes(b"not PDF")
    assert client.get(f"/api/v1/translations/{queued['id']}/artifacts/mono").status_code == 409
    preview = prepared(client, paper, body)
    assert preview["cache_hit"] is False
    with Session(engine) as session:
        assert session.get(PDFTranslation, queued["id"]).status == "COMPLETED"


def test_settings_loopback_and_full_document_contract(workspace):
    _engine, client, _root, paper, body, _source, _bridge, _proxy = workspace
    assert (
        client.put(
            "/api/v1/settings/translation",
            json={"enabled": True, "service_url": "https://example.invalid"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/settings/translation",
            json={"enabled": True, "service_url": "http://localhost:8890"},
        ).json()["service_url"]
        == "http://127.0.0.1:8890"
    )
    assert (
        client.post(
            f"/api/v1/papers/{paper}/translations/prepare", json={**body, "page_start": 2}
        ).status_code
        == 422
    )


def test_managed_output_never_overwrites_existing_files(tmp_path):
    identifier = str(uuid4())
    _save_outputs(tmp_path, identifier, {"mono": pdf_bytes(), "dual": pdf_bytes()})
    with pytest.raises(ValueError, match="未覆盖"):
        _save_outputs(tmp_path, identifier, {"mono": pdf_bytes(), "dual": pdf_bytes()})


def test_zero_usage_pdf_and_proxy_failure_cannot_publish(workspace):
    engine, client, root, paper, body, _source, bridge, proxy = workspace
    bridge.zero_usage = True
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_MODEL_USAGE_INCOMPLETE"
    bridge.zero_usage = False

    def failed_during_poll():
        proxy.error_code = "TRANSLATION_BUDGET_EXCEEDED"

    bridge.before_poll = failed_during_poll
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["artifacts"] == []


def test_job_uses_real_loopback_proxy_with_synthetic_upstream(workspace, monkeypatch):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    requests = []

    def upstream(request):
        requests.append(request)
        assert request.url.host == "example.invalid"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "匿名合成译文。"}}],
                "usage": {"prompt_tokens": 23, "completion_tokens": 7, "total_tokens": 30},
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(upstream), **kw),
    )
    monkeypatch.setattr("researchgraph.translation_proxy.TranslationProxy", RealTranslationProxy)

    async def submit(self, _content, stem, proxy_url, proxy_token, model, *, output_mode="both"):
        self.stem = stem
        self.output_mode = output_mode
        async with HTTP_CLIENT(trust_env=False) as model_client:
            response = await model_client.post(
                proxy_url + "/chat/completions",
                headers={"Authorization": f"Bearer {proxy_token}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Translate this synthetic text."}],
                },
            )
        assert response.status_code == 200, response.text
        return {"status": "accepted", "taskId": "live-proxy-test"}

    monkeypatch.setattr(bridge, "submit", submit)
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED", result
    assert result["usage"]["calls"] == len(requests) == 1
    assert (result["usage"]["input_tokens"], result["usage"]["output_tokens"]) == (23, 7)
    assert result["usage"]["cost_estimate"] is None


@pytest.mark.parametrize(
    ("failure", "code", "message_fragment"),
    [
        ("budget", "TRANSLATION_BUDGET_EXCEEDED", "预算"),
        ("http_400", "TRANSLATION_PROVIDER_REQUEST_REJECTED", "拒绝"),
        ("http_401", "TRANSLATION_PROVIDER_AUTH_FAILED", "鉴权"),
        ("http_429", "TRANSLATION_PROVIDER_RATE_LIMITED", "限流"),
        ("length", "TRANSLATION_PROVIDER_TRUNCATED", "截断"),
        ("invalid", "TRANSLATION_PROVIDER_RESPONSE_INVALID", "格式"),
    ],
)
def test_proxy_failures_have_specific_terminal_errors_without_replay_or_artifacts(
    workspace, monkeypatch, failure, code, message_fragment
):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    provider_requests = []
    loopback_responses = []
    private_marker = "synthetic-private-provider-diagnostic"

    def upstream(request):
        provider_requests.append(request)
        assert request.url.host == "example.invalid"
        if failure.startswith("http_"):
            return httpx.Response(int(failure.removeprefix("http_")), text=private_marker)
        if failure == "invalid":
            return httpx.Response(200, text=private_marker)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if failure == "length" else "stop",
                        "message": {"content": "匿名合成译文。"},
                    }
                ],
                "usage": {"prompt_tokens": 23, "completion_tokens": 7, "total_tokens": 30},
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(upstream), **kw),
    )
    monkeypatch.setattr("researchgraph.translation_proxy.TranslationProxy", RealTranslationProxy)

    async def submit(self, _content, stem, proxy_url, proxy_token, model, *, output_mode="both"):
        type(self).submissions += 1
        self.stem, self.output_mode = stem, output_mode
        async with HTTP_CLIENT(trust_env=False) as model_client:
            for text in (
                ["First anonymous paragraph.", "Second anonymous paragraph."]
                if failure == "budget"
                else ["One anonymous paragraph."]
            ):
                response = await model_client.post(
                    proxy_url + "/chat/completions",
                    headers={"Authorization": f"Bearer {proxy_token}"},
                    json={"model": model, "messages": [{"role": "user", "content": text}]},
                )
                loopback_responses.append(response)
            repeated = await model_client.post(
                proxy_url + "/chat/completions",
                headers={"Authorization": f"Bearer {proxy_token}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "One more anonymous paragraph."}],
                },
            )
            assert repeated.status_code == 403
            assert repeated.json()["error"]["code"] == code
        return {"status": "accepted", "taskId": "blocked-proxy-test"}

    monkeypatch.setattr(bridge, "submit", submit)
    queued = create(client, paper, {**body, "max_calls": 1}).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED" and result["error_code"] == code
    assert message_fragment in result["error"]
    assert "模型代理预算或请求校验失败" not in result["error"]
    assert private_marker not in str(result)
    assert all(private_marker not in response.text for response in loopback_responses)
    assert result["artifacts"] == bridge.downloads == []
    assert not (root / "translations" / queued["id"]).exists()
    assert result["usage"]["calls"] == len(provider_requests) == 1
    assert result["usage"]["retry_count"] == 0
    assert bridge.submissions == 1
    # Polling the final record and running the same worker again cannot replay
    # a request that may already have been charged by the provider.
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    for _ in range(2):
        assert client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json() == result
    assert len(provider_requests) == bridge.submissions == 1


def managed_setup(workspace, monkeypatch, *, mode="managed"):
    engine, _client, _root, _paper, _body, _source, _bridge, _proxy = workspace

    class FakeRuntime:
        instances = []
        reject = False
        ownership_lost = False
        stop_failure = False
        bundled_service_url = "http://127.0.0.1:54321"
        bundled_service_token = "synthetic-owned-service-ticket"

        def __init__(self, settings, data_dir, **_options):
            self.settings = settings
            self.service_url = settings.service_url
            self.service_token = None
            self.expected_version = "4.1.8"
            self.started = False
            self.stopped = False
            self.published_before_stop = False
            type(self).instances.append(self)

        def validate(self):
            if self.reject:
                raise KnowledgeError("TRANSLATION_RUNTIME_CONFIG", "合成启动配置不完整")
            if self.settings.launch_mode == "bundled":
                from researchgraph.translation_bundled import BUNDLED_SERVICE_VERSION

                self.expected_version = BUNDLED_SERVICE_VERSION

        async def __aenter__(self):
            self.validate()
            self.started = True
            if self.settings.launch_mode == "bundled":
                self.service_url = self.bundled_service_url
                self.service_token = self.bundled_service_token
            return self

        async def ensure_owned(self):
            if self.ownership_lost:
                raise KnowledgeError("TRANSLATION_RUNTIME_OWNERSHIP_LOST", "合成服务归属失效")

        async def stop(self):
            if self.stopped:
                return
            if self.started and not self.stopped:
                with Session(engine) as session:
                    self.published_before_stop = any(
                        row.status == "COMPLETED"
                        for row in session.scalars(select(PDFTranslation)).all()
                    )
            self.stopped = True
            if self.stop_failure:
                raise KnowledgeError("TRANSLATION_RUNTIME_STOP_UNCONFIRMED", "合成清理未确认")

    monkeypatch.setattr("researchgraph.translation_runtime.ManagedTranslationRuntime", FakeRuntime)
    with Session(engine) as session, session.begin():
        settings = session.get(PDFTranslationSettings, "global")
        settings.launch_mode = mode
        settings.python_path = "C:/synthetic/python.exe"
        settings.server_path = "C:/synthetic/server.py"
    return FakeRuntime


def test_managed_preflight_does_not_launch_and_runtime_closes_before_publish(
    workspace, monkeypatch
):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch)
    preview = prepared(client, paper, body)
    assert preview["launch_mode"] == "managed" and preview["service_ready"]
    assert not any(item.started for item in runtime.instances)
    assert bridge.submissions == 0
    queued = create(client, paper, body).json()
    assert not any(item.started for item in runtime.instances)
    # Worker uses the frozen startup configuration, not settings changed later.
    with Session(engine) as session, session.begin():
        settings = session.get(PDFTranslationSettings, "global")
        settings.python_path = "C:/other/python.exe"
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    started = [item for item in runtime.instances if item.started]
    assert len(started) == 1 and started[0].stopped
    assert not started[0].published_before_stop
    assert started[0].settings.python_path == "C:/synthetic/python.exe"
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED" and result["launch_mode"] == "managed"
    before = len(started)
    assert create(client, paper, body).json()["cache_hit"]
    assert len([item for item in runtime.instances if item.started]) == before


def test_managed_failure_and_cancellation_close_owned_runtime(workspace, monkeypatch):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch)
    bridge.invalid_pdf = True
    queued = create(client, paper, body).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert all(item.stopped for item in runtime.instances if item.started)
    bridge.invalid_pdf = False
    queued = create(client, paper, body).json()

    def cancel_during_poll():
        with Session(engine) as session, session.begin():
            cancel_translation_job(session, session.get(Job, queued["job_id"]))
            session.get(Job, queued["job_id"]).status = "cancelled"

    bridge.before_poll = cancel_during_poll
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "CANCELLED"
    assert all(item.stopped for item in runtime.instances if item.started)
    assert "自动启动的服务已关闭" in result["error"]


def test_managed_startup_changes_require_preflight_again(workspace, monkeypatch):
    engine, client, _root, paper, body, _source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch)
    preview = prepared(client, paper, body)
    with Session(engine) as session, session.begin():
        settings = session.get(PDFTranslationSettings, "global")
        settings.server_path = "C:/changed/server.py"
    response = client.post(
        f"/api/v1/papers/{paper}/translations",
        json={
            **body,
            "expected_fingerprint": preview["prepare_fingerprint"],
            "allow_network": True,
            "exclusive_service": True,
        },
    )
    assert response.status_code == 409
    assert not any(item.started for item in runtime.instances) and bridge.submissions == 0
    runtime.reject = True
    health = client.post("/api/v1/settings/translation/check").json()
    assert not health["available"]
    assert not prepared(client, paper, body)["service_ready"]


def test_managed_lost_ownership_rejects_upload_and_stops_runtime(workspace, monkeypatch):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch)
    queued = create(client, paper, body).json()
    runtime.ownership_lost = True
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_RUNTIME_OWNERSHIP_LOST"
    assert bridge.submissions == 0
    assert all(item.stopped for item in runtime.instances if item.started)


def test_managed_unconfirmed_cleanup_cannot_publish_success(workspace, monkeypatch):
    engine, client, root, paper, body, _source, _bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch)
    queued = create(client, paper, body).json()
    runtime.stop_failure = True
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_RUNTIME_STOP_UNCONFIRMED"
    assert result["artifacts"] == []


def test_bundled_preflight_and_queue_freeze_engine_identity_without_starting(
    workspace, monkeypatch
):
    from researchgraph.translation_bundled import BUNDLED_ENGINE_ID

    engine, client, _root, paper, body, _source, bridge, proxy = workspace
    runtime = managed_setup(workspace, monkeypatch, mode="bundled")
    with Session(engine) as session, session.begin():
        settings = session.get(PDFTranslationSettings, "global")
        settings.python_path = settings.server_path = None
    request = {**body, "output_mode": "dual"}
    preview = prepared(client, paper, request)
    assert preview["service_ready"] and preview["launch_mode"] == "bundled"
    assert preview["output_mode"] == "dual"
    assert any("内置翻译核心" in warning for warning in preview["warnings"])
    assert not any(item.started for item in runtime.instances)
    assert bridge.instances == [] and bridge.submissions == proxy.instances == 0
    with Session(engine) as session:
        assert session.scalars(select(LiteTokenUsage)).all() == []
        assert session.scalars(select(Job)).all() == []
    denied = client.post(
        f"/api/v1/papers/{paper}/translations",
        json={**request, "expected_fingerprint": preview["prepare_fingerprint"]},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "TRANSLATION_CONSENT_REQUIRED"
    queued = create(client, paper, request).json()
    assert not any(item.started for item in runtime.instances)
    assert bridge.submissions == proxy.instances == 0
    with Session(engine) as session:
        row = session.get(PDFTranslation, queued["id"])
        assert row.engine_version == row.model_snapshot["translation_engine"] == BUNDLED_ENGINE_ID
        assert row.runtime_snapshot["launch_mode"] == "bundled"
        assert row.runtime_snapshot["python_path"] is row.runtime_snapshot["server_path"] is None


def test_bundled_worker_passes_owned_service_ticket_and_version_to_bridge(workspace, monkeypatch):
    from researchgraph.translation_bundled import BUNDLED_SERVICE_VERSION

    engine, client, root, paper, body, source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch, mode="bundled")
    original = source.read_bytes()
    queued = create(client, paper, {**body, "output_mode": "dual"}).json()
    with Session(engine) as session, session.begin():
        settings = session.get(PDFTranslationSettings, "global")
        settings.launch_mode = "manual"
        settings.service_url = "http://127.0.0.1:54322"
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    started = [item for item in runtime.instances if item.started]
    assert len(started) == 1 and started[0].stopped
    assert started[0].settings.launch_mode == "bundled"
    assert not started[0].published_before_stop
    owned_bridges = [item for item in bridge.instances if item.before_request is not None]
    assert len(owned_bridges) == 1
    worker_bridge = owned_bridges[0]
    assert worker_bridge.service_url == runtime.bundled_service_url
    assert worker_bridge.service_token == runtime.bundled_service_token
    assert worker_bridge.expected_version == BUNDLED_SERVICE_VERSION
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED" and result["launch_mode"] == "bundled"
    assert {item["kind"] for item in result["artifacts"]} == {"dual"}
    assert runtime.bundled_service_token not in str(result)
    assert source.read_bytes() == original


def test_new_bundled_jobs_freeze_minimal_requests_without_mutating_reading_profile(
    workspace, monkeypatch
):
    engine, client, root, paper, body, _source, bridge, proxy = workspace
    managed_setup(workspace, monkeypatch, mode="bundled")
    reading_parameters = {"temperature": 0.7, "top_p": 0.8, "reasoning_effort": "high"}
    with Session(engine) as session, session.begin():
        session.get(ModelProfile, body["profile_id"]).parameters = reading_parameters
    queued = create(client, paper, {**body, "output_mode": "mono"}).json()
    with Session(engine) as session:
        row = session.get(PDFTranslation, queued["id"])
        assert row.model_snapshot["translation_request_policy"] == "text-chat-minimal-1"
        assert row.model_snapshot["parameters"] == reading_parameters
        assert session.get(ModelProfile, body["profile_id"]).parameters == reading_parameters
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED", result
    assert proxy.forwarded_parameters == [False]
    assert proxy.snapshots[0]["parameters"] == reading_parameters
    assert bridge.submissions == 1


def test_legacy_bundled_snapshot_keeps_prior_identity_parameters_and_worker_policy(
    workspace, monkeypatch
):
    from researchgraph.translation_bundled import BUNDLED_ENGINE_ID

    engine, client, root, paper, body, _source, bridge, proxy = workspace
    managed_setup(workspace, monkeypatch, mode="bundled")
    reading_parameters = {"temperature": 0.4, "reasoning_effort": "low"}
    with Session(engine) as session, session.begin():
        session.get(ModelProfile, body["profile_id"]).parameters = reading_parameters
    queued = create(client, paper, {**body, "output_mode": "dual"}).json()
    with Session(engine) as session, session.begin():
        row = session.get(PDFTranslation, queued["id"])
        snapshot = dict(row.model_snapshot)
        snapshot.pop("translation_request_policy")
        revision = session.get(AttachmentRevision, row.document_version_id)
        prior_identity = digest(
            {
                "paper_id": revision.paper_id,
                "document_version_id": revision.id,
                "source_hash": revision.sha256,
                "engine": BUNDLED_ENGINE_ID,
                "source_language": "en",
                "target_language": "zh-CN",
                "outputs": ["dual"],
                "range": [1, revision.page_count],
                "provider": snapshot["provider"],
                "base_url": snapshot["base_url"],
                "model": snapshot["model"],
                "parameters": reading_parameters,
            }
        )
        assert _identity(revision, snapshot, "dual") == prior_identity
        assert row.cache_key != prior_identity
        row.model_snapshot, row.cache_key = snapshot, prior_identity
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED", result
    assert proxy.forwarded_parameters == [True]
    assert proxy.snapshots[0]["parameters"] == reading_parameters
    assert "translation_request_policy" not in proxy.snapshots[0]
    with Session(engine) as session:
        assert session.get(PDFTranslation, queued["id"]).cache_key == prior_identity
        assert session.get(ModelProfile, body["profile_id"]).parameters == reading_parameters
    assert bridge.submissions == 1


def test_bundled_and_external_engines_do_not_share_completed_cache(workspace, monkeypatch):
    from researchgraph.translation_bundled import BUNDLED_ENGINE_ID
    from researchgraph.translation_contracts import ENGINE_VERSION

    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    managed_setup(workspace, monkeypatch, mode="bundled")
    request = {**body, "output_mode": "mono"}
    bundled_job = create(client, paper, request).json()
    asyncio.run(execute_translation(engine, bundled_job["job_id"], root))
    assert prepared(client, paper, request)["cache_hit"]
    with Session(engine) as session, session.begin():
        session.get(PDFTranslationSettings, "global").launch_mode = "manual"
    assert not prepared(client, paper, request)["cache_hit"]
    external_job = create(client, paper, request).json()
    assert external_job["id"] != bundled_job["id"]
    with Session(engine) as session:
        bundled_row = session.get(PDFTranslation, bundled_job["id"])
        external_row = session.get(PDFTranslation, external_job["id"])
        assert bundled_row.cache_key != external_row.cache_key
        assert bundled_row.engine_version == BUNDLED_ENGINE_ID
        assert external_row.engine_version == ENGINE_VERSION
    assert bridge.submissions == 1


def test_bundled_cancelled_before_start_does_not_report_manual_external_process(
    workspace, monkeypatch
):
    _engine, client, _root, paper, body, _source, bridge, proxy = workspace
    runtime = managed_setup(workspace, monkeypatch, mode="bundled")
    queued = create(client, paper, body).json()
    cancelled = client.post(f"/api/v1/papers/{paper}/translations/{queued['id']}/cancel").json()
    assert cancelled["status"] == "CANCELLED" and cancelled["launch_mode"] == "bundled"
    assert "后续模型请求已阻断" in cancelled["error"]
    assert "手动服务" not in cancelled["error"]
    assert not any(item.started for item in runtime.instances)
    assert bridge.submissions == proxy.instances == 0


def test_bundled_cancel_during_translation_closes_owned_runtime_without_publication(
    workspace, monkeypatch
):
    engine, client, root, paper, body, source, bridge, _proxy = workspace
    runtime = managed_setup(workspace, monkeypatch, mode="bundled")
    original = source.read_bytes()
    queued = create(client, paper, body).json()

    def cancel_during_poll():
        with Session(engine) as session, session.begin():
            cancel_translation_job(session, session.get(Job, queued["job_id"]))

    bridge.before_poll = cancel_during_poll
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "CANCELLED" and result["artifacts"] == []
    assert "自动启动的服务已关闭" in result["error"]
    assert "手动服务" not in result["error"]
    assert all(item.stopped for item in runtime.instances if item.started)
    assert bridge.downloads == [] and source.read_bytes() == original


@pytest.mark.parametrize(
    ("mode", "expected"), [("dual", {"dual"}), ("mono", {"mono"}), ("both", {"mono", "dual"})]
)
def test_selected_output_mode_controls_frozen_job_artifacts_and_cache(workspace, mode, expected):
    engine, client, root, paper, body, source, bridge, _proxy = workspace
    original = source.read_bytes()
    request = {**body, "output_mode": mode}
    preview = prepared(client, paper, request)
    assert preview["output_mode"] == mode and not preview["cache_hit"]
    queued = create(client, paper, request).json()
    assert queued["output_mode"] == mode
    with Session(engine) as session:
        assert session.get(PDFTranslation, queued["id"]).output_mode == mode
        assert session.get(Job, queued["job_id"]).payload["output_mode"] == mode
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "COMPLETED", result
    assert result["output_mode"] == mode
    assert {item["kind"] for item in result["artifacts"]} == expected
    assert len(bridge.downloads) == len(expected)
    for kind in {"mono", "dual"}:
        target = root / "translations" / queued["id"] / f"{kind}.pdf"
        opened = client.get(f"/api/v1/translations/{queued['id']}/artifacts/{kind}")
        assert target.exists() == (kind in expected)
        assert opened.status_code == (200 if kind in expected else 404)
    cached = create(client, paper, request).json()
    assert cached["id"] == queued["id"] and cached["cache_hit"]
    assert cached["output_mode"] == mode and cached["usage"]["calls"] == 0
    assert bridge.submissions == 1 and source.read_bytes() == original


def test_output_modes_have_distinct_cache_and_pending_keys_legacy_defaults_to_both(workspace):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    rows = []
    for mode in ("dual", "mono", "both"):
        request = {**body, "output_mode": mode}
        assert not prepared(client, paper, request)["cache_hit"]
        queued = create(client, paper, request).json()
        rows.append(queued["id"])
        asyncio.run(execute_translation(engine, queued["job_id"], root))
        assert (
            client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()["status"]
            == "COMPLETED"
        )
    assert len(set(rows)) == bridge.submissions == 3
    with Session(engine) as session:
        assert len({row.cache_key for row in session.scalars(select(PDFTranslation))}) == 3
    assert prepared(client, paper, body)["output_mode"] == "both"
    assert create(client, paper, body).json()["id"] == rows[-1]
    assert bridge.submissions == 3


def test_output_mode_change_requires_new_preflight_and_rejects_unknown_mode(workspace):
    _engine, client, _root, paper, body, _source, bridge, proxy = workspace
    preview = prepared(client, paper, {**body, "output_mode": "dual"})
    response = client.post(
        f"/api/v1/papers/{paper}/translations",
        json={
            **body,
            "output_mode": "mono",
            "expected_fingerprint": preview["prepare_fingerprint"],
            "allow_network": True,
            "exclusive_service": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TRANSLATION_PREPARE_CHANGED"
    assert (
        client.post(
            f"/api/v1/papers/{paper}/translations/prepare", json={**body, "output_mode": "pdf"}
        ).status_code
        == 422
    )
    assert bridge.submissions == proxy.instances == 0


def test_missing_selected_output_fails_without_download_or_publication(workspace):
    engine, client, root, paper, body, _source, bridge, _proxy = workspace
    bridge.missing_output = True
    queued = create(client, paper, {**body, "output_mode": "dual"}).json()
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_OUTPUT_INVALID"
    assert result["artifacts"] == bridge.downloads == []


def test_output_mode_drift_cannot_reuse_frozen_task_identity(workspace):
    engine, client, root, paper, body, _source, bridge, proxy = workspace
    queued = create(client, paper, {**body, "output_mode": "dual"}).json()
    with Session(engine) as session, session.begin():
        session.get(PDFTranslation, queued["id"]).output_mode = "mono"
    asyncio.run(execute_translation(engine, queued["job_id"], root))
    result = client.get(f"/api/v1/papers/{paper}/translations/{queued['id']}").json()
    assert result["status"] == "FAILED"
    assert result["error_code"] == "TRANSLATION_CONFIG_CHANGED"
    assert bridge.submissions == proxy.instances == 0


def test_save_outputs_rejects_unselected_extra_artifact_before_writing(tmp_path):
    identifier = str(uuid4())
    with pytest.raises(KnowledgeError):
        _save_outputs(
            tmp_path, identifier, {"mono": pdf_bytes(), "dual": pdf_bytes()}, output_mode="dual"
        )
    assert not (tmp_path / "translations").exists()
