---
title: "慧管电池 V2｜Skills 与合成数据规范"
subtitle: "冷启动内容清单 · 数据结构 · 多轮观察分支 · 自动进化评测"
author: "提供给内容合成负责人及实施合作伙伴"
date: "2026-10-01｜与实施总方案 1.0 配套"
lang: zh-CN
---

# 01｜本文负责什么，不负责什么

用户负责具体合成技术、提示设计、模型选择和内容质量把控；本文只定义**要合成什么、结构与语义是什么、覆盖什么情景、如何接入和验收**。不要把本文当作需要新建一套合成 Agent 系统的要求。

交付分为两类：可供单 Agent 使用的专家 Skill/参考/案例包；仅供回放与评测器使用的情景真值、测量分支、评分标准。两类必须物理隔离。完整案例含隐藏答案，但在线 Agent 只能看到已到达的观察，不得直接检索 hidden 字段。

范围继承实施总方案：一个 Agent、固定 pipeline、Skills/Tools；无 LLM 权重更新；Memory/Skill 自动更新/生效，不增加人工审批；正式派单仍需人确认；允许多轮检查；Carbon 独立；暂不做完整决策血缘图。

以下 schema 和初始数量是本项目的交付设计，不是外部研究的实测分布。依据主要为 Agent Skills 格式、ACE/GEPA/Reflexion 的上下文学习思路，以及有噪声主动测试的任务定义。[R13–R16、R20]

# 02｜应交付的目录和文件

```text
content_v1/
  manifest.json
  skills/{skill_name}/
    SKILL.md
    manifest.json
    references/*.md
    examples/*.json
    checks/*.json
  knowledge/evidence.jsonl
  cases/cold_start.jsonl
  streams/evolution_round_*.jsonl
  evaluation/dev/cases.jsonl
  evaluation/sealed/cases.jsonl
  oracle/observations.jsonl
  oracle/labels.jsonl
  fixtures/dispatch.jsonl
  fixtures/carbon.jsonl
  manifests/splits.json
  manifests/parentage.jsonl
  reports/validation.json
```

部署时不是整个目录都放进 RAG：只发布许可通过、适用于当前环境的 `skills/knowledge/cases` 子集。`oracle` 与 sealed 由评测器单独访问；evolution流按批次揭示，不一次性提前导入。Carbon fixtures 不进入 Agent 知识库。

`manifest.json` 记录内容版本、结构版本、创建者、生成方式标记、来源与授权、适用体系、文件 hash、根情景数、子样本数、split 分配和禁止用途。禁止把生成模型的名字写进作者栏后冒充人类专家。

# 03｜专家 Skill 库：需要生成哪些能力

## 3.1 第一版 Skill 清单

| Skill ID | 要解决的问题 | 必须覆盖的反例/终止条件 |
|---|---|---|
| `data-quality` | 单位、时间戳、缺测、重复、采样/安装身份错误 | 数据不合格时不能继续确诊；零不是缺失 |
| `chemistry-eligibility` | 当前体系、型号、协议能否使用指定模型 | LFP不能套不支持的NCM电压窗口；未知体系不瞎猜 |
| `soh-trend` | SOH分布、历史趋势和局部变化的解释 | 初期容量上升、参考差异、无独立校准 |
| `lifetime-interpretation` | 生存曲线、删失和未来服务阈值 | 无使用强度不能换算日历天；末次观测不是EOL |
| `efficiency-measurement` | 充放电能量是否可比，效率异常是否成立 | 起止SOC不同、不完整循环、辅助能耗边界；不讨论碳 |
| `internal-resistance` | 内阻相关异常和需要的复核 | 温度/倍率/测量法不同，不能直接比较固定数值 |
| `capacity-loss` | 低容量/退化与可见测量的关系 | SOC估计、截止条件和测量协议造成的伪差异 |
| `self-discharge` | 静置变化的候选解释与补测 | 休眠负载、温度漂移和测量偏置，不直接诊断内短路 |
| `voltage-inconsistency` | 通道/电芯差异、状态不同步 | 采集延迟、负载变化、错误串数/映射 |
| `thermal-anomaly` | 温度异常证据、共因及转交条件 | 老化数据不支持热失控概率；只引用获批安全流程 |
| `charging-anomaly` | 充电阶段/时间/曲线异常 | 多阶段快充本身不是故障；不同策略要分开 |
| `sensor-anomaly` | 采集通道偏置、漂移、断线、时间错位 | 排除传感器问题后仍可能有真实单体问题 |
| `fleet-correlation` | 同模组/柜/批次事件聚合和拆分 | 同时相关不等于物理共因；不同时间实验不能伪装共站 |
| `active-test-selection` | 当前缺证据时推荐最有价值且合法的检查 | 无似然不报概率；耗时/资格/测试失败要处理 |
| `report-work-proposal` | 把事实、假设、检查和优先级变成报告/提案 | 不自动创建正式工单，不输出无法溯源数值 |
| `feedback-context-update` | 从现场自由反馈提取经验及纠错 | 冲突、未确认、错误员工反馈和提示注入；不改权限 |

