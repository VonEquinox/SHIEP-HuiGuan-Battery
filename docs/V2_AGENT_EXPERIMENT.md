# V2 单 Agent：预登记真实云端回放实验记录

此文件独立记录实际 Agent 对照实验，不以两根 smoke 或离线合成报告代替模型实测。实验由 `tools/content/experiment.py` 驱动，使用既有 `AgentExecutor`、`SkillLibrary`、`ContextStore`、`EvaluatorReplay` 和 `GEPAService`。不修改固定 pipeline，不训练 LLM 权重，不调用 Carbon，不创建正式工单。

## 冻结协议与样本

每次运行必须使用新的空输出目录，首先保存 `protocol.json`，其中冻结内容 manifest SHA-256、所有 Agent/主动检查/实验脚本的代码 hash、模型/base URL、thinking 参数、context_v0 与 hash、工具白名单、token/调用/工具/Skill 预算、12 桶根 ID、评分公式和最终封存里程碑。代码或内容在运行中变化会中断，不静默继续使用旧协议。云端服务只能冻结 provider/model alias 与返回的 model/system_fingerprint，不能取得其私有权重 hash，不能把服务端版本固定程度夸大为本地权重 artifact 固定。

选择规则在第一次预测前确定：12 个主桶各一个 evolution 根（母模板组 8），独立 dev 根（组 14）和独立 sealed 根（组 17），成员索引为桶索引 modulo 8。三个集合各 12 根，彼此无根/母模板交叉。evolution 顺序固定为六批，每批 2 根，A0–A4 对相同原始可见输入分别使用该批开始时的冻结 context。真实生成器的全部 2,400 根可作为 A0 的完整离线执行覆盖，但不能证明 LLM 泛化。

A0 是规则基线；A1 是静态 Skill/RAG 与真实云端报告；A2 保存具体事件的 Reflexion 记忆；A3 使用 ACE 局部增量经验；A4 使用 ACE 加真实云端 GEPA 文本候选/独立 dev 回归。A2 记忆限同安装身份，所有独立根的安装身份不同，因此它不应该凭一例跨资产推广，可能没有跨根收益。A3 保留 chemistry/protocol 条件和 reported 信任等级，不能把人员描述升级为现场确诊。

每批先将全部预测写入独立 `batch_NN_predictions.json` 并 hash 冻结，再让实际选中且授权的虚拟检查返回观察。只有反馈所引 evidence_ids 实际到达后才提取自由反馈、修改 Memory 或提议 Skill。GEPA 每批最多一个候选，在独立的两根 dev 上分别跑基线和候选，最多四个 dev report rollout；失败也占用次数和成本。缺两根有效反馈时正确结果是 NO_UPDATE，不能强补候选。Memory 更新无需经理审批；Skill 自动激活仍受可编辑字段、基线比较、程序约束、回归和取消检查控制。

GEPA 不读取 sealed case 文件。实验环境在训练阶段只解析选中的 evolution/dev oracle 行，未来观察只装入对应 evolution 根。最后冻结所有 final context 后关闭优化器，才首次打开 12 根 sealed 输入。sealed 结果保存为 `selection_eligible=false`，没有任何后续 Memory、候选生成或选优。context_v0 在 A1–A4 完全相同，因此 sealed 初始静态报告只真实调用一次并共享；A1 的 final context 仍是 v0，也复用完全相同的报告。这些复用明确记录，不计为独立新样本。

原情景的时刻用于可见性；各 evolution 批次按整数天重排虚拟回放时间，保留量值、物理身份与 observation ID，反馈可用时间在下一批 cutoff 之前。这个映射预登记，防止“上下文版本增加了但其 available_at 永远晚于后续查询”导致记忆实际不可检索。

## 调用成本和取消

云端只使用用户授权的 OpenAI 兼容 DeepSeek 服务和 `deepseek-flash`，从运行环境读取 Key，不保存 Key、请求认证头或原始服务错误 body。网络走 7897 代理。报告适配器每份最多一个实际 HTTP 请求，禁用自动重试；程序工具 rank_tests 仍在固定执行器内计算。逐次 `provider_calls.jsonl` 记录请求/最终答案 hash、tag、usage、finish_reason、thinking、model、系统 fingerprint、耗时和状态，不保存 reasoning_content。

