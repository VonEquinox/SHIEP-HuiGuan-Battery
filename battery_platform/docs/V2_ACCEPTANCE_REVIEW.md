# V2 独立跨模块验收记录

日期：2026-10-02。范围：文档一 T01–T20、文档二 S01–S12 中的服务连接、权限、身份、时间截止、封存隔离、派单、碳账与异步发布边界。此文档记录独立 QA Agent 的实际工作；实现说明、合成过程、真实数据实验与界面验收分别由对应 Agent 的交付文档记录。

本次新增 `battery_platform/tests/test_v2_acceptance.py`，使用真实 FastAPI 路由、SQLite 事务、CP-SAT、碳引擎和后台作业的 snapshot → compute → complete 发布流程。诊断计算使用显式 `llm=False` 的确定性规则基线；这只验证服务行为，不代表云端模型诊断质量。所有场景均为隔离测试数据库中的人工构造样例，没有读取或评分受保护的 model_lab 最终 holdout。

## 1. 执行证据

从仓库根目录执行，依赖来自根目录 UV 环境。第一阶段新增 18 条跨模块验收用例全部通过；包含历史证据、记忆修订、群组接入和真实轮次提交中先复现再修复的回归。该阶段组合检查为 177 passed in 22.77s。随后 GEPA 接入审阅增加一条专门的完整变更发布用例，通过后当前独立用例共 19 条；新增结果单独见第 7 节，不将它混入此前 177 的计数。

```bash
.venv/bin/python -m pytest battery_platform/tests/test_v2_acceptance.py -q
# 添加第 18 条之前独立执行：17 passed in 4.52s
# 当前文件的 18 条均已在以下组合命令中通过

.venv/bin/python -m pytest \
  battery_platform/tests/test_v2_acceptance.py \
  battery_platform/tests/test_v2_workflow.py \
  battery_platform/tests/test_v2_agent_core.py \
  battery_platform/tests/test_v2_dispatch.py \
  battery_platform/tests/test_v2_carbon.py \
  tests/content/test_content_pipeline.py tests/content/test_fixtures.py -q
# 最终执行：177 passed in 22.77s（包含全部 18 条跨模块用例）
# 之前执行：176 passed in 24.53s（添加第 18 条之前）

.venv/bin/python -m pytest \
  model_lab/tests/v2/test_data_v2.py \
  model_lab/tests/v2/test_features_v2.py \
  model_lab/tests/v2/test_models_v2.py \
  -k 'continuation or group_split or future_label or censoring or protected or manifest_rejects or unknown_chemistry' -q
# 8 passed, 11 deselected in 1.77s；仅程序生成的微型身份、时间和拒判样例
```

这三次执行互有覆盖，不能将通过数相加解释为独立验收情景数。40 个派单数学 fixture 和 24 个碳 fixture 的独立 oracle 位于 `tests/content/test_fixtures.py`，它们不属于诊断准确率评测。

## 2. 发现、修复与复测

| 编号 | 实际问题与影响 | 对应修复 | 回归证据 |
|---|---|---|---|
| A01 | 测试目录要求 instrumentation 资格，但原人员登记接口拒绝此资格；合法检查无法登记合格人员 | 人员资格白名单加入 instrumentation | 正式提案 → 人员登记 → CP-SAT → 人工确认 → 技术员观察的完整链路通过 |
| A02 | 历史 Agent 使用截止时间前预测 ID，但另一适配器读取最新预测；写入未来预测会改变过去输入 | V1/V2 预测查询同时绑定资产、安装身份、截止时间；指定预测亦受约束 | `test_future_prediction_write_cannot_change_past_agent_snapshot` |
| A03 | 数值模型的 23/24 等来源序号被当成 ISO 墙钟时间，诊断作业异常 | 适配器显式映射 source_record_ordinal；核心区分来源时间和服务器时间 | `test_registered_v2_source_coordinates_reach_agent_without_becoming_wall_clock` |
| A04 | 人工提案/批准可把 T_TIME_ALIGN 资格削弱为 battery，派单可能选中无仪表资格人员 | 入库和批准均合并测试目录最低资格，不能削弱最低要求 | `test_approval_cannot_reduce_catalogue_qualification_requirements` |
| A05 | 观察修正后仍以首次 available_at 入选历史截止时间；未来人工事实或验收状态进入早期重判 | 按版本记录的 created_at 选择截止时间内证据，抽取/验收发布也保存版本 | `test_later_fact_correction_is_not_visible_to_earlier_reassessment_cutoff` |
| A06 | Memory REVISE 沿用第一条来源的 available_at/raw_feedback_id；未来反馈内容进入过去检索 | 修订保留旧版本来源记录，并更新当前版本来源时间；截止时间前检索排除后来的版本 | `test_later_memory_revision_keeps_its_own_availability_cutoff` |
| A07 | 群组已入库且会话有 group_id，但 Agent 适配器未提供 group_context，群组工具一直返回空集 | 提供有界群组、成员身份、截止时间内证据；发布前校验群组及成员版本 | `test_persisted_incident_context_and_split_preserve_individual_alerts`，含计算过程中拆分后拒绝旧报告落库 |
| A08 | 实际轮次提交后适配器未传 completed_test_ids，规则基线重复推荐刚完成的 T_TIME_ALIGN | 从截止时间内版本化观察生成已执行检查集合，传入核心程序筛选，不依靠提示词防重复 | `test_submitted_round_does_not_recommend_an_already_completed_check`；首次复现失败，修复后通过 |