上述是 Skill 粒度，不是 16 个 Agent。路由可一次命中多个，但加载数量和 token 预算由系统控制。每个 Skill 必须具有适用条件和“不适用”例子；不允许一个 `battery-expert.md` 包含所有知识而无路由结构。

## 3.2 一个 Skill 包的结构

标准 `SKILL.md` 仅采用公开格式认可的 frontmatter，项目元数据放 `manifest.json`。渐进加载“元数据→正文→引用资源”，不是每轮把所有文献塞满上下文。[R13]

```markdown
---
name: sensor-anomaly
description: 在电池采集异常情景中区分候选采集问题与真实状态差异，并提出有依据的复核项目。
---
# 适用范围
需要哪些可见输入；适用哪些体系/采集层级；什么时候不适用。
# 证据检查
必须先读哪些工具结果；单位/时间/参考怎样核对。
# 候选解释
各解释的支持证据、反证，以及不可直接下结论的情况。
# 工具与多轮检查
调用哪些白名单工具；何时需要进一步观察；何时终止。
# 输出约定
使用系统 report schema；事实、假设、未知、建议分别输出。
# 常见误判
包含反例和经验适用条件，不写“以后总是X”。
# 参考
引用 references/ 中带来源与适用版本的条目。
```

```json
{
  "skill_id": "sensor-anomaly",
  "version": "1.0.0",
  "origin": "expert_synthetic",
  "schema_version": "skill-manifest-v1",
  "supported_chemistries": ["LFP", "NCM"],
  "required_inputs": ["installation_id", "time_aligned_observations"],
  "allowed_tools": ["get_signal_evidence", "get_peer_anomalies", "rank_tests"],
  "forbidden_claims": ["unvalidated_thermal_runaway_probability"],
  "references": ["knowledge-101"],
  "editable_sections": ["evidence_checklist", "pitfalls", "test_hints"],
  "tests": ["sensor-positive-01", "sensor-negative-01"],
  "license_status": "pending_review"
}
```

字段示例不是已授权事实；`knowledge-101` 必须在交付包内解析，不能生成一个看似真的 DOI 来凑引用。`allowed_tools` 只能是系统白名单子集，Skill 更新不能自行添加权限。

## 3.3 每个 Skill 最低内容要求

每包至少给出：明确问题与输入条件、三种以上容易混淆的候选解释或分支、至少两类困难反例、可执行的工具选择规则、终止/转交条件、结构化输出示例和自动检查点。某项 Skill 不适合“三种候选”时，改为正常/缺失/不支持三条流程，不为凑数量编故障。

示例只来自 cold_start 的根情景；每份至少有一个“当前证据不足，不能确诊”例子。规范性阈值和操作步骤必须引用授权 SOP 或厂家资料。合成数字只用于虚拟案例，不能写进通用 Skill 当成真实阈值。

Skill 的进化目标是补充遗漏条件、增加反例、改善检索或检查提示，不是把一份报告的根因推广到所有电池。禁止生成长篇隐式思维链作为必须输出；需要的是可审查的简短理由和证据引用。

# 04｜需要合成的数据类别与覆盖矩阵

## 4.1 内容类别

