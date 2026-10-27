"""Local MCP stdio handshake and calls to deterministic tools; no LLM calls."""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED = {"list_profiles", "route_geochronology", "profile_contract", "validate_delta", "prepare_honeypot", "inject_honeypot", "evaluate_honeypot", "plan_document_tools_tool", "extract_upb_in_situ", "extract_profile_delta", "audit_coverage"}

def unpack(result, *, sequence=False):
    if result.isError:
        raise RuntimeError(str(result))
    structured = result.structuredContent
    if structured is not None:
        if sequence and isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured
    blocks = [json.loads(block.text) for block in result.content if hasattr(block, "text")]
    if sequence:
        return blocks[0] if len(blocks) == 1 and isinstance(blocks[0], list) else blocks
    if len(blocks) != 1:
        raise RuntimeError("Expected one object in MCP tool response")
    return blocks[0]

async def main():
    params = StdioServerParameters(command=str(Path(sys.executable).parent / "geochron-mcp"), args=[], cwd=str(Path(__file__).resolve().parents[1]))
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            listing = await session.list_tools()
            names = {tool.name for tool in listing.tools}
            if names != EXPECTED:
                raise RuntimeError(f"Unexpected MCP tools: {names}")
            profiles = unpack(await session.call_tool("list_profiles", {}), sequence=True)
            routes = unpack(await session.call_tool("route_geochronology", {"text": "Zircon U-Pb LA-ICP-MS spot analyses."}), sequence=True)
            contract = unpack(await session.call_tool("profile_contract", {"profile_id": "upb_in_situ"}))
            fixture = json.loads((Path(__file__).resolve().parents[1] / "examples/fixtures/synthetic_delta.json").read_text())
            validation = unpack(await session.call_tool("validate_delta", {"profile_id": "upb_in_situ", "delta": fixture}))
            prepared = unpack(await session.call_tool("prepare_honeypot", {"document_id": "synthetic", "profile_ids": ["upb_in_situ"], "max_controls": 3}))
            injected = unpack(await session.call_tool("inject_honeypot", {"paper_text": "3.1 Results\nSample DEMO101 zircon U-Pb age is 120±1 Ma.\n4 Discussion\n", "run": prepared}))
            observed = [{**r, "profile_id": "upb_in_situ"} for c in prepared["controls"] for r in c["expected_relations"]]
            evaluated = unpack(await session.call_tool("evaluate_honeypot", {"run": prepared, "observed_relations": observed}))
            if len(profiles) != 17 or not any(r["status"] == "selected" for r in routes) or contract["profile_id"] != "upb_in_situ" or not validation["valid"] or evaluated["status"] != "pass":
                raise RuntimeError("Deterministic MCP tool checks failed")
            if "HPUPB-01" not in injected["paper_text"] or len(injected["run"]["injections"]) != 3:
                raise RuntimeError("No control injection response")
            print(json.dumps({"transport": "stdio", "tool_count": len(names), "tools": sorted(names), "registered_profiles": len(profiles), "deterministic_calls_passed": 7, "honeypot_evaluation_status": evaluated["status"], "model_calls": 0}, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