A05 的历史读取恢复截止时间前保存的原始版本；A06 当前实现过滤截止时间之后的最新记忆修订，不自动恢复旧记忆文本。该保守行为避免未来信息泄漏，但旧内容恢复仍是独立能力，不能据此声称已实现完整的时间旅行检索。

## 3. 新增跨模块用例的实际覆盖

| 服务链或边界 | 验证的行为 |
|---|---|
| 提案 → 批准 → 派单 → 现场观察 → 自动记忆 → 重判 | 批准前没有正式工单；重复人工批准只有一个工单；数学草案经人工确认才派发；观察作者来自登录身份；原文和抽取 span 保留；自动更新无新增人工审批；碳账未被写入 |
| 小程序凭据与 QR | 服务端绑定技术员角色、工单和安装身份；不能访问碳账或派单列表；客户端伪造 author_id 被拒；换装后旧 QR 无效；注销后的 token 无效 |
| 历史预测、观察与记忆 | 未来预测、迟到但回填时间的观察、后续事实修正和后续记忆修订不能进入较早 cutoff；来源序号不冒充墙钟时间 |
| 群组与单体告警 | 拓扑关系不升级为已确认共因；真实持久化群组可进入诊断；拆分保留每个单体告警和子组映射；拆分后旧批准和运行中旧报告被拒绝 |
| Agent/Carbon 故障隔离 | 模拟云端失败的 Agent 作业真实进入 failed，Carbon 作业仍完成；合成碳演示条目保留 provenance，正式导出排除这些条目 |
| 取消与重启 | 在真实计算结束、发布之前请求取消，Agent 无报告/提案、Memory 无激活、派单无草案结果/正式分配、Carbon 无部分结果/活动/账；注册表覆盖 13 类作业，重启将 running 标为 interrupted 而不重放 |
| 封存边界 | Agent 输入不含隐藏真值、期望行为、反馈答案或未揭示分支；封存根不能被选作 evolution；ACE/反思/GEPA 的封存实验被 API 拒绝；Skill 引用无法越目录读取封存案例 |
| 轮次提交 | 真实观察及 round/submit UUID 重复请求保持同一作业；轮次提交不替代最终独立验收，也不扩大批准测试集合；已执行检查不被重复推荐 |

封存边界测试只使用一条封存案例检查输入投影和控制流，将评分函数替换为不读取标签的固定结构度量。该测试不产生或发布封存诊断分数，不激活上下文，不作为通用性能证据。对诊断内容的专家语义验收和正式封存重放尚需单独冻结配置执行。

## 4. 文档一 T01–T20 对照

“程序验证”指上述实际运行或已运行组合测试；“待独立验收”表示这些程序验证不能代替该项的全部现实条件。