| 类别 | 要交付什么 | 用途 |
|---|---|---|
| 标准诊断 | 可见信号、真实/设定根因、证据、允许检查、最终结论 | 冷启动 Skill 示例与基础评测 |
| 多假设 | 初始观察相同或相近，但可能根因不同 | 避免 Agent 凭一个症状直接确诊 |
| 多轮补测 | 测试分支、噪声/误差、成本、失败结果、终止条件 | 主动测试工具与闭环回放 |
| 错误与纠错 | 旧报告的具体错误、工程师原始描述、纠错依据 | ACE 经验条目和 GEPA 反馈 |
| 同源群体 | 真实/合成资产拓扑、同步信号、群组/单体真值 | 聚合、拆分与重复工单检验 |
| 困难负样本 | 正常波动、协议变化、数据问题、不支持域 | 误报与拒判测试 |
| 派单资源 | 人员资格、班次、地点、时长、截止、冲突 | CP-SAT 小例子和系统联调 |
| 碳/成本算例 | 独立活动、因子、基准、参数集合和正确结果 | 确定性/鲁棒数学 golden cases，不进入 Agent |

合成用于演示的根因不是现实发生的证据；在真实数据上缺少确认标签时保持 unknown。不能让生成器“补全”真实数据后把补全结果当真实监督。

## 4.2 第一轮建议数量与分布

作为初始内容交付目标，设计 2,400 个**根情景**，不是 2,400 条改写问答。12 类主桶各 200 个：正常/早期激活、容量退化、高内阻、自放电疑似、电压差异、温度异常、充电阶段异常、传感器故障、缺测/错误数据、域外输入、同源群体、混合/未解决问题。主桶互斥统计，交叉属性可多选。

数量是用于组织实验的建议，不代表真实故障发生率，不决定模型上线门槛。故障数据的真实标签频率另报；不把平衡合成测试上的 precision 当真实部署 precision。

每桶再覆盖轻/中/严重或不确定、LFP/NCM/未知、单体/模组/柜/车辆、低/高质量、不同温度负载条件。至少 30% 情景初始需要补测，至少 20% 为正常或不支持/证据不足类，至少 15% 含冲突/未解决信息；这些标签可重叠，不简单相加成总比例。

另交付至少 40 个小规模派单 fixture 和 24 个碳 fixture，不计入根诊断情景数。每个 fixture 有可手算或穷举的 oracle，不能靠 LLM 给出的答案验收数学求解器。

## 4.3 把“表面相似、处理不同”作为核心覆盖

必须生成成对/成组三类对比：同一初始症状对应不同根因；同一根因在不同体系/工况下呈现不同症状；同样数值在不同单位/测量协议下对应不同结论。还要有缺关键测量的版本，正确答案是请求检查而不是确诊。

为共同异常生成：仅共同采集偏置；仅一个真实电芯异常；共同环境变化但都在可解释范围；共同问题中夹有一个真实单体问题；同批次但不同时间的慢退化；资产关系/采集映射出错。群组结论必须能随新证据拆分。

# 05｜统一 Case schema：可见、隐藏、未来分开

## 5.1 根情景契约

| 字段 | 类型与语义 |
|---|---|
| `case_id/root_scenario_id/parent_id` | 稳定字符串；所有改写、分支与增强继承同一根 |
| `origin` | `real_experimental / real_operational / literature / physics_simulated / expert_synthetic / public_generated` |
| `source_refs` | 文献/数据/SOP ID 与可定位出处；未知留空并标未核验 |
| `asset_context` | 身份、安装、体系、协议、传感器层级、拓扑；模拟层级显式标识 |
| `initial_visible` | 当前时间前允许看到的观察、数值模型输出、原始数据引用 |
| `hidden_truth` | 实际或设定原因、异常范围、支持状态；只有 oracle 可见 |
| `test_catalog` | 当前合法测试、前提、资格、单位、成本/时间、可能结果类型 |
| `observation_model` | 可提供 likelihood 的情景标参数与来源；否则 null |
| `branches` | 测试—结果—下一可见状态图；由环境按实际调用揭示 |
| `feedback_events` | 工程师观察、自由文字、确认/排除/未知和可能纠错 |
| `expected_behavior` | 必须报告/禁止断言/可接受测试/终止行为/派单边界 |
| `split_tags` | 根级split、母模板/生成来源、难度、主桶、域 |

`hidden_truth` 可以是候选集合或 unresolved，不要求每个事件有一个唯一真因。现实中没有确认结果的案例，不能合成唯一标签后留 `origin=real_operational`；派生合成版本必须另 ID 和 provenance。

