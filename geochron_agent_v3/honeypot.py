"""In-document control-suite validation for extraction compression and routing.

Controls are synthetic evidence records inserted into a real structural domain
of the model-visible document.  Their expected relations and insertion
coordinates stay outside the paper text; observed control output is stripped
before the ordinary state reducer receives a profile delta.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class ControlCase:
    control_id: str
    profiles: tuple[str, ...]
    text: str
    expected_relations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StructuralSpan:
    start: int
    end: int
    kind: str
    heading_path: tuple[str, ...]
    text: str


CONTROL_CASES: tuple[ControlCase, ...] = (
    ControlCase(
        control_id="hp_upb_relation_split",
        profiles=("upb_in_situ",),
        text=(
            "样品 HPUPB-01 的 SHRIMP 锆石 U-Pb 结果显示，其边部的加权平均年龄为"
            "452.3±3.1 Ma；同一颗粒的继承核年龄为120.0±1.0 Ma。"
        ),
        expected_relations=(
            {"sample_id": "HPUPB-01", "number": 452.3, "error": 3.1, "isotope_system": "U-Pb", "scope": "self"},
            {"sample_id": "HPUPB-01", "number": 120.0, "error": 1.0, "isotope_system": "U-Pb", "scope": "self"},
        ),
    ),
    ControlCase(
        control_id="hp_upb_entity_binding",
        profiles=("upb_in_situ",),
        text=(
            "样品 HPUPB-02 的 LA-ICP-MS 锆石 U-Pb 加权平均年龄为251.4±2.2 Ma；"
            "样品 HPUPB-03 在同一批分析中的加权平均年龄为310.7±3.4 Ma。"
        ),
        expected_relations=(
            {"sample_id": "HPUPB-02", "number": 251.4, "error": 2.2, "isotope_system": "U-Pb", "scope": "self"},
            {"sample_id": "HPUPB-03", "number": 310.7, "error": 3.4, "isotope_system": "U-Pb", "scope": "self"},
        ),
    ),
    ControlCase(
        control_id="hp_upb_parse_variant",
        profiles=("upb_in_situ",),
        text=(
            "样品 HPUPB-04 的锆石 U-Pb 年龄为（98.6 ± 0.7） Ma，"
            "该值为作者本次 SHRIMP 测定的结果。"
        ),
        expected_relations=(
            {"sample_id": "HPUPB-04", "number": 98.6, "error": 0.7, "isotope_system": "U-Pb", "scope": "self"},
        ),
    ),
)


_NORMALIZED_EQUIVALENTS = str.maketrans({"（": "(", "）": ")", "－": "-", "−": "-", "～": "~"})
_NORMALIZED_DROP = set(" \t\r\n，,。；;：:、")


def _normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    """Normalize harmless OCR/typographic variation while retaining source offsets."""
    values: list[str] = []
    offsets: list[int] = []
    for offset, char in enumerate(text.translate(_NORMALIZED_EQUIVALENTS).casefold()):
        if char in _NORMALIZED_DROP:
            continue
        values.append(char)
        offsets.append(offset)
    return "".join(values), offsets


def _locate_router_anchor(paper_text: str, evidence_text: str) -> tuple[int, int] | None:
    normalized_paper, offsets = _normalized_with_offsets(paper_text)
    normalized_evidence, _ = _normalized_with_offsets(evidence_text)
    start = normalized_paper.find(normalized_evidence)
    if start < 0 or not normalized_evidence:
        return None
    end_index = start + len(normalized_evidence) - 1
    return offsets[start], offsets[end_index] + 1


def pair_key(number: Any, error: Any) -> tuple[float, float] | None:
    try:
        return round(float(number), 9), round(float(error), 9)
    except (TypeError, ValueError):
        return None


def _first_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    matched = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(matched.group(0)) if matched else None


def _aggregate_pair(fields: dict[str, Any]) -> tuple[float, float] | None:
    age = _first_number(
        fields.get("Age_Text")
        or fields.get("CalibAge_Text")
        or fields.get("CalendarAge")
        or fields.get("Age")
    )
    uncertainty_keys = (
        "AgeUnc_Text", "AgeUnc1S_Text", "AgeUncInt", "AgeUncExt", "AgeUnc2sTracer",
        "CalibAgeUnc_Text", "CalendarAgeUnc", "AgeUnc",
    )
    error = None
    for key in uncertainty_keys:
        if fields.get(key) is None:
            continue
        candidate = _first_number(fields[key])
        if candidate is not None:
            error = candidate
            break
    return pair_key(age, error)


def select_controls(profile_ids: Iterable[str], max_controls: int = 3) -> list[ControlCase]:
    selected = set(profile_ids)
    return [
        control for control in CONTROL_CASES
        if set(control.profiles).issubset(selected)
    ][:max_controls]


def build_control_run(document_id: str, profile_ids: Iterable[str], max_controls: int = 3) -> dict[str, Any]:
    controls = select_controls(profile_ids, max_controls=max_controls)
    return {
        "run_id": f"{document_id}:honeypot:1",
        "controls": [
            {
                "control_id": control.control_id,
                "profiles": list(control.profiles),
                "text": control.text,
                "expected_relations": [dict(item) for item in control.expected_relations],
            }
            for control in controls
        ],
        "observed_deltas": [],
        "injections": [],
        "skipped_controls": [],
        "report": None,
    }


_MARKDOWN_TITLE_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_NUMBERED_TITLE_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+){0,5}|[一二三四五六七八九十]+[、.])\s*\S"
)
_RESULT_TITLE_RE = re.compile(r"结果|测年|年代|定年|U\s*-?\s*Pb|锆石|分析结果|data|result|age", re.I)
_RESULT_TEXT_RE = re.compile(r"U\s*-?\s*Pb|锆石|年龄|测年|定年|加权平均|谐和|分析结果|Ma\b", re.I)
_EXCLUDED_TITLE_RE = re.compile(r"摘要|参考文献|references?|致谢|abstract", re.I)


def _text_value(block: dict[str, Any]) -> str:
    for key in ("text", "text_content", "content", "markdown", "text_str"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _kind_value(block: dict[str, Any]) -> str:
    value = block.get("type") or block.get("block_type") or block.get("kind") or "text"
    return str(value).casefold()


def _is_title(block: dict[str, Any], text: str) -> bool:
    kind = _kind_value(block)
    return kind in {"title", "heading", "header"} or bool(
        _MARKDOWN_TITLE_RE.match(text) or _NUMBERED_TITLE_RE.match(text)
    )


def _span_from_block(block: dict[str, Any], text: str, cursor: int, paper_text: str) -> tuple[int, int] | None:
    start = block.get("char_start", block.get("start"))
    end = block.get("char_end", block.get("end"))
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(paper_text):
        return start, end
    found = paper_text.find(text, cursor)
    if found < 0:
        return None
    return found, found + len(text)


def recover_structural_spans(
    paper_text: str, document_structure: Sequence[dict[str, Any]] | None = None
) -> list[StructuralSpan]:
    """Use normalized MinerU blocks when available, otherwise recover text domains.

    MinerU's title/text sequence is enough for placement; no LLM decides the
    insertion point.  The fallback keeps the same hard heading boundaries for
    plain Markdown or OCR text passed directly to the agent.
    """
    spans: list[StructuralSpan] = []
    heading_path: list[str] = []
    cursor = 0
    if document_structure:
        for block in document_structure:
            if not isinstance(block, dict):
                continue
            text = _text_value(block)
            if not text:
                continue
            located = _span_from_block(block, text, cursor, paper_text)
            if located is None:
                continue
            start, end = located
            cursor = max(cursor, end)
            if _is_title(block, text):
                level = block.get("text_level", block.get("level"))
                if isinstance(level, int) and level > 0:
                    heading_path = heading_path[: level - 1]
                else:
                    heading_path = []
                heading_path.append(text.strip())
                spans.append(StructuralSpan(start, end, "title", tuple(heading_path), text))
            else:
                spans.append(StructuralSpan(start, end, _kind_value(block), tuple(heading_path), text))
        if spans:
            return spans

    offset = 0
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_start, paragraph_end, paragraph_lines
        if paragraph_start is not None and paragraph_end is not None and paragraph_lines:
            spans.append(
                StructuralSpan(
                    paragraph_start,
                    paragraph_end,
                    "text",
                    tuple(heading_path),
                    " ".join(paragraph_lines),
                )
            )
        paragraph_start = paragraph_end = None
        paragraph_lines = []

    for chunk in paper_text.splitlines(keepends=True):
        start = offset
        end = start + len(chunk)
        text = chunk.strip()
        offset = end
        if not text:
            flush_paragraph()
            continue
        if _MARKDOWN_TITLE_RE.match(text) or _NUMBERED_TITLE_RE.match(text):
            flush_paragraph()
            heading_path = [text]
            spans.append(StructuralSpan(start, end, "title", tuple(heading_path), text))
        else:
            if paragraph_start is None:
                paragraph_start = start
            paragraph_end = end
            paragraph_lines.append(text)
    flush_paragraph()
    if spans:
        return spans
    return [StructuralSpan(0, len(paper_text), "text", (), paper_text)] if paper_text.strip() else []


def _profile_terms(control: dict[str, Any]) -> tuple[str, ...]:
    expected = control.get("expected_relations") or []
    systems = {str(item.get("isotope_system", "")) for item in expected if isinstance(item, dict)}
    if "U-Pb" in systems:
        return ("U-Pb", "锆石", "测年", "定年", "年龄", "Ma")
    return tuple(term for term in systems if term)


def _score_anchor(span: StructuralSpan, profile_terms: tuple[str, ...]) -> int:
    if span.kind in {"title", "table", "image", "figure"}:
        return -100
    path = " ".join(span.heading_path)
    if _EXCLUDED_TITLE_RE.search(path):
        return -100
    text = span.text
    score = 0
    if _RESULT_TITLE_RE.search(path):
        score += 8
    if _RESULT_TEXT_RE.search(text):
        score += 6
    score += sum(2 for term in profile_terms if term.casefold() in text.casefold())
    if "Ma" in text:
        score += 2
    return score


def plan_structural_injections(
    paper_text: str,
    run: dict[str, Any],
    document_structure: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Place controls inside result paragraphs, retaining source coordinates externally."""
    spans = recover_structural_spans(paper_text, document_structure)
    used_anchors: set[tuple[int, int]] = set()
    injections: list[dict[str, Any]] = []
    active_controls: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for control in run.get("controls", []):
        terms = _profile_terms(control)
        candidates = sorted(
            (
                (_score_anchor(span, terms), span)
                for span in spans
                if _score_anchor(span, terms) > 0
            ),
            key=lambda item: (item[0], -item[1].start),
            reverse=True,
        )
        selected = next((span for _, span in candidates if (span.start, span.end) not in used_anchors), None)
        if selected is None and candidates:
            selected = candidates[0][1]
        if selected is None:
            skipped.append({"control_id": control["control_id"], "reason": "no_structural_result_anchor"})
            continue
        used_anchors.add((selected.start, selected.end))
        insertion_text = "\n" + str(control["text"]).strip() + "\n"
        injections.append(
            {
                "control_id": control["control_id"],
                "offset": selected.end,
                "text": insertion_text,
                "anchor": {
                    "start": selected.start,
                    "end": selected.end,
                    "kind": selected.kind,
                    "heading_path": list(selected.heading_path),
                    "anchor_text": selected.text,
                },
            }
        )
        active_controls.append(control)
    planned = deepcopy(run)
    planned["controls"] = active_controls
    planned["injections"] = injections
    planned["skipped_controls"] = skipped
    return planned


