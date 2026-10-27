"""Deterministic state transitions for one document-run agent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .contracts import AgentBudget, AgentState, ProfileDelta, ToolRequest
from .honeypot import (
    build_control_run,
    inject_controls_into_structure,
    plan_structural_injections,
    recovery_tasks,
)
from .registry import get_profile
from .router import route_geochronology


DEFAULT_BUDGET: AgentBudget = {
    "max_router_rounds": 2,
    "max_profile_attempts_per_profile": 2,
    "max_audit_rounds": 1,
    "max_audit_rounds_on_risk": 2,
    "max_honeypot_controls": 3,
}

_PATCH_BRANCHES = {
    "sample_attributes_add",
    "sample_evidence",
    "method_context_add",
    "method_evidence",
    "raw_observations_add",
    "aggregate_observations_add",
    "author_inferences_add",
}


def create_state(
    document_id: str,
    document_text: str,
    budget: AgentBudget | None = None,
    document_structure: list[dict[str, Any]] | None = None,
) -> AgentState:
    state: AgentState = {
        "document_id": document_id,
        "document_text": document_text,
        "state_revision": 0,
        "shared_sample_registry": {},
        "route_decisions": [],
        "jobs": [],
        "profile_states": {},
        "unresolved": [],
        "audit_flags": [],
        "honeypot": {"active_run": None, "reports": []},
        "model_artifacts": [],
        "controller": {"router_rounds": 0, "audit_rounds": 0},
        "budget": {**DEFAULT_BUDGET, **(budget or {})},
    }
    if document_structure:
        state["document_structure"] = document_structure
    return state


def prepare_honeypot_run(
    state: AgentState,
    profile_ids: Iterable[str],
    route_anchors: dict[str, list[dict[str, str]]] | None = None,
) -> AgentState:
    """Inject controls at router-selected evidence anchors when available."""
    updated = deepcopy(state)
    if updated["honeypot"].get("active_run") is not None:
        return updated
    run = build_control_run(
        updated["document_id"],
        profile_ids,
        max_controls=updated["budget"]["max_honeypot_controls"],
    )
    if route_anchors is not None:
        from .honeypot import plan_router_injections

        run = plan_router_injections(updated["document_text"], run, route_anchors)
    else:
        run = plan_structural_injections(
            updated["document_text"], run, updated.get("document_structure")
        )
    if run["controls"]:
        updated["honeypot"]["active_run"] = run
    return updated


def document_with_controls(state: AgentState) -> str:
    run = state["honeypot"].get("active_run")
    return inject_controls_into_structure(state["document_text"], run) if run else state["document_text"]


def record_honeypot_report(state: AgentState, report: dict[str, Any]) -> AgentState:
    updated = deepcopy(state)
    run = updated["honeypot"].get("active_run")
    report = {**report, "trace": deepcopy(run) if run else None}
    updated["honeypot"]["reports"].append(report)
    updated["honeypot"]["active_run"] = None
    severity = "info" if report.get("status") == "pass" else "warning"
    updated["audit_flags"].append(
        {"type": "honeypot_validation", "severity": severity, "report": report}
    )
    for task in recovery_tasks(report):
        updated["unresolved"].append({"type": "honeypot_recovery", "detail": task})
    return updated


def _empty_profile_state() -> dict[str, Any]:
    return {"samples": {}, "conflicts": [], "uncovered": []}


def _empty_sample_state(sample_id: str) -> dict[str, Any]:
    return {
        "sample_id": sample_id,
        "sample_attributes": {},
        "method_context": {},
        "raw_observations": [],
        "aggregate_observations": [],
        "author_inferences": [],
        "evidence": [],
    }


def _profile_attempts(state: AgentState, profile_id: str) -> int:
    return sum(1 for job in state["jobs"] if job["profile_id"] == profile_id)


def _has_open_job(state: AgentState, profile_id: str) -> bool:
    return any(
        job["profile_id"] == profile_id and job["status"] in {"pending", "running"}
        for job in state["jobs"]
    )


def queue_tool_jobs(
    state: AgentState,
    requests: Iterable[ToolRequest],
    *,
    trigger: str,
) -> AgentState:
    """Queue any number of registered profile tools; the model never writes jobs directly."""
    updated = deepcopy(state)
    for request in requests:
        profile_id = request["profile_id"]
        try:
            profile = get_profile(profile_id)
        except ValueError:
            updated["unresolved"].append(
                {
                    "type": "unknown_profile_request",
                    "profile_id": profile_id,
                    "reason": request.get("reason", ""),
                    "evidence": request.get("evidence", []),
                }
            )
            continue
        if _has_open_job(updated, profile_id):
            continue
        attempt = _profile_attempts(updated, profile_id) + 1
        if attempt > updated["budget"]["max_profile_attempts_per_profile"]:
            updated["unresolved"].append(
                {
                    "type": "profile_budget_exhausted",
                    "profile_id": profile_id,
                    "reason": request["reason"],
                    "evidence": request["evidence"],
                }
            )
            continue
        updated["jobs"].append(
            {
                "job_id": f"{updated['document_id']}:{profile_id}:{attempt}",
                "profile_id": profile_id,
                "mcp_server": profile.mcp_server,
                "tool_id": profile.tool_id,
                "status": "pending",
                "route_evidence": request["evidence"],
                "honeypot_anchor": request.get("honeypot_anchor"),
                "repair_context": request.get("repair_context", []),
                "trigger": trigger,
                "operation": request.get("operation", "discover"),
                "attempt": attempt,
                "capability": profile.capability,
                "result": None,
                "error": None,
                "model_artifact": None,
            }
        )
    return updated


def record_router_plan(
    state: AgentState,
    requests: Iterable[ToolRequest],
    *,
    trigger: str,
    usage: dict[str, Any] | None = None,
) -> AgentState:
    updated = queue_tool_jobs(state, requests, trigger=trigger)
    updated["controller"]["router_rounds"] += 1
    if usage:
        updated["audit_flags"].append(
            {"type": "router_usage", "severity": "info", "usage": usage}
        )
    return updated


def record_model_artifact(
    state: AgentState,
    *,
    kind: str,
    payload: dict[str, Any],
    job_id: str | None = None,
) -> AgentState:
    """Persist every model reply, including replies later rejected by validation."""
    updated = deepcopy(state)
    artifact = {"kind": kind, "payload": payload}
    if job_id is not None:
        artifact["job_id"] = job_id
        _job(updated, job_id)["model_artifact"] = payload
    updated["model_artifacts"].append(artifact)
    return updated


def queue_recovery_enrichment(state: AgentState) -> AgentState:
    """Turn a rejected initial patch or failed control into one narrow repair job."""
    requests: list[ToolRequest] = []
    honeypot_failed = bool(
        (state["honeypot"].get("reports") or [{}])[-1].get("status") == "fail"
    )
    for job in state["jobs"]:
        if job["attempt"] != 1 or job["status"] not in {"rejected", "completed"}:
            continue
        repair_context: list[str] = []
        if job["status"] == "rejected" and job.get("error"):
            repair_context.append(job["error"])
        if honeypot_failed:
            repair_context.append("本 profile 的结构化控制验证失败；优先核对样品归属和结果是否被遗漏或合并。")
        if not repair_context:
            continue
        requests.append(
            {
                "profile_id": job["profile_id"],
                "operation": "enrich_candidates",
                "reason": "针对首次状态写入或控制验证失败进行局部修复。",
                "evidence": job["route_evidence"],
                "repair_context": repair_context,
            }
        )
    return queue_tool_jobs(state, requests, trigger="validation_recovery")


def route_state(state: AgentState) -> AgentState:
    """Compatibility fallback: deterministic signals can seed the first tool batch."""
    updated = deepcopy(state)
    decisions = route_geochronology(updated["document_text"])
    updated["route_decisions"] = decisions
    requests: list[ToolRequest] = []
    for decision in decisions:
        if decision["status"] == "selected" and decision["tool_id"]:
            requests.append(
                {
                    "profile_id": decision["profile_id"],
                    "reason": decision["reason"],
                    "evidence": decision["matched_evidence"],
                }
            )
        else:
            updated["unresolved"].append(
                {
                    "type": "profile_route",
                    "profile_id": decision["profile_id"],
                    "status": decision["status"],
                    "reason": decision["reason"],
                    "evidence": decision["matched_evidence"],
                }
            )
    if not decisions:
        updated["audit_flags"].append(
            {
                "type": "no_geochronology_route",
                "severity": "info",
                "message": "未检测到当前 registry 支持的年代学 profile。",
            }
        )
    return queue_tool_jobs(updated, requests, trigger="signal_fallback")


def _job(updated: AgentState, job_id: str) -> dict[str, Any]:
    for job in updated["jobs"]:
        if job["job_id"] == job_id:
            return job
    raise ValueError(f"unknown job_id {job_id!r}")


def mark_job_running(state: AgentState, job_id: str) -> AgentState:
    updated = deepcopy(state)
    job = _job(updated, job_id)
    if job["status"] != "pending":
        raise ValueError(f"job {job_id!r} is not pending")
    job["status"] = "running"
    return updated


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {item["id"] for item in items if isinstance(item.get("id"), str)}


def _evidence_values(patch: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for key in ("sample_evidence", "method_evidence"):
        value = patch.get(key)
        if isinstance(value, dict) and value.get("evidence_text"):
            evidence.append(value)
    for branch in (
        "raw_observations_add",
        "aggregate_observations_add",
        "author_inferences_add",
    ):
        for child in patch.get(branch) or []:
            value = child.get("evidence") if isinstance(child, dict) else None
            if isinstance(value, dict) and value.get("evidence_text"):
                evidence.append(value)
    return evidence


def _merge_mapping(
    target: dict[str, Any], source: dict[str, Any], path: str, errors: list[str]
) -> None:
    for key, value in source.items():
        if key in target and target[key] is not None and target[key] != value:
            errors.append(f"conflicting update for {path}.{key}")
        else:
            target[key] = value


def _validate_patch_against_state(
    profile_state: dict[str, Any], patches: list[dict[str, Any]], errors: list[str]
) -> None:
    seen_samples: set[str] = set()
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        unknown = set(patch) - ({"sample_id"} | _PATCH_BRANCHES)
        if unknown:
            errors.append(f"sample patch {patch.get('sample_id')} has forbidden keys {sorted(unknown)}")
        sample_id = patch.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            continue
        if sample_id in seen_samples:
            errors.append(f"duplicate sample patch in delta: {sample_id}")
        seen_samples.add(sample_id)
        sample = profile_state["samples"].get(sample_id, _empty_sample_state(sample_id))

        current_raw = _ids(sample["raw_observations"])
        current_aggregate = _ids(sample["aggregate_observations"])
        current_inferences = _ids(sample["author_inferences"])
        new_raw = _ids(patch.get("raw_observations_add") or [])
        new_aggregate = _ids(patch.get("aggregate_observations_add") or [])
        new_inferences = _ids(patch.get("author_inferences_add") or [])
        for label, current, new in (
            ("raw_observation", current_raw, new_raw),
            ("aggregate_observation", current_aggregate, new_aggregate),
            ("author_inference", current_inferences, new_inferences),
        ):
            overlap = current & new
            if overlap:
                errors.append(f"sample {sample_id} already has {label} ids {sorted(overlap)}")

        known_raw = current_raw | new_raw
        for aggregate in patch.get("aggregate_observations_add") or []:
            refs = aggregate.get("source_raw_observation_ids") if isinstance(aggregate, dict) else None
            if not isinstance(refs, list):
                continue
            missing = [raw_id for raw_id in refs if raw_id not in known_raw]
            if missing:
                errors.append(
                    f"sample {sample_id} aggregate {aggregate.get('id')} references missing raw observations {missing}"
                )

        known_aggregate = current_aggregate | new_aggregate
        for inference in patch.get("author_inferences_add") or []:
            refs = inference.get("aggregate_observation_ids") if isinstance(inference, dict) else None
            if not isinstance(refs, list) or not refs:
                errors.append(
                    f"sample {sample_id} author inference {inference.get('id')} must reference aggregate observations"
                )
                continue
            missing = [aggregate_id for aggregate_id in refs if aggregate_id not in known_aggregate]
            if missing:
                errors.append(
                    f"sample {sample_id} author inference {inference.get('id')} references missing aggregates {missing}"
                )


def _register_sample(updated: AgentState, patch: dict[str, Any], profile_id: str) -> None:
    sample_id = patch["sample_id"].strip()
    key = sample_id.casefold()
    record = updated["shared_sample_registry"].setdefault(
        key,
        {"canonical_id": sample_id, "aliases": [], "evidence": [], "profiles": []},
    )
    if sample_id not in record["aliases"]:
        record["aliases"].append(sample_id)
    for evidence in _evidence_values(patch):
        if evidence not in record["evidence"]:
            record["evidence"].append(evidence)
    if profile_id not in record["profiles"]:
        record["profiles"].append(profile_id)


def apply_profile_delta(state: AgentState, job_id: str, delta: ProfileDelta) -> AgentState:
    """The sole state writer. It converts a semantic tree patch into checked local writes."""
    updated = deepcopy(state)
    job = _job(updated, job_id)
    profile = get_profile(job["profile_id"])
    report = profile.validator(delta)
    errors = list(report["errors"])
    if delta.get("profile_id") != job["profile_id"]:
        errors.append("delta profile_id does not match the job capability")
    patches = delta.get("sample_patches") if isinstance(delta.get("sample_patches"), list) else []

    local_state = deepcopy(updated["profile_states"].get(job["profile_id"], _empty_profile_state()))
    _validate_patch_against_state(local_state, patches, errors)
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        requested_branches = set(patch) & {
            "sample_attributes_add",
            "method_context_add",
            "raw_observations_add",
            "aggregate_observations_add",
            "author_inferences_add",
        }
        forbidden_branches = requested_branches - set(job["capability"]["allowed_patch_branches"])
        if forbidden_branches:
            errors.append(
                f"sample {patch.get('sample_id')} violates patch write capability {sorted(forbidden_branches)}"
            )
        context = patch.get("method_context_add") or {}
        if context and context.get("isotope_system") not in job["capability"]["allowed_methods"]:
            errors.append(f"sample {patch.get('sample_id')} violates method write capability")
        if context and context.get("technique") not in job["capability"]["allowed_techniques"]:
            errors.append(f"sample {patch.get('sample_id')} violates technique write capability")

    if errors:
        job["status"] = "rejected"
        job["error"] = "; ".join(errors)
        updated["audit_flags"].append(
            {
                "type": "tool_contract_violation",
                "severity": "error",
                "job_id": job_id,
                "profile_id": job["profile_id"],
                "errors": errors,
            }
        )
        return updated

    accepted_raw = accepted_aggregate = accepted_inferences = 0
    for patch in patches:
        sample_id = patch["sample_id"]
        sample = local_state["samples"].setdefault(sample_id, _empty_sample_state(sample_id))
        _merge_mapping(
            sample["sample_attributes"],
            patch.get("sample_attributes_add") or {},
            sample_id,
            errors,
        )
        _merge_mapping(
            sample["method_context"],
            patch.get("method_context_add") or {},
            f"{sample_id}.method_context",
            errors,
        )
        for evidence in _evidence_values(patch):
            if evidence not in sample["evidence"]:
                sample["evidence"].append(evidence)
        sample["raw_observations"].extend(patch.get("raw_observations_add") or [])
        sample["aggregate_observations"].extend(
            patch.get("aggregate_observations_add") or []
        )
        sample["author_inferences"].extend(patch.get("author_inferences_add") or [])
        accepted_raw += len(patch.get("raw_observations_add") or [])
        accepted_aggregate += len(patch.get("aggregate_observations_add") or [])
        accepted_inferences += len(patch.get("author_inferences_add") or [])
        if job["capability"]["may_propose_shared_samples"]:
            _register_sample(updated, patch, job["profile_id"])

    if errors:
        job["status"] = "rejected"
        job["error"] = "; ".join(errors)
        updated["audit_flags"].append(
            {"type": "merge_conflict", "severity": "error", "job_id": job_id, "errors": errors}
        )
        return updated

    local_state["conflicts"].extend(delta.get("conflicts", []))
    local_state["uncovered"].extend(delta.get("uncovered", []))
    updated["profile_states"][job["profile_id"]] = local_state
    for item in delta.get("uncovered", []):
        updated["unresolved"].append(
            {"type": "profile_uncovered", "profile_id": job["profile_id"], "detail": item}
        )
    for item in delta.get("conflicts", []):
        updated["audit_flags"].append(
            {"type": "profile_conflict", "severity": "warning", "profile_id": job["profile_id"], "detail": item}
        )
    job["status"] = "completed"
    job["result"] = {
        "validation": report,
        "accepted": {
            "sample_patches": len(patches),
            "raw_observations": accepted_raw,
            "aggregate_observations": accepted_aggregate,
            "author_inferences": accepted_inferences,
        },
    }
    updated["state_revision"] += 1
    return updated


def record_job_failure(state: AgentState, job_id: str, error: str) -> AgentState:
    updated = deepcopy(state)
    job = _job(updated, job_id)
    job["status"] = "failed"
    job["error"] = error
    updated["audit_flags"].append(
        {"type": "profile_job_failed", "severity": "error", "job_id": job_id, "error": error}
    )
    return updated


def record_coverage_report(state: AgentState, report: dict[str, Any]) -> AgentState:
    """Coverage audit reports tasks; it cannot mutate any profile state."""
    updated = deepcopy(state)
    for item in report.get("uncovered", []):
        updated["unresolved"].append({"type": "coverage_uncovered", "detail": item})
    for item in report.get("conflicts", []):
        updated["audit_flags"].append(
            {"type": "coverage_conflict", "severity": "warning", "detail": item}
        )
    for item in report.get("route_hints", []):
        updated["unresolved"].append({"type": "route_hint", "detail": item})
    updated["controller"]["audit_rounds"] += 1
    return updated


def _profile_counts(local: dict[str, Any]) -> dict[str, int]:
    samples = list(local.get("samples", {}).values())
    return {
        "sample_count": len(samples),
        "raw_observations": sum(len(sample.get("raw_observations", [])) for sample in samples),
        "aggregate_observations": sum(
            len(sample.get("aggregate_observations", [])) for sample in samples
        ),
        "author_inferences": sum(
            len(sample.get("author_inferences", [])) for sample in samples
        ),
        "conflicts": len(local.get("conflicts", [])),
        "uncovered": len(local.get("uncovered", [])),
    }


def state_digest(state: AgentState) -> dict[str, Any]:
    """Small controller context: never include the paper text or duplicate profile trees."""
    return {
        "document_id": state["document_id"],
        "state_revision": state["state_revision"],
        "samples": [record["canonical_id"] for record in state["shared_sample_registry"].values()],
        "jobs": [
            {
                "profile_id": job["profile_id"],
                "status": job["status"],
                "attempt": job["attempt"],
                "trigger": job["trigger"],
                "operation": job["operation"],
            }
            for job in state["jobs"]
        ],
        "profile_counts": {
            profile_id: _profile_counts(local)
            for profile_id, local in state["profile_states"].items()
        },
        "unresolved_count": len(state["unresolved"]),
        "audit_flag_count": len(state["audit_flags"]),
        "honeypot": {
            "runs": len(state["honeypot"].get("reports", [])),
            "last_status": (state["honeypot"].get("reports") or [{}])[-1].get("status"),
        },
        "controller": state["controller"],
        "budget": state["budget"],
    }


def coverage_context(state: AgentState, max_claims_per_profile: int = 200) -> dict[str, Any]:
    """Compact audit inventory; raw rows stay out while semantic hierarchy remains."""
    profiles: dict[str, dict[str, Any]] = {}
    for profile_id, local in state["profile_states"].items():
        samples: list[dict[str, Any]] = []
        for sample in local.get("samples", {}).values():
            aggregates = sample.get("aggregate_observations", [])[:max_claims_per_profile]
            inferences = sample.get("author_inferences", [])[:max_claims_per_profile]
            samples.append(
                {
                    "sample_id": sample["sample_id"],
                    "method_context": sample.get("method_context", {}),
                    "raw_observation_count": len(sample.get("raw_observations", [])),
                    "aggregate_observations": aggregates,
                    "author_inferences": inferences,
                    "aggregates_truncated": (
                        len(sample.get("aggregate_observations", [])) > len(aggregates)
                    ),
                    "inferences_truncated": (
                        len(sample.get("author_inferences", [])) > len(inferences)
                    ),
                }
            )
        profiles[profile_id] = {"samples": samples, **_profile_counts(local)}
    return {
        "document_id": state["document_id"],
        "state_revision": state["state_revision"],
        "registered_samples": [
            record["canonical_id"] for record in state["shared_sample_registry"].values()
        ],
        "profiles": profiles,
        "unresolved": state["unresolved"],
        "audit_flags": state["audit_flags"],
    }