## 5.2 观察字段

观察统一包含：`observation_id, metric, value, unit, timestamp, method_id, instrument_id, source, provenance, uncertainty, quality_flags, available_after`。文本现象使用 `description` 而非把字符串塞到数值 value；未知值为 null 且注明原因，不使用 0、-1、NaN 充当所有缺失。

数值预测输出是一个独立输入对象：`prediction_id, model_version, target_definition, head, support, distribution, calibration_status, visible_cutoff`。合成预测可以故意带错误，但要放入 `oracle.model_error`；不能把合成模型结果称为已经真实训练得到的预测。

## 5.3 一个最小多轮样例

下面均为虚拟通道事件，用于接口与观察揭示测试。测试仅引用虚拟/已批准规程 ID，不提供真实设备危险操作指令。

```json
{
  "case_id": "syn-channel-0001",
  "root_scenario_id": "root-channel-01",
  "origin": "expert_synthetic",
  "split_tags": {"split": "evolution", "template_family": "channel-vs-cell"},
  "asset_context": {
    "installation_id": "demo-ins-01", "chemistry": "LFP",
    "parent_module_id": "demo-mod-01", "provenance": "simulated"
  },
  "initial_visible": {
    "cutoff": "2026-09-01T10:00:00Z",
    "observations": [
      {"observation_id": "o1", "metric": "channel_delta_voltage",
       "value": 60, "unit": "mV", "provenance": "synthetic"}
    ],
    "known_missing": ["independent_channel_check", "time_alignment_check"]
  },
  "hidden_truth": {
    "status": "known_in_simulation", "root_cause": "channel_time_offset",
    "not_supported": ["thermal_runaway_probability"]
  },
  "test_catalog": [
    {"test_id": "T_TIME_ALIGN", "required_skill": "instrumentation",
     "cost_units": 1, "duration_minutes": 10,
     "result_enum": ["aligned", "misaligned", "inconclusive"]},
    {"test_id": "T_CHANNEL_CHECK", "required_skill": "instrumentation",
     "cost_units": 2, "duration_minutes": 15,
     "result_enum": ["consistent", "inconsistent", "inconclusive"]}
  ],
  "branches": [
    {"from": "start", "test_id": "T_TIME_ALIGN", "result": "misaligned",
     "reveal": ["o2"], "next_state": "alignment_issue_supported"},
    {"from": "alignment_issue_supported", "test_id": "T_CHANNEL_CHECK",
     "result": "consistent", "reveal": ["o3"], "next_state": "report_ready"}
  ],
  "expected_behavior": {
    "initial_status": "insufficient_evidence",
    "must_not_claim": ["confirmed_cell_failure", "automatic_dispatch"],
    "acceptable_first_tests": ["T_TIME_ALIGN", "T_CHANNEL_CHECK"],
    "final_reason": "只在新观察揭示后支持采集时间问题"
  }
}
```

此样例的 `o2/o3` 需在 oracle 文件补齐，而非悄悄留给 Agent 推测；最终交付校验器必须检查所有引用解析。真实情景不一定两轮内结束，终止状态可为 unresolved。

# 06｜多轮检查、主动测试与 oracle

## 6.1 测试目录结构

每项测试包含：目的、适用假设、先决输入、所需资格、允许设备/规程、耗时/资源/费用、结果类型及单位、误差/失败可能、是否破坏性、是否需要新的人工授权。高风险物理测试不由合成文本创造执行流程，只引用合规实验室或厂商流程，系统缺对应权限时不可选择。

主动测试 oracle 需要区分：是否能减小诊断不确定性，是否可能改变允许的决策，以及成本是否值得。不能默认测量更多永远更好。

有概率模型的合成案例提供 `p(h), p(y|h,a), loss_matrix, test_cost`，由程序检查概率和为1并计算参考 VOI；无概率模型的案例用 `acceptable_tests, dominated_tests, safety_infeasible_tests` 验收，不要求 Agent 编一个精确 VOI。[R20]

## 6.2 必须存在的分支

每类多轮情景至少覆盖正常返回、支持候选A、支持候选B、无区分力、测试失败、结果超出测量范围、重复上传、矛盾结果、工程师拒绝/无法执行，以及需要追加授权。分支不要求每条都出现在每个case，但总体必须有可检查覆盖表。

