"""完整 pipeline — R1 → filter → R2a/b/c 全并发 + 输出校验
用法: python pipeline.py <docx_path>
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openpyxl import Workbook

import urllib.request
import urllib.parse

from prompts import make_system, R1_USER, R2A_USER, R2B_USER, build_r2c_user
from filter import filter_skeleton_for_r2
from run_layer1 import build_r1_schema, load_docx
from run_layer2a import build_r2a_schema
from run_layer2b import build_r2b_schema
from run_layer2c import build_r2c_schema

load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.environ["DEEPSEEK_API_KEY"]
BASE_URL = os.environ["DEEPSEEK_BASE_URL"]
MODEL = os.environ["DEEPSEEK_MODEL"]
OPENALEX_EMAIL = os.environ.get("OPENALEX_EMAIL", "structured-extract@example.com")

# R1 事件的基础字段（R2c 不应删除）
_EVENT_BASE_KEYS = {"value", "method", "annotation"}
# R2c 新增的受控词表字段（事件顶层）
_EVENT_VOCAB_KEYS = {"technique", "mineral", "isotope_system", "physical_method"}
# R2c 新增的受控词表字段（嵌套在 value 内）
_VALUE_VOCAB_KEYS = {"statistical_model", "distribution_state"}
# R2a 只修改这些槽位
_R2A_KEYS = {"rock_type", "formation", "group", "member",
             "province", "city", "basin", "locality"}
# spot 允许的字段
_SPOT_KEYS = {"id", "u_ppm", "th_ppm", "th_u_ratio", "concordance",
              "r207_206", "r207_235", "r206_238", "age_206_238", "age_207_235"}

def _log_cache(usage, label: str):
    hit = getattr(usage, 'prompt_cache_hit_tokens', 0) or 0
    miss = getattr(usage, 'prompt_cache_miss_tokens', 0) or 0
    total = hit + miss
    pct = f"{hit/total*100:.0f}%" if total else "N/A"
    print(f"  [{label}] cache: hit={hit} miss={miss} ({pct})")


def _clean_r2a_output(r1_sample: dict, r2a_sample: dict) -> dict:
    """R2a: 只更新 rock_type/formation/group/member/location，其余原样保留。"""
    out = dict(r1_sample)
    for k in _R2A_KEYS:
        out[k] = r2a_sample.get(k, "")
    # location 是 dict，单独处理
    if "location" in r2a_sample:
        out["location"] = r2a_sample["location"]
    return out


def _clean_spot(spot: dict) -> dict:
    """清洗 spot：只保留允许的字段。"""
    return {k: spot.get(k) for k in _SPOT_KEYS if k in spot}


def enrich_reference(ref: dict) -> dict:
    """用 OpenAlex 按标题搜索，补全 reference 缺失字段。"""
    title = (ref.get("title") or "").strip()
    if not title or len(title) < 10:
        return ref

    filled = {k: v for k, v in ref.items() if v}
    if all(filled.get(k) for k in ("doi", "journal", "year", "volume", "pages")):
        return ref

    q = urllib.parse.quote(title[:150])
    url = f"https://api.openalex.org/works?search={q}&per_page=1&mailto={OPENALEX_EMAIL}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"structured-extract/1.0 (mailto:{OPENALEX_EMAIL})"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            print("  OpenAlex: 无匹配")
            return ref
        w = results[0]
        loc = w.get("primary_location", {}) or {}
        source = loc.get("source") or {}

        if not filled.get("doi"):
            raw_doi = w.get("doi") or ""
            filled["doi"] = raw_doi.replace("https://doi.org/", "")
        if not filled.get("journal"):
            filled["journal"] = source.get("display_name", "")
        if not filled.get("year"):
            y = w.get("publication_year")
            filled["year"] = str(y) if y else ""
        if not filled.get("volume"):
            bib = w.get("biblio") or {}
            filled["volume"] = bib.get("volume") or ""
        if not filled.get("pages"):
            bib = w.get("biblio") or {}
            first = bib.get("first_page") or ""
            last = bib.get("last_page") or ""
            filled["pages"] = f"{first}-{last}" if first and last else (first or "")

        added = [k for k in ("doi", "journal", "year", "volume", "pages") if filled.get(k) and not ref.get(k)]
        if added:
            print(f"  OpenAlex 补充: {', '.join(added)}")
        return filled
    except Exception as e:
        print(f"  OpenAlex 查询失败: {str(e)[:80]}")
        return ref



def _clean_r2b_output(r1_sample: dict, r2b_sample: dict) -> list:
    """R2b: 只更新 spots 内的数值字段，id 不变。"""
    r1_spots = {s["id"]: s for s in r1_sample.get("spots", [])}
    cleaned = []
    for spot in r2b_sample.get("spots", []):
        sid = spot.get("id", "")
        base = dict(r1_spots.get(sid, {"id": sid}))
        # 只更新数值字段
        for k in _SPOT_KEYS:
            if k != "id" and k in spot:
                base[k] = spot[k]
        cleaned.append(_clean_spot(base))
    return cleaned


def _clean_r2c_output(r1_sample: dict, r2c_sample: dict) -> list:
    """R2c: R1 事件 + 受控词表字段，strip 多余字段。
    value.error.scale 从 R2c 映射，value.number/error.value 保留 R1 原值。
    value.statistical_model / distribution_state 从 R2c 映射。"""
    r1_events = r1_sample.get("measure_events", [])
    r2c_events = r2c_sample.get("measure_events", [])
    cleaned = []
    for i, r1e in enumerate(r1_events):
        out = {k: r1e[k] for k in _EVENT_BASE_KEYS if k in r1e}
        r2ce = r2c_events[i] if i < len(r2c_events) else {}
        # value: 保留 R1 的 number + error.value，用 R2c 映射 error.scale + 统计字段
        r1_val = r1e.get("value") or {}
        r1_err = r1_val.get("error") or {}
        r2c_val = r2ce.get("value") or {}
        r2c_err = r2c_val.get("error") or {}
        out["value"] = {
            "number": r1_val.get("number"),
            "error": {
                "value": r1_err.get("value"),
                "scale": r2c_err.get("scale", r1_err.get("scale", "未声明")),
            },
            "statistical_model": r2c_val.get("statistical_model", "null"),
            "distribution_state": r2c_val.get("distribution_state", "null"),
        }
        # 事件顶层受控词表字段
        for k in _EVENT_VOCAB_KEYS:
            out[k] = r2ce.get(k, "null")
        cleaned.append(out)
    return cleaned


# ═══════════════════════════════════════════════════
# Round 1
# ═══════════════════════════════════════════════════

async def run_r1(client: AsyncOpenAI, paper_text: str, temperature: float = 0) -> dict:
    t0 = time.time()
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": make_system(paper_text)},
            {"role": "user", "content": R1_USER},
        ],
        temperature=temperature,
        reasoning_effort="max",
        extra_body={"thinking": {"type": "enabled"}},
        response_format={"type": "json_object"},
    )
    elapsed = time.time() - t0
    usage = resp.usage
    print(f"[R1 t={temperature}] {elapsed:.1f}s | in={usage.prompt_tokens} out={usage.completion_tokens}")
    _log_cache(usage, f"R1 t={temperature}")
    return json.loads(resp.choices[0].message.content)


# ═══════════════════════════════════════════════════
# R1 多 temperature 采样 + event 合并
# ═══════════════════════════════════════════════════

R1_TEMPERATURES = [0, 0.3, 0.7]


def _event_dedup_key(event: dict) -> tuple:
    val = event.get("value") or {}
    err = val.get("error") or {}
    return (val.get("number"), err.get("value"))


def merge_r1_events(base: dict, others: list[dict]) -> dict:
    """合并多次 R1 的 measure_events，只合并同 id sample 的事件。"""
    # 建立 {sample_id: {dedup_key: event}} 映射
    merged = {}
    for s in base.get("samples", []):
        seen = {}
        for e in s.get("measure_events", []):
            seen[_event_dedup_key(e)] = e
        merged[s["id"]] = seen

    for skel in others:
        for s in skel.get("samples", []):
            sid = s["id"]
            if sid not in merged:
                merged[sid] = {}
            for e in s.get("measure_events", []):
                key = _event_dedup_key(e)
                if key not in merged[sid]:
                    merged[sid][key] = e

    # 回写到 base skeleton
    for s in base.get("samples", []):
        s["measure_events"] = list(merged[s["id"]].values())
    return base


async def run_r1_multi(client: AsyncOpenAI, paper_text: str) -> dict:
    """多 temperature 并行采样，合并 measure_events。"""
    print(f"[R1 multi] temperatures={R1_TEMPERATURES}")
    results = await asyncio.gather(*[
        run_r1(client, paper_text, temperature=t)
        for t in R1_TEMPERATURES
    ])
    base = results[0]
    n_before = sum(len(s.get("measure_events", [])) for s in base.get("samples", []))
    merged = merge_r1_events(base, results[1:])
    n_after = sum(len(s.get("measure_events", [])) for s in merged.get("samples", []))
    print(f"[R1 multi] events: {n_before} → {n_after} (+{n_after - n_before})")
    return merged


# ═══════════════════════════════════════════════════
# Round 2a
# ═══════════════════════════════════════════════════

async def run_r2a_one(client: AsyncOpenAI, paper_text: str, sample: dict) -> dict:
    skel = {"samples": [sample]}
    skel_json = json.dumps(skel, ensure_ascii=False)
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": make_system(paper_text)},
                {"role": "user", "content": f"=== Entity Tree JSON ===\n{skel_json}\n\n{R2A_USER}"},
            ],
            temperature=0,
            reasoning_effort="max",
            extra_body={"thinking": {"type": "enabled"}},
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"  [ERROR] R2a:{sample['id']} {str(e)[:100]}")
        return sample
    usage = resp.usage
    _log_cache(usage, f"R2a:{sample['id']}")
    result = json.loads(resp.choices[0].message.content)
    if "samples" not in result:
        print(f"  [WARN] R2a:{sample['id']} 返回无 samples: {str(result)[:200]}")
        return sample
    return _clean_r2a_output(sample, result["samples"][0])


# ═══════════════════════════════════════════════════
# Round 2b
# ═══════════════════════════════════════════════════

BATCH_SIZE = 5


async def run_r2a_batch(client: AsyncOpenAI, paper_text: str, samples: list) -> dict:
    """R2a 批量：一次请求处理最多 BATCH_SIZE 个 sample，返回 {id: cleaned_result}。"""
    skel = {"samples": samples}
    skel_json = json.dumps(skel, ensure_ascii=False)
    ids = [s["id"] for s in samples]
    label = f"R2a:{ids[0]}..{ids[-1]}({len(samples)})"
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": make_system(paper_text)},
                {"role": "user", "content": f"=== Entity Tree JSON ===\n{skel_json}\n\n{R2A_USER}"},
            ],
            temperature=0,
            reasoning_effort="max",
            extra_body={"thinking": {"type": "enabled"}},
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"  [ERROR] {label} {str(e)[:100]}")
        return {s["id"]: s for s in samples}
    usage = resp.usage
    _log_cache(usage, label)
    result = json.loads(resp.choices[0].message.content)
    if "samples" not in result:
        print(f"  [WARN] {label} 返回无 samples")
        return {s["id"]: s for s in samples}
    r2a_map = {r["id"]: r for r in result["samples"]}
    out = {}
    for s in samples:
        if s["id"] in r2a_map:
            out[s["id"]] = _clean_r2a_output(s, r2a_map[s["id"]])
        else:
            print(f"  [WARN] R2a 批量结果缺少 {s['id']}，保留原值")
            out[s["id"]] = s
    return out


# ═══════════════════════════════════════════════════
# Round 2b
# ═══════════════════════════════════════════════════

async def run_r2b(client: AsyncOpenAI, paper_text: str, skeleton: dict) -> dict:
    skel_json = json.dumps(skeleton, ensure_ascii=False)
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": make_system(paper_text)},
                {"role": "user", "content": f"=== Entity Tree JSON ===\n{skel_json}\n\n{R2B_USER}"},
            ],
            temperature=0,
            reasoning_effort="max",
            extra_body={"thinking": {"type": "enabled"}},
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"  [ERROR] R2b {str(e)[:100]}")
        return {}
    usage = resp.usage
    _log_cache(usage, "R2b")
    try:
        result = json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        print(f"  [WARN] R2b JSON 解析失败")
        return {}
    if "samples" not in result:
        print(f"  [WARN] R2b 返回无 samples: {str(result)[:200]}")
        return {}
    return {s["id"]: s for s in result["samples"]}


# ═══════════════════════════════════════════════════
# Round 2c
# ═══════════════════════════════════════════════════

async def run_r2c_one(client: AsyncOpenAI, paper_text: str, sample: dict) -> list:
    skel = {"samples": [sample]}
    skel_json = json.dumps(skel, ensure_ascii=False)
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": make_system(paper_text)},
            {"role": "user", "content": build_r2c_user(skel_json)},
        ],
        temperature=0,
        reasoning_effort="max",
        extra_body={"thinking": {"type": "enabled"}},
        response_format={"type": "json_object"},
    )
    usage = resp.usage
    _log_cache(usage, f"R2c:{sample['id']}")
    result = json.loads(resp.choices[0].message.content)
    if "samples" not in result:
        print(f"  [WARN] R2c:{sample['id']} 返回无 samples: {str(result)[:200]}")
        return _clean_r2c_output(sample, {"measure_events": [{}] * len(sample.get("measure_events", []))})
    return _clean_r2c_output(sample, result["samples"][0])


async def run_r2c_batch(client: AsyncOpenAI, paper_text: str, samples: list) -> dict:
    """R2c 批量：一次请求处理最多 BATCH_SIZE 个 sample，返回 {id: cleaned_events}。"""
    skel = {"samples": samples}
    skel_json = json.dumps(skel, ensure_ascii=False)
    ids = [s["id"] for s in samples]
    label = f"R2c:{ids[0]}..{ids[-1]}({len(samples)})"
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": make_system(paper_text)},
                {"role": "user", "content": build_r2c_user(skel_json)},
            ],
            temperature=0,
            reasoning_effort="max",
            extra_body={"thinking": {"type": "enabled"}},
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"  [ERROR] {label} {str(e)[:100]}")
        return {s["id"]: _clean_r2c_output(s, {"measure_events": [{}] * len(s.get("measure_events", []))}) for s in samples}
    usage = resp.usage
    _log_cache(usage, label)
    result = json.loads(resp.choices[0].message.content)
    if "samples" not in result:
        print(f"  [WARN] {label} 返回无 samples")
        return {s["id"]: _clean_r2c_output(s, {"measure_events": [{}] * len(s.get("measure_events", []))}) for s in samples}
    r2c_map = {r["id"]: r for r in result["samples"]}
    out = {}
    for s in samples:
        if s["id"] in r2c_map:
            out[s["id"]] = _clean_r2c_output(s, r2c_map[s["id"]])
        else:
            print(f"  [WARN] R2c 批量结果缺少 {s['id']}，填空")
            out[s["id"]] = _clean_r2c_output(s, {"measure_events": [{}] * len(s.get("measure_events", []))})
    return out


# ═══════════════════════════════════════════════════
# Excel 导出（denormalized，给人看）
# ═══════════════════════════════════════════════════

_SAMPLE_COLS = ["sample_id", "origin", "rock_type", "formation", "group", "member",
                "province", "city", "basin", "locality",
                "lat", "lng"]
_EVENT_COLS = ["technique", "value_number", "value_error_value", "value_error_scale",
               "annotation", "isotope_system", "mineral", "physical_method",
               "statistical_model", "distribution_state"]
_SPOT_COLS = ["u_ppm", "th_ppm", "th_u_ratio", "concordance",
              "r207_206_value", "r207_206_err",
              "r207_235_value", "r207_235_err",
              "r206_238_value", "r206_238_err",
              "age_206_238_value", "age_206_238_err",
              "age_207_235_value", "age_207_235_err"]
_RATIO_KEYS = ["r207_206", "r207_235", "r206_238", "age_206_238", "age_207_235"]


def _spot_row(sample_id: str, spot: dict) -> list:
    row = [sample_id]
    for k in _SPOT_COLS:
        if k in ("r207_206_value", "r207_206_err", "r207_235_value", "r207_235_err",
                 "r206_238_value", "r206_238_err", "age_206_238_value", "age_206_238_err",
                 "age_207_235_value", "age_207_235_err"):
            rk, sub = k.rsplit("_", 1)
            sub = "err_1s" if sub == "err" else sub
            obj = spot.get(rk)
            row.append(obj.get(sub) if isinstance(obj, dict) else None)
        else:
            v = spot.get(k)
            # R2b 有时把标量字段也存成 dict
            if isinstance(v, dict):
                v = v.get("value")
            row.append(v)
    return ["" if v in (None, "null") else v for v in row]


def _is_noise_event(e: dict) -> bool:
    """统计模型和分布状态均为空的事件，不输出到表格"""
    val = e.get("value") or {}
    return (val.get("statistical_model") in (None, "null", "") and
            val.get("distribution_state") in (None, "null", ""))


def _is_empty_event(e: dict) -> bool:
    """value 和 annotation 同时为空的事件"""
    val = e.get("value") or {}
    return (val.get("number") in (None, "null", "") and
            e.get("annotation") in (None, "null", ""))


def _dedup_events(events: list) -> list:
    """同一 sample 内，physical_method + statistical_model + distribution_state
    重复 ≥5 次的只保留第一条"""
    from collections import Counter
    keys = []
    for e in events:
        val = e.get("value") or {}
        key = (e.get("physical_method"),
               val.get("statistical_model"),
               val.get("distribution_state"))
        keys.append(key)
    counts = Counter(keys)
    seen: set = set()
    kept = []
    for e, key in zip(events, keys):
        if counts[key] >= 5:
            if key in seen:
                continue
            seen.add(key)
        kept.append(e)
    return kept


def _event_row(e: dict) -> list:
    """将 event dict 展开为 _EVENT_COLS 对应的行。"""
    val = e.get("value") or {}
    err = val.get("error") or {}
    row = []
    for k in _EVENT_COLS:
        if k == "value_number":
            row.append(val.get("number"))
        elif k == "value_error_value":
            row.append(err.get("value"))
        elif k == "value_error_scale":
            row.append(err.get("scale"))
        elif k == "statistical_model":
            row.append(val.get("statistical_model"))
        elif k == "distribution_state":
            row.append(val.get("distribution_state"))
        else:
            row.append(e.get(k))
    return ["" if v in (None, "null") else v for v in row]


def _export_flat_xlsx(merged: dict, out_path: Path):
    wb = Workbook()

    # Sheet 0: reference
    ws_ref = wb.active
    ws_ref.title = "reference"
    ref = merged.get("reference", {})
    for k in ["title", "authors", "journal", "year", "volume", "pages", "doi"]:
        ws_ref.append([k, ref.get(k) or ""])

    # Sheet 1: measure_events
    ws_e = wb.create_sheet("measure_events")
    ws_e.append(_SAMPLE_COLS + _EVENT_COLS)
    has_real_value = False
    vn_idx = len(_SAMPLE_COLS) + _EVENT_COLS.index("value_number")
    for s in merged.get("samples", []):
        loc = s.get("location") or {}
        base = [s["id"], s.get("origin", ""), s.get("rock_type", ""),
                s.get("formation", ""), s.get("group", ""), s.get("member", ""),
                s.get("province", ""), s.get("city", ""), s.get("basin", ""),
                s.get("locality", ""),
                loc.get("lat"), loc.get("lng")]
        for e in _dedup_events(
                [e for e in s.get("measure_events", [])
                 if not _is_noise_event(e) and not _is_empty_event(e)]):
            row = base + _event_row(e)
            ws_e.append(row)
            if row[vn_idx] not in (None, "", "null"):
                has_real_value = True

    # Sheet 2: observations
    ws_s = wb.create_sheet("observations")
    ws_s.append(["sample_id"] + _SPOT_COLS)
    for s in merged.get("samples", []):
        for sp in s.get("spots", []):
            row = _spot_row(s["id"], sp)
            if any(v not in (None, "", "null") for v in row[1:]):
                ws_s.append(row)

    # observation 全空 + events 全无数字 → 不输出
    if ws_s.max_row <= 1 and not has_real_value:
        return
    wb.save(out_path)


# ═══════════════════════════════════════════════════
# 树状审核表（分 sheet，每层只带父节点 id）
# ═══════════════════════════════════════════════════

def _export_tree_xlsx(merged: dict, out_path: Path):
    wb = Workbook()

    # Sheet 1: reference
    ws_ref = wb.active
    ws_ref.title = "reference"
    ref = merged.get("reference", {})
    for k in ["title", "authors", "journal", "year", "volume", "pages", "doi"]:
        ws_ref.append([k, ref.get(k) or ""])

    # Sheet 2: samples
    ws_s = wb.create_sheet("samples")
    sample_cols = ["sample_id", "origin", "rock_type", "formation", "group", "member",
                   "province", "city", "basin", "locality", "lat", "lng"]
    ws_s.append(sample_cols)
    for s in merged.get("samples", []):
        loc = s.get("location") or {}
        row = [s["id"], s.get("origin", ""), s.get("rock_type", ""),
               s.get("formation", ""), s.get("group", ""), s.get("member", ""),
               s.get("province", ""), s.get("city", ""), s.get("basin", ""),
               s.get("locality", ""),
               loc.get("lat"), loc.get("lng")]
        ws_s.append(["" if v in (None, "null") else v for v in row])

    # Sheet 3: observations
    ws_sp = wb.create_sheet("observations")
    spot_cols = ["sample_id", "spot_id", "u_ppm", "th_ppm", "th_u_ratio", "concordance",
                 "r207_206_value", "r207_206_err",
                 "r207_235_value", "r207_235_err",
                 "r206_238_value", "r206_238_err",
                 "age_206_238_value", "age_206_238_err",
                 "age_207_235_value", "age_207_235_err"]
    ws_sp.append(spot_cols)
    for s in merged.get("samples", []):
        for sp in s.get("spots", []):
            row = _spot_row(s["id"], sp)
            row.insert(1, sp.get("id", ""))
            row = ["" if v in (None, "null") else v for v in row]
            if any(v not in (None, "", "null") for v in row[2:]):
                ws_sp.append(row)

    # Sheet 4: measure_events
    ws_e = wb.create_sheet("measure_events")
    event_cols = ["sample_id", "technique", "value_number", "value_error_value",
                  "value_error_scale", "annotation", "isotope_system", "mineral",
                  "physical_method", "statistical_model", "distribution_state"]
    ws_e.append(event_cols)
    has_real_value = False
    vn_idx = event_cols.index("value_number")
    for s in merged.get("samples", []):
        for e in _dedup_events(
                [e for e in s.get("measure_events", [])
                 if not _is_noise_event(e) and not _is_empty_event(e)]):
            row = [s["id"]] + _event_row(e)
            row = ["" if v in (None, "null") else v for v in row]
            ws_e.append(row)
            if row[vn_idx] not in (None, "", "null"):
                has_real_value = True

    # observation 全空 + events 全无数字 → 不输出
    if ws_sp.max_row <= 1 and not has_real_value:
        return
    wb.save(out_path)
# ═══════════════════════════════════════════════════

async def run_pipeline(docx_path: str):
    paper_text = load_docx(docx_path)
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stem = Path(docx_path).parent.name or Path(docx_path).stem

    # ── R1 ──
    print(f"文件: {Path(docx_path).name} ({len(paper_text)} 字符)")
    t_total = time.time()
    skeleton = await run_r1_multi(client, paper_text)
    n_samples = len(skeleton.get("samples", []))
    n_events = sum(len(s.get("measure_events", [])) for s in skeleton.get("samples", []))
    n_spots = sum(len(s.get("spots", [])) for s in skeleton.get("samples", []))
    print(f"  R1 结果: samples={n_samples} events={n_events} spots={n_spots}")
    (out_dir / f"{stem}_r1.json").write_text(
        json.dumps(skeleton, ensure_ascii=False, indent=2))
    print(f"  已保存: {stem}_r1.json")

    # ── OpenAlex 补全 reference ──
    skeleton["reference"] = enrich_reference(skeleton.get("reference", {}))

    # ── Filter ──
    n_before = len(skeleton.get("samples", []))
    skeleton = filter_skeleton_for_r2(skeleton)
    n_after = len(skeleton.get("samples", []))
    print(f"  过滤: {n_after} self samples ({n_before - n_after} cited removed)")

    # ── R2a + R2b + R2c ──
    self_samples = skeleton.get("samples", [])
    n = len(self_samples)
    n_batches = (n + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n  R2 启动: R2a×{n}(batch={BATCH_SIZE}) + R2b×1 + R2c×{n}(batch={BATCH_SIZE})")
    t_r2 = time.time()

    # 分批
    batches = [self_samples[i:i+BATCH_SIZE] for i in range(0, n, BATCH_SIZE)]

    # R2a 批量 + R2b + R2c 批量 全并发
    tasks_r2a = [run_r2a_batch(client, paper_text, batch) for batch in batches]
    tasks_r2b = [run_r2b(client, paper_text, skeleton)]
    tasks_r2c = [run_r2c_batch(client, paper_text, batch) for batch in batches]

    results_2a_maps, results_2b_list, results_2c_maps = await asyncio.gather(
        asyncio.gather(*tasks_r2a),
        asyncio.gather(*tasks_r2b),
        asyncio.gather(*tasks_r2c),
    )
    # 合并 batch 结果为 {id: ...}
    r2a_map = {}
    for m in results_2a_maps:
        r2a_map.update(m)
    r2b_map = results_2b_list[0]
    r2c_map = {}
    for m in results_2c_maps:
        r2c_map.update(m)

    print(f"  R2 完成: {time.time() - t_r2:.1f}s")

    # ── 合并 ──
    merged = {"reference": skeleton.get("reference", {}), "samples": []}
    for s in self_samples:
        sid = s["id"]
        sample = r2a_map.get(sid, s)
        if sid in r2b_map:
            sample["spots"] = _clean_r2b_output(s, r2b_map[sid])
        if sid in r2c_map:
            sample["measure_events"] = r2c_map[sid]
        merged["samples"].append(sample)

    # ── 保存 ──
    out_path = out_dir / f"{stem}_final.json"
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    xlsx_path = out_dir / f"{stem}_flat.xlsx"
    _export_flat_xlsx(merged, xlsx_path)
    tree_path = out_dir / f"{stem}_tree.xlsx"
    _export_tree_xlsx(merged, tree_path)
    print(f"\n  总耗时: {time.time() - t_total:.1f}s")
    print(f"  保存: {out_path}")
    print(f"  保存: {xlsx_path}")
    print(f"  保存: {tree_path}")


def main():
    if len(sys.argv) < 2:
        print("用法: python pipeline.py <docx_path>")
        sys.exit(1)
    asyncio.run(run_pipeline(sys.argv[1]))


if __name__ == "__main__":
    main()
