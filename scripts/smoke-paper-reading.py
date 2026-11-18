"""Run the actual sidecar whole-paper notes path against a loopback SSE fixture.

The fixed usage values test accounting only. They are not a model-quality or
real-token measurement. Source PDFs, databases and settings are temporary.
The sibling section smoke supplies the same audited startup/HTTP/SSE harness.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def harness() -> Any:
    path = Path(__file__).with_name("smoke-section-reading.py")
    spec = importlib.util.spec_from_file_location("section_reading_smoke_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Section reading smoke harness is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    shared = harness()

    class PaperProvider(shared.SyntheticProvider):
        def respond(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
            assert body.get("model") == shared.MODEL
            assert body.get("stream") is True
            assert body.get("stream_options", {}).get("include_usage") is True
            assert not body.get("tools")
            messages = body["messages"]
            assert len(messages) == 2 and messages[0]["role"] == "system"
            assert "不重复输出英文全文" in messages[0]["content"]
            wrapper = json.loads(messages[1]["content"])
            data, schema = wrapper["untrusted_source_data"], wrapper["output_schema"]
            assert schema["title"] == "PaperReadingAnalysis"
            assert "整篇论文" in data["scope"]
            assert data["allowed_graph_nodes"] == []
            paragraphs = data["paragraphs"]
            assert paragraphs and len({p["paragraph_id"] for p in paragraphs}) == len(paragraphs)
            assert all(set(p) == {"paragraph_id", "section_id", "text_en"} for p in paragraphs)
            assert all(
                "text_en" not in item.get("properties", {})
                for item in schema.get("$defs", {}).values()
            )
            return {
                "schema_version": "paper_reading_analysis.v1",
                "paragraphs": [
                    {
                        "paragraph_id": p["paragraph_id"],
                        "translation_zh": "这是匿名合成文档的中文测试译文，方法保留不确定性。",
                        "paragraph_function": "EXPLAIN_METHOD",
                        "logic_role_zh": "说明合成研究全文中的方法和限定条件。",
                        "critical_note_zh": "这是程序夹具，不代表真实科学结论。",
                        "reading_question_zh": None,
                        "highlights": [
                            {"type": "METHOD", "quote_en": p["text_en"][:12], "occurrence_index": 0}
                        ],
                        "related_graph_node_ids": [],
                    }
                    for p in paragraphs
                ],
                "paper_argument": {
                    "logic_chain_zh": ["提出合成研究场景。", "说明方法并保留不确定性。"],
                    "core_claim_zh": "全文正文介绍一个合成测试方法。",
                    "strong_point_zh": None,
                    "question_to_verify_zh": "实际实验和图表应回看原始材料。",
                },
            }, "A04"

    def exercise(base: str, token: str, provider: PaperProvider, pdf: Path) -> dict[str, Any]:
        request, wait_job = shared.request, shared.wait_job
        health = request(base, token, "GET", "/health")
        assert health["schema_version"] == "lite0011" and health["database"] == "ready"
        project = request(base, token, "POST", "/projects", {"name": "Synthetic whole-paper smoke"})
        imported = request(
            base,
            token,
            "POST",
            f"/projects/{project['id']}/papers/import/pdf",
            {"path": str(pdf), "mode": "reference"},
        )
        result = wait_job(base, token, imported["id"])["result"]
        paper_id, revision = result["paper_id"], result["revision_id"]
        document_url = f"/papers/{paper_id}/reading-document"
        document = request(base, token, "GET", document_url + f"?document_version_id={revision}")
        refreshed = request(
            base, token, "POST", document_url + "/refresh", {"document_version_id": revision}
        )
        ids = [unit["id"] for unit in refreshed["units"] if unit["kind"] == "paragraph"]
        assert ids and refreshed["projection_version"] == "reading-document-2"
        assert all(unit["sources"] for unit in refreshed["units"] if unit["kind"] == "paragraph")
        usage_url = f"/projects/{project['id']}/lite/usage"
        assert request(base, token, "GET", usage_url)["calls"] == 0 and not provider.calls
        notes_url = f"/papers/{paper_id}/reading-notes"
        assert request(base, token, "GET", notes_url) is None
        connection = request(
            base,
            token,
            "POST",
            "/settings/connections",
            {
                "name": "Loopback whole-paper SSE fixture",
                "provider": "local",
                "base_url": provider.base_url,
            },
        )
        assert not connection["has_api_key"]
        profile = request(
            base,
            token,
            "POST",
            "/settings/models",
            {
                "name": "Synthetic whole-paper model",
                "connection_id": connection["id"],
                "model": shared.MODEL,
                "parameters": {"timeout_seconds": 20},
            },
        )
        assert not profile["has_api_key"]
        request(base, token, "POST", "/settings/model-roles", {"extraction": profile["id"]})
        body = {"document_version_id": revision, "allow_network": True}
        generated = request(base, token, "POST", notes_url + "/generate", body)
        wait_job(base, token, generated["job_id"])
        completed = request(base, token, "GET", notes_url + f"?result_id={generated['id']}")
        assert completed["status"] == "COMPLETED", completed
        assert completed["projection_hash"] == refreshed["projection_hash"]
        assert [item["paragraph_id"] for item in completed["analysis"]["paragraphs"]] == ids
        assert completed["analysis"]["paper_argument"] and not completed["missing_paragraph_ids"]
        assert all(
            "text_en" not in item and item["translation_zh"]
            for item in completed["analysis"]["paragraphs"]
        )
        cached = request(base, token, "POST", notes_url + "/generate", body)
        assert cached["status"] == "COMPLETED" and cached["cache_hit"]
        request(base, token, "GET", document_url)
        request(base, token, "GET", notes_url)
        assert provider.calls == ["A04"] and not provider.errors
        final = request(base, token, "GET", usage_url)
        assert (
            final["calls"],
            final["input_tokens"],
            final["output_tokens"],
            final["total_tokens"],
            final["retry_count"],
        ) == (1, 23, 41, 64, 0)
        assert final["cost_estimate"] is None and not final["cost_known"]
        return {
            "status": "passed",
            "schema_version": health["schema_version"],
            "usage_kind": "synthetic loopback SSE fixture; not real model usage",
            "real_model_calls": 0,
            "local_import_projection_refresh_calls": 0,
            "paragraph_count": len(ids),
            "initial_projection_units": len(document["units"]),
            "whole_paper_calls": 1,
            "cache_extra_calls": 0,
            "synthetic_input_tokens": final["input_tokens"],
            "synthetic_output_tokens": final["output_tokens"],
            "synthetic_total_tokens": final["total_tokens"],
            "cache_hits": final["cache_hits"],
            "cost": None,
            "cost_known": False,
            "non_loopback_requests": 0,
        }

    shared.SyntheticProvider, shared.exercise = PaperProvider, exercise
    return shared.run(executable, source_python)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