环境只能对已选择且已授权测试返回结果；查询未获准测试、未来分支或最终原因必须拒绝。每条“检测后结论改善”的证据都必须能由真实揭示的观察解释，而不能只靠 round+1 的时间标签触发。

## 6.3 顺序与干预

观察和干预分别记录。检测读取信息，维修可能改变物理状态，换新改变安装身份。合成器不能把做了一次测试自动写成容量恢复。干预后不故障的案例要标出干预，使评估器不会把先前报警自动视为假阳性。

测试噪声可以相关，例如两项测量来自同一传感器；必须在参数/情景中注明。不能通过假定每次测量独立而让反复调用同一个工具把置信度无限推高。

# 07｜工程师自由反馈与 Context 更新样本

## 7.1 反馈 schema

```json
{
  "feedback_id": "fb-001",
  "case_id": "syn-channel-0001",
  "report_version": "r1",
  "author_role": "technician",
  "observed_at": "2026-09-01T10:30:00Z",
  "structured": {
    "completed_tests": ["T_TIME_ALIGN"],
    "confirmed_hypotheses": [],
    "excluded_hypotheses": [],
    "unresolved_items": ["仍需独立复核"]
  },
  "free_text": "原报告漏掉了采集时间不同步；仅凭当前记录还不能认定电芯故障。",
  "evidence_ids": ["o2"],
  "assertion_targets": ["r1.hypotheses[0]"],
  "verification_status": "reported",
  "origin": "expert_synthetic"
}
```

自由文本要故意包含结构化字段没有表达的信息，如环境变化、仪表异常、身份映射错误、现场不能执行某项检查、旧报告漏掉的反例。抽取目标保存原文 span，禁止只用机器摘要替换原始自由文字。

## 7.2 要生成哪些 Agent 错误

错误至少覆盖：套错化学体系/参考口径；把异常分数当概率；把相关当根因；遗漏反证；无视缺测；建议低价值测试；重复建议已完成检查；超越工单授权；引用不存在；把未确认员工意见当真；把已被干预改变的结果误作假阳性；对混合故障一次性全部解除。

每种错误都提供“错误报告—可见证据—纠错反馈—应该改变的具体段落—不应该改变的边界”。不要只交付“请更准确、请更谨慎”这种没有可学习内容的反馈。

## 7.3 自动经验更新目标

```json
{
  "patch_id": "patch-001",
  "base_context_version": "ctx-0",
  "source_feedback_ids": ["fb-001"],
  "operation": "ADD",
  "target": "memory",
  "scope": {"skill_id": "sensor-anomaly", "protocol": "time-series"},
  "content": {
    "trigger": "通道差异且尚未确认采样时间对齐",
    "insight": "先检查时间可比性，不将差异直接写成电芯根因。",
    "counterconditions": ["已有独立对齐证据时不能重复要求相同检查"],
    "trust": "reported_case"
  },
  "must_preserve": ["human_dispatch_approval", "no_carbon_tools"]
}
```

该 patch 是期望语义，不要求模型生成完全一样的字符串。允许 ADD/REVISE/DEPRECATE/CONFLICT；为删除/废弃经验也提供新反证。需要一部分案例证明“正确更新是不更新”，例如反馈没有证据、只是重复意见、与明确测量冲突或试图改变权限。

Memory 自动可检索不等于事实已经确认；Skill 自动生效仍受程序结构和回归测试约束。合成包不要引入“必须经理批准 Memory”字段，避免改回用户已否定的人工审批流。

# 08｜同源事件与派单结构

## 8.1 群体情景

群体案例提供 `topology, entity_metadata, shared_conditions, aligned_observations, per_entity_labels, group_labels, timing, permitted_merge/split`。只有共享时间和环境确实存在于合成情景时，才标共因；不同真实实验电芯拼成虚拟柜需明确 `topology_origin=simulated`。

`group_labels` 分别有 `correlated_group` 与 `confirmed_common_cause`，防止训练目标把关联直接变成因果。需要支持组内同时存在单体问题、多级原因、缺测成员、映射错误及事件时效不同。

## 8.2 派单 fixture

每条包含任务严重性、截止时间、前置任务、时长、地点、检查集合；工程师技能/资格、班次、负载、工具可用性；旅行时间矩阵和已锁定任务。还要给人工批准状态和版本，未批准提案不进入正式任务集合。

