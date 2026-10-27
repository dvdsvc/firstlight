"""Registered specialist tools: isotope MCP boundary, instrument profile inside it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import ToolCapability
from .profiles.standard import (
    PROFILE_SPECS,
    USGS_TEMPLATE_RELEASE,
    ProfileSpec,
    build_delta_prompt,
    delta_schema,
    validate_delta as validate_standard_delta,
)


Validator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ProfileDefinition:
    spec: ProfileSpec
    system_role: str
    capability: ToolCapability
    validator: Validator

    @property
    def profile_id(self) -> str:
        return self.spec.profile_id

    @property
    def mcp_server(self) -> str:
        return self.spec.mcp_server

    @property
    def tool_id(self) -> str:
        return self.spec.tool_id

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def delta_prompt(self) -> str:
        return build_delta_prompt(self.spec, "discover")

    @property
    def json_schema(self) -> dict[str, Any]:
        return self.json_schema_for("discover")

    def json_schema_for(self, operation: str) -> dict[str, Any]:
        return delta_schema(self.profile_id, operation)

    def prompt_for(self, operation: str) -> str:
        return build_delta_prompt(self.spec, operation)

    def public_contract(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "mcp_server": self.mcp_server,
            "tool_id": self.tool_id,
            "isotope_system": self.spec.isotope_system,
            "techniques": list(self.spec.techniques),
            "template": self.spec.template,
            "source": USGS_TEMPLATE_RELEASE,
            "semantic_tree": [
                "sample_attributes_add",
                "method_context_add",
                "raw_observations_add",
                "aggregate_observations_add",
                "author_inferences_add",
            ],
            "operations": {
                "discover": self.spec.fields_for("discover"),
                "enrich_candidates": self.spec.fields_for("enrich_candidates"),
            },
            "capability": self.capability,
            "json_schema": self.json_schema,
        }

    def tool_card(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "mcp_server": self.mcp_server,
            "tool_id": self.tool_id,
            "isotope_system": self.spec.isotope_system,
            "techniques": list(self.spec.techniques),
            "description": self.description,
            "when_to_call": "全文出现本体系、工作流或待补全的本 profile 证据时。",
            "operations": ["discover", "enrich_candidates"],
            "writes": self.capability["allowed_patch_branches"],
            "source_template": self.spec.template,
        }


def _definition(spec: ProfileSpec) -> ProfileDefinition:
    capability: ToolCapability = {
        "profile_id": spec.profile_id,
        "allowed_state_key": f"profiles.{spec.profile_id}.samples",
        "allowed_methods": [spec.isotope_system],
        "allowed_techniques": list(spec.techniques),
        "allowed_patch_branches": [
            "sample_attributes_add",
            "method_context_add",
            "raw_observations_add",
            "aggregate_observations_add",
            "author_inferences_add",
        ],
        "may_propose_shared_samples": True,
    }
    return ProfileDefinition(
        spec=spec,
        system_role=(
            f"你是 {spec.description}。你可阅读论文全文以保持跨段、表格、图注、结果与讨论"
            f"的证据链；你只为 {spec.profile_id} 的局部状态提出增量。"
        ),
        capability=capability,
        validator=lambda delta, profile_spec=spec: validate_standard_delta(profile_spec, delta),
    )


_PROFILES = {spec.profile_id: _definition(spec) for spec in PROFILE_SPECS}


def get_profile(profile_id: str) -> ProfileDefinition:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(_PROFILES))
        raise ValueError(f"unknown profile {profile_id!r}; known profiles: {known}") from exc


def list_profiles() -> list[dict[str, Any]]:
    return [profile.tool_card() for profile in _PROFILES.values()]
