"""LA-ICP-MS-first U-Pb in-situ specialist tool."""

from __future__ import annotations

from typing import Any

from ..contracts import ToolCapability


PROFILE_ID = "upb_in_situ"
MCP_SERVER = "geochron_upb"
TOOL_ID = "geochron_upb.extract_in_situ_delta"
DESCRIPTION = (
    "U-Pb 原位点分析增量工具，优先覆盖 LA-ICP-MS，并兼容相同 spot/domain 语义的 "
    "SIMS/SHRIMP；不处理 ID-TIMS aliquot/fraction 数据。"
)

CAPABILITY: ToolCapability = {
    "profile_id": PROFILE_ID,
    "allowed_state_key": "profiles.upb_in_situ.samples",
    "allowed_methods": ["U-Pb"],
    "allowed_techniques": ["LA-ICP-MS", "SIMS", "SHRIMP", "unknown"],
    "allowed_patch_branches": [
        "sample_fields_add",
        "analytical_context_add",
        "spots_add",
        "age_results_add",
        "events_add",
    ],
    "may_propose_shared_samples": True,
}

SYSTEM_ROLE = (
    "你是 LA-ICP-MS 优先的 U-Pb 原位分析专业工具。你能阅读整篇论文以保持方法、"
    "表格、图注、结果和讨论之间的证据链，但只处理 U-Pb 原位点分析。你不拥有全局"
    "数据库写权限，也不处理 Ar-Ar、Rb-Sr、Sm-Nd、(U-Th)/He 或 ID-TIMS 结果。"
)

DELTA_PROMPT = r"""
任务：基于论文全文和当前 upb_in_situ 局部状态，返回仅属于 U-Pb 原位点分析的树状状态增量。
本文 profile 优先处理 LA-ICP-MS；SIMS/SHRIMP 仅在其原位 spot/domain 结构明确时兼容。
不得将 ID-TIMS、CA-ID-TIMS、isotope-dilution、fraction、tracer 或 Pb blank 数据作为本
profile 的新增结果。

全文可见是为了核对跨段、表格、图注和讨论中的归属关系，不是为了抽取其他同位素体系。
不要复述 current_profile_state 中已有节点，不要输出完整 samples 或最终 JSON。输出单位是
sample_patch，而不是平铺节点：每个 patch 对应一个物理 sample，sample 的属性、spot、样品级
年龄结果与作者事件解释必须保持父子关系。

sample_patch 中只填写本轮新增内容：
- sample_fields_add：sample 的静态属性增量，例如 origin、rock_type、formation、group、member；
- analytical_context_add：该样品的 U-Pb 原位分析上下文，必须为 isotope_system=U-Pb，technique
  只能为 LA-ICP-MS、SIMS、SHRIMP 或 unknown；
- spots_add：该 sample 下新增的点、颗粒或分析域身份。spot 不是样品级年龄结果；
- age_results_add：该 sample 的加权平均、谐和、截距、峰值、最年轻年龄群或最大沉积年龄等结果。
  仅有单颗粒/spot 行级年龄时，不得自行创建此层；
- events_add：作者赋予 age_result 的喷发、结晶、继承、沉积、变质等意义。每个 event 必须通过
  result_ids 引用该 sample 下已有或本次新增的 age_result。

conflicts 用于报告新证据与当前本 profile 状态不兼容的情况，不自行覆盖旧节点。uncovered 用于
报告非本 profile 的年代学证据、方法归属不充分或无法安全写入的证据；它不是新增 event，可带
suggested_profile_id，但不得写入其他 profile。每个新增 child 均需 evidence_text 与 source_locator。
不得根据领域常识补全原文未声明的 technique、误差尺度或地质解释。

严格输出 JSON，不输出解释文字：
{
  "profile_id": "upb_in_situ",
  "sample_patches": [
    {
      "sample_id": "",
      "sample_fields_add": {},
      "sample_evidence": {"evidence_text": "", "source_locator": ""},
      "analytical_context_add": {"isotope_system": "U-Pb", "technique": "LA-ICP-MS", "mineral": null},
      "analytical_evidence": {"evidence_text": "", "source_locator": ""},
      "spots_add": [
        {"id": "", "material": null, "evidence": {"evidence_text": "", "source_locator": ""}}
      ],
      "age_results_add": [
        {
          "id": "", "result_type": null,
          "value": {"number": null, "unit": "Ma", "error": {"value": null, "scale": null}},
          "statistical_model": null, "distribution_state": null, "source_spot_ids": [],
          "evidence": {"evidence_text": "", "source_locator": ""}
        }
      ],
      "events_add": [
        {
          "id": "", "result_ids": [], "geologic_process": null, "isotopic_role": null,
          "preferred": null, "annotation": null,
          "evidence": {"evidence_text": "", "source_locator": ""}
        }
      ]
    }
  ],
  "conflicts": [],
  "uncovered": []
}
"""


