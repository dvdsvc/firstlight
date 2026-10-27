"""统一 prompt 构建 — system message 共享全文，task-specific 内容放 user message"""


# ═══════════════════════════════════════════════════
# System message: 通用角色 + 全文（所有轮次共享，缓存命中）
# ═══════════════════════════════════════════════════

SYSTEM_ROLE = "你是工业级吞吐的超大规模结构化信息抽取系统。基于 NER + relation extraction 范式，对全文做 exhaustive slot filling，所有出现的实体和数值全部抽取。输出完整 JSON。上下文窗口 1M tokens，支持全文级 exhaustive extraction。"


def make_system(paper_text: str) -> str:
    return f"{SYSTEM_ROLE}\n\n{paper_text}"


# ═══════════════════════════════════════════════════
# Round 1: 骨架抽取
# ═══════════════════════════════════════════════════

R1_USER = """任务：从文本中识别实体树，逐槽填值，输出 JSON。

═══ 实体树 ═══

reference（根实体，仅一个）:
  槽位: title, authors, journal, year, volume, pages, doi
  约束: 从文本首页 / 标题页提取；缺失字段填空字符串

samples（父实体）: 文本中每个唯一标识符 → 一个实例
  槽位: id, origin, rock_type, formation, group, member
  子节点: spots[], measure_events[]

spots（samples 的子节点）:
  槽位: id, u_ppm, th_ppm
  约束: id = 原文中出现的完整标识符字符串，逐字抄录。
        子节点 id 通常包含父实体 id 作为前缀（如父="MZ815"，子="MZ815-1"）。
        u_ppm、th_ppm 从原文中读取，缺失填 null。

measure_events（samples 的子节点，minItems: 1）:
  槽位: method, technique, value, statistical_model, annotation
  约束:
    value — 对象 {number, error, distribution_state}，number 为数值或 null，error 为 {value, scale}，scale 为原文声明的误差倍率（如 "2σ"、"1σ"），无声明填"未声明"；distribution_state 为原文中对该数值的 peak attribution 描述（如 primary peak、secondary peak、baseline），逐字抄录，缺失填 null
    statistical_model — 原文中用于计算该 value 的统计模型名称，逐字抄录；缺失填 null
    annotation — 原文中对该数值的 determination/explanation 原句，逐字抄录；缺失填 null

═══ 输出结构与示例 ═══

{
  "reference": {
    "title": "",
    "authors": "",
    "journal": "",
    "year": "",
    "volume": "",
    "pages": "",
    "doi": ""
  },
  "samples": [
    {
      "id": "MZ815",
      "origin": "self",
      "rock_type": "",
      "formation": "",
      "group": "",
      "member": "",
      "spots": [
        {"id": "MZ815-1", "u_ppm": null, "th_ppm": null},
        {"id": "MZ815-2", "u_ppm": null, "th_ppm": null}
      ],
      "measure_events": [
        {
          "method": "U-Pb",
          "technique": "LA-ICPMS",
          "value": {"number": 452.3, "error": {"value": 3.1, "scale": "2σ"}, "distribution_state": null},
          "statistical_model": null,
          "annotation": null
        },
        {
          "method": "U-Pb",
          "technique": "LA-ICPMS",
          "value": {"number": 120.0, "error": {"value": 1.0, "scale": "未声明"}, "distribution_state": null},
          "statistical_model": null,
          "annotation": null
        },
        {
          "method": "Ar-Ar",
          "technique": "Ar-Ar",
          "value": {"number": 65.2, "error": {"value": 0.8, "scale": "2σ"}, "distribution_state": null},
          "statistical_model": null,
          "annotation": null
        }
      ]
    }
  ]
}

═══ 抽取规则 ═══

1. origin: "self" 或 "cited"
2. annotation = 原文中对该数值的 determination/explanation 原句，逐字抄录；缺失填 null
3. 所有缺失槽位统一填 null
4. group = 更大范围的包含单位，member = 更小范围的包含单位，从原文层级描述中提取"""


# ═══════════════════════════════════════════════════
# Round 2a: 样品静态属性填充
# ═══════════════════════════════════════════════════

