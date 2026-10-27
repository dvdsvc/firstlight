# Geochronology Agent v3

这个 Agent 的数据模型不是让一个总提示词把所有体系压成同一张结果表。顶层 controller 读取全文、紧凑状态摘要和 registry 工具卡，通过一次 tool-use 规划选择零个、一个或多个专业 profile；每个 profile 同样读取全文，因此方法段、表格、图注、结果和讨论仍在同一证据视野中，但只接收并写入自己的局部状态。`geochron_<method>` 是 MCP 的领域边界，例如 `geochron_upb` 同时承载 `upb_in_situ` 和 `upb_id_tims`；profile 是该 MCP 内按观测工作流切换的字段卡。它不是另一轮切文，也不是嵌套提示词：router 选择 profile，profile 根据自己的字段卡形成增量，reducer 依据 profile 身份、体系、技术和字段权限执行唯一的状态写入。

所有 profile 使用同一棵自然树：`sample_attributes_add → method_context_add → raw_observations_add → aggregate_observations_add → author_inferences_add`。样品属性保存地质与空间上下文；原始观测承载 spot、grain、fraction、heating step、aliquot 等物理分析单位；聚合观测保存加权平均、峰值、平台、等时线、校正年龄等结果；作者推理只保存作者明确赋予聚合结果的年龄类别、解释描述或注释。这样 U-Pb 的点分析、Ar-Ar 的加热阶段和 Rb-Sr 的矿物/全岩等时线不必被压进 `kind` 枚举，也不会把“原始数值”和“作者解释”混成一个 event。

字段采用 [USGS Geochron: Data Compilation Templates 2.0 (June 2025)](https://doi.org/10.5066/P14SSWBH) 的实际模板字段名；源码中的 `profiles/standard.py` 同时记录主数据字典链接、模板文件名、discover 字段卡和 enrich 字段卡。这里的“标准”指这套当前公开、方法分模板的官方数据字典，而不是声称存在覆盖全部体系的单一 ISO schema。EarthChem 的 `Sample Metadata / Method Metadata` 与 Sparrow 的 `sample → session → analysis → datum` 是互操作的参考背景；本项目的语义树服务于论文抽取与状态管理，不试图复刻实验室 LIMS。

| MCP 边界 | Profile | USGS 模板 | 原始观测的代表字段 |
|---|---|---|---|
| `geochron_upb` | `upb_in_situ` | `U-Th-Pb_insitu` | `Analysis_ID`、`Pb206U238`、`Pb207U235`、`PctDiscordW`、`DomainAnalyzed` |
| `geochron_upb` | `upb_id_tims` | `U-Th-Pb_TIMS` | `U_ID`、`Pb_ID`、`CommonLeadModel`、spike/blank correction、fraction ages |
| `geochron_arar` | `arar_incremental_heating` | `Ar40-Ar39` | `Temperature`、`Ar40…Ar36`、`Ar39perc`、`JValueAbs`、isochron ratios |
| `geochron_arar` | `arar_fusion` | `Ar40-Ar39` | `LaserPower`、argon isotopes、fusion analysis |
| `geochron_kar` | `k_ar` | `K-Ar` | `K2OWtPct`、`ConcRad40`、`PctRadAr40`、decay constants |
| `geochron_u_th_he` | `u_th_he` | `U-Th-He` | `U`、`Th`、`Sm`、`He`、grain geometry、`FT`、uncorrected age |
| `geochron_u_series` | `u_series_in_situ` / `u_series_solution` | `U-series insitu` / `U-series Solution` | U-Th activity ratios、detrital correction、initial activity ratio |
| `geochron_fission_track` | `fission_track` | `Fission_Track` | track densities、zeta、track length、`Dpar` / `Dper` |
| `geochron_cosmogenic` | `cosmogenic_be10_al26` / `cosmogenic_he3` | `Be10-Al26` / `He3` | nuclide concentrations、shielding、thickness、density、scaling reference |
| `geochron_radiocarbon` | `radiocarbon_c14` | `C14` | uncalibrated/calibrated age、calibration curve、`F14C`、`D13C` |
| `geochron_luminescence` | `luminescence` | `Luminescence` | dose rate、equivalent dose、aliquot count、MAM/CAM ages |
| `geochron_rb_sr` | `rb_sr` | `Rb-Sr` | `Rb87Sr86Ratio`、`Sr87Sr86Ratio`、initial Sr ratio |
| `geochron_sm_nd` | `sm_nd` | `Sm-Nd` | `Sm147Nd144Measured`、`Nd143Nd144Measured`、`eNd_t`、`Tdm` |
| `geochron_lu_hf` | `lu_hf` | `Lu-Hf` | `Lu176Hf177Measured`、`Hf176Hf177Measured`、`eHf_t`、`Tdm` |
| `geochron_re_os` | `re_os` | `Re-Os` | Re/Os concentrations、`Re187Os188`、`Os187Os188`、initial Os ratio |

同一 profile 有两个操作。`discover` 只使用较短的标准字段卡建立四层骨架；`enrich_candidates` 围绕该 profile 已有的 sample、原始观测或聚合观测补充第二组官方字段和来源。两者都返回 delta 而非完整树。coverage audit、蜜罐或局部结构补全只提出未覆盖项、冲突项和 route hint，controller 因而能把后续任务变成 `enrich_candidates`，不会要求工具再抄一遍全文结果。缓存键应包含 document hash、profile、operation、field-card 版本与 local-state revision。

状态 reducer 是语义写入权限的硬边界：profile 的 `method_context_add.isotope_system` 与 `technique` 必须符合自己的注册卡；每一层的字段名都必须在该 operation 的 USGS 字段卡中；聚合观测只能引用同一样品下的原始观测，作者推理只能引用同一样品下的聚合观测。即使模型将另一个体系伪装成当前 profile，method/profile/field/reference 任一检查失败都会拒绝该 delta，并把异常留给 audit 或 router，而不是污染别的状态树。

蜜罐仍是独立 validation MCP：controller 在未修改论文上用低成本信号选择可安全注入的控制项，将少量控制关系嵌入结果段，router 与已选 profile 读取同一增广全文；控制输出在 reducer 前移除。验证结果只有 `pass` 或 `fail + reasons`，当前 reason 包括 `missing`、`merged`、`misbound`、`misrouted`、`source_confusion` 与 `parse_noise`。真实模型 E2E 尚未执行；当前测试覆盖 registry、路由、多体系 batch、语义树 reducer、字段权限和结构化蜜罐。
