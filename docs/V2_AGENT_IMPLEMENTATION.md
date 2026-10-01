# V2 单 Agent、主动检查与 Context 进化实施记录

本文件独立记录《01_实施总方案》05、06、08、14.2 的代码、验证和实验限制。实现代码在 `battery_platform/app/agent/` 与 `battery_platform/app/diagnosis/`；数据库、HTTP 端点、作业发布与正式派单由后端模块负责。该记录供主协调 Agent 在每个分段 commit 时纳入完整实施日志，子 Agent 不单独提交 Git。

## 已实现的单执行器

`app.agent.run_agent(payload, *, tools=None, llm=None, skill_library=None, context_store=None)` 返回 `report/run/context_snapshot/tool_trace`。固定流程包含采集、适用性检查、Skill 路由、候选分析、程序工具、严格报告验证，以及等待补测或结束；第二轮从 `REASSESS` 开始。执行器不创建另一个诊断 LLM Agent，不训练或改动 LLM 权重，不输出隐式思维链，不控制设备。

报告 schema、资产/安装身份、轮次、时间截断和上下文版本由服务端约束。引用必须来自当前可见证据；未来测量、晚到的回填测量、其他安装身份和 `hidden_truth/oracle/branches/sealed` 被递归隔离。数值模型的 cycle/sample 坐标与服务端 ISO 时间分开：嵌套模型 query 必须声明来源字段，且 `feature_max_time <= visible_cutoff`；这不改变实际测量的 ISO 可见时间规则。

假设概率默认 `null`；非空值必须精确匹配校准数值工具给出的权威概率。数值事实必须在所引用证据中找到对应数字。该检查证明数字和引用可追溯，不能替代专家对自然语言语义和因果关系的独立复核。未经独立确认的人员描述不能令报告直接确诊；`confirmed` 假设需要 `independently_verified` 来源支持。

`ToolRegistry` 固定允许十项工具：`get_asset_context/get_signal_evidence/read_prediction/get_peer_anomalies/search_knowledge/load_skill/search_memory/rank_tests/propose_work_order/append_report`。参数类型、对象权限、时间边界、最多 12 次调用及工具结果长度均在程序检查中执行。批准、分配、Carbon、任意 SQL、Shell、HTTP 和设备控制无法注册。报告写入回调先检查 schema 与引用，提案回调只能返回未批准提案；持久化回调应由后端暂存并在作业最终发布时统一提交，执行器本身不修改 ContextStore。

`SkillLibrary` 只索引 `approved/approved_synthetic` 元数据，先读取标准 frontmatter 的 name/description 及 manifest，按化学体系、可见输入和关键词路由，再读最多四个正文。引用资源必须属于当前 Skill 的授权清单/带哈希发布文件，路径不可越界。知识检索只读许可知识文件，不接触 oracle、sealed 或 evolution 真值。默认库为 `content_v1`；显式 `llm=False` 的 A0 基线不自动加载 Skill。

## 云端接口与可复现安装

`OpenAICompatibleClient.from_env()` 使用以下环境变量：

| 变量 | 默认值/用途 |
| --- | --- |
| `BATTERY_LLM_API_KEY` | 必填的云端测试凭据；缺失时返回 `None` |
| `BATTERY_LLM_BASE_URL` | `https://api.deepseek.com` |
| `BATTERY_LLM_MODEL` | `deepseek-flash` |
| `BATTERY_LLM_PROXY` | `http://127.0.0.1:7897`；空字符串表示直连 |
| `BATTERY_LLM_TIMEOUT` | 60 秒 |

接口调用 `/chat/completions`，支持 function tools 和 JSON object；所有报告再过本地严格 schema。有限重试处理限流与服务错误，错误只记录状态/类型，不保存返回体或密钥。累计统计每轮全部成功调用的 token 和请求数，并另记失败请求数。没有 key 的运行明确标 `rule_baseline`；已配置云端的失败保留 `execution_mode=cloud` 和问题报告，不能伪装成成功云端诊断。依赖由根目录 `pyproject.toml/uv.lock` 的 `uv sync` 安装，不另装系统包。

## 主动补测与同源事件

`diagnosis.rank_tests` 使用标准化先验、按假设定义的离散结果似然和专业设定 loss matrix 计算 Bayes risk、后验、期望风险下降减测试成本；包括失败和越界结果。未归一化先验/似然、无来源概率模型、非有限成本/耗时会拒绝。无概率模型只输出成本/耗时修正的规则排序，VOI 字段为 `null`。已做测试不能被默认当作独立新证据重复使用。