DELTA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "profile_id": {"const": PROFILE_ID},
        "sample_patches": {"type": "array"},
        "conflicts": {"type": "array"},
        "uncovered": {"type": "array"},
    },
    "required": ["profile_id", "sample_patches", "conflicts", "uncovered"],
    "additionalProperties": False,
}


def _has_evidence(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("evidence_text"))


def validate_delta(delta: dict[str, Any]) -> dict[str, Any]:
    """Validate this profile's tree-shaped patch, not a flattened fact ledger."""
    errors: list[str] = []
    warnings: list[str] = []
    if delta.get("profile_id") != PROFILE_ID:
        errors.append(f"profile_id must be {PROFILE_ID!r}")
    patches = delta.get("sample_patches")
    conflicts = delta.get("conflicts")
    uncovered = delta.get("uncovered")
    if not isinstance(patches, list):
        errors.append("sample_patches must be an array")
        patches = []
    if not isinstance(conflicts, list):
        errors.append("conflicts must be an array")
    if not isinstance(uncovered, list):
        errors.append("uncovered must be an array")

    sample_ids: set[str] = set()
    spot_count = result_count = event_count = 0
    for patch_index, patch in enumerate(patches):
        path = f"sample_patches[{patch_index}]"
        if not isinstance(patch, dict):
            errors.append(f"{path} must be an object")
            continue
        sample_id = patch.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            errors.append(f"{path}.sample_id must be a non-empty string")
        elif sample_id in sample_ids:
            errors.append(f"duplicate sample patch: {sample_id}")
        else:
            sample_ids.add(sample_id)

        for branch in CAPABILITY["allowed_patch_branches"]:
            if branch not in patch:
                continue
            value = patch[branch]
            if branch.endswith("_add") and branch not in {
                "sample_fields_add",
                "analytical_context_add",
            } and not isinstance(value, list):
                errors.append(f"{path}.{branch} must be an array")
            if branch in {"sample_fields_add", "analytical_context_add"} and not isinstance(value, dict):
                errors.append(f"{path}.{branch} must be an object")

        context = patch.get("analytical_context_add") or {}
        if context:
            if context.get("isotope_system") != "U-Pb":
                errors.append(f"{path}.analytical_context_add.isotope_system must be U-Pb")
            if context.get("technique") not in CAPABILITY["allowed_techniques"]:
                errors.append(f"{path}.analytical_context_add.technique is outside capability")
            if not _has_evidence(patch.get("analytical_evidence")):
                errors.append(f"{path}.analytical_evidence.evidence_text is required")

        if patch.get("sample_fields_add") and not _has_evidence(patch.get("sample_evidence")):
            errors.append(f"{path}.sample_evidence.evidence_text is required")

        spot_ids: set[str] = set()
        for spot in patch.get("spots_add") or []:
            spot_count += 1
            spot_id = spot.get("id") if isinstance(spot, dict) else None
            if not isinstance(spot_id, str) or not spot_id.strip():
                errors.append(f"{path}.spots_add contains an empty id")
            elif spot_id in spot_ids:
                errors.append(f"{path}.spots_add has duplicate id {spot_id}")
            else:
                spot_ids.add(spot_id)
            if not isinstance(spot, dict) or not _has_evidence(spot.get("evidence")):
                errors.append(f"{path}.spots_add evidence_text is required")

        result_ids: set[str] = set()
        for result in patch.get("age_results_add") or []:
            result_count += 1
            result_id = result.get("id") if isinstance(result, dict) else None
            if not isinstance(result_id, str) or not result_id.strip():
                errors.append(f"{path}.age_results_add contains an empty id")
            elif result_id in result_ids:
                errors.append(f"{path}.age_results_add has duplicate id {result_id}")
            else:
                result_ids.add(result_id)
            if not isinstance(result, dict) or not _has_evidence(result.get("evidence")):
                errors.append(f"{path}.age_results_add evidence_text is required")

        for event in patch.get("events_add") or []:
            event_count += 1
            event_id = event.get("id") if isinstance(event, dict) else None
            if not isinstance(event_id, str) or not event_id.strip():
                errors.append(f"{path}.events_add contains an empty id")
            if not isinstance(event, dict) or not _has_evidence(event.get("evidence")):
                errors.append(f"{path}.events_add evidence_text is required")
            refs = event.get("result_ids") if isinstance(event, dict) else None
            if not isinstance(refs, list) or not refs:
                warnings.append(f"{path} event {event_id} has no result_ids; reducer will reject it")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "sample_patches": len(patches),
            "spots": spot_count,
            "sample_age_results": result_count,
            "measure_events": event_count,
            "conflicts": len(conflicts) if isinstance(conflicts, list) else 0,
            "uncovered": len(uncovered) if isinstance(uncovered, list) else 0,
        },
    }