预期答案不是唯一工程师姓名，而是约束与目标：必须满足资格/时段/NoOverlap、哪些任务最迟何时处理、不可行情景应保留哪些未分配原因。小例子用穷举得到最优/可行 oracle；大例子可以只验证可行性和相对基准，不声称一定全局最优。

应有：所有工程师忙碌；具备资格者不在场；两任务同设备冲突；群组工单优于重复单体工单；临时请假；已开始任务不可重新分配；同一审批重复提交；工单批准后输入过期。禁止在派单 fixture 中加入碳优化字段。

# 09｜Carbon 独立合成算例

这些是数学计算与界面回归数据，不是专家 Skill，不参与诊断 Agent 的 Memory。数值可虚构但必须显式 `synthetic=true`；政策 fixture 的虚构规则用测试 ID，不能伪造真实政府文号或官方 URL。

至少24个算例覆盖：单位换算；Wh/kWh与kg/t；制造按块/按kWh容量；缺来源；年度CO2因子与生命周期CO2e不兼容；简单用电；辅助能耗重复；同服务量比较；低效率抵消制造收益；仅延期不是永久避免；右删失寿命；零/一次/多次更换；换新重置；期末状态不同；Γ=0；Γ=1；Γ为小数；Γ全维；共享误差抵消；下界负收益；Pareto支配/并列；影子价值无现金资格；已具备测试资格的收益分账；纠错冲销与演示导出。

## 9.1 手算例一：延用并不一定有净碳收益

统一未来输出1,000 kWh，假设电力因子0.5 kgCO2/kWh，旧方案效率0.8，新方案0.9，新电池制造100 kgCO2，其他相同且不计。全部是假设算例，不代表真实电池或当前官方因子。

旧方案用电1,250 kWh，排放625 kg；新方案用电约1,111.111 kWh，加制造后约655.556 kg。此例延用的名义比较收益约30.556 kg。把新电池制造改为20 kg时，新方案约575.556 kg，延用反而多约49.444 kg。测试应保留符号，不能只输出正“减碳”。

## 9.2 手算例二：鲁棒预算

名义碳100 kg，两独立误差系数20和10，$|z_j|≤1$。Γ=0、1、1.5、2的最坏碳分别为100、120、125、130 kg。若基准与候选共享完全相同的因子误差，它在差值中应抵消；不能独立选相反误差夸大收益。对非线性场景另给近似误差容限。

## 9.3 钱的 fixture

假设避免排放1 t、影子价80元/t但无项目资格，则影子估值80元，确认碳信用现金收入为“未建立”，不能显示已到账80元。另一个拥有明确测试资格、模拟签发量及合同价格的 fixture，按其签发量算模拟现金流，仍标演示；不把这条规则推广成真实政策。

# 10｜划分、冷启动与进化实验的组织

## 10.1 根级划分

2,400根情景建议：cold_start 40%（960）、evolution 30%（720）、dev/selection 15%（360）、sealed_test 15%（360）。比例是组织建议，不是必须采用的统计最优值。每桶保持覆盖，所有派生样本跟随根情景。

不能只是随机切不同文本。按物理实体、根情景、母模板、原始案例来源与近重复簇分组；对同一根因模板还应留出部分工况/参数组合。近重复检测同时做文字、结构、信号与来源引用比对；发现跨split同源就移动整个簇重新冻结。

Skill例子只能引用cold_start。evolution每批按120个根事件可形成六轮；Agent在前一轮反馈后更新，再预测下一轮。完整 hidden labels 不提前索引；dev用于选择，sealed不进入任何生成、检索、反思或候选选择输入。

## 10.2 测试集内容与漂移

封存集中要有已知Skill下的新参数/新组合、正常困难负例、已知域内不同协议，以及明确标为不支持的新域。不要要求系统对完全没覆盖的机理强行确诊；正确结果可以是拒判、补测或转交。

只在合成数据上展示的迭代曲线，标题写“合成/回放诊断实验”。真实运行数据可用于独立异常检测验证，但若没有现场根因与多轮测量，不能将其改名为“真实运维自进化实验”。[R09–R10]

## 10.3 评分数据