已批准检查按资格、设备能力、SOP/场地、破坏性授权、轮次和时间预算过滤。首次尚无获派人员/检查轮次的请求使用明确的 proposal-only 状态，允许建议需要新批准及资格分配的检查，返回 `execution_eligible=false`；这不会扩大可执行授权。破坏性、能力和 SOP 硬失败继续过滤。正价值检查耗尽、预算耗尽或需专业转交时可终止为未解决。

`diagnosis.analyze_groups` 从正常参考窗口计算 median/MAD 残差，仅比较同化学体系、负载、温度且时间对齐的邻接通道。常数参考、缺测、错位分别标质量问题。关系只称同步关联或批次关联，不称确认共同根因；虚拟拓扑明确标模拟。`split_group` 要求每个安装成员恰好进入一个子组，拆分后保留单体复核需求。

## 自由反馈与自动 Context 更新

`extract_feedback` 保留原始文字、作者、版本、测量对象与逐项原文 offset；候选事实带 `reported/measurement_supported/independently_verified/contradicted`。文字未测到不作阴性标签；干预后无故障或预测窗口未结束不作误报标签。服务端保存过的结构化修正可供 `evolve_context` 保留，具体断言目标和原报告比较被返回为审查信息。

`ContextStore` 可用内存或本地原子 JSON 文件，也可从后端持久化 snapshot dictionary 水合。快照不可变，活动指针以 version CAS 更新；文件模式只在短临界区使用进程锁，不跨 LLM 请求持锁。ACE 采用局部 `ADD/REVISE/DEPRECATE/CONFLICT/NO_UPDATE`，保留来源、作用范围、反例、信任、使用计数、过期和状态。矛盾反馈保留冲突双方，完全重复反馈不制造新版本。未核实案例可立即作为“人员报告过”被下一次相似查询检索，不自动成为普适事实。dev/selection/sealed 标签不能写入运行 Context。

Skill 改动只能涉及 `instructions/routing_description/evidence_checklist/retrieval_query_template/inspection_selection_hints`，且需要独立 dev/selection 自动回归通过；否则进入 quarantined 并保留原因。符合条件自动激活，无新增人工 Memory/Skill 审批。权限异常或关键回归通过 `check_regression` 自动回滚到前一活动快照。中途新版本不改变当前已冻结的运行快照。

`GEPASearch` 为项目的 GEPA 风格适配器：用已完成 evolution 轨迹/反馈提出局部候选，在互不重叠的 dev/selection 根事件上评价；失败候选和基线都计入 rollout 预算。默认工程参数为 batch 50、rollout 200，可配置为小样本试验。它不声称完整复现上游 GEPA 算法，也不声称小规模结构检查已证明诊断泛化提升。

## 实际验证证据

本地命令：

```sh
uv run python -m pytest battery_platform/tests/test_v2_agent_core.py -q
```

测试覆盖隐藏/未来/安装隔离、回填可见时间、模型来源坐标、未批准首轮提案、服务身份越权、参数/调用预算、VOI 手算（含失败结果）、非法概率、规则退路、常数/错位/跨域群组与拆分、反馈 offset、未独立确认不能确诊、立即记忆检索、冲突、CAS、隔离/激活/自动回滚、失败候选预算、封存里程碑限制，以及真正先授权选测试再揭示的多轮回放。最终实际结果为 **28 passed in 2.82s**；主实施日志同步该结果。

2026-10-02 已实际调用用户授权的 DeepSeek 测试云端 API，代理使用 7897：

| 实验 | 已发生的结果 | 证据 |
| --- | --- | --- |
| 单次报告＋供应商 function-call 流程 | 最终严格报告通过；6 次程序工具调用；缺失 prediction 请求产生一次已报告工具失败，根因保留未知、概率为 null | `battery_platform/reports/v2_agent/cloud_single_report.json` |
| A0–A4 小规模 prequential smoke | 每组 2 个合成根事件；A1–A4 各 2 个云端报告全部过严格检查；14 个实际 provider 请求、0 个 provider 失败；累计 76,602 token | `battery_platform/reports/v2_agent/cloud_smoke.json` |
| Context 变化 | A0/A1 最终 v0，A2 情景记忆 v2，A3 ACE v2，A4 两次 ACE 与两次 GEPA 通过自动 dev gate 后 v4 | 同上 artifact |

单次 function-call artifact 的 token 数是开发早期记录的**最终一次 provider 请求**用量（12,320），不能当成整个工具交互总成本；其完整工具失败原文和运行状态被保留。A0–A4 artifact 使用修订后的累计计数，包含候选生成及基线/候选选择请求。所有 artifact 不含密钥或供应商内部思维文本。

重跑小规模实验：

