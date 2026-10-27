"""Framework-independent tool functions; MCP only adapts these functions."""

from __future__ import annotations

from typing import Any

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


async def plan_document_tools(
    paper_text: str, state_digest: dict[str, Any]
) -> dict[str, Any]:
    return await plan_registered_jobs(paper_text, state_digest)


async def extract_upb_in_situ_delta(
    paper_text: str, current_profile_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    return await extract_profile_delta(
        "upb_in_situ", paper_text, current_profile_state or {"additions": []}
    )


async def audit_document_coverage(
    paper_text: str, coverage_context: dict[str, Any]
) -> dict[str, Any]:
    return await audit_coverage(paper_text, coverage_context)