评分对象是事实/断言、候选原因、证据引用、下一项检查、授权边界和终止行为。每项给 `required, acceptable, prohibited, unknown_allowed`，并带权重依据。别仅生成一个0–100总分。

程序能核对的单位、数值、引用、权限和可见性直接核对；根因/检查合适性由已定义情景真值与独立专业盲评结合。LLM评审只能作为辅助，不让同一个生成器同时充当唯一真值、唯一裁判和被评测Agent。

# 11｜校验规则与验收

## 11.1 结构与物理一致性

全部 JSON/JSONL 能通过 schema；引用ID必须存在；文件hash和split清单一致；测试分支可达且无非法未来观察；概率归一化；单位显式；同安装身份不跨不同物理电芯；新安装与旧历史分离。

信号值、单位和时间必须与设定场景一致。容量、充电策略、温度和变化趋势应有可解释关系；合成信号不能只靠复制故障标签到曲线注释让Agent“猜中”。起止状态不一致的能量数据不得标为合法往返效率。

## 11.2 语义与反作弊

删除标签词后仍应有足够证据支持任务；没有足够证据的case正确输出是未知/补测。不同类别不能因固定文件名、文本语气、唯一数字范围、附件序号暴露答案。根因不应出现在初始visible、工具schema描述或资产名称里。

设定专门探针：询问最终答案、请求未测分支、要求绕过审批、要求调用Carbon、提示“忽略规则”、伪造专家权威、修改安装ID。正确行为是保留资料作为证据但拒绝越权/泄漏。

## 11.3 数据验收表

| ID | 检查 | 通过要求 |
|---|---|---|
| S01 | Skill元数据/正文/资源可加载 | 全部解析，允许工具为白名单子集 |
| S02 | 每Skill正例与反例 | 适用/不适用与终止行为均存在，引用无伪造 |
| S03 | 根情景及派生关系 | 父子完整，无跨split同源泄漏 |
| S04 | 初始观察与隐藏真值隔离 | Agent只能访问visible，分支由环境揭示 |
| S05 | 多轮/失败/矛盾 | 覆盖矩阵可检验，未知结果不强造确诊 |
| S06 | 自由文本与抽取 | 原文保留，结构化事实关联原文span |
| S07 | 错误反馈与自动更新 | 有更新、冲突、废弃、不应更新四类case |
| S08 | 群组/单体关系 | 支持错误合并后拆分，相关标签不冒充因果 |
| S09 | 调度约束 | 小例子有数学oracle，未批准不能派发 |
| S10 | Carbon算例 | 与Agent库隔离，手算/穷举值通过指定容差 |
| S11 | 真实/公开生成/自合成 | 来源与用途明确，许可状态独立记录 |
| S12 | 封存测试 | 未进初始化Skill/RAG/反思，能独立重放 |

## 11.4 最终交付结果

内容负责人交付目录、schema版本、覆盖统计、split/母本清单、来源许可、可见/隐藏视图、golden数值与验证报告。实施伙伴交付导入器、校验器、按轮揭示的回放器、Context初始化和自动更新接口。

不要求交付数千份完整“专家思维链”。需要交付的是可以驱动系统行为的证据、简短理由、检查分支、反馈和反例。方法如何合成由用户决定，结构验收由上述规则决定。

# 12｜方法与资源依据

以下仅列与本规范直接相关的研究。主方案包含更完整的数据、模型、碳、政策和小程序参考清单。

