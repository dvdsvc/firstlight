"""One top-level agent loop; specialist tools remain isolated by capability."""

from __future__ import annotations

from typing import Any

from .contracts import AgentState
from .service import audit_coverage, extract_profile_delta, plan_registered_jobs
from .state import (
    apply_profile_delta,
    coverage_context,
    mark_job_running,
    record_coverage_report,
    record_job_failure,
    record_router_plan,
    state_digest,
)


def _router_available(state: AgentState) -> bool:
    return state["controller"]["router_rounds"] < state["budget"]["max_router_rounds"]


def _risk_limit(state: AgentState) -> int:
    has_compression_risk = any(
        flag.get("type") in {"honeypot_failed", "tool_contract_violation"}
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
) -> AgentState:
    """One tool-use planning call can queue a batch of registered specialists."""
    if not _router_available(state):
        return state
    plan = await plan_registered_jobs(
        state["document_text"],
        state_digest(state),
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    return record_router_plan(state, plan["jobs"], trigger=trigger, usage=plan["usage"])


async def execute_pending_jobs(
    state: AgentState,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
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
                updated["document_text"],
                local_state,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            updated = apply_profile_delta(updated, job_id, result["delta"])
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


async def run_coverage_audit(
    state: AgentState,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> AgentState:
    if not _audit_available(state):
        return state
    result = await audit_coverage(
        state["document_text"],
        coverage_context(state),
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    updated = record_coverage_report(state, result["report"])
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
    run_audit: bool = True,
) -> AgentState:
    """Bounded default loop: plan batch, run tools, audit once, then repair if warranted."""
    updated = await dispatch_from_router(
        state, trigger="initial", api_key=api_key, base_url=base_url, model=model
    )
    updated = await execute_pending_jobs(
        updated, api_key=api_key, base_url=base_url, model=model
    )
    if not run_audit:
        return updated

    updated = await run_coverage_audit(
        updated, api_key=api_key, base_url=base_url, model=model
    )
    if _needs_follow_up(updated) and _router_available(updated):
        updated = await dispatch_from_router(
            updated, trigger="coverage_follow_up", api_key=api_key, base_url=base_url, model=model
        )
        updated = await execute_pending_jobs(
            updated, api_key=api_key, base_url=base_url, model=model
        )
    return updated
