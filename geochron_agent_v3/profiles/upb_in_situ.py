"""LA-ICP-MS-first U-Pb in-situ profile compatibility module.

The actual field card lives in ``profiles.standard`` alongside every other
USGS-backed profile.  Keeping this module preserves the explicit U-Pb tool
boundary used by the controller and MCP facade.
"""

from __future__ import annotations

from typing import Any

from .standard import build_delta_prompt, delta_schema, get_spec, validate_delta as _validate


SPEC = get_spec("upb_in_situ")
PROFILE_ID = SPEC.profile_id
MCP_SERVER = SPEC.mcp_server
TOOL_ID = SPEC.tool_id
DESCRIPTION = SPEC.description
CAPABILITY = {
    "profile_id": PROFILE_ID,
    "allowed_state_key": f"profiles.{PROFILE_ID}.samples",
    "allowed_methods": [SPEC.isotope_system],
    "allowed_techniques": list(SPEC.techniques),
    "allowed_patch_branches": [
        "sample_attributes_add",
        "method_context_add",
        "raw_observations_add",
        "aggregate_observations_add",
        "author_inferences_add",
    ],
    "may_propose_shared_samples": True,
}
SYSTEM_ROLE = (
    "你是 LA-ICP-MS 优先的 U-Pb 原位分析专业工具。你读取论文全文以保持方法、表格、"
    "图注、结果和讨论之间的证据链；你的局部状态与写入权限只属于 U-Pb 原位 profile。"
)
DELTA_PROMPT = build_delta_prompt(SPEC, "discover")
DELTA_SCHEMA: dict[str, Any] = delta_schema(PROFILE_ID, "discover")


def prompt_for(operation: str) -> str:
    return build_delta_prompt(SPEC, operation)


def validate_delta(delta: dict[str, Any]) -> dict[str, Any]:
    return _validate(SPEC, delta)