R2A_USER = """任务：为每个 samples 实例补充缺失的槽位值。

═══ 待填槽位 ═══

rock_type — 从原文中提取，无则留空
formation — 从原文中提取，无则留空
group — 从原文中提取，无则留空
member — 从原文中提取，无则留空
province — 省或大区域名称，从原文中提取，无则留空
city — 城市或次级行政区名称，从原文中提取，无则留空
basin — 盆地名称，从原文中提取，无则留空
locality — 具体地点、剖面名称等最高颗粒度位置描述，从原文中提取，无则留空
location — 对象 {lat, lng, source}；从原文中提取采样点经纬度，source 填"paper"；原文无则 lat、lng 填 null，source 填"paper"

═══ 规则 ═══

1. 仅修改上述槽位，其他槽位（spots、measure_events 等）原样保留
2. 严格从原文抄录，不得推测或补全
3. 输出完整 JSON，结构与输入一致"""


# ═══════════════════════════════════════════════════
# Round 2b: Spot 数值填充
# ═══════════════════════════════════════════════════

R2B_USER = """任务：从表格中读取数值，填入 spots 子节点的槽位。

═══ 待填槽位 ═══

- u_ppm, th_ppm, th_u_ratio, concordance — 直接填数值或 null
- r207_206, r207_235, r206_238 — 比值字段，结构为 {value, err_1s}，从表格对应列读取
- age_206_238, age_207_235 — 年龄字段，结构为 {value, err_1s}，从表格对应列读取
- 表格中有但上述未列出的数值列，按原文列名小写命名填入

比值/年龄字段填法：若表格有对应列，填 {"value": 数值, "err_1s": 误差}；若无对应列，填 null。

═══ 规则 ═══

1. 仅修改 spots 内的数值槽位，其他槽位（id、父实体属性、measure_events）原样保留
2. 数值直接从表格读取，不计算、不推测
3. 表格中缺失的数值填 null
4. spots[].id 必须与输入中的 id 完全一致，不得修改
5. 输出完整 JSON，结构与输入一致"""


# ═══════════════════════════════════════════════════
# Round 2c: Ontology Annotation (closed vocabulary mapping)
# ═══════════════════════════════════════════════════

R2C_USER_TEMPLATE = """任务：对每个 measure_events 实例进行 ontology annotation。
将原文描述 map 到 closed vocabulary 中的标准术语。

═══ Closed Vocabulary ═══

事件顶层:
  isotope_system（required）:
{isotope_system_options}

  technique（required）:
{technique_options}

  mineral（required）:
{mineral_options}

  physical_method（optional）:
{physical_method_options}

value 内嵌套:
  value.statistical_model（optional）:
{statistical_model_options}

  value.distribution_state（optional）:
{distribution_state_options}

  value.error.scale（required）:
{error_scale_options}

═══ Rules ═══

1. 每个 slot 的值必须从上述 closed vocabulary 中选取，不得生成新术语
2. 若原文无法判断，填 "null"（字符串）
3. 输出结构必须与输入完全一致：error.scale 嵌套在 value.error 内，statistical_model 和 distribution_state 嵌套在 value 内，其余 vocabulary 字段作为 measure_events 的顶层 slot
4. value.number、value.error.value、annotation 保持原值不修改；error.scale、statistical_model、distribution_state 从 closed vocabulary 中 map
5. 输出完整 JSON"""


def build_r2c_user(skeleton_json: str) -> str:
    from vocab import (
        ISOTOPE_SYSTEM_OPTIONS, DATING_TECHNIQUE_OPTIONS,
        DATING_MINERAL_OPTIONS,
        PHYSICAL_METHOD_OPTIONS, STATISTICAL_MODEL_OPTIONS,
        DISTRIBUTION_STATE_OPTIONS, ERROR_SCALE_OPTIONS,
    )
    def _fmt(options):
        return "\n".join(f"    - {o}" for o in options)
    task = R2C_USER_TEMPLATE.format(
        isotope_system_options=_fmt(ISOTOPE_SYSTEM_OPTIONS),
        technique_options=_fmt(DATING_TECHNIQUE_OPTIONS),
        mineral_options=_fmt(DATING_MINERAL_OPTIONS),
        physical_method_options=_fmt(PHYSICAL_METHOD_OPTIONS),
        statistical_model_options=_fmt(STATISTICAL_MODEL_OPTIONS),
        distribution_state_options=_fmt(DISTRIBUTION_STATE_OPTIONS),
        error_scale_options=_fmt(ERROR_SCALE_OPTIONS),
    )
    return f"=== Entity Tree JSON ===\n{skeleton_json}\n\n{task}"
