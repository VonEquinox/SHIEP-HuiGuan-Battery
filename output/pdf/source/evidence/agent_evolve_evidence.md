# Agent / Self Evolve：PDF 已核验事实稿

核验日期：2026-10-02（Asia/Shanghai）。只读既有文档与原始机器回执；没有重新调用云端、没有重新评分 sealed、没有读取凭据。当前最新 F02–F07 软件修复没有产生新一轮云端诊断成绩。

## 可以出版的核心结论

系统已具备“报告 → 授权检查 → 可见反馈 → ACE/Memory → GEPA 候选 → 独立 dev 选择 → 自动激活/拒绝 → 回归与恢复”的真实云端闭环。历史试验完成 6 次候选提案、24 次选择 rollout，4 次候选激活、2 次 NO_UPDATE，完整保留失败与费用。闭环可执行性已有证据。

历史 sealed 小试验中，A2 程序质量从共享静态基线 0.7000 到 0.8556，观察差 +0.1556，相对 +22.22%；A3 到 0.7778，相对 +11.11%；A4 到 0.3111，相对 −55.56%。这些是实际归档分数，必须同时展示。A2 是云端臂中最高分，但规则 A0 为 0.9250，高于 A2；不能笼统声称 A2 优于全部基线。

上述观察不能证明自进化造成升分：A2 的情景记忆限同安装，独立根/独立安装无跨根可用情景记忆；云端未固定 seed，温度为 0 不等于服务确定性；每根单次实测、仅 12 根，未完成专业语义盲审。A4 的独立 final dev 与 sealed 都下降；4 次被激活候选的选择分数均与基线持平 0.9333。项目尚未取得“Self Evolve 泛化有效性已由分数提升证明”的证据。可以写“观察到 A2 更高程序质量；自进化收益仍需新的受控实验确认”，不能写“已证明提升 22.22%”。

0.7000 属于 V2 pilot 内部的静态 Skill 云端消融 A1，**不是 main 版本 Agent 分数**。版本功能差异与同协议消融必须分开。main 若无对应实验，应标“无同口径 Agent 评分”，不能将 main→DEV 画成 0.7000→0.8556。

## 模块与用户可见行为

单执行器负责采集、适用性检查、Skill 路由、假设、工具调用、报告验证、等待测量和再评估；不训练 LLM 权重、不控制设备。云端接口为 OpenAI 兼容 Chat Completions，历史实测 DeepSeek `deepseek-flash`。数值模型负责 SOH/RUL/概率的数值估计，云端 Agent 组织证据与行动建议；二者不同。默认假设概率 null，非空必须匹配校准工具权威值。

报告显示事实、引用、候选解释、支持与反证、未知项、适用性、建议检查、优先级及未批准工单提案；未来数据/其他安装/隐藏原因不可用。10 项工具受固定白名单，最多 12 调用、4 个 Skill 正文；批准、分配、Carbon、任意 Shell/HTTP 不在 Agent 工具中。工具错误保留，不能伪装成成功云端结果。

ACE 以 ADD/REVISE/DEPRECATE/CONFLICT/NO_UPDATE 局部更新，不把人员描述升级为确诊，不用 LLM 自评增加 helpful/harmful。新修复保存完整 fact_references，引用原文 offset、反馈 ID/版本、时间和信任；最多 6 事实/2,400 claim 字符的显示投影优先纠错、测量、反证、未知项、结论，全文可按需检索。

检索现在区分同根/同安装的事件历史和相似经验；中文双字片段、英文词边界/有限中英症状映射建立确定性词项门槛，零相关返回空。时间、作用域、状态先过滤；正反例最多各 3 条，总计 6 个唯一 Memory ID，初始与工具共用预算。无 Memory 在执行层关闭历史、相似检索和工具检索，记录真实 ID，外部 callback 不能重新打开。

GEPA 是项目的 GEPA 风格文本候选适配，不声称完整复现上游算法。只编辑 instructions/routing_description/evidence_checklist/retrieval_query_template/inspection_selection_hints；不改权限、权重、数值预测。默认 50 个不同根事件触发，预算 200 rollout；pilot 显式使用每批 2 根、一个候选、baseline/candidate 各 2 dev 根，总 4 rollout。候选只读取已完成 evolution 轨迹，不读取 sealed。

发布后自动 ContextRegression 对同独立 dev previous/current 各 5 根，下降或硬失败可经取消/CAS屏障生成恢复快照并 quarantine。无 prior/Key/dev/完整预算返回 no_check。调度消费键为 root+feedbackID+version，区分 reserved/consumed/retryable/deferred/cancelled/interrupted；同版本/恢复代最多 3 自动尝试，60/120 秒退避，主动取消/重启须显式 retry，既有费用保留。

## 历史分数：保持原始口径

程序质量 Q = 0.4×初始状态符合 + 0.3×引用完整 + 0.2×合适首项检查/拒判 + 0.1/(1+检查数)。直接云端报告 JSON/严格契约失败记 0。每根一次初始报告，失败仍进入分母。该分数不是最终根因准确率；保守拒判可获高分。漏/误检查是 requires_initial_test 的项目配置计数，不是现场故障 recall/precision。

