"""One top-level agent loop; specialist tools remain isolated by capability."""

from __future__ import annotations

from typing import Any

from .contracts import AgentState
from .honeypot import evaluate_control_run, extract_delta_relations, strip_control_relations
from .service import audit_coverage, extract_profile_delta, plan_registered_jobs
from .state import (
    apply_profile_delta,
    coverage_context,
    document_with_controls,
    mark_job_running,
    prepare_honeypot_run,
    queue_recovery_enrichment,
    record_coverage_report,
    record_honeypot_report,
    record_job_failure,
    record_model_artifact,
    record_router_plan,
    state_digest,
)


def _router_available(state: AgentState) -> bool:
    return state["controller"]["router_rounds"] < state["budget"]["max_router_rounds"]


def _risk_limit(state: AgentState) -> int:
    has_compression_risk = any(
        flag.get("type") == "tool_contract_violation"
        or (
            flag.get("type") == "honeypot_validation"
            and (flag.get("report") or {}).get("status") == "fail"
        )
        for flag in state["audit_flags"]
    )
    return (
        state["budget"]["max_audit_rounds_on_risk"]
        if has_compression_risk
        else state["budget"]["max_audit_rounds"]
    )


def _audit_available(state: AgentState) -> bool:
    completed = any(job["status"] == "completed" for job in state["jobs"])
    return completed and state["controller"]["audit_rounds"] < _risk_limit(state)


async def dispatch_from_router(
    state: AgentState,
    *,
    trigger: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    thinking_enabled: bool = False,
) -> AgentState:
    """One tool-use planning call can queue a batch of registered specialists."""
    if not _router_available(state):
        return state
    plan = await plan_registered_jobs(
        document_with_controls(state),
        state_digest(state),
        api_key=api_key,
        base_url=base_url,
        model=model,
        thinking_enabled=thinking_enabled,
    )
    updated = record_router_plan(state, plan["jobs"], trigger=trigger, usage=plan["usage"])
    return record_model_artifact(
        updated, kind="router", payload={"trigger": trigger, **plan["artifact"]}
    )


async def execute_pending_jobs(
    state: AgentState,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    thinking_enabled: bool = True,
    reasoning_effort: str = "high",
    max_tokens: int = 65536,
) -> AgentState:
    """Run each queued profile against the full document and apply only validated deltas."""
    updated = state
    pending_ids = [job["job_id"] for job in state["jobs"] if job["status"] == "pending"]
    for job_id in pending_ids:
        updated = mark_job_running(updated, job_id)
        job = next(job for job in updated["jobs"] if job["job_id"] == job_id)
        local_state = updated["profile_states"].get(
            job["profile_id"], {"samples": {}, "conflicts": [], "uncovered": []}
        )
        try:
            result = await extract_profile_delta(
                job["profile_id"],
                document_with_controls(updated),
                local_state,
                operation=job["operation"],
                api_key=api_key,
                base_url=base_url,
                model=model,
                repair_context=job.get("repair_context") or None,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            )
            updated = record_model_artifact(
                updated,
                kind="profile_delta",
                job_id=job_id,
                payload={
                    "profile_id": job["profile_id"],
                    "operation": job["operation"],
                    **result["artifact"],
                },
            )
            run = updated["honeypot"].get("active_run")
            delta = result["delta"]
            if run:
                run["observed_deltas"].append(
                    {
                        "profile_id": job["profile_id"],
                        "relations": extract_delta_relations(job["profile_id"], delta),
                    }
                )
                delta = strip_control_relations(run, delta)
            updated = apply_profile_delta(updated, job_id, delta)
            updated["audit_flags"].append(
                {
                    "type": "profile_usage",
                    "severity": "info",
                    "profile_id": job["profile_id"],
                    "usage": result["usage"],
                }
            )
        except Exception as exc:  # Preserve state and make retry policy explicit.
            updated = record_job_failure(updated, job_id, str(exc))
    return updated


def validate_honeypot(state: AgentState) -> AgentState:
    run = state["honeypot"].get("active_run")
    if not run:
        return state
    observed = [
        relation
        for delta in run.get("observed_deltas", [])
        for relation in delta.get("relations", [])
    ]
    executed_profile_ids = [
        job["profile_id"] for job in state["jobs"]
        if job["status"] in {"completed", "failed", "rejected"}
    ]
    return record_honeypot_report(
        state, evaluate_control_run(run, observed, executed_profile_ids)
    )


async def run_coverage_audit(
    state: AgentState,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    thinking_enabled: bool = False,
) -> AgentState:
    if not _audit_available(state):
        return state
    result = await audit_coverage(
        state["document_text"],
        coverage_context(state),
        api_key=api_key,
        base_url=base_url,
        model=model,
        thinking_enabled=thinking_enabled,
    )
    updated = record_coverage_report(state, result["report"])
    updated = record_model_artifact(
        updated, kind="coverage_audit", payload=result["artifact"]
    )
    updated["audit_flags"].append(
        {"type": "coverage_usage", "severity": "info", "usage": result["usage"]}
    )
    return updated


def _needs_follow_up(state: AgentState) -> bool:
    return any(item.get("type") in {"route_hint", "coverage_uncovered"} for item in state["unresolved"])


async def run_document_agent(
    state: AgentState,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    router_model: str | None = None,
    specialist_model: str | None = None,
    specialist_max_tokens: int = 65536,
    run_audit: bool = True,
) -> AgentState:
    """Plan, inject one router-anchored control, extract, validate, then repair locally."""
    router_model = router_model or model
    specialist_model = specialist_model or model
    updated = await dispatch_from_router(
        state,
        trigger="initial",
        api_key=api_key,
        base_url=base_url,
        model=router_model,
        thinking_enabled=False,
    )
    selected_profiles = [job["profile_id"] for job in updated["jobs"] if job["operation"] == "discover"]
    anchors: dict[str, list[dict[str, str]]] = {}
    for job in updated["jobs"]:
        anchor = job.get("honeypot_anchor")
        if anchor:
            anchors.setdefault(job["profile_id"], []).append(anchor)
    updated = prepare_honeypot_run(updated, selected_profiles, route_anchors=anchors)
    updated = await execute_pending_jobs(
        updated,
        api_key=api_key,
        base_url=base_url,
        model=specialist_model,
        thinking_enabled=True,
        reasoning_effort="high",
        max_tokens=specialist_max_tokens,
    )
    updated = validate_honeypot(updated)
    updated = queue_recovery_enrichment(updated)
    updated = await execute_pending_jobs(
        updated,
        api_key=api_key,
        base_url=base_url,
        model=specialist_model,
        thinking_enabled=True,
        reasoning_effort="high",
        max_tokens=specialist_max_tokens,
    )
    if not run_audit:
        return updated

    updated = await run_coverage_audit(
        updated,
        api_key=api_key,
        base_url=base_url,
        model=router_model,
        thinking_enabled=False,
    )
    if _needs_follow_up(updated) and _router_available(updated):
        updated = await dispatch_from_router(
            updated,
            trigger="coverage_follow_up",
            api_key=api_key,
            base_url=base_url,
            model=router_model,
            thinking_enabled=False,
        )
        updated = await execute_pending_jobs(
            updated,
            api_key=api_key,
            base_url=base_url,
            model=specialist_model,
            thinking_enabled=True,
            reasoning_effort="high",
            max_tokens=specialist_max_tokens,
        )
    return updated
