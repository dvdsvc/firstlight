"""Registered specialist tools and their write capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import ToolCapability
from .profiles import upb_in_situ


Validator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    mcp_server: str
    tool_id: str
    description: str
    system_role: str
    delta_prompt: str
    json_schema: dict[str, Any]
    capability: ToolCapability
    validator: Validator

    def public_contract(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "mcp_server": self.mcp_server,
            "tool_id": self.tool_id,
            "description": self.description,
            "capability": self.capability,
            "delta_prompt": self.delta_prompt,
            "json_schema": self.json_schema,
        }

    def tool_card(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "tool_id": self.tool_id,
            "description": self.description,
            "when_to_call": "全文存在该体系/技术的作者自测或需补全的疑似证据时。",
            "writes": self.capability["allowed_patch_branches"],
            "does_not_handle": "其他同位素体系的提取或全局最终结果编译。",
        }


_PROFILES = {
    upb_in_situ.PROFILE_ID: ProfileDefinition(
        profile_id=upb_in_situ.PROFILE_ID,
        mcp_server=upb_in_situ.MCP_SERVER,
        tool_id=upb_in_situ.TOOL_ID,
        description=upb_in_situ.DESCRIPTION,
        system_role=upb_in_situ.SYSTEM_ROLE,
        delta_prompt=upb_in_situ.DELTA_PROMPT,
        json_schema=upb_in_situ.DELTA_SCHEMA,
        capability=upb_in_situ.CAPABILITY,
        validator=upb_in_situ.validate_delta,
    )
}


def get_profile(profile_id: str) -> ProfileDefinition:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(_PROFILES))
        raise ValueError(f"unknown profile {profile_id!r}; known profiles: {known}") from exc


def list_profiles() -> list[dict[str, Any]]:
    return [profile.tool_card() for profile in _PROFILES.values()]
