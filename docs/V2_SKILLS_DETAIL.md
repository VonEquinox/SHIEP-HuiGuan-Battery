# 慧管电池 V2：Skill 内容实施记录

本文单独记录文档二第 03 节要求的 Skill 内容实施。运行时服务、数据生成和其他总方案内容由各自实施记录覆盖。

## 授权和来源边界

用户明确要求多 Agent 协作、允许合成数据与 Skill，并要求在 DEV 分支分阶段提交。本文实现遵循该请求，文档中的“由用户负责合成”不是禁止本次合成的指令。

Skill 使用 `skill-creator` 的标准格式和渐进加载原则。标准 `SKILL.md` frontmatter 只有 `name`、`description`；项目自定义字段全部进入 manifest。内容标为 `expert_synthetic`、`approved_synthetic`，作者归属为 “AI-assisted project synthesis; not expert-authored”，没有冒充人类专家，没有伪造 DOI、厂家阈值、授权 SOP 或现场结论。此许可状态只表示项目自合成材料可用于本项目合成/回放，不代表外部临床、物理或安全认证。

## 本阶段交付

`tools/content/skill_catalog.py` 提供 `generate_skills(output, cold_cases, cloud_enrichment=None)`。调用后写入 `output/skills/{skill_id}`，返回 Skill 数量、示例数量与 16 条知识证据记录，供总生成器合并到 `knowledge/evidence.jsonl`。

16 个包完整采用文档二的 ID：`data-quality`、`chemistry-eligibility`、`soh-trend`、`lifetime-interpretation`、`efficiency-measurement`、`internal-resistance`、`capacity-loss`、`self-discharge`、`voltage-inconsistency`、`thermal-anomaly`、`charging-anomaly`、`sensor-anomaly`、`fleet-correlation`、`active-test-selection`、`report-work-proposal`、`feedback-context-update`。

每包包含 3 条支持/反条件清晰的候选或流程、2 条困难反例、可执行的工具选择规则、终止/转交条件、4 份案例示例（适用、2 份反例挑战、证据不足）以及 JSON 行为检查点。适用正例表示 Skill 的整理证据流程适用，不代表已确认最终根因。反例挑战明确是针对现有证据的错误推断请求，不虚构源案例具有未观察的物理条件。

每个包写入 `references/evidence.md`，以稳定的 `knowledge-skill-{skill_id}` 引用连接知识记录。manifest 记录来源、许可、适用条件、白名单子集、禁止断言、可修改内容段、权限不变量、例子来自哪个 cold_start 案例和包内文件 SHA-256。

## 可见性和权限实现

示例输入仅投影 `case_id`、`root_scenario_id`、`origin`、`asset_context`、`initial_visible`、`test_catalog`，以及确实在公开案例内存在的 `fleet_context`。不读取 `hidden_truth`、`expected_behavior`、未来分支、未来反馈、观测似然或 oracle 来生成报告。递归过滤嵌套隐藏字段，非 cold_start 输入直接拒绝。初始观察的 `available_after` 若指向未来测试，或时间晚于可见 cutoff，也直接拒绝。路由示例只基于公开症状文本，不使用 split 主桶/隐藏原因。

示例报告将初始事实与未确认候选分开。事实只能引用当前可见 observation/evidence ID；候选不自动继承事实成为支持证据，confidence 留空，初始状态保持 `insufficient_evidence`。示例结构是文档级 Skill 报告示意，在线输出仍由运行时真实 schema 验证。

工具声明采用运行时白名单：`get_asset_context`、`get_signal_evidence`、`read_prediction`、`get_peer_anomalies`、`search_knowledge`、`load_skill`、`search_memory`、`rank_tests`、`propose_work_order`、`append_report`。每个 Skill 仅取所需子集；Carbon 工具不在列表。工作提案与正式派单分开，正式派单保留人确认。Memory 自动更新不新增经理审批；反馈不能增权。

可选云端补充只接受每 Skill 的 `reviewed_notes` 字符串列表。不会导入模型生成的案例答案、报告、oracle 或新增权限。补充文本明确标为项目合成，不作为外部专家结论。

## 验证和提交记录

2026-10-02，本模块在临时目录中以 12 个主桶各 2 个公开冷启动根案例生成完整 Skill 包，执行以下验证，全部通过：

- `python3 -m py_compile tools/content/skill_catalog.py`：语法通过。
- 使用 `uv run --no-project --with pyyaml python`，调用 `skill-creator/scripts/quick_validate.py` 的 `validate_skill`：16/16 标准格式通过。
- 生成数量：16 个包、64 个 JSON 示例、16 条可检索知识证据记录。
- 各包工具声明均为运行时白名单子集；候选数均至少 3，困难反例至少 2。
- 各示例事实的 evidence ID 均属于同一初始可见观察；`known_missing` 被完整记录为未知项，未确认候选没有填造概率。
- 在输入顶层隐藏真值、预期答案及 initial_visible 嵌套隐藏字段植入哨兵，包内所有文件均未出现哨兵。
- evolution、dev、sealed_test 输入全部拒绝；未来测试观察作为 initial_visible 输入也拒绝。
- 正式派单状态始终为 false，工作提案保留人确认。

首次使用系统 `python3` 执行标准校验时，环境缺少 PyYAML；改用 UV 隔离环境运行成功，没有更改项目依赖或全局 Python 包。本模块不访问网络 API、不接触用户测试 Key。UV 网络环境遵循用户给出的 7897 代理设置。

本模块负责人不单独提交，避免共享工作区的并发 Git 操作。实际本阶段 commit 信息由内容负责人完成集成后追加。

后续集成补充：公开 cold_start 案例中可提供截止时间之前已到达的 `initial_visible.visible_feedback`。`feedback-context-update` 路由示例优先选择这种案例，保留工程师自由原文、完整字符 span、当前可见 evidence ID 和 reported 状态；未独立核验的意见演示 `NO_UPDATE`，不变成确认事实。未来反馈仍不读取。manifest 补充 `route_keywords`、`expert_review=not_performed`、`cloud_supplemental_note_count`，明确云端内容只有发布前程序校验，没有冒称专家盲评。

每次后续修改应在此记录具体更改、验证命令/结果与相关提交，不能只写“已优化”。