| ID | 当前证据 | 范围与尚需证据 |
|---|---|---|
| T01 | 数值微型 MATR 续测身份/曲线合并、group split 测试通过 | 真实来源批次的完整续测映射及 split 审计见数据 Agent 交付；本报告不虚构未运行的真实数据结果 |
| T02 | 未知化学体系/schema/日历预测拒判测试、适配器 unsupported 输出测试通过 | 真实跨源外推性能仍须独立实验 |
| T03 | 删失、未来特征、protected/cross split 拒绝及跨模块历史截止测试通过 | 没有通过构造样例宣称真实 RUL 校准已达标 |
| T04 | 核心工具白名单与权限测试，提案未批准无正式工单、无碳写入 | 现场电气设备控制从未接入此套测试 |
| T05 | 跨模块重复批准与 workflow 请求 hash/版本冲突测试通过 | 审批人来自服务端当前用户 |
| T06 | 核心逐轮揭示测试及真实服务端观察/重判/轮次提交、已执行检查过滤通过 | 真实云端多轮质量、失败检查的新授权条件重试另验 |
| T07 | 持久化群组接入、运行中拆分阻止发布、拆分告警保留通过 | 当前 API 聚合属于拓扑关联；真实残差共因判定不由此证明 |
| T08 | CP-SAT 资格、忙碌、锁定工作、冲突原因和数学 oracle 测试通过 | 人员/路程/工具日历数据的现实准确性需部署方校验 |
| T09 | 自由文本、作者、原文 span、自动经验及重判服务链通过 | 抽取目前为有版本的确定性 span 规则，专家语义判断另验 |
| T10 | 自动 Memory、Skill 候选白名单、隔离/回滚核心测试通过 | 自动运营反馈不会把员工原文直接改成通用 Skill；GEPA 完整独立候选选择实验未由本报告执行 |
| T11 | 恶意反馈原文保留/隔离及未核实事实不可确认根因测试通过 | 完整真实攻击面与专家事实核查不由少数样例代替 |
| T12 | 实际失败 Agent 作业与正常 Carbon 作业并行独立通过 | 反向故障和真实云端连接由其他验收记录补充 |
| T13 | 因子来源、单位/边界不兼容、缺少清单和禁止输出伪零的碳测试通过 | 生产因子证据、许可与更新周期需独立审核 |
| T14 | 工单/反馈链不自动写碳账；碳模块要求计算结果和比较基准 | 完成真实工单后正式账审核属于人工证据流程 |
| T15 | 影子价、现金资格/兑现和重复信用约束算例通过 | 情景价格不构成现金收入、信用资格或认证承诺 |
| T16 | 真实 API UUID 重复/冲突、token、QR/错安装身份与范围测试通过 | 微信真机离线网络与恢复交互待真机验收 |
| T17 | 服务链保留 independent_acceptance_required；原 V1 服务端验收权限测试保留 | 实际技术员自验收拒绝的 V1 回归由主 Agent 全量回归记录确认 |
| T18 | 合成 Carbon 条目演示标识保留，formal=true 正式导出排除通过 | 没有把合成 fixture 作为真实碳效益证据 |
| T19 | Agent、反馈、派单、Carbon 发布前取消和 running 重启终态通过 | 不宣称已对所有操作系统进程崩溃窗口做穷举故障注入 |
| T20 | 未删除 V1 路由、角色与原模型；原测试文件仍保留 | 完整 V1/备份恢复/界面回归结果以主 Agent 最终执行记录为准；本报告不重复宣称未在这里执行的检查 |

## 5. 文档二 S01–S12 对照

| ID | 当前证据 | 解释 |
|---|---|---|
| S01 | SkillLibrary 元数据/正文/资源加载及包验证通过 | 运行库为文档二列出的 16 个诊断 Skill；本次未误报为 18 个 |
| S02 | content 包 schema/hash/正反例与引用检查通过 | 程序结构通过不等于专家已完成语义签署 |
| S03 | 根级 split、派生关系及公开导出不含 oracle 测试通过 | split 从根分配，不以多轮记录增大独立样本数 |
| S04 | 逐轮授权揭示、公开投影和本次封存边界通过 | 测试没有执行真实封存准确率评分 |
| S05 | 矛盾、失败、未知和相同可见信号不同真值的合成包测试通过 | 真实服务轮次提交及重复推荐问题 A08 的修复回归通过 |
| S06 | 观察原文/版本/作者/span 和事实修正 cutoff 回归通过 | 没有用最终结构化字段覆盖原文证据 |
| S07 | 自动 Memory 更新、无更新、冲突、弃用、权限恶意反馈隔离的核心/内容测试通过 | 当前来源可信度仍明确区分 reported 与独立验收 |
| S08 | 群组 runtime 上下文、拆分和单体告警保留通过 | 拓扑相关性明确标为未确认因果 |
| S09 | 40 个独立派单 oracle、服务范围与人工确认边界通过 | oracle 为程序穷举；不使用 LLM 答案验证求解器 |
| S10 | 24 个碳 oracle、容差、额定容量/服务/不确定性/更新算例通过 | 碳 fixture 与诊断 Skill/RAG 隔离 |
| S11 | provenance、信任与来源/许可字段 schema 和负例检查通过 | synthetic、public_generated、real 的字段校验不自动产生现实许可或认证 |
| S12 | 初始化排除封存根，路径工具拒绝越目录，sealed 禁反思/激活通过 | 正式冻结后的独立封存重放是后续实验；本次只验证边界 |

