"""Shared, serializable contracts for the document-run agent."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


RouteStatus = Literal["selected", "review", "unsupported"]
JobStatus = Literal["pending", "running", "completed", "failed", "rejected", "skipped"]
ToolKind = Literal["profile", "audit", "metadata"]


class RouteDecision(TypedDict):
    profile_id: str
    status: RouteStatus
    mcp_server: str | None
    tool_id: str | None
    confidence: float
    isotope_system: str
    technique: str | None
    matched_evidence: list[str]
    blocking_evidence: list[str]
    reason: str


class ToolCapability(TypedDict):
    profile_id: str
    allowed_state_key: str
    allowed_methods: list[str]
    allowed_techniques: list[str]
    allowed_patch_branches: list[str]
    may_propose_shared_samples: bool


class ToolRequest(TypedDict):
    profile_id: str
    reason: str
    evidence: list[str]


class ProfileJob(TypedDict):
    job_id: str
    profile_id: str
    mcp_server: str
    tool_id: str
    status: JobStatus
    route_evidence: list[str]
    trigger: str
    attempt: int
    capability: ToolCapability
    result: dict[str, Any] | None
    error: str | None


class ProfileDelta(TypedDict):
    profile_id: str
    sample_patches: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    uncovered: list[dict[str, Any]]


class AgentBudget(TypedDict):
    max_router_rounds: int
    max_profile_attempts_per_profile: int
    max_audit_rounds: int
    max_audit_rounds_on_risk: int


class AgentState(TypedDict):
    document_id: str
    document_text: str
    state_revision: int
    shared_sample_registry: dict[str, dict[str, Any]]
    route_decisions: list[RouteDecision]
    jobs: list[ProfileJob]
    profile_states: dict[str, dict[str, Any]]
    unresolved: list[dict[str, Any]]
    audit_flags: list[dict[str, Any]]
    controller: dict[str, int]
    budget: AgentBudget
