"""MCP facade for the controller, specialist profile, and audit tools."""

from __future__ import annotations

from typing import Any

try:
    from mcp.server import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit('Install the official SDK with: pip install "mcp[cli]"') from exc

from .tools import (
    audit_document_coverage,
    extract_profile_delta_for_profile,
    extract_upb_in_situ_delta,
    get_profile_contract,
    evaluate_honeypot_validation,
    inject_honeypot_controls,
    list_geochron_profiles,
    plan_document_tools,
    prepare_honeypot_validation,
    route_geochronology_document,
    validate_profile_delta,
)


mcp = MCPServer(
    "Geochronology Agent Tools",
    instructions=(
        "顶层 Agent 可先调用 plan_document_tools 分发零个、一个或多个注册工具。"
        "专业工具读取全文但只返回自己的增量；coverage audit 只报告缺口、冲突和路由提示。"
    ),
)


@mcp.tool()
def list_profiles() -> list[dict[str, Any]]:
    """列出已注册 profile、职责和写入能力。"""
    return list_geochron_profiles()


@mcp.tool()
def route_geochronology(text: str) -> list[dict[str, Any]]:
    """提供低成本关键词 fallback，不替代顶层 tool-use planner。"""
    return route_geochronology_document(text)


@mcp.tool()
def profile_contract(profile_id: str) -> dict[str, Any]:
    """获取某一专业 tool 的 delta 契约与能力边界。"""
    return get_profile_contract(profile_id)


@mcp.tool()
def validate_delta(profile_id: str, delta: dict[str, Any]) -> dict[str, Any]:
    """验证 profile delta 是否越过 method、technique 或节点类型权限。"""
    return validate_profile_delta(profile_id, delta)


@mcp.tool()
def prepare_honeypot(
    document_id: str, profile_ids: list[str], max_controls: int = 3
) -> dict[str, Any]:
    """按本轮已路由 profile 选择少量控制记录。"""
    return prepare_honeypot_validation(document_id, profile_ids, max_controls)


@mcp.tool()
def inject_honeypot(
    paper_text: str,
    run: dict[str, Any],
    document_structure: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """在结果段内部嵌入控制证据，并返回增广文本及外部注入坐标。"""
    return inject_honeypot_controls(paper_text, run, document_structure)


@mcp.tool()
def evaluate_honeypot(
    run: dict[str, Any], observed_relations: list[dict[str, Any]]
) -> dict[str, Any]:
    """返回 pass，或 fail 加精确失败原因。"""
    return evaluate_honeypot_validation(run, observed_relations)


@mcp.tool()
async def plan_document_tools_tool(
    paper_text: str, state_digest: dict[str, Any]
) -> dict[str, Any]:
    """顶层 Agent 的一次多工具派发调用，不抽取数据。"""
    return await plan_document_tools(paper_text, state_digest)


@mcp.tool()
async def extract_upb_in_situ(
    paper_text: str, current_profile_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    """全文输入的 LA-ICP-MS-first U-Pb 工具；只返回新增、冲突、未覆盖项。"""
    return await extract_upb_in_situ_delta(paper_text, current_profile_state)


@mcp.tool()
async def extract_profile_delta(
    profile_id: str,
    operation: str,
    paper_text: str,
    current_profile_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行一张已注册 profile 卡的 discover 或 enrich_candidates 操作。

    顶层 Agent 先通过计划工具选择 profile；该调用读取全文，但只返回该 profile 的树状状态增量。
    """
    return await extract_profile_delta_for_profile(
        profile_id, operation, paper_text, current_profile_state
    )


@mcp.tool()
async def audit_coverage(
    paper_text: str, coverage_context: dict[str, Any]
) -> dict[str, Any]:
    """全文覆盖审查，不重新输出抽取结果。"""
    return await audit_document_coverage(paper_text, coverage_context)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
