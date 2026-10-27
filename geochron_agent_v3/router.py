"""Low-cost evidence router for the registered isotope/profile cards.

This router is only a fallback and honeypot seed selector.  The top-level
tool-use planner remains free to dispatch zero, one, or many registered
profiles after reading the full document and state digest.
"""

from __future__ import annotations

import re

from .contracts import RouteDecision
from .profiles.standard import PROFILE_SPECS, ProfileSpec


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _hits(text: str, signals: tuple[str, ...]) -> list[str]:
    return [signal for signal in signals if signal.casefold() in text]


def _technique(spec: ProfileSpec, technique_hits: list[str]) -> str | None:
    if not technique_hits:
        return None
    text = re.sub(r"[^a-z0-9]+", "", " ".join(technique_hits).casefold())
    for technique in spec.techniques:
        compact = re.sub(r"[^a-z0-9]+", "", technique.casefold())
        if compact in text:
            return technique
    return spec.techniques[0] if len(spec.techniques) == 1 else "unknown"


def route_geochronology(text: str) -> list[RouteDecision]:
    """Return every registered profile supported by independent evidence.

    A paper may contain multiple isotope systems, and an Ar-Ar paper can
    legitimately contain both incremental-heating and total-fusion records.
    The result is therefore a set of evidence decisions, not a forced choice.
    """
    normalized = _normalized(text)
    decisions: list[RouteDecision] = []
    specs_with_system_evidence: list[tuple[ProfileSpec, list[str], list[str]]] = []
    for spec in PROFILE_SPECS:
        system_hits = _hits(normalized, spec.route_signals)
        if not system_hits:
            continue
        technique_hits = _hits(normalized, spec.technique_signals)
        specs_with_system_evidence.append((spec, system_hits, technique_hits))

    isotope_profile_counts: dict[str, int] = {}
    for spec, _, _ in specs_with_system_evidence:
        isotope_profile_counts[spec.isotope_system] = (
            isotope_profile_counts.get(spec.isotope_system, 0) + 1
        )

    for spec, system_hits, technique_hits in specs_with_system_evidence:
        technique = _technique(spec, technique_hits)
        exact_workflow = bool(technique_hits)
        unambiguous_method = isotope_profile_counts[spec.isotope_system] == 1
        if exact_workflow or unambiguous_method:
            decisions.append(
                {
                    "profile_id": spec.profile_id,
                    "status": "selected",
                    "mcp_server": spec.mcp_server,
                    "tool_id": spec.tool_id,
                    "confidence": 0.98 if exact_workflow else 0.72,
                    "isotope_system": spec.isotope_system,
                    "technique": technique or "unknown",
                    "matched_evidence": list(dict.fromkeys(system_hits + technique_hits)),
                    "blocking_evidence": [],
                    "reason": (
                        f"检测到 {spec.isotope_system} 的"
                        f"{'profile 工作流' if exact_workflow else '体系证据'}，路由到 {spec.profile_id}。"
                    ),
                }
            )
        else:
            decisions.append(
                {
                    "profile_id": spec.profile_id,
                    "status": "review",
                    "mcp_server": spec.mcp_server,
                    "tool_id": None,
                    "confidence": 0.45,
                    "isotope_system": spec.isotope_system,
                    "technique": None,
                    "matched_evidence": system_hits,
                    "blocking_evidence": [],
                    "reason": (
                        f"确认存在 {spec.isotope_system}，但尚未从低成本信号区分其 profile；"
                        "交由顶层 tool-use planner 结合全文选择。"
                    ),
                }
            )
    return decisions
