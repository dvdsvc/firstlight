"""Framework-independent tool functions; MCP only adapts these functions."""

from __future__ import annotations

from typing import Any

from .honeypot import (
    build_control_run,
    evaluate_control_run,
    inject_controls_into_structure,
    plan_structural_injections,
)
from .registry import get_profile, list_profiles
from .router import route_geochronology
from .service import audit_coverage, extract_profile_delta, plan_registered_jobs


def list_geochron_profiles() -> list[dict[str, Any]]:
    return list_profiles()


def route_geochronology_document(text: str) -> list[dict[str, Any]]:
    """Deterministic fallback; the top-level planner is the primary dispatcher."""
    return route_geochronology(text)


def get_profile_contract(profile_id: str) -> dict[str, Any]:
    return get_profile(profile_id).public_contract()


def validate_profile_delta(profile_id: str, delta: dict[str, Any]) -> dict[str, Any]:
    return get_profile(profile_id).validator(delta)


def prepare_honeypot_validation(
    document_id: str, profile_ids: list[str], max_controls: int = 3
) -> dict[str, Any]:
    """Create a small profile-aware control bundle for one document run."""
    return build_control_run(document_id, profile_ids, max_controls=max_controls)


def inject_honeypot_controls(
    paper_text: str,
    run: dict[str, Any],
    document_structure: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Embed controls in result domains and return text plus external coordinates."""
    planned = plan_structural_injections(paper_text, run, document_structure)
    return {"paper_text": inject_controls_into_structure(paper_text, planned), "run": planned}


def evaluate_honeypot_validation(
    run: dict[str, Any], observed_relations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare observed relation deltas with control expectations."""
    return evaluate_control_run(run, observed_relations)


async def plan_document_tools(
    paper_text: str, state_digest: dict[str, Any]
) -> dict[str, Any]:
    return await plan_registered_jobs(paper_text, state_digest)


async def extract_upb_in_situ_delta(
    paper_text: str, current_profile_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    return await extract_profile_delta(
        "upb_in_situ", paper_text, current_profile_state or {"samples": {}}, operation="discover"
    )


async def extract_profile_delta_for_profile(
    profile_id: str,
    operation: str,
    paper_text: str,
    current_profile_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MCP adapter for one already-selected profile card.

    The selected ``profile_id`` determines the isolated local state, standard
    field card and write capability.  This adapter avoids duplicating Python
    transport code for every isotope server while preserving distinct profile
    tool IDs in the registry.
    """
    get_profile(profile_id)
    return await extract_profile_delta(
        profile_id,
        paper_text,
        current_profile_state or {"samples": {}},
        operation=operation,
    )


async def audit_document_coverage(
    paper_text: str, coverage_context: dict[str, Any]
) -> dict[str, Any]:
    return await audit_coverage(paper_text, coverage_context)
