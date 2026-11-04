"""Versioned keyed ranking with one bounded, auditable protocol correction.

Partial decisions are private checkpoints, never published selections. Every
response is decoded again on resume and all source checks precede any new call.
"""

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model
from researchgraph.knowledge_models import ModelRun
from researchgraph.knowledge_store import digest, text_hash
from researchgraph.models import Job, now
from researchgraph.providers import Provider
from researchgraph.reading_ranking_wire import (
    POLICY,
    PROMPT,
    RankingWireError,
    assert_prompt_contract,
    bind_ranking,
    generated_rules,
    output_schema,
    split_validate,
)
from researchgraph.reading_stage_validation import (
    StageValidation,
    StageValidationError,
    record_validation_failure,
    validate_ranking_input,
    validate_stage,
)

MAX_REQUESTS = 2


def _exhausted() -> StageValidationError:
    return StageValidationError(
        "protocol",
        "RANKING_PROTOCOL_EXHAUSTED",
        "贡献评估格式修复已达本次构建上限；已保存候选和旧图保留，继续不会重复请求",
    )


async def rank_claims(
    engine: Engine,
    job_id: str,
    provider: Provider,
    wire: dict[str, Any],
    canonical: dict[str, Any],
    context: dict[str, Any],
    snapshot: str,
    check_context: Callable[[Session, dict[str, Any]], None],
) -> tuple[str, StageValidation]:
    assert_prompt_contract((PROMPT_DIR / (PROMPT + ".md")).read_text(encoding="utf-8"))
    refs = list(context["claim_aliases"])
    root_hash = digest([wire, canonical, context, snapshot])
    accepted: dict[str, dict[str, Any]] = {}
    provenance: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    diagnostics: dict[str, Any] = {}

    def check() -> None:
        with Session(engine) as session:
            check_context(session, canonical)
            validate_ranking_input(session, canonical, snapshot=snapshot)

    for sequence in range(MAX_REQUESTS):
        check()
        pending = [ref for ref in refs if ref not in accepted]
        # Keep all units and source evidence for paper-wide contribution and
        # duplicate comparisons; only the required output slots become smaller.
        request = {**wire, "contract_rules": generated_rules(pending)}
        request["assessment_refs"] = pending
        if sequence:
            request["completed_assessments"] = accepted
            request["protocol_correction"] = {
                "attempt": sequence,
                "errors": diagnostics,
                "instruction": (
                    "Return only the required assessment slots and warnings. "
                    "Do not repeat or revise completed_assessments; use them for "
                    "paper-wide consistency and duplicate representatives. "
                    "Do not change the supplied knowledge."
                ),
            }
        schema = output_schema(pending)
        manifest = {
            "pipeline": "paper-reading-v1",
            "schema_hash": digest(schema),
            "ranking_protocol": POLICY,
            "ranking_root_hash": root_hash,
            "request_sequence": sequence,
            "semantic_context": context,
        }
        identity = {
            "input_hash": digest(request),
            "schema_hash": digest(schema),
            "manifest_hash": digest(manifest),
        }
        with Session(engine, expire_on_commit=False) as session, session.begin():
            job = session.get(Job, job_id)
            if not job or job.status != "running":
                raise ValueError("任务已取消，不再请求贡献评估")
            state = (job.payload or {}).get("reading_ranking_state")
            if state is None:
                state = {"policy": POLICY, "root_hash": root_hash, "requests": []}
            if state["policy"] != POLICY or state["root_hash"] != root_hash:
                raise StageValidationError(
                    "context",
                    "RANKING_INPUT_CHANGED",
                    "排序检查点输入已变化，请新建构建",
                    response_invalid=False,
                )
            ledger = state["requests"]
            fresh = len(ledger) == sequence
            if fresh:
                ledger = [*ledger, identity]
                job.payload = {
                    **(job.payload or {}),
                    "reading_ranking_state": {**state, "requests": ledger},
                }
            elif (
                sequence >= len(ledger)
                or {key: ledger[sequence].get(key) for key in identity} != identity
            ):
                raise StageValidationError(
                    "context",
                    "RANKING_CHECKPOINT_CHANGED",
                    "排序请求账本已变化，请新建构建",
                    response_invalid=False,
                )
            run = session.scalar(
                select(ModelRun)
                .where(
                    ModelRun.job_id == job_id,
                    ModelRun.prompt_name == PROMPT,
                    ModelRun.input_hash == identity["input_hash"],
                )
                .order_by(ModelRun.created_at.desc())
            )
            expected_parameters = {
                **getattr(provider, "parameters", {"temperature": 0, "timeout_seconds": 35}),
                "input_manifest": manifest,
            }
            actual_parameters = (
                {
                    key: value
                    for key, value in run.parameters.items()
                    if key
                    not in {
                        "attempts",
                        "usage",
                        "duration_seconds",
                        "ranking_recovery",
                        "stage_validation",
                    }
                }
                if run
                else {}
            )
            if run and (
                run.parameters.get("input_manifest") != manifest
                or run.prompt_hash
                != text_hash((PROMPT_DIR / (PROMPT + ".md")).read_text(encoding="utf-8"))
                or run.provider != provider.name
                or run.model != provider.model
                or run.document_version_id != context["document_version_id"]
                or run.schema_version != "reading-1.0"
                or actual_parameters != expected_parameters
            ):
                raise StageValidationError(
                    "context",
                    "RANKING_CHECKPOINT_CHANGED",
                    "排序响应谱系已变化，请新建构建",
                    response_invalid=False,
                )
            cached = (
                (run.id, run.raw_output)
                if run
                and run.status in {"received", "succeeded", "validation_failed"}
                and run.raw_output
                else None
            )
            job.result = {
                **(job.result or {}),
                "ranking_protocol": POLICY,
                "ranking_completed_claims": len(accepted),
                "ranking_total_claims": len(refs),
                "ranking_request": sequence + 1,
                "ranking_request_limit": MAX_REQUESTS,
                "ranking_repairing": bool(sequence),
            }
        if cached:
            run_id, raw = cached
        elif not fresh:
            # A previous dispatch has unknown or failed delivery. Only an
            # explicit resume reaches here; never resend the same request slot.
            diagnostics = {"$": [{"path": "$", "type": "previous_request_unavailable"}]}
            continue
        else:
            run_id, raw = await call_model(
                engine,
                job_id,
                context["document_version_id"],
                provider,
                PROMPT,
                request,
                schema,
                manifest,
                adaptive_timeout=True,
                max_attempts=1,
            )
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            assert job
            state = (job.payload or {})["reading_ranking_state"]
            ledger = list(state["requests"])
            response = {"run_id": run_id, "raw_sha256": text_hash(raw)}
            recorded_response = ledger[sequence].get("response")
            if recorded_response is not None and recorded_response != response:
                raise StageValidationError(
                    "context",
                    "RANKING_RESPONSE_CHANGED",
                    "排序原始响应已变化，停止复用和追加请求",
                    response_invalid=False,
                )
            ledger[sequence] = {**ledger[sequence], "response": response}
            job.payload = {
                **(job.payload or {}),
                "reading_ranking_state": {**state, "requests": ledger},
            }
        try:
            check()
        except StageValidationError as error:
            record_validation_failure(engine, run_id, error, request, raw)
            raise
        try:
            part = split_validate(raw, pending)
            accepted.update(part.assessments)
            provenance.update(
                {ref: {"run_id": run_id, "raw_sha256": text_hash(raw)} for ref in part.assessments}
            )
            warnings = list(dict.fromkeys([*warnings, *part.warnings]))
            diagnostics = part.errors
        except RankingWireError as error:
            diagnostics = {"$": [{"path": "$", "type": error.code}]}
        if set(accepted) != set(refs):
            invalid_slots = StageValidationError(
                "schema",
                "RANKING_SLOTS_INVALID",
                "贡献评估响应存在缺失或不合法字段；软件仅修复未完成的输出槽位",
            )
            record_validation_failure(engine, run_id, invalid_slots, request, raw)
            with Session(engine) as session, session.begin():
                run = session.get(ModelRun, run_id)
                assert run
                run.parameters = {
                    **run.parameters,
                    "ranking_recovery": {
                        "policy": POLICY,
                        "root_hash": root_hash,
                        "accepted_refs": list(accepted),
                        "errors": diagnostics,
                        "slot_provenance": provenance,
                    },
                }
                job = session.get(Job, job_id)
                assert job
                job.result = {
                    **(job.result or {}),
                    "ranking_completed_claims": len(accepted),
                    "ranking_repairing": sequence < MAX_REQUESTS - 1,
                }
            continue
        bound = bind_ranking(accepted, context, warnings=warnings)
        try:
            with Session(engine) as session:
                check_context(session, canonical)
                result = validate_stage(
                    session,
                    "P13",
                    json.dumps(bound, ensure_ascii=False),
                    canonical,
                    snapshot=snapshot,
                )
        except StageValidationError as error:
            record_validation_failure(engine, run_id, error, request, raw)
            raise
        with Session(engine) as session, session.begin():
            run = session.get(ModelRun, run_id)
            assert run
            run.parameters = {
                **run.parameters,
                "ranking_recovery": {
                    "policy": POLICY,
                    "root_hash": root_hash,
                    "accepted_refs": list(accepted),
                    "slot_provenance": provenance,
                    "terminal_validated": True,
                },
            }
            run.status, run.error, run.finished_at = "succeeded", None, now()
            job = session.get(Job, job_id)
            assert job
            job.result = {
                **(job.result or {}),
                "ranking_completed_claims": len(refs),
                "ranking_repairing": False,
            }
        return run_id, result
    raise _exhausted()
