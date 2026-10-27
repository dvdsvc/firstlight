"""骨架过滤 + 校验：R1 → R2 之间的数据清洗"""
from __future__ import annotations
import copy


def fix_spot_ids(skeleton: dict) -> dict:
    """
    兜底校验：如果 spot id 不含 sample id 前缀，尝试用 sample id 拼接修复。
    例: sample_id="MZ815", spot_id="1" → 修复为 "MZ815-1"
    """
    for sample in skeleton.get("samples", []):
        sid = sample.get("id", "")
        for spot in sample.get("spots", []):
            spot_id = spot.get("id", "")
            if not spot_id or not sid:
                continue
            if spot_id.startswith(sid):
                continue  # 已经正确
            # 尝试修复：可能是截断的后缀
            if spot_id.lstrip("-").lstrip("0123456789") == "":
                # 纯数字或带前导横杠的数字 → 拼上 sample id
                suffix = spot_id.lstrip("-")
                spot["id"] = f"{sid}-{suffix}" if suffix else sid
    return skeleton


def filter_skeleton_for_r2(skeleton: dict) -> dict:
    """
    1. 过滤掉 origin != "self" 的 sample
    2. 从 measure_events 中移除 method / technique（R2c 用受控词表重新分类）
    3. 修复 spot id（兜底）
    """
    data = copy.deepcopy(skeleton)
    data["samples"] = [
        s for s in data.get("samples", []) if s.get("origin") == "self"
    ]
    for sample in data["samples"]:
        for event in sample.get("measure_events", []):
            event.pop("method", None)
            event.pop("technique", None)
    data = fix_spot_ids(data)
    return data
