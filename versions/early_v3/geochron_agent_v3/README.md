# Geochronology Agent v3

v3 采用单顶层 document-run controller，而不是互相聊天的多 Agent。controller 在每轮读取全文、紧凑状态摘要和 registry 工具卡，通过一次 function/tool-use 调用派发零个、一个或多个已注册 profile。专业 profile 也读取论文全文，以保持方法、结果、表格、图注和讨论间的证据链；隔离发生在写入权限：每个 profile 只接收自己的局部状态，只能返回自己的 `sample_patches`、`conflicts`、`uncovered`，不能重写全局结果或其他同位素体系。

当前唯一实现的专业工具是 `upb_in_situ`，优先面向 LA-ICP-MS，也兼容 spot/domain 结构清楚的 SIMS/SHRIMP；ID-TIMS 被明确排除，等待独立 profile。它不再输出一次性的 R1 总骨架，而是返回树状增量：每个 `sample_patch` 保留 `sample_fields_add → spots_add / age_results_add / events_add` 的自然层级，event 通过 result_ids 指向同一 sample 下的结果。状态 reducer 在内部拆分并检查 job capability、method、technique、profile 身份及 event 到 result 的引用；模型即使将 Ar-Ar 伪装成 U-Pb，也不能越过结构权限检查，随后仍应由 claim-grounding audit 判断原文是否真正支持归属。

正常论文的预算路径是一次 router 批量派发、每个被选 profile 一次全文 delta、一次 coverage audit。只有蜜罐失败、未覆盖证据、冲突或 route hint 才允许 controller 进行第二轮；默认每 profile 最多两次、router 最多两次、audit 最多一次，高风险最多两次。缓存键应使用 document hash、profile、prompt version 与 local-state revision；缓存的是 delta 结果，不是重复模型对话。`coverage audit` 是只读工具：它只能报告未覆盖证据包、冲突和建议路由，不能重新输出完整抽取结果。

本地核心可从 `geochron_agent_v3.controller` 调用：`create_state` 后执行 `run_document_agent`。MCP 服务器仅是同一组能力的外壳，使用官方 Python MCP SDK；安装 `mcp[cli]` 后可运行 `python -m geochron_agent_v3.mcp_server`。实际 LLM 调用读取现有 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`，也兼容 `OPENAI_API_KEY` 与 `OPENAI_MODEL`。未配置 API 时，状态、reducer、registry 与 validator 的单元测试仍可运行。