```sh
# 先在进程环境设置 BATTERY_LLM_*，不要把凭据写入代码或 commit。
PYTHONPATH=battery_platform uv run python -m app.agent.experiment_cli \
  --output battery_platform/reports/v2_agent/cloud_smoke.json
```

smoke 固定一份 JSON provider 调用/报告、最多四份 Skill 正文、相同数值输入和工具预算；A4 的两次候选只用独立 dev 根事件筛选。实验没有读 sealed 文件。`ReplayEvaluator` 保持 A0/A1 静态、A2 情景记忆、A3 ACE、A4 ACE＋批次文本候选；dev/selection 不更新 Context，sealed 只能作为事先确定的隔离 milestone 且不能回传优化器。`replay_session` 可连接 evaluator-only 分支环境，Agent 只收当前可见对象，未选择/未授权的结果无法揭示，多个轮次按一个根事件归档。

## 尚未声称完成的验证

这两类云端实验证明真实接口、结构边界和小规模更新链可以执行。两根事件的困难度很低，所有组都保持“证据不足”，各组评分相同；这不能证明 ACE/GEPA 改善泛化、真实故障根因准确率、真实部署漏报率或员工运维收益。`grounded_assertion_ratio` 是引用结构检查，不是独立语义判分。没有专家盲评、真实现场根因标签或完整封存评测，本次也没有训练新的故障概率模型。早期 smoke 未保存整包内容 checksum，固定的是记录中的模型/工具/上下文配置标识；长期比较还需冻结整个发布包的内容 hash。

正式自动激活在后端取消/输入版本/CAS 检查后的短事务执行。首次运行真实设备、扩大回放样本、使用真实多通道群组数据和独立语义评价仍需要各自完整证据，不能把这里的合成 smoke 改名为真实运维自进化实验。

## 后续补齐：可执行 GEPA 服务与时间隔离回归

新增 `app.agent.gepa_service.GEPAService` 与 `make_batch_optimizer`，使 API 作业和 A4 可以复用同一套真实候选生成/独立 dev 选择服务。`optimize(events, store)` 不修改输入 store，返回 `activation_update/regression/candidateevaluation/rollouts/budget/provider_usage/provider_requests` 等暂存结果；最终持久化仍由后端取消检查与 base snapshot CAS 后完成。Replay callback 只允许在内存 ContextStore 中暂存激活，下一根事件可以看到经过自动 gate 的文本。

默认需要 50 个**不同根事件**，不足时明确 `no_update/awaiting_distinct_feedback_batch`；实验可以显式选择较小 batch。剩余预算按 `max_rollouts - direct_root_count - 已用 GEPA rollouts` 计算，至少需要基线与候选各一次独立选择评价。schema 失败的候选也保留占用的 selection rollout 预算；实际 provider 请求/token 另计，不把预算预留伪装成已经发生的云端调用。

`DevSelectionScorer` 从固定 dev 根集合稳定选择、排除提案来源根，并冻结 Skill 正文及 selection 内容 checksum。oracle 内容只在 scorer 内用于预定义指标，生成器只能看到已完成的 report、tool trace 和反馈；sealed 文件不参与服务选择。评分明确由初始状态正确性、引用存在比例、可接受首项检查及检查数量构成，并保留权限/格式 hard failures；它仍不是专家盲评或真实部署效果证据。

服务在候选生成前后、每个 dev 根执行前后及暂存激活前检查取消。激活使用**生成开始时**捕获的 version，不能改为结束时的最新 version，从而防止旧候选覆盖并发新增经验。独立测试检查不修改传入 store、合格候选的暂存激活、默认 50 阈值、预算耗尽、失败候选预算与实际费用区别、封存/重复根拒绝和调用中取消。

此外修正两条跨模块回归：Memory `REVISE/CONFLICT` 必须更新本次来源的 `available_at/raw_feedback_id`，避免用第一次反馈时间暴露后续修正；含 `time_basis=source_record_ordinal/source_id` 的模型 query 可使用数值 `available_at/reference_cutoff`，但仍须不晚于来源 cutoff，平台最外层 publication availability 继续是 ISO 时间。

真实分支回放不得在初始报告后直接学习 oracle 的未来反馈。`ReplayEvaluator.evaluate` 可接收 evaluator-only 环境和明确冻结的虚拟检查授权，先冻结报告、按所选已授权检查揭示，再只学习 `visible_feedback`。没有分支环境时，引用未揭示观察的反馈返回 `no_update`。固定 Memory 对照可设置 `allow_context_updates=False`；dev/selection/sealed 始终不写 Context。已有 API 接受测试验证了后到 Memory 修正不会进入旧 cutoff 的诊断。