每次先按请求 UTF-8 字节上界加完整 4,096 completion cap 预留 token，成功后按 provider usage 结算；失败但无 usage 时按预留上界收费，从而不把失败当成零成本。本实验 V1 与后续续跑累计最多 200 请求、2,000,000 tokens。续跑必须用 `--prior-run` 扣除已经发生的实际成本，不能把新目录重置当成新额度。创建输出目录内 `CANCEL` 或中断进程即可取消；已发生的调用 ledger、冻结批次和 partial results 保留，取消后不激活新 Skill。

## V1：保留的失败实验

首个协议输出在 `battery_platform/reports/v2_agent/preregistered_pilot_v1/`。原协议 hash 为 `48e43bf519e1f586746eeb1af1a06b77039233faa720b173bf7ffafefd90e145`。实际完成三个 evolution 批次（每臂 6 根）后主动取消；第四批已启动的 5 次请求也计入总账，但该批没有完成冻结报告集合，未执行 dev 或打开 sealed。总计 **29 次真实 HTTP 请求、359,656 provider tokens**：prompt 267,218、completion 92,438；7 次返回/JSON失败，严格报告成功每个云端臂仅 1/6。取消时已经发出的请求仍完整计入 ledger。

| 臂 | 根数 | 严格有效云端报告 | 平均程序质量 | 平均建议检查 | 漏检查 | 误检查 |
|---|---:|---:|---:|---:|---:|---:|
| A0 | 6 | 不适用 | 0.9250 | 3.000 | 0 | 1 |
| A1 | 6 | 1 | 0.1542 | 0.500 | 0 | 1 |
| A2 | 6 | 1 | 0.1533 | 0.667 | 0 | 1 |
| A3 | 6 | 1 | 0.1533 | 0.667 | 0 | 1 |
| A4 | 6 | 1 | 0.1542 | 0.500 | 0 | 1 |

失败云端报告的质量记 0，不把证据型 fallback 当模型成功。这里漏/误检查依据项目 `requires_initial_test` 配置和实际对外报告（含失败问题报告），不是现场故障 recall/precision。对外报告无错误引用和越权，但 V1 未保存模型原始最终答案，不能据此声称模型未提出错误引用。没有足够两根 A4 合法反馈形成 GEPA 批次，因此没有虚构 GEPA 改善。

观察到 4,096 completion 上限内多次无法给出可解析/严格有效 JSON，推测默认 thinking 与报告长度可能是原因；V1 没有保存 finish_reason，尚不能把这一推测写成已证实的全部失败原因。为修复调试可观察性，V2 保存最终答案与 finish_reason（不保存内部 reasoning），限制报告为最多 3 facts/3 hypotheses/3 unknowns/2 checks，保持服务器 ID/time/version 原样。