def plan_router_injections(
    paper_text: str,
    run: dict[str, Any],
    route_anchors: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    """Use a verbatim, router-selected result sentence; never fall back to front matter."""
    planned = deepcopy(run)
    active_controls: list[dict[str, Any]] = []
    injections: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = list(planned.get("skipped_controls") or [])
    used_profiles: set[str] = set()
    for control in planned.get("controls", []):
        profile_id = next((item for item in control.get("profiles", []) if item not in used_profiles), None)
        anchor = next(iter(route_anchors.get(profile_id or "", [])), None)
        evidence_text = str((anchor or {}).get("evidence_text", "")).strip()
        sample_id = str((anchor or {}).get("sample_id", "")).strip()
        age_text = str((anchor or {}).get("age_text", "")).strip()
        located = _locate_router_anchor(paper_text, evidence_text) if evidence_text else None
        if not evidence_text or not sample_id or not age_text or located is None:
            skipped.append({"control_id": control["control_id"], "reason": "router_anchor_unavailable"})
            continue
        normalized_anchor, _ = _normalized_with_offsets(evidence_text)
        normalized_sample, _ = _normalized_with_offsets(sample_id)
        normalized_age, _ = _normalized_with_offsets(age_text)
        if normalized_sample not in normalized_anchor or normalized_age not in normalized_anchor:
            skipped.append({"control_id": control["control_id"], "reason": "router_anchor_not_self_describing"})
            continue
        start, end = located
        injections.append(
            {
                "control_id": control["control_id"],
                "offset": end,
                "text": "\n" + str(control["text"]).strip() + "\n",
                "anchor": {
                    "start": start,
                    "end": end,
                    "kind": "router_evidence",
                    "heading_path": [],
                    "anchor_text": evidence_text,
                    "sample_id": sample_id,
                    "age_text": age_text,
                },
            }
        )
        used_profiles.add(profile_id)
        active_controls.append(control)
    planned["controls"] = active_controls
    planned["injections"] = injections
    planned["skipped_controls"] = skipped
    return planned


def inject_controls_into_structure(paper_text: str, run: dict[str, Any]) -> str:
    """Apply externally recorded insertions without modifying the source document."""
    injections = run.get("injections") or []
    if not injections:
        return paper_text
    augmented = paper_text
    # Later same-offset controls go in first, preserving control order in the
    # final prose while offsets remain coordinates in the untouched document.
    ordered = sorted(
        enumerate(injections),
        key=lambda pair: (int(pair[1]["offset"]), pair[0]),
        reverse=True,
    )
    for _, injection in ordered:
        offset = int(injection["offset"])
        augmented = augmented[:offset] + str(injection["text"]) + augmented[offset:]
    return augmented


def expected_relations(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        relation
        for control in run.get("controls", [])
        for relation in control.get("expected_relations", [])
    ]


def control_sample_ids(run: dict[str, Any]) -> set[str]:
    return {str(relation["sample_id"]) for relation in expected_relations(run)}


def control_pairs(run: dict[str, Any]) -> set[tuple[float, float]]:
    return {
        pair
        for relation in expected_relations(run)
        if (pair := pair_key(relation.get("number"), relation.get("error"))) is not None
    }


def extract_delta_relations(profile_id: str, delta: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten only aggregate observations for control comparison.

    The profile's isotope system is the reliable default when a patch does not
    repeat analytical context.  A future candidate router can also feed this
    evaluator explicit scope and system observations.
    """
    relations: list[dict[str, Any]] = []
    for patch in delta.get("sample_patches", []) if isinstance(delta, dict) else []:
        if not isinstance(patch, dict):
            continue
        sample_id = patch.get("sample_id")
        context = patch.get("method_context_add") or {}
        isotope_system = context.get("isotope_system") or (
            "U-Pb" if profile_id == "upb_in_situ" else None
        )
        for aggregate in patch.get("aggregate_observations_add") or []:
            if not isinstance(aggregate, dict):
                continue
            pair = _aggregate_pair(aggregate.get("fields") or {})
            if not isinstance(sample_id, str) or pair is None:
                continue
            relations.append(
                {
                    "sample_id": sample_id,
                    "number": pair[0],
                    "error": pair[1],
                    "isotope_system": isotope_system,
                    "scope": context.get("scope", "self"),
                    "profile_id": profile_id,
                    "result_id": aggregate.get("id"),
                }
            )
    return relations


def evaluate_control_run(
    run: dict[str, Any],
    observed_relations: list[dict[str, Any]],
    executed_profile_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return pass/fail with diagnostic reasons, never a semantic write."""
    reports: list[dict[str, Any]] = []
    executed = set(executed_profile_ids) if executed_profile_ids is not None else None
    for control in run.get("controls", []):
        expected = control.get("expected_relations", [])
        expected_pairs = {
            pair_key(item.get("number"), item.get("error"))
            for item in expected
        }
        expected_pairs.discard(None)
        observed = [
            item for item in observed_relations
            if pair_key(item.get("number"), item.get("error")) in expected_pairs
        ]
        reasons: set[str] = set()
        matched = 0
        route_missing = (
            executed is not None
            and bool(control.get("profiles"))
            and not set(control["profiles"]).intersection(executed)
        )
        if route_missing:
            reasons.add("misrouted")
            reports.append(
                {
                    "control_id": control["control_id"],
                    "status": "fail",
                    "fail_reasons": ["misrouted"],
                    "expected_relation_count": len(expected),
                    "observed_relation_count": len(observed),
                }
            )
            continue
        for relation in expected:
            target_pair = pair_key(relation.get("number"), relation.get("error"))
            matches = [item for item in observed if pair_key(item.get("number"), item.get("error")) == target_pair]
            if not matches:
                reasons.add("parse_noise" if "parse_variant" in control["control_id"] else "missing")
                continue
            exact = [
                item for item in matches
                if item.get("sample_id") == relation.get("sample_id")
                and item.get("isotope_system") == relation.get("isotope_system")
                and item.get("scope") == relation.get("scope")
            ]
            if exact:
                matched += 1
                continue
            if any(item.get("sample_id") != relation.get("sample_id") for item in matches):
                reasons.add("misbound")
            if any(item.get("isotope_system") != relation.get("isotope_system") for item in matches):
                reasons.add("misrouted")
            if any(item.get("scope") != relation.get("scope") for item in matches):
                reasons.add("source_confusion")
        if len(expected) > 1 and 0 < matched < len(expected):
            reasons.discard("missing")
            reasons.add("merged")
        reports.append(
            {
                "control_id": control["control_id"],
                "status": "pass" if not reasons else "fail",
                "fail_reasons": sorted(reasons),
                "expected_relation_count": len(expected),
                "observed_relation_count": len(observed),
            }
        )
    failed = [report for report in reports if report["status"] == "fail"]
    return {
        "run_id": run.get("run_id"),
        "status": "pass" if not failed else "fail",
        "controls": reports,
        "skipped_controls": run.get("skipped_controls", []),
        "fail_reasons": sorted({reason for report in failed for reason in report["fail_reasons"]}),
    }


def recovery_tasks(report: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        "merged": "run_local_coverage_completion",
        "missing": "run_local_coverage_completion",
        "misbound": "review_entity_binding",
        "misrouted": "review_isotope_route",
        "source_confusion": "review_self_or_cited",
        "parse_noise": "repair_numeric_evidence",
    }
    return [
        {"type": mapping[reason], "trigger": "honeypot", "reason": reason}
        for reason in report.get("fail_reasons", [])
        if reason in mapping
    ]


def strip_control_relations(run: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Keep control output observable while removing it from real state writes."""
    cleaned = deepcopy(delta)
    samples = control_sample_ids(run)
    pairs = control_pairs(run)
    cleaned_patches = []
    for patch in cleaned.get("sample_patches", []) if isinstance(cleaned, dict) else []:
        if not isinstance(patch, dict) or patch.get("sample_id") in samples:
            continue
        aggregate_ids_to_drop = {
            aggregate.get("id")
            for aggregate in patch.get("aggregate_observations_add") or []
            if isinstance(aggregate, dict)
            and (_aggregate_pair(aggregate.get("fields") or {}) in pairs)
        }
        patch["aggregate_observations_add"] = [
            aggregate for aggregate in patch.get("aggregate_observations_add") or []
            if aggregate.get("id") not in aggregate_ids_to_drop
        ]
        patch["author_inferences_add"] = [
            inference for inference in patch.get("author_inferences_add") or []
            if not set(inference.get("aggregate_observation_ids") or []) & aggregate_ids_to_drop
        ]
        cleaned_patches.append(patch)
    cleaned["sample_patches"] = cleaned_patches
    return cleaned