该补齐阶段运行了核心、GEPA 服务及真实 API Memory 回归组合测试；加入固定上下文开关后最终结果为 **37 passed, 17 deselected in 3.38s**（前次为 36 passed in 4.75s）。这里的 provider 计数 stub 仅用于检查计账程序，不冒充新增云端实验；更大的实际 protocol 实验由独立实验记录文档保存。`context_changes` 汇总所有成功 ACE/Skill 更新，避免只展示最后一个快照的局部 changes。

## 独立审查修复：固定基线、安全建议与失败费用

独立审查用离线可控 scorer 复现了候选 ID 冒充基线的缺陷：真实基线分数 0.9，生成的 `candidate_id=baseline` 分数 0.1，后续 0.2 候选可能被错误选择。现改为由搜索器内部位置识别基线，生成器不能修改其角色和回归下限；保留 ID、重复 ID 及空 ID 被拒绝，仍按同样的 selection 根数预留预算。该精确场景现为 `no_update`，无激活，三个预留 rollout 都保留记录。另一回归验证重复 ID 不能覆盖已评分候选。

所有 `safety_infeasible_tests` 推荐都触发 scorer hard failure，包括标注 `authorization=required` 的建议。运行报告、append 和提案也只允许程序 `rank_tests` 已筛出的可行检查或可待批准检查；目录中存在的破坏性/不满足硬前置条件的项目不能被模型再次建议。测试同时覆盖真实 `run_agent` 严格报告边界与 scorer 的独立预定义安全判分。

云端计账在验证 choices 之前保存供应商给出的有效 usage。因此缺失 choices、无效 final JSON、非对象 final JSON 和非法 message 均计一次失败并保留已知 token；重试失败与后续成功各按一次真实请求计账。缺少或无法解析 usage 的请求通过 `unknown_usage_request_count` 明确标识，累计 token 只是已知部分，不把未知费用说成零。`last_usage` 每次请求清空，防止把上一次成功的成本错误带入新失败。executor 的 `complete` 路径也会把 JSON/报告验证失败标为失败，重复标记不会双计。

`GEPAService.optimize` 的 `finally` 保留候选生成/选择已发生的 provider 费用和已预留 rollout，包括中途取消的当前候选。`accounting()` 仅返回预算、来源/选择根和费用，没有激活操作或候选内容；共享 client 的直接回放请求不会重复算成 GEPA 请求。后端可在取消/异常路径独立保存该费用，仍跳过激活。新增回归验证取消后 Context 保持 v0、生成＋一次 dev 报告的两次实际 stub 请求/30 token 被保留，以及失败提案的费用不因 `no_update` 丢失。

固定 4096 completion 预算继续保留。仅在显式设置 `BATTERY_LLM_THINKING=disabled` 或 `enabled` 时发送 `thinking.type`，未设置时省略，使用标准兼容请求。该字段已按 [DeepSeek 官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)核实；新增 MockTransport 检查默认省略与显式关闭两种请求形态。V1 实验已取消并保存实际 29 次请求、359,656 token，sealed 尚未打开；运行代码变化后必须以新 checksum 重新预登记 V2，不能在同一冻结协议中悄悄替换。

该必要修复阶段实际命令与结果：

```sh
.venv/bin/python -m pytest battery_platform/tests/test_v2_agent_core.py \
  battery_platform/tests/test_v2_gepa_service.py \
  battery_platform/tests/test_v2_llm_accounting.py \
  battery_platform/tests/test_v2_gepa_workflow.py -q
```

**57 passed in 9.46s**（核心 29、GEPA 服务 12、LLM 计账 8、API GEPA 8）。新验证均为离线/MockTransport，不额外花费云端调用，不声称新的诊断提升或真实部署结论。运行模块与 `active_tests` 在该结果后冻结，供独立实验文档 `docs/V2_AGENT_EXPERIMENT.md` 记录更大实际实验。

## Post-pilot 通用数字词法修复

独立手工中英文用例确认旧 Unicode `\w` 边界会将 `温度18.25` 错取为 `25`，并误抓 ID/时间碎片。完成完整 signed/scientific token 扫描、CJK 邻接、明确紧邻单位和 ID/date 过滤；来源文本共用同一规则，物理值比对容差未放宽。独立复查再补齐句末英文句点、范围双端点、千位分组和非有限指数拒绝。最终新 38 项手工回归及前述必要组合实际为 **95 passed in 11.95s**。详细独立证据见 [V2_REPORT_VALIDATION_FIX.md](V2_REPORT_VALIDATION_FIX.md)。这是后续软件修复：没有读取 sealed/pilot 数据、调用 LLM、改动冻结 artifact 或重评分原实验。