## 6. 提交与交付边界

本 QA Agent 只修改上述验收测试与本独立文档。A01–A08 的模块修复由主 Agent 或模块所有者完成；Git Commit 由主 Agent 在 DEV 上按阶段记录。本报告没有保存凭据、调用真实云端接口、发布 benchmark 质量结论或签署真实碳核算。

真实 DeepSeek/OpenAI 兼容接口 smoke、浏览器流程、微信真机、生产部署和完整 V1 回归分别需要附上各自的命令、运行记录与局限后再认定验收完成。程序通过数不得替代这些证据。

## 7. GEPA 最终接入追加审阅

审阅 `schedule_context_gepa`、GEPA snapshot/compute/complete、实验 compute/complete、GEPASearch 与独立 dev scorer。没有读取最终 holdout、调用云端或修改这些模块所有者的文件；另一个独立只读 Agent 并行复核 scorer 的最小离线样例。

当前确认的正确边界：自动调度按反馈根去重；无云端 Key 时返回明确 no_update，零 provider 请求且不激活；基线和失败候选均预留选择集 rollout 预算；dev 与提案根独立；最终取消与上下文 CAS 阻止激活。`ReplayEvaluator.context_changes` 从全段审计提取实际激活变化，发布完整的早期 ACE、早期 GEPA 和最后 ACE 增量。

新增 `test_evolution_publication_retains_earlier_ace_and_gepa_changes` 使用两个手工 evolution 根、规则诊断及显式标记的测试增量，通过真实实验路由与最终发布验证 `ADD → SKILL_REVISE → ADD` 三条变化全部存入运行与快照。它隔离发布逻辑，不证明该测试 Skill 增量经过现实专家或云端质量验收。

```bash
.venv/bin/python -m pytest battery_platform/tests/test_v2_acceptance.py -k earlier_ace -q
# 1 passed, 18 deselected in 0.40s

.venv/bin/python -m pytest battery_platform/tests/test_v2_gepa_service.py battery_platform/tests/test_v2_gepa_workflow.py -q
# 修复后的必要 GEPA 边界组合：20 passed in 5.51s
# 未再次运行原来的 18 条跨模块验收或整个 177 条组合
```

| 编号 | 最小离线复现 | 状态 |
|---|---|---|
| G01 | 生成候选使用保留名 baseline，把真正的 0.9 基线分数覆盖成 0.1；之后仅 0.2 的候选仍可被选中 | 已修复并通过原最小复现：保留名候选被拒，no_update、无激活，失败候选仍计入 3 个 rollout |
| G02 | Provider 返回缺 choices 或非法结构时 failed_request_count 没有增加；缺 choices 响应包含的 usage 也丢失 | 已修复并通过原离线 HTTP 复现：两种异常分别 request=1、failed=1，响应报告的 3 个 token 保留 |
| G03 | 选择用例标为 safety_infeasible 的检查以 authorization=required 推荐，unsafe_test_count=1 却无 hard failure，可得到高分并被选中 | 已修复并通过原 run_agent/本地 JSON Stub 复现：报告校验失败且不可选中，独立 scorer 也拒绝任何 unsafe_test_count |
| G04 | 取消前真实发生的 provider 请求与 token 费用没有写入取消作业产物；中途取消亦在服务累计遥测前抛出 | 已修复并通过自动 GEPA、实验 GEPA、选择途中取消和失败比较回归：短事务单独保存 accounting_only 遥测，原取消/CAS 激活屏障保持有效 |

G04 修复将服务账务累计放入 finally，实验使用 tracked runner 汇总直接诊断与搜索费用；后台作业失败/取消时只调用账务钩子，不调用会激活上下文的 complete。实际已报告 token 用量、失败请求和预留 rollout 留在作业关联的进化记录中；没有用默认 0 冒充供应商未报告的 token 用量。

本追加审阅复现的 G01–G04 均已修复并通过上述局部复测。正式云端 GEPA 效果、专家盲评与冻结后封存成绩仍需要各自的实验记录，不能由这些程序边界测试代替。
