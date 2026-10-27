"""Evidence-based dispatch into method/profile tools."""

from __future__ import annotations

import re

from .contracts import RouteDecision
from .profiles import upb_in_situ


_UPB_SIGNALS = (
    "u-pb",
    "u–pb",
    "u—pb",
    "铀铅",
    "206pb/238u",
    "207pb/235u",
    "207pb/206pb",
)
_IN_SITU_SIGNALS = (
    "la-icp-ms",
    "la-icpms",
    "la icp ms",
    "laser ablation",
    "激光剥蚀",
    "激光烧蚀",
    "sims",
    "shrimp",
    "ion microprobe",
    "离子探针",
    "spot analysis",
    "spot analyses",
    "分析点",
    "测点",
)
_LA_ICP_MS_SIGNALS = (
    "la-icp-ms",
    "la-icpms",
    "la icp ms",
    "laser ablation",
    "激光剥蚀",
    "激光烧蚀",
)
_SIMS_SIGNALS = ("sims", "ion microprobe", "离子探针")
_SHRIMP_SIGNALS = ("shrimp",)
_SPOT_CONTEXT_SIGNALS = ("zircon", "锆石", "spot", "grain", "颗粒", "domain", "分析域")
_ID_TIMS_SIGNALS = (
    "id-tims",
    "ca-id-tims",
    "isotope dilution",
    "thermal ionization",
    "chemical abrasion",
    "tracer",
    "spike",
    "pb blank",
    "同位素稀释",
    "热电离",
    "化学磨蚀",
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _hits(text: str, signals: tuple[str, ...]) -> list[str]:
    return [signal for signal in signals if signal.casefold() in text]


def _technique(text: str) -> str:
    """Choose the dominant in-situ technique instead of trusting any mention.

    Papers often cite SHRIMP/SIMS studies in the introduction or discussion. A
    whole-document boolean match therefore misroutes LA-ICP-MS papers. Counting
    explicit technique phrases is still a coarse first pass; later the capsule
    router can give method sections and table headers higher weights.
    """
    scores = {
        "LA-ICP-MS": sum(text.count(signal) for signal in _LA_ICP_MS_SIGNALS),
        "SIMS": sum(text.count(signal) for signal in _SIMS_SIGNALS),
        "SHRIMP": sum(text.count(signal) for signal in _SHRIMP_SIGNALS),
    }
    best_score = max(scores.values())
    if best_score == 0:
        return "unknown"
    winners = [technique for technique, score in scores.items() if score == best_score]
    return winners[0] if len(winners) == 1 else "unknown"


def route_geochronology(text: str) -> list[RouteDecision]:
    """Return all supported and explicitly unsupported profile decisions.

    Decisions are evidence records. The router, not the extraction model, assigns
    MCP server and tool identifiers from the profile registry.
    """
    normalized = _normalized(text)
    system_hits = _hits(normalized, _UPB_SIGNALS)
    if not system_hits:
        return []

    in_situ_hits = _hits(normalized, _IN_SITU_SIGNALS)
    context_hits = _hits(normalized, _SPOT_CONTEXT_SIGNALS)
    id_tims_hits = _hits(normalized, _ID_TIMS_SIGNALS)
    technique = _technique(normalized)
    decisions: list[RouteDecision] = []

    # Generic words such as zircon, grain and analysis point also occur in
    # ID-TIMS papers. They may infer an in-situ profile only when no explicit
    # ID-TIMS workflow is present; named in-situ techniques remain decisive.
    inferred_spot_profile = len(context_hits) >= 2 and not id_tims_hits
    if technique != "unknown" or inferred_spot_profile:
        evidence = list(dict.fromkeys(system_hits + in_situ_hits + context_hits))
        confidence = 0.98 if in_situ_hits else 0.76
        decisions.append(
            {
                "profile_id": upb_in_situ.PROFILE_ID,
                "status": "selected",
                "mcp_server": upb_in_situ.MCP_SERVER,
                "tool_id": upb_in_situ.TOOL_ID,
                "confidence": confidence,
                "isotope_system": "U-Pb",
                "technique": technique,
                "matched_evidence": evidence,
                "blocking_evidence": id_tims_hits,
                "reason": (
                    "检测到 U-Pb 与原位点分析结构；按 registry 路由到 upb_in_situ。"
                ),
            }
        )
    else:
        decisions.append(
            {
                "profile_id": upb_in_situ.PROFILE_ID,
                "status": "review",
                "mcp_server": upb_in_situ.MCP_SERVER,
                "tool_id": None,
                "confidence": 0.45,
                "isotope_system": "U-Pb",
                "technique": None,
                "matched_evidence": system_hits,
                "blocking_evidence": id_tims_hits,
                "reason": "确认存在 U-Pb，但缺少足够的原位点分析证据。",
            }
        )

    if id_tims_hits:
        decisions.append(
            {
                "profile_id": "upb_id_tims",
                "status": "unsupported",
                "mcp_server": None,
                "tool_id": None,
                "confidence": 0.95,
                "isotope_system": "U-Pb",
                "technique": "ID-TIMS",
                "matched_evidence": system_hits + id_tims_hits,
                "blocking_evidence": id_tims_hits,
                "reason": "检测到 ID-TIMS 数据结构；当前版本明确不将其塞入原位点 profile。",
            }
        )

    return decisions