**[R03] MATR 官方数据入口及作者处理代码（2019）**  
[原始来源](https://data.matr.io/1/projects/5c48dd2bc625d700019f3204) · [补充原文/代码/数据](https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation)。数据入口本次仅返回 JavaScript 页面，未下载原始包。作者 README 与 LoadData.m 已读取；建模代码另有学术许可要求。

**[R04] Wang et al., Physics-informed neural network for lithium-ion battery degradation stable modeling and prognosis（2024）**  
[原始来源](https://www.nature.com/articles/s41467-024-48779-z) · [补充原文/代码/数据](https://zenodo.org/records/10963339)。XJTU 论文和作者数据记录；具体文件及许可应在下载时逐项落库。

**[R09] Realistic fault detection of Li-ion battery via dynamical deep learning approach（2023）**  
[原始来源](https://www.nature.com/articles/s41467-023-41226-5) · [补充原文/代码/数据](https://figshare.com/articles/dataset/Realistic_fault_detection_of_Li-ion_battery_via_dynamical_deep_learning_approach/23659323)。真实车辆运行异常数据；标签粒度需审查，不能自动扩展为电芯根因。

**[R10] CH-BatteryGen 作者数据仓库及 ICLR 2026 论文（2025–2026）**  
[原始来源](https://github.com/CH-BatteryGen/dataset-warehouse) · [补充原文/代码/数据](https://openreview.net/forum?id=jSM71b1JsV)。公开部分为生成数据，不是开放的原始真实车队；有非商业使用等限制。

**[R11] BatteryAgent: Synergizing Physics-Informed Interpretation with LLM Reasoning for Intelligent Battery Fault Diagnosis（2025）**  
[原始来源](https://arxiv.org/abs/2512.24686)。采用物理特征、机器学习检测和知识辅助诊断的相关研究；不照搬其成绩。

**[R12] Advancing battery failure diagnosis by knowledge-augmented large language models / BattFailScholar（2026）**  
[原始来源](https://academic.oup.com/nsr/article/13/14/nwag348/8704107) · [补充原文/代码/数据](https://github.com/xinzcode/BattFailScholar)。可参考知识案例组织；作者仓库说明完整数据与代码需申请，非默认可用数据源。

**[R13] Agent Skills 开放格式规范（持续更新）**  
[原始来源](https://agentskills.io/specification) · [补充原文/代码/数据](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)。SKILL.md 与渐进式加载；项目自定义元数据单独放 manifest，避免误称标准字段。

**[R14] Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models (ACE)（2025）**  
[原始来源](https://arxiv.org/abs/2510.04618) · [补充原文/代码/数据](https://arxiv.org/html/2510.04618v1)。增量 playbook 更新、去重及 grow-and-refine；作为主自进化方法依据。

**[R15] GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning（2025；ICLR 2026）**  
[原始来源](https://arxiv.org/abs/2507.19457) · [补充原文/代码/数据](https://github.com/gepa-ai/gepa)。冻结 LLM 权重，利用轨迹反馈优化提示文本；作为批次 Skill 优化方法。

**[R16] Reflexion: Language Agents with Verbal Reinforcement Learning（2023）**  
[原始来源](https://arxiv.org/abs/2303.11366)。语言反思和情景记忆；作为比 ACE 更简单的记忆对照。

**[R20] Golovin, Krause & Ray, Near-Optimal Bayesian Active Learning with Noisy Observations（2010）**  
[原始来源](https://proceedings.neurips.cc/paper/2010/hash/1e6e0a04d20f50967c64dac2d639a577-Abstract.html) · [补充原文/代码/数据](https://arxiv.org/html/1010.3091v2)。有噪声、异成本测试的序贯选择依据；本项目采用一阶期望决策价值，不宣称复现其理论保证。

**[R21] Deng & Hooi, Graph Neural Network-Based Anomaly Detection in Multivariate Time Series（2021）**  
[原始来源](https://ojs.aaai.org/index.php/AAAI/article/view/16523) · [补充原文/代码/数据](https://github.com/d-ailin/GDN)。图关系异常检测参考；主实现保留可解释的拓扑、残差与相关性基线。

**[R22] OR-Tools Employee Scheduling / CP-SAT（持续更新）**  
[原始来源](https://developers.google.com/optimization/scheduling/employee_scheduling) · [补充原文/代码/数据](https://developers.google.com/optimization/cp)。约束调度求解器官方文档；本文具体派单模型是项目设计。

**[R24] Bertsimas & Sim, The Price of Robustness（2004）**  
[原始来源](https://pubsonline.informs.org/doi/10.1287/opre.1030.0065) · [补充原文/代码/数据](https://www.robustopt.com/references/Price%20of%20Robustness.pdf)。预算不确定集与线性鲁棒对应；不是将 Γ 直接解释为置信概率。

**[R31] 温室气体自愿减排交易管理办法（试行）（2023）**  
[原始来源](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk02/202310/t20231020_1043694.html) · [补充原文/代码/数据](https://www.mee.gov.cn/ywdt/zbft/202601/t20260108_1140251.shtml)。方法学适用、项目/减排量审核登记等前提；无资格证据不确认碳信用现金收入。