V2 optional `thinking.type=disabled` 的字段核对来自 [DeepSeek 官方 thinking 文档](https://api-docs.deepseek.com/guides/thinking_mode/) 和 [官方 Chat Completions 接口](https://api-docs.deepseek.com/api/create-chat-completion/)。这是提供商特定的可选参数；普通 OpenAI 兼容服务默认不发送。冻结模型与参数后重新登记，不能覆盖 V1 的失败记录。

## V2：修订后协议与结果

修订运行继承 V1 成本，剩余上限为 171 次请求、1,640,344 tokens。为保留完整五臂 evolution 和 final sealed 对比，final dev 只比较 A0/A1/A4 的 12 根；A2/A3 的 frozen final 仍在全部 12 sealed 根上对比。理论最多 150 新请求（48 evolution、30 GEPA proposal/selection、24 final dev、48 sealed），加 V1 最多 179，严格低于授权请求数。

预登记 V2 前，独立只读工程审查发现并修复四项执行缺陷：一个并发 future 失败时已经完成的报告未及时落盘、预测后反馈更新前缺取消检查、链式续跑未继承 combined 成本、只核对 manifest 而未核对真实内容字节。现在每份完成报告立即写到 `partial_records/`，取消/错误保留 partial_stage 和 last_contexts；更新和批次发布前再次检查取消；续跑使用累计成本；初始化、各批/阶段前后、封存读取前检查全部真实文件 SHA-256，正文和知识加载使用 FrozenSkills 缓存；运行代码 hash 包括 replay/common/generate。Ctrl-C handler 先标记取消，并在 executor 内立即取消排队 future、保留已完成/活动请求的结果；HTTP 预留锁内再查取消。新增回归后十项预算/协议/取消/冻结测试通过。修复没有读取封存结果或以提升分数为目标调参。

修订协议 SHA-256 为 `cc626a7d4681ad32007fd56b067d1ac8470271ffec334e6d7844761e76282b38`，注册于 UTC 2026-10-01 17:57:04，实际状态 **completed**。不覆写 V1、不因分数重启、不在封存结果后修改验证或重新评分。

所有实测请求使用同一 `https://api.deepseek.com/chat/completions`、`deepseek-flash`、代理 `http://127.0.0.1:7897`、temperature=0、max_tokens=4096、response_format=json_object、HTTP retries=0、60 秒 timeout；不传 tools 字段、seed、top_p 或 stream。报告调用和 GEPA 调用均通过只有 generate_json 的适配器，避免提供商主动扩展工具循环。V1 不发送 thinking 字段、使用原报告约束；V2 显式发送 thinking.type=disabled，并使用协议记录的精简报告约束。V2 全部 148 个实际响应 finish_reason=stop，返回 model=deepseek-flash、system_fingerprint=`aeb56401ca74e127821c4f9126dcb669`。这些返回字段记录版本痕迹，不等于冻结云端权重。

### 实际覆盖和成本

| 阶段 | 根/评估覆盖 | 实际 HTTP | provider tokens |
|---|---|---:|---:|
| evolution | 12 桶各 1 根；5 臂各 12 报告 | 48 | 500,310 |
| GEPA proposal + selection | 6 候选提案；独立 dev 12 根各 baseline/candidate，24 rollout | 30 | 273,750 |
| final dev | 12 根 × A0/A1/A4；该 dev 集也参与 selection，不能称盲测 | 24 | 268,800 |
| sealed 初始 v0 | 独立 12 根 × A0/A1，静态报告供 A1–A4 共享 | 12 | 120,848 |
| sealed final | 相同 12 根 × A2/A3/A4；两份 A4 在 HTTP 前被预留上界阻断 | 34 | 364,226 |
| 完整 A0 离线 | 全部 2,400 根，全部输出 insufficient_evidence | 0 | 0 |
| V2 合计 | 156 份直接报告，另有 24 selection rollout/6 proposal | **148** | **1,527,934** |
| 加已取消 V1 | V1 29 次实际调用也完整计费 | **177** | **1,887,590** |

V2 prompt=1,403,366、completion=124,568；合并 V1 prompt=1,670,584、completion=217,006。V1 7 次 API/JSON 失败均有 provider usage；V2 API/JSON 失败为 0，但运行时契约失败仍拒绝报告并记质量 0。两次预留阻断没有发出 HTTP，费用为 0，仍保留失败报告并进入 12 根分母。两次运行的全部 177 调用均为 provider_reported，unknown usage=0；无 usage 的失败按完整预留上界计费逻辑已有受控 transport 回归，未伪称本次发生这种失败。

### 六批冻结结果

下表每个质量数的分母为同批 2 个根。成本含对应 GEPA，不把 selection rollout 充作新 evolution 样本。

| 批 | A0 | A1 | A2 | A3 | A4 | GEPA | A2/A3/A4 结束版本 | 累计 HTTP | 累计 tokens |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|
| 1 | 0.9250 | 0.9333 | 0.9333 | 0.9333 | 0.9333 | 候选激活 | 2/2/3 | 13 | 119,604 |
| 2 | 0.9250 | 0.9333 | 0.9333 | 0.9333 | 0.9333 | NO_UPDATE | 4/4/5 | 26 | 246,867 |
| 3 | 0.9250 | 0.9333 | 0.9333 | 0.9333 | 0.9333 | 候选激活 | 6/6/8 | 39 | 369,587 |
| 4 | 0.9250 | 0.9333 | 0.9333 | 0.9333 | 0.9333 | 候选激活 | 8/8/11 | 52 | 498,947 |
| 5 | 0.9250 | 0.4667 | 0.4667 | 0.4667 | 0.9333 | NO_UPDATE | 9/9/13 | 65 | 636,417 |
| 6 | 0.9250 | 0.9333 | 0.9333 | 0.9333 | 0.9333 | 候选激活 | 11/11/16 | 78 | 774,060 |

四次激活的候选/基线 selection 程序分均为 0.9333，说明在这两个选择根上不劣，不证明改善。第二批候选出现一份严格无效云报告，得分 0.8667 且硬门失败；第五批基线和候选都出现无效报告、各 0.8667，拒绝更新。失败 selection fallback 不被当作成功候选。全部 Memory/Skill context 在 final_contexts.json 冻结后关闭优化器，后续不再写上下文。

### 按根最终指标

每行根数均为 12。直接对外报告错误引用、越权推荐、无依据确认均为 0；封存及 dev 原始最终答案的 facts/citations/hypothesis supports/contradicts 只读核验也未发现未知引用或 ID/time/version 改写。专业语义正确性仍为 pending。

| 阶段/臂 | 有效云报告/12 | 程序质量 | 平均检查数 | 漏检查 | 误检查 |
|---|---:|---:|---:|---:|---:|
| evolution A0 | 不适用 | 0.9250 | 3.0000 | 0 | 1 |
| evolution A1 | 11 | 0.8556 | 1.8333 | 0 | 1 |
| evolution A2 | 11 | 0.8556 | 1.8333 | 0 | 1 |
| evolution A3 | 11 | 0.8556 | 1.8333 | 0 | 1 |
| evolution A4 | 12 | 0.9333 | 2.0000 | 0 | 1 |
| dev A0 | 不适用 | 0.9250 | 3.0000 | 0 | 1 |
| dev A1 | 12 | 0.9333 | 2.0000 | 0 | 1 |
| dev A4 | 7 | 0.5444 | 1.1667 | 0 | 1 |
| sealed A0 | 不适用 | 0.9250 | 3.0000 | 0 | 1 |
| sealed static v0（A1–A4 初始共享） | 9 | 0.7000 | 1.5000 | 0 | 1 |
| sealed A2 final v11 | 11 | 0.8556 | 1.8333 | 0 | 1 |
| sealed A3 final v11 | 10 | 0.7778 | 1.6667 | 0 | 1 |
| sealed A4 final v16 | 4 | 0.3111 | 0.6667 | 0 | 1 |

sealed A2/A3/A4 相对共享 v0 的观察质量差为 +0.1556/+0.0778/−0.3889。A4 在 final dev 与 sealed 都下降。A2 记忆受安装范围限制，独立安装没有跨根可检索事件，报告波动不能直接归因于记忆收益。云端没有固定 seed，temperature=0 也不等于服务级确定性；共享静态基线和单次每根实测不能识别因果效应或统计显著改善。

### 失败诊断与不可夸大的结论

22 份直接云报告无效：20 份被数值引用契约拒绝，2 份被保守 token 预留规则阻断。GEPA selection 还有 3 份无效报告，均通过硬门拒绝其候选。API 返回 JSON 成功与严格有效报告是不同指标。

封存结束后的只读审计在保持原分数和验证器不变的前提下复核全部 156 个原始 input SHA-256、16 个运行代码 hash、全部内容实际文件 hash、final context hash 和成本 ledger。20 份直接数值拒绝中，12 份可确定是当前验证器的中文数字边界误分词：例如“温度34.89 degC”被正则抽为 89，而其引用测量就是 34.89；仅用 ASCII 数字边界作事后诊断时这些数值全部可匹配原引用。另 8 份仍含不直接存在于所引记录的派生/舍入值，例如模型自行报“比值约 0.825”；不能仅凭这个分组认定每份都是舍入错误。这 8 份不能被当作 numerical service 的原值，也不能据此断言物理数值一定错误。

中文误拒、原值/派生数值边界和两个保守预算阻断共同限制该程序质量指标的解释。**未修改冻结验证器、未调整分数、未重新运行 sealed，也未把 sealed 失败反馈交给优化器。**这份实验不支持“GEPA 已提升泛化”或“GEPA 必然损害诊断”的结论；完成的是实际云端候选生成、检查反馈、回归、激活/拒绝、冻结比较和失败保留的能力试验。封存与只读审计完成后，Agent 负责人用独立手工字符串确认并修复通用词法器，未读取 pilot/sealed、未调用模型、未改原评分或数值容差；该生产软件修复属于后置版本，不回填本次结果。新的对照实验需要另登记协议。

原始 artifact 在两个 preregistered_pilot 目录；post_execution_audit.json 的 training_eligible=false、preregistered_scores_changed=false、live_provider_calls_added=0。独立专业盲审一律 pending。

## 原运行版本与后置软件修复

V2 原 Agent/active-test/common/replay/generate 运行源码可由 Git commit `ce4f87fc987eb4739e4fe5972f115b92d4a4c052`（也与 `a13d1a27894ae84ad9771b6c9e79b08d124d8c63` 的这些路径相同）复原；experiment.py 的精确源码 hash 在 protocol.code_sha256 中。原 contracts.py SHA-256 为 `4ef7608d7b56cd474e07305e24e7e46aa0ae633ac4c0fffda20fcbc2f6c84c63`。审计完成时 16 个源码与 161 个内容文件 hash 均符合协议。

后置词法修复允许完整中文邻接数字、符号和科学记数，同时过滤 ID/日期；负责人使用独立手工用例验证，未以封存数据调参。修复后的生产代码不再匹配旧 protocol，因此旧 audit 命令在当前新源码工作树中将正确拒绝运行，不能把这个冻结保护误解为原 artifact 损坏。要重复旧契约核验，应先恢复上述原 runtime 与 protocol 对应实验源码；复核分数仍使用保留原结果，不能使用新验证器重评分旧 sealed。后置版本信息单独保存在 post_pilot_runtime_change.json，不覆写 protocol/results/summary/post_execution_audit。

## 重复执行（须先恢复对应冻结源码）

```bash
uv sync --frozen
# 在环境中设置 BATTERY_LLM_API_KEY、BASE_URL、MODEL、PROXY。
BATTERY_LLM_THINKING=disabled uv run python -m tools.content.experiment \
  --out battery_platform/reports/v2_agent/preregistered_pilot_v2 \
  --prior-run battery_platform/reports/v2_agent/preregistered_pilot_v1 \
  --max-calls 200 --max-tokens 2000000 --workers 4
uv run python -m tools.content.audit_experiment \
  --out battery_platform/reports/v2_agent/preregistered_pilot_v2
uv run python -m pytest tests/content -q
```

目录已存在且非空时命令拒绝覆盖；另选新的目录重新登记。上面 shell 未包含任何 Key。协议/budget/cancel/filter/rebase/累计成本/内容字节冻结的十项独立测试通过，内容测试合计 92 passed（8.11s）；测试中的受控 transport 失败仅验证预算程序，不作为实测 LLM 或 benchmark 数据。

## 评分与限制

质量分是预登记的程序指标：0.4 初始状态符合 + 0.3 可见引用完整 + 0.2 合适首项检查/拒判 + 0.1/(1+检查数)。云端 JSON/严格报告失败记 0；候选 schema/权限失败同样拒绝。每根只统计一次初始报告，检查轮次不充作独立样本。错误引用、检查数、漏报/误报、越权、无依据确认分别保存，而非仅交一个总分。

这只是 12 桶代表性小试验；不能证明统计显著泛化、真实设备准确性或自进化必然优于静态基线。信号/标签为粗粒度项目配置，自由反馈为合成。程序无法判断的根因和检查专业合理性仍需独立盲审，状态 pending。静态报告保守地拒判也可能获得高程序分，因此高分不能当最终确诊准确率。所有失败、无更新和回退保留，不只报告最好批次。

提交由总负责人统一记录，本文负责详细命令、协议、真实调用和限制，不单独执行 Git commit。

## 本部分交付与提交范围

新增 tools/content/experiment.py（真实云端受限实验）、tools/content/audit_experiment.py（封存结束后只读核验）、tests/content/test_experiment_protocol.py（十项控制回归）、本文，以及 battery_platform/reports/v2_agent/preregistered_pilot_v1/ 与 preregistered_pilot_v2/ 下 protocol/context/batch/report/summary/ledger/final-answer/audit artifact。输出 V1 cancelled/V2 completed 均原样保留。提交排除本地 CANCEL 标记、任何 runtime lock、临时凭据和内部 reasoning；没有修改 app/agent 或主动检查代码。只读审计不会修改 context 或原 sealed 评分，总负责人统一 commit。
