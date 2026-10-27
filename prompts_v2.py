"""v2.0 prompt 构建 — R1 新结构：samples + observations（脚手架）+ measure_events"""

SYSTEM_ROLE = "你是工业级吞吐的超大规模结构化信息抽取系统。基于 NER + relation extraction 范式，对全文做 exhaustive slot filling，所有出现的实体和数值全部抽取。输出完整 JSON。上下文窗口 1M tokens，支持全文级 exhaustive extraction。"


def make_system(paper_text: str) -> str:
    return f"{SYSTEM_ROLE}\n\n{paper_text}"


# ═══════════════════════════════════════════════════
# Round 1: 骨架抽取（v2.0 新结构）
# ═══════════════════════════════════════════════════

R1_USER = """═══ 任务：地质年代学文献实体抽取 ═══

从输入文本中识别实体树，逐槽填值，输出 JSON。
核心原则：一次观测，多个聚合视角 —— 原始测定数据（observations）与基于这些观测从不同统计角度产生的解释（measure_events）严格分离；同一组观测数据可以有多个平行的聚合事件，全部召回，无遗漏。
方法通用性：原始观测槽位不依赖具体同位素体系，使用 measurements 数组自我描述各项测定值。

═══ 实体树 ═══

reference（根实体，仅一个）
槽位：title, authors, journal, year, volume, pages, doi
约束：从文本首页/标题页提取；缺失填空字符串。

samples（父实体，每个唯一样品标识符 → 一个实例）
槽位：id, origin, rock_type, formation, group, member
子节点：
  observations[] —— 原始测定数据点（minItems: 0）
  measure_events[] —— 聚合解释事件（minItems: 1，所有角度全部召回）

observations（samples 的子节点）
代表一次基本的原始测定（如一个锆石颗粒、一个 Ar-Ar 升温阶段、一个 SIMS 点位）。
  id : 原文中该测定点的完整标识字符串，逐字抄录
  sample_material : 被测定物质描述（如 zircon, feldspar），缺失填 null
  measurements : 数组，每个元素为一项独立的测量值：
    property : 测量属性名，如 206Pb/238U, 40Ar/39Ar, U, Th
    age : 对象 {number, error: {value, scale}}，年龄值；无则填 null
    ratio : 对象 {number, error: {value, scale}}，同位素比值；无则填 null

measure_events（samples 的子节点）
代表一次对 observations 的统计聚合/解释，同一组观测可以有多个 event。
  method : 定年方法，如 U-Pb, Ar-Ar, Rb-Sr
  technique : 测试技术，如 LA-ICPMS, TIMS, SIMS
  value : 聚合年龄 {number, error: {value, scale}}
  distribution_state : 峰归属描述，逐字抄录；缺失填 null
  statistical_model : 统计模型名称，逐字抄录；缺失填 null
  annotation : 原文解释原句，逐字抄录；缺失填 null

关键约束：必须遍历所有提及的聚合年龄（峰值、坪年龄、等时线等），全部召回。

═══ 输出 JSON 模板 ═══

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
      "id": "",
      "origin": "",
      "rock_type": "",
      "formation": "",
      "group": "",
      "member": "",
      "observations": [
        {
          "id": "",
          "sample_material": null,
          "measurements": [
            {
              "property": "",
              "age": {
                "number": null,
                "error": { "value": null, "scale": "未声明" }
              },
              "ratio": null
            }
          ]
        }
      ],
      "measure_events": [
        {
          "method": "",
          "technique": "",
          "value": {
            "number": null,
            "error": { "value": null, "scale": "未声明" }
          },
          "distribution_state": null,
          "statistical_model": null,
          "annotation": null
        },
        {
          "method": "",
          "technique": "",
          "value": {
            "number": null,
            "error": { "value": null, "scale": "未声明" }
          },
          "distribution_state": null,
          "statistical_model": null,
          "annotation": null
        }
      ]
    }
  ]
}"""


# ═══════════════════════════════════════════════════
# Round 2a: 样品静态属性填充（沿用 v1）
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

1. 仅修改上述槽位，其他槽位原样保留
2. 严格从原文抄录，不得推测或补全
3. 输出完整 JSON，结构与输入一致"""


# ═══════════════════════════════════════════════════
# Round 2b: Spot 数值填充（沿用 v1，固定列）
# ═══════════════════════════════════════════════════

R2B_USER = """任务：从表格中读取数值，填入 spots 子节点的槽位。

═══ 待填槽位 ═══

- u_ppm, th_ppm, th_u_ratio, concordance — 直接填数值或 null
- r207_206, r207_235, r206_238 — 比值字段，结构为 {value, err_1s}，从表格对应列读取
- age_206_238, age_207_235 — 年龄字段，结构为 {value, err_1s}，从表格对应列读取
- 表格中有但上述未列出的数值列，按原文列名小写命名填入

比值/年龄字段填法：若表格有对应列，填 {"value": 数值, "err_1s": 误差}；若无对应列，填 null。

═══ 规则 ═══

1. 仅修改 spots 内的数值槽位，其他槽位原样保留
2. 数值直接从表格读取，不计算、不推测
3. 表格中缺失的数值填 null
4. spots[].id 必须与输入中的 id 完全一致，不得修改
5. 输出完整 JSON，结构与输入一致"""


# ═══════════════════════════════════════════════════
# Round 2c: Ontology Annotation（沿用 v1）
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

  statistical_model（optional）:
{statistical_model_options}

  distribution_state（optional）:
{distribution_state_options}

value 内嵌套:
  value.error.scale（required）:
{error_scale_options}

═══ Rules ═══

1. 每个 slot 的值必须从上述 closed vocabulary 中选取，不得生成新术语
2. 若原文无法判断，填 "null"（字符串）
3. 输出结构必须与输入完全一致：statistical_model、distribution_state、isotope_system、technique、mineral、physical_method 作为 measure_events 的顶层 slot；error.scale 嵌套在 value.error 内
4. value.number、value.error.value、annotation 保持原值不修改
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