| 臂/实际机制 | evolution Q /有效云报告 | final dev Q /有效云报告 | sealed Q /有效云报告 |
| --- | --- | --- | --- |
| A0 规则，无 LLM、无 Skills、无 Memory | 0.9250 / 不适用 | 0.9250 / 不适用 | 0.9250 / 不适用 |
| A1 静态 Skill/RAG 云端 | 0.8556 /11 | 0.9333 /12 | 0.7000 /9 |
| A2 Reflexion 情景记忆 | 0.8556 /11 | 未运行 | 0.8556 /11 |
| A3 ACE 局部经验 | 0.8556 /11 | 未运行 | 0.7778 /10 |
| A4 ACE+GEPA文本候选 | 0.9333 /12 | 0.5444 /7 | 0.3111 /4 |

全部阶段每行 12 根；A2/A3 final dev 为节省已登记累计预算没有执行，不能填补或估计。sealed A1–A4 初始静态 Context 都为 v0，静态报告共享；A1 final复用同一次，不能当4组独立样本。final A2/A3 Context v11各 11 条 Memory，A4 v16有 12 条 Memory与 data-quality Skill覆盖。

## GEPA 每批结果

| 批 | selection baseline | selection candidate | 状态 | A4 Context版本 |
| --- | ---: | ---: | --- | ---: |
| 1 | 0.9333 | 0.9333 | 激活 | 3 |
| 2 | 0.9333 | 0.8667 | NO_UPDATE；候选严格失败 | 5 |
| 3 | 0.9333 | 0.9333 | 激活 | 8 |
| 4 | 0.9333 | 0.9333 | 激活 | 11 |
| 5 | 0.8667 | 0.8667 | NO_UPDATE；两侧严格失败 | 13 |
| 6 | 0.9333 | 0.9333 | 激活 | 16 |

选择分数与 direct report Q 是不同评估回执，不将 selection rollout 充当新 evolution样本。四次激活证明自动门槛链执行，并未显示选择集升分。修改发生在 data-quality Skill 的允许字段，包含引用编号必须可解析、校准和工况未核对不得确诊、独立复核优先等细则。

## 样本与费用

12 桶各选1个 evolution、1个 dev、1个 sealed根，共36不同根，根/母模板不交叉；evolution6批各2根。先预测冻结，再揭示实际选中且授权的检查，只用到达反馈学习。final Context冻结关闭优化器后首次读12sealed。dev参与selection，不能称盲测。

| V2阶段 | 实际HTTP | provider tokens |
| --- | ---: | ---: |
| evolution | 48 | 500,310 |
| GEPA提案/选择 | 30 | 273,750 |
| final dev | 24 | 268,800 |
| sealed静态 | 12 | 120,848 |
| sealed final | 34 | 364,226 |
| V2合计 | 148 | 1,527,934 |
| V1+V2合计 | 177 | 1,887,590 |

V1 cancelled：29 HTTP，359,656 tokens，7次API/JSON失败；三个完成批次云端每臂仅1/6严格有效，Q约0.154。保留失败；没有sealed。V2修订报告长度并显式关闭thinking，148响应均JSON成功/finish_reason stop，但报告严格有效与API成功不同。直接云报告无效22份：20数值契约拒绝，2在HTTP前预算预留阻断。事后只读发现12份数字拒绝来自中文边界误分词，另8含来源中没有的派生/舍入值；没有用新校验器回填旧分数。

另有两根/臂低难度 smoke：14 HTTP/76,602 tokens，全部组“证据不足”，诊断状态符合和引用结构分都1.0。它证明接口和更新可以执行，不能用作0.7→1.0提升。全2400根A0离线均insufficient_evidence，无HTTP，是执行覆盖。

## F05与当前版本的解释边界

原 API no_memory 使用活动非空 Context 时仍会检索旧Memory，因此此类历史“无Memory”对照失效；原结果不变。原 preregistered pilot A1确实冻结空v0，context_v0.json有0条Memory且A1 final仍v0，所以F05不让这份静态baseline自动作废；同时不能给整个旧系统颁发Memory隔离保证。F05新回归证明真实初始/工具使用ID为空，不证明诊断升分。

F02/F03修复小数与末尾事实、F04修复失败来源恢复、F05修复消融、F06修复指标、F07修复检索，均为后置软件版本；604项Python与浏览器passed不能换算为Agent准确率，也不能将旧报告套新契约重算以宣称当前Agent达到0.9。普通ReplayEvaluator新ExperimentMetrics没有综合score；pilot程序质量必须作为独立协议展示，不与新曲线串联。

## 原始证据路径

- `docs/V2_AGENT_EXPERIMENT.md`
- `docs/V2_AGENT_IMPLEMENTATION.md`
- `docs/V2_AGENT_FINAL_REVIEW.md`
- `docs/V2_F01_F07_REPAIR_20261002.md`
- `battery_platform/reports/v2_agent/preregistered_pilot_v2/{protocol,summary,results,context_v0,final_contexts,post_execution_audit,post_pilot_runtime_change}.json`
- `battery_platform/reports/v2_agent/preregistered_pilot_v2/provider_calls.jsonl`
- `battery_platform/reports/v2_agent/preregistered_pilot_v1/summary.json`
- `battery_platform/reports/v2_agent/cloud_smoke.json`
