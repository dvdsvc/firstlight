# Structured Extract

<img src="assets/mark.svg" alt="文档到关联实体树" width="64" />

**以实体树、分阶段槽位抽取和关联研究表为核心的科学文献信息处理项目。** 这个仓库以地质年代学主抽取流程为入口，同时收录增量 Agent、MCP、已知答案控制和种子驱动文档图恢复实验，保留原始研究实现并明确各自的数据契约。

[English](README.md) · [简体中文](README.zh-CN.md)

## 🔬 研究问题

科学文献抽取需要保持样品、分析测点、年龄、误差与解释之间的归属关系。本项目通过显式实体树和阶段分工组织这些关系，限制后续模型响应可改写的字段，并将论文／样品关联传递到分析表。值得展示的研究工作包括任务拆解、提示词与结构设计、确定性合并、导出语义，以及遗漏和错绑关系的可观测校验。[研究介绍](docs/research_summary.zh-CN.md)。

## 🌳 主抽取流程

```mermaid
flowchart LR
    D[DOCX 段落与表格] --> R1[R1 实体树]
    R1 --> F[来源筛选与标识符清理]
    F --> A[R2a 样品属性]
    F --> B[R2b 测点数值]
    F --> C[R2c 受控词表映射]
    A --> M[按字段限制合并]
    B --> M
    C --> M
    M --> J[最终 JSON]
    J --> T[关联的论文／样品／观测／事件表]
```

主流程以三个温度运行 R1，对基准树已有样品合并事件；R2a、R2c 按样品分批处理，R2b 读取观测数值。R2c 添加描述字段时，程序保留 R1 的年龄数值与误差大小。这些是具体的实现约束：事件仍按位置对齐，主 API 使用 JSON object 模式，并未把代码中声明的 JSON Schema 接入严格服务端校验。[方法与实际合并规则](docs/methods.md) · [导出契约](docs/exports.md)。

## 🧭 版本与相关实验

| 组成 | 保留入口 | 定位 |
|---|---|---|
| 主分阶段流程 | [pipeline.py](pipeline.py) | 实体树、R2a/b/c、受限合并及 JSON／Excel 输出 |
| 分阶段 v2 尝试 | [pipeline_v2.py](pipeline_v2.py) | observations 脚手架、独立 spot 抽取；事件结构和表名不同 |
| 早期增量 v3 | [versions/early_v3](versions/early_v3/README.md) | 独立存档，保留当时唯一已实现的专业工具及配套测试 |
| 状态式控制／MCP | [geochron_agent_v3](geochron_agent_v3/controller.py) | profile 局部增量、写入权限、已知答案控制、覆盖审计与 MCP 外壳 |
| 种子文档图研究 | [research/seeded_graph](docs/graph_recovery.md) | 以前期抽取关系为锚点的路径探查与图补全实验 |

这些内容统一在一个科研展示仓库中。增量 Agent 的状态尚未接通旧版导出器；图候选也不会由 controller 自动写回。[版本关系与数据契约](docs/versions.md)。

## ▶️ 运行离线示例

需要 Python 3.11+ 和 `uv`，在本仓库根目录执行：

```bash
uv sync --locked --all-extras
uv run --locked --all-extras python -B -m examples.staged_demo
uv run --locked --all-extras python -B -m unittest discover -s tests -v
uv run --locked --all-extras python -B -m examples.offline_demo
uv run --locked --all-extras python -B -m examples.graph_demo
uv run --locked --all-extras python -B -m scripts.mcp_smoke
uv run --locked --all-extras python -B -m scripts.check_repository
```

安装依赖可能访问软件包索引；上述示例使用虚构数据，不调用模型。主流程示例以预设响应执行原始调度器，再检查两篇论文中同名样品在关联工作簿里的归属。[模型配置、导出及历史版本运行说明](docs/running.md)。

## 📊 执行证据

历史 `doi_output/json` 集合中保留 **310 份最终 JSON**，包含 **1,752 条样品、9,789 条测点、6,140 条事件记录**，其中 46 份最终文件样品为空。其他目录单独统计，避免把重复运行算成不同论文。这些数字证明存在实际产出，不能作为独立论文总数或抽取准确率。[逐文件计数与哈希](evidence/historical_artifacts.jsonl) · [证据解释](docs/evidence.md)。

本地验证覆盖保留数值的合并、异常响应边界、出口投影、跨论文关联、原始 Agent 契约、已知答案控制及实际 MCP stdio 会话。[检查记录](docs/validation.md)。

## 🗂️ 仓库结构

```text
pipeline.py / run_layer*.py / prompts.py / vocab.py   主分阶段研究实现
pipeline_v2.py / prompts_v2.py                        另一套分阶段契约
export_total.py / merge_tree_xlsx.py                  原始汇总导出路径
geochron_agent_v3/                                   配套一致的控制／MCP 快照
research/seeded_graph/                               独立文档图实验
versions/early_v3/                                  早期核心和测试，隔离保存
examples/ / tests/ / scripts/                       离线示例与整理辅助工具
docs/ / evidence/ / provenance/                     方法、证据和来源映射
```

## 📚 来源与本地审阅

十二个主流程模块和选中的历史 Agent／图代码逐字节保留；新增内容包括展示文档、依赖配置、虚构示例、本地检查和带覆盖检查的运行／导出辅助入口。主流程原目录是大工作区中的未追踪子目录，没有可归属到该组件的提交历史，因此不会据此推定个人独立创作比例。[来源清单](provenance/source_manifest.json) · [贡献及保留边界](docs/provenance.md)。

实际论文语料、原始抽取文本、密钥、模型权重和私人环境未打包。项目许可证与贡献者署名仍需作者在 [LICENSE_PENDING.md](LICENSE_PENDING.md) 中确认。当前为本地审阅候选，尚未公开仓库或部署网站。
