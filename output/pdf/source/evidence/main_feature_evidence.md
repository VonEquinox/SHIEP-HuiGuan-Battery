# main → DEV 产品功能与工程证据

核对时间：2026-10-02（Asia/Shanghai）。本文件只读研究，由 PDF 内容协作 Agent 编写；没有运行服务、训练模型、调用云端或读取凭据。Git 比较基准为真实本地 `main=c4203014c4c6999c2d176b1402d596813a072f73`，当前 `DEV=0d9a53de2afaf062e4a2fa433dec97f759d56680`。`git diff main...HEAD`、`git show main:<path>` 与当前源码/实施记录交叉核对。下述“新增”指 main 中不存在，“增强”指 main 功能继续保留并追加能力。

## 1. 应写在 PDF 最前面的版本定位

main 已经是可用的 V1 健康与运维平台，而不是空工程：有 7 个工作区、五种角色、资产层级、XJTU 开发数据、冻结快速 ExtraTrees/完整混合模型、真实推理和训练、健康告警、持久化工单、维修附件、独立验收、任务队列、取消、审计、备份和恢复。

DEV 在这个基础上增加专业诊断与研究闭环：多来源数值研究、JSON+NPZ 安全模型包、多头预测及不支持状态、单个云端诊断 Agent、16 个 Skill、版本化 Memory、自动 Context 进化、群组风险、待审批提案、授权检查轮次、数学约束排程、独立碳与经济核算、原生微信 TEST 小程序，以及 F01–F07 一致性修复。

关键架构是“数值模型计算 + 云端 Agent 解释和补测提案 + 人批准 + CP-SAT 排程 + 人确认 + 现场反馈 + Context 文本进化”。Carbon 另走确定性结构化计算链。开发时使用多个协作 Agent，产品运行时仍为一个固定流程诊断 Agent。

### 版本规模（源码静态统计，不能代替质量分数）

| 指标 | main | DEV | 正确解释 |
| --- | ---: | ---: | --- |
| 一级侧栏工作区 | 7 | 11 | 原 7 区保留，新增风险与群组、诊断、Context 进化、碳与经济 4 区 |
| HTTP router 声明 | 56 | 119 | 9 个已 include 的 API 模块中 get/post/put/patch/delete 装饰器计数；新增 63 条，不是性能指标 |
| 原生微信页面 | 0 | 7 | 新 TEST 工程；尚无微信原生编译/真机证明 |
| 项目 Skill 包 | 0 | 16 | 合成授权内容，有 hash/来源/边界；不等于 16 项专家认证能力 |

API 声明计数依据：main 的 `app/api_core.py=21`、`api_data.py=18`、`api_ops.py=17`；DEV 原三模块计数相同，新增 `api_v2.py=11`、`api_agent.py=13`、`api_inspection.py=7`、`api_evolution.py=10`、`api_carbon.py=13`、`api_dispatch.py=9`。未把静态资源、SPA fallback 和 `/docs` 自动路由计入。

## 2. 总览与资产：在原资产底座上形成诊断入口

**main 用户看到什么。** 总览显示数据库派生的资产、数据覆盖、告警、工单、后台任务；资产按站点→柜→模组→电芯组织，可创建、编辑、退役、更换安装身份和绑定实验回放。原界面已经提供固定坐标示意和历史下钻，不能把这些列为 DEV 新建。

**DEV 增强。** 总览追加未确认提案、待测轮次、失败作业、不支持预测头及来源分类，卡片可跳转列表。资产详情显示当前安装身份、多头预测、充电片段、可见截止时间、输入来源与模型包；用户选择服务器安全包和对应开发源观察后可运行 V2 推理并进入诊断。切换包会清空旧观察行，包内明确没有观测时不回退使用 XJTU 行。

**为什么这样做。** 将“设备槽位”“实验电芯”“当前安装”“某时刻可见预测”分别标识，避免把实验室曲线显示成现场 BMS 或把更换前读数用于新电池判断。同一安装不能改绑另一物理对象；必须先登记更换或新建资产。

**可验证路径。** `GET /api/v2/overview`、`/assets/{id}/prediction-profile?cutoff`、`/model-packages`、`POST /assets/{id}/v2-binding`、`POST /model-runs`。真实浏览器链已验证包绑定→SOH 推理→保存诊断；实际图示的 SOH 95.32% 是某次开发观测预测，不是模型准确率。

**边界。** 虚拟资产保持 simulated，实验输入保持 experimental_replay；没有生产网关和设备控制。旧 main 的“更换生成新安装身份、清空绑定、保留历史”规则继续存在。

证据：main `battery_platform/README.md`、`frontend/src/pages/Foundation.tsx`；DEV `app/api_v2.py`、`frontend/src/pages/V2Foundation.tsx`、`frontend/e2e/v2.integration.spec.ts`。

## 3. 数据中心：从 XJTU 单来源回放到可追溯多来源研究

**main 已有。** 真实导入既有 XJTU 验证特征 2,058 行、21 个开发电芯；原三个保护电芯及 346 行不导入或评分。已有 71 维观测、来源/hash/质量、按电芯分页、CSV 导入导出和被引用版本不可删除。原冻结模型已见过这些开发电芯，因此含训练电芯的评估有明确标记。

**DEV 增强。** 增加 XJTU、MATR、DyAD、CH-BatteryGen 等来源登记、许可状态、解析回执、物理身份、化学体系、协议、域、split 和 hash。区分“刷新来源元数据”与“关联已登记本地数据”：元数据刷新不宣称已经下载全源；不具备许可/下载/资格的来源保持 metadata-only/blocked。已解析来源显示 raw_scope，不能把小样本解析当成全量。

**实现方法。** 数据源 registry 进入 `source_manifests`；特征视图有 schema、cutoff、split、physical_ids 与 manifest。运行时只使用白名单开发特征，不读取标签/final；来源作业在事务外获取元数据，完成时持久化回执。对象级切分与别名/重复簇隔离由数值研究管线负责。

**效果应该怎么写。** 可以写“取得并资格化了多来源研究输入，能追溯来源、身份和划分”，数据扩展倍数必须采用同一联合实验有效对象/行数，不能将 MATR 摘要、续测 MAT、CH 生成对象和 DyAD 车辆标签随意相加。本 PDF 的分数与扩展倍数应使用数值证据 Agent 提供的同一口径表。

证据：`app/api_v2.py`、`app/v2_jobs.py`、`model_lab/reports/v2/sources/DELIVERY.md`、`model_lab/reports/v2/sources/source_registry.yaml`、`docs/V2_RUNBOOK.md`。

## 4. 模型中心与健康预测：原 M0 保留，新增跨域模型与显式支持契约

**main 已有。** 快速 ExtraTrees 与完整混合模型分支可选择；平台能进行真实 ET 训练、按电芯验证、同样本评估对比、推理、队列/日志/取消/失败及版本血缘。其输入是当前/参考各 71 维和局部电量比，要求特定 3.7–4.1V 部分恒流窗口与初始参考，不是通用任意 BMS 表格。

**DEV 新增/增强。** M1/M2 研究训练、三种子、消融、校准、评测及安全导出；新增 XJTU+MATR 联合研究和 H-M1 结构优化。用户可以看到 SOH、寿命/生存、越阈、效率、故障等每个头的 target、unit、distribution、support、calibration、source 和 evidence。实际未支持的头保持 null/unsupported；不填零，不把 SOH 直接转成寿命或热失控概率。

**实现方法。** SafePackage 仅加载服务器白名单 JSON/NPZ，验证 hash、schema 和保存输出；NPZ 禁止 pickle。训练、校准、评测使用固定模块/服务端路径，不接受客户端任意 shell 或 pickle。所有数值作业共用单计算锁，事务外运行，取消、父进程退出、超时都会清理子进程。研究结果不自动替换当前生产注册模型。

**用户看得懂的分布呈现。** 有合法 lognormal/logit-normal 参数时显示密度，有物理时间轴和真实 survival 值时显示生存曲线；分位带明确是分位而非完整密度。样本不足/域未校准时 CQR 上下界 null，页面注明区间无界，不把 coverage=1 当作有效保证。经确认物理循环的来源才显示真实 cycle，其余仍是来源记录序号，均不伪装为 UTC 现场时间。

**最新 F01 安全增强。** 新 schema `battery_features_v2_channel_validity_1` 在序列中增加温度有效通道，真实 0°C 与缺温可区分；温度统计只用合格值；包加载拒绝新特征与旧权重混用。4,744 个准入 V/I/time 分段扫描中旧缺温触发为 0；在独立目录完成 H-M1/M1/M2 各三种子重训，历史结果未改。M2 在 XJTU 退化，必须在 PDF 中保留负结果。

**限制。** 高级头“已实现模型契约”不代表全部真实来源均已有有效标签。MATR 寿命研究只有有限 dev 电芯、右删失占多数，相关包 `validated_deployment=false`。H-M1 的开发成绩不能重新命名为 final 或生产效果，具体分数采用数值 Agent 的证据表。

证据：`model_lab/modeling/v2/`、`app/v2_jobs.py`、`v2_model_worker.py`、`frontend/src/pages/V2Foundation.tsx`、`battery_platform/docs/HM1_OPTIMIZATION_RESULTS_20261002.md`、`docs/V2_F01_F07_REPAIR_20261002.md`。

## 5. 风险与群组：将单体告警扩展到可拆分的共享异常分析

**main 已有。** 单电芯健康阈值、持续性/冷却/去重、告警确认/解除/重开和工单。没有 V2 incident group、数值残差同伴工具或群组拆分。

**DEV 新增。** 风险页按严重性选多个资产，发起共享风险分析；显示单体问题、数据质量、数值或拓扑关联、源观察版本、残差相关和未知原因。新证据支持拆组时以版本与说明拆为子组，原单体告警保留；旧群组提案和计算结果不能覆盖新结构。

**模型到底算什么。** 对有资格的同工况序列，以早期正常参考的 median/MAD 计算标准化残差，再按精确时间戳对齐计算邻接通道残差相关和异常重叠。至少 3 个早期参考点、3 个后续分析点；同指标/单位/方法、同体系/协议/负载/温度、同 cohort/拓扑、当前安装、有效仪器和校准、授权资格全部满足才计算。缺条件、常数 MAD、错位、冲突或不合格来源分别拒判。

**为什么建立这层。** 共享采集偏置、环境影响和真正单体退化可以产生近似告警；将来源问题、同步关联和单体复核分开，给 Agent 提供同伴证据，并支持后续拆组。输出始终 `causality=not_established`、`confirmed_common_cause=false`，数值相关不能自动确认共因。

**验收。** 真实 HTTP 工单观察已进入算法；合成数值夹具出现 MAD residual>3、rho=1、3 点对齐并保留源引用，来源变化使 CAS 拒绝旧结果。该夹具证明程序链，不是现场共因效果实验。实验室电芯回放不进入站内相关统计。

证据：`app/diagnosis/groups.py`、`group_adapter.py`、`app/api_agent.py`、`app/migrations/005_group_measurements.sql`、`tests/test_v2_group_numeric.py`、`frontend/src/pages/V2Diagnosis.tsx`。

## 6. 诊断 Agent：从数值结果跳到可追溯的候选、反证与补测

**main→DEV。** main 没有云端诊断执行器、Skill 路由、程序工具报告、候选反证或诊断会话。DEV 新增一个固定流程 Agent：采集→适用性→Skill 路由→候选分析→工具→严格报告→等待补测/结束，第二轮从重新评估开始。开发协作多 Agent 不等于产品多诊断 Agent。

**用户界面。** 诊断三栏左侧是本安装/截止时间可见片段与引用，中间显示候选、反证、未知与状态，右侧显示可建议/已授权补测。页面保留报告版本、实际 execution_mode、cloud_report_valid、工具轨迹、Token、失败原因、原始反馈及逐轮差异。没有 Key 时明确 rule_baseline，不用规则结果冒充云报告。

**方法与保护。** OpenAI 兼容服务端 `/chat/completions`，配置 URL/模型/代理和 Key；前端不接收 Key。固定十项工具可读取资产/证据/数值/同伴/授权知识/Skill/Memory、排序测试、提案和写报告；批准、派单、Carbon、任意 SQL/Shell/HTTP、设备控制没有工具权限。最多 12 工具调用，最多 4 Skill 正文，报告引用和数值由程序验证，未知假设概率默认 null。未来反馈、oracle、sealed、其他安装证据被隔离。

**主动检查。** 有可追溯先验、似然、loss matrix 与成本时计算 Bayes risk 和预期下降减成本；无完整模型时返回成本/时间修正规则排序，VOI=null。已经执行的测试不作为新的独立证据重复累加。资格、设备/SOP、破坏性授权、轮次和预算均过滤；首轮只建议待批准测试，不直接执行。可以合理终止于未解决/转交。

**证明到哪里。** 真实 DeepSeek HTTP→worker→cloud 报告→pending proposal 成功，批准前正式工单为 0。引用结构正确证明可追溯，不是专家语义正确或现场确诊准确率。准确率和自进化提升应另列同协议量化实验，不能用成功 smoke/Token 数作质量证明。

证据：`app/agent/executor.py`、`contracts.py`、`llm.py`、`tools.py`、`skills.py`、`app/diagnosis/active_tests.py`、`app/api_agent.py`、`docs/V2_AGENT_IMPLEMENTATION.md`、`reports/v2_integration/cloud_api.json`。

## 7. Skill 和回放内容：新增 16 个可路由专业包与受控评测环境

**main→DEV。** main 无 `content_v1/` 和专业 Skill 内容管线。DEV 交付 16 Skill、64 冷启动示例、2,400 根情景、31,200 授权观察分支、33,600 parentage 记录、17 条知识证据、40 派单/30 Carbon 数学 fixture、七类越权/泄漏探针及 JSON Schema/hash manifest。

**如何构造。** 12 主桶各 200 根，母模板组在生成前整体切分；cold_start/evolution/dev/sealed=960/720/360/360。程序生成冻结物理配置、身份/单位/缺失/时间、隐藏答案和分支；真实 DeepSeek 28 请求生成 16 包的 48 条条件/反例补充与 12 桶的 72 段反馈变体，总 45,408 token。LLM 提供语言补充，不充当唯一物理答案和裁判。

**如何使用。** 在线 store 只读已授权 Skill、知识和 cold_start 当前可见事实；按体系、症状和输入路由后读正文。oracle/未来分支由 evaluator-only 环境持有，先选合法已授权测试才揭示反馈；重复测试 `new_evidence=false`。通用 Skill 不能从 dev/sealed 标签生成。

**限制。** `approved_synthetic` 是项目合成/回放许可状态，非专家认证；没有独立专家盲审。2,400 根是合成场景覆盖，不是 2,400 个真实电池或真实事故。合成分布效果不能直接当现实部署 precision。

证据：`content_v1/manifests/`、`tools/content/`、`docs/V2_CONTENT_IMPLEMENTATION.md`、`docs/V2_SKILLS_DETAIL.md`、`docs/V2_FIXTURES_DETAIL.md`。

## 8. 提案审批与授权检查：在原正式工单链之前加入诊断闭环

**main 已有。** 告警幂等建单、调度人员资格与负载/距离推荐、维修接单/处理/证据/结果、另一身份验收/关闭/退回/重开/取消。关闭工单不把 SOH 改成 100%，不自动解除告警；这些保留。

**DEV 新增。** Agent 报告先形成 PENDING_APPROVAL 提案；调度员/管理员核对安装、群组、版本、测试、最低资格、时长、轮次、工具、期限等后批准才生成正式 V1 工单。多资产工单有 `order_assets`、多告警映射，批准范围由服务器冻结，不能靠现场再填一个测试自行扩权。

**现场用户能做什么。** 获派技术员在开放轮次填写本测试测量、仪器/校准、照片、自由文字及支持/排除/未知；value=0合法，缺失=null；failed/inconclusive/out_of_range/refused/requires_authorization 为独立结果，不按阴性处理。观察提交后可重新诊断，再看到新候选和下一步。针对具体 assertion 或原文 span 修正，不必只给整报告“对/错”。

**冲突与追溯。** 作者、角色和独立验收状态由服务器绑定；工单/观察/轮次 version CAS + Idempotency-Key +稳定 client_submission_id防重复；相同键不同内容409。报告发布前复查安装、资产、群组、告警和工单版本，旧结果不覆盖换装或拆组后的对象。

证据：`app/api_agent.py`、`api_inspection.py`、`contracts/v2.py`、`frontend/src/pages/V2Operations.tsx`、`tests/test_v2_workflow.py`、`tests/test_v2_acceptance.py`。

## 9. 约束排程：从单次人员推荐到可确认的时段/资源优化

**main→DEV。** main 已按技能、值班、负载和位置排序维修人员，人工派单；DEV 新增真正 OR-Tools CP-SAT 求解时段、次序、工具与前置关系的排程草案，不能说原来没有派单。

**用户看到。** 资源/班次/工具、任务资格/时长/release/due、异步求解状态、甘特图与人员负载、未分配原因、旅行分钟、逐阶段最优状态；可人工编辑但重新检查全部硬约束，编辑后不宣称最优。最终人工 confirm 才写 ASSIGNED、时段、事件、通知和审计。

**模型怎么做。** 每任务恰好分配一工程师或未分配；活跃技术员、on_call、技能并集是前置。可选 interval+NoOverlap 防跨班次/重叠，AddCumulative限制工具容量。depot circuit表示真实任务顺序，已声明分钟矩阵约束相邻旅行；未知路线不可通行，不能把直线距离当行车时间。已确认任务锁定，V1未安排时间却仍在现场的任务保守占用。

**优化目标为什么这样选。** 依次最小化 critical漏派、critical逾期、high漏派、high逾期、routine漏派、routine逾期、旅行、工时差，上一阶段证明最优后等式固定。普通任务不能用权重抵消严重漏派；碳收益不参与排程。预算耗尽有incumbent显示feasible，无解显示timeout/infeasible，不能强称optimal。

**验收与限制。** 40个小实例与不调用CP-SAT的独立穷举oracle比较目标和区间；真实API验证审批/编辑/confirm/幂等/stale/RBAC。最多40新工单、30候选工程师、30秒；路线/班次由人声明，无外部交通/值班自动同步；不计末任务返回基地，字段明确false。

证据：`app/dispatch/solver.py`、`contracts.py`、`jobs.py`、`app/api_dispatch.py`、`tests/test_v2_dispatch.py`、`battery_platform/docs/V2_DISPATCH_IMPLEMENTATION.md`。

## 10. Self Evolve：新增版本化经验与 Skill 文本进化，不改 LLM 权重

**main→DEV。** main 只有追加健康/工单反馈，没有 Context、Memory/Skill进化、自动回归、Context版本对比或A0–A4对照。DEV 增加自动反馈抽取→Memory、ACE局部更新、GEPA风格候选→独立dev选择→自动回归/CAS发布→回滚。

**用户看到。** Skill/Memory版本、状态、来源、反例、实际使用ID；Context diff与恢复；fixed/no_memory/Reflexion/ACE/GEPA实验的真实指标/失败/预算/费用。普通ReplayEvaluator字段按严格 `experiment-metrics.v1`返回，包括诊断准确率、grounded_assertion_ratio、检查均值、misses/false_alarms计数及合法分母对应rate。没有综合score时显示unsupported；不同协议/split/方法/案例集/云端模式不会串成一条改善线。

**机制细节。** ACE进行ADD/REVISE/DEPRECATE/CONFLICT/NO_UPDATE，保留原反馈、信任、范围和反证。GEPA默认累积50不同完成反馈根，生成可编辑Skill文本，以与来源根分开的固定dev子集选择；默认200rollout预算，全部失败候选/基线也记预算，provider调用与token单独计。只允许修改instructions等文本字段，权限不随学习增加。活动版本唯一，当前运行快照冻结，计算期间并发新反馈不能被旧候选覆盖。

**F02–F07最新可靠性修复。** 小数友好原文span；Memory保存完整事实引用、有限摘要按纠错/测量/反证等优先级并可按需取完整事实；GEPA按root+feedback_id+version预留/消费，失败可有限退避恢复，主动取消/重启不自动重试，显式retry保留费用；no_memory在初始/历史/工具全部关闭且记录空ID；严格指标贯通API/浏览器；零相关中文不填检索预算，事件历史与相似经验分开。以上修复经604项全仓回归等验收，不等于Agent分数已上升。

**量化证明必须如实写。** 旧冻结云pilot有A2局部优势和A4下降，具体请使用Agent分数Agent表。此前A4 sealed=0.3111、静态v0=0.7000，不能把机制可运行和软件修复写成已证明自进化泛化改善。当前F02–F07未重跑所有云端质量对照，保留旧结果/失败/成本；未完成专家语义盲评和真实现场验证。若PDF呈现“自进化有效性”，应写清哪些同协议对照支持局部提升，哪些不支持，不能凭用户想要提升而改baseline或分数。

证据：`app/agent/context.py`、`feedback.py`、`evaluation.py`、`gepa_service.py`、`regression.py`、`experiment_metrics.py`、`app/api_evolution.py`、`frontend/src/pages/V2Evolution.tsx`、`docs/V2_AGENT_EXPERIMENT.md`、`docs/V2_F01_F07_REPAIR_20261002.md`。

## 11. Carbon Emission：新增独立、可复算的碳/经济决策模型

**main→DEV。** main 没有Carbon模块或页面。DEV 新增结构化因子/政策、情景、活动、状态递推、鲁棒比较、Pareto、敏感性、NPV和不可变台账；不是Agent用文字估一个碳数。

**普通用户看到什么。** 在碳中心查看/创建情景，填写共同服务量、起始状态、期末处理、电力因子、两方案用电与成本，明确约束可比；研究比较标合成。复杂多期寿命、材料流、回收抵扣和政策用完整规范编辑器。详情分别显示名义kg CO2/CO2e、不确定参数集范围、各项成本、NPV、正/负减排、内部影子价值、政策资格现金，点数字查看活动和因子来源。调整Γ触发异步重算，旧结果版本继续保留；查看Pareto、epsilon约束和敏感性。

**为什么建模型。** 比较继续用、检查、换电池等方案时，要求相同服务边界和起始状态；健康/效率改变会影响用电、换新带来制造负担、缺服务需显式记未满足服务。单看SOH或直接用碳价乘一个预测寿命无法做可核算比较，因此分开物理服务、活动碳、成本及资格现金。

**模型具体怎么算。** 活动量×带单位/气体范围/日期/地区/来源的因子得到活动碳；多期有限状态分布以行随机transition矩阵递推，按E[D/η]计算期望耗电，换新转入age-zero新cohort并显式制造活动，未满足服务保留。固定活动库存的仿射系数用Bertsimas–Sim支持函数：对绝对系数排序取Γ整数项+分数项；共享不确定key为同一维，共用电力误差在方案差值可能相消。Γ是预算参数不是置信度。候选有限枚举得到Pareto/epsilon与单源仿射切换点敏感性，不是无限空间优化。

**账怎么记。** 物理碳不做货币贴现；经营NPV、政策合格现金、已实现现金、内部shadow value分账。资格或证据不足不给现金，负减排保留负值。已结算要求真实已结算活动，不能改标签把模型预测变成实测。台账追加、幂等、管理员冲销且同entry只一次纠正；正式导出剔除synthetic/unverified/projected/unreviewed、不一致冲销和重复声明，保留边界/期间/气体/来源。

**验收与边界。** 24确定性程序检查+30数学fixture覆盖单位、共享误差、负减排、Γ端点、状态/换新、资格、NPV、Pareto、敏感性、取消/版本和台账。数学正确不证明现实减排/碳信用。当前XJTU缺合法寿命/效率转移头，`validated_model`状态输入拒绝；仍可用明确measured或user-scenario transition。没有经注册验证的预测→状态适配器，不强接SOH到碳模型；没有第三方核证或信用发行。

证据：`app/carbon/engine.py`、`schemas.py`、`storage.py`、`jobs.py`、`app/api_carbon.py`、`frontend/src/pages/V2Carbon.tsx`、`tests/test_v2_carbon.py`、`battery_platform/docs/V2_CARBON_IMPLEMENTATION.md`。

## 12. 微信现场 TEST 端：新增七页客户端与离线恢复

**main→DEV。** main 只有Web运维界面；DEV 新增原生微信工程，七页为测试登录、本人任务、工单、扫码、本轮检查、诊断往返、待同步。没有把现成Web截图冒称微信真机结果。

**用户流程。** 用已有有限技术员账户登录→只看本人派单→扫码确认order/asset/installation→接单/开始→选授权测试→填写仪器、测量和反馈、拍照/选图→本机队列→服务器接受后才标接收→读取重新诊断与下一步。无自行选角色、本人验收、审批/派单/Carbon控制。

**实现方法。** 服务端演示登录须显式开启，token hash存储、有效期1小时/可撤销，客户端Bearer只内存保存；QR HMAC签名绑定身份、15分钟有效，签名验证仍检查分配权限。草稿/队列以HTTPS环境+server用户ID隔离，稳定提交UUID与附件ID用于丢响应幂等，单实例同步。网络/429/5xx有限指数退避，断网暂停；401/403/422待处理、409冲突，不无界重试。上传响应不确定先核对附件，避免盲重传；换装/轮次变化拒绝合并。

**验收与限制。** 11 Node行为测试、7页JS/JSON/WXML检查、59事件绑定解析已通过；本机无微信开发者工具CLI/合法AppID/手机HTTPS能力成功证据，nativeCompiler=not_run。因此写“可测试工程与行为逻辑已交付”，不写“真机扫码/拍照/断网已验收”。

证据：`battery_platform/miniprogram/`、`app/api_v2.py`、`api_inspection.py`、`security.py`、`battery_platform/docs/V2_MINIPROGRAM_IMPLEMENTATION.md`。

## 13. 权限、审计与 API：保留角色，新增操作边界与并发保护

**main 已有。** 五角色(admin/researcher/dispatcher/technician/viewer)、服务端session和CSRF、观察员只读、维修员仅本人派单、另一身份验收、最后管理员保护、口令重置/会话撤销、日志/通知、9MiB body限额和loopback监听。不要声称DEV首次实现这些安全设施。

**DEV 增强。** V2严格extra-forbid请求、版本/UUID/范围/枚举验证；所有V2错误附request_id/code/message/missing_fields/retryable，返回X-Request-ID；409防旧输入覆盖。角色操作细化：研究员训练/评测/实验及碳研究，调度员/管理员批准与排程confirm，technical仅获派授权检查，viewer不写。instrumentation新资格标签支持仪表校核。mobile Bearer有限路由，扫码不提升权限。因子/政策/台账更正有独立写权限，Agent工具不拥有这些权利。

**时间与出处。** installation_id、作者、实际权限服务端绑定，measured_at与available_at分开；晚到测量不能穿回历史。观察/反馈修正保存版本，历史cutoff选当时可见版本。Context唯一active，报告运行/来源版本/CAS全部保留，回滚创建新的单调版本而非删除历史。

证据：main `app/security.py`、`api_core.py`、`api_ops.py`；DEV `app/main.py`、`contracts/v2.py`、`api_v2.py`、`api_agent.py`、`api_evolution.py`、`api_carbon.py`、`api_dispatch.py`。

## 14. 运行、迁移与工程质量：从独立 requirements 到根 UV 锁定

**main 已有。** manage.sh setup/build/bootstrap/demo/serve/test/e2e/verify-models/backup/restore；原队列/进程锁/计算锁，异常重启running标interrupted，不自动重放；备份hash和新目录恢复、会话撤销。

**DEV 增强。** 根pyproject.toml+uv.lock冻结Python，`scripts/v2.sh`一键安装/启动/测试；旧manage setup委托根UV，固定sklearn/tabicl兼容V1权重。迁移002–005按序执行并记录SHA，升级前SQLite备份、失败事务回滚、已发布脚本hash校验。现有JobSupervisor以snapshot→compute→complete扩展数值、Agent、来源、排程、碳、Context作业；事务外网络/重算，最终取消/CAS检查；取消/失败仍通过accounting-only保存实际云费用。

**界面工程。** React专业页共享结构化错误、版本、作业、证据展开与请求竞态保护；390px单列、侧栏滚动、可访问标签。修复部署路径从battery_platform启动找不到model_lab、`/assets/{id}`被静态资源mount吞掉的问题。原7区和真实工单后半链仍做回归。

**可复现验收。** 已存在独立Git archive验收：不复制.env/runtime/原始包/final，仅复用依赖，用归档代码/包/开发样例重载和真实API；旧提交归档验证是旧SHA证据，不能说当前HEAD全量归档已经重测。当前F01–F07的机器可读回执明确604 Python、13浏览器合同、2真实浏览器测试、TypeScript/Vite通过；模型9次重训完成，云调用0；不能把新增测试数当模型分数提升。

证据：`pyproject.toml`、`uv.lock`、`scripts/v2.sh`、`battery_platform/manage.sh`、`app/migrations/__init__.py`、`app/jobs.py`、`battery_platform/scripts/verify_v2_checkout.py`、`docs/V2_RUNBOOK.md`、`docs/V2_F01_F07_ACCEPTANCE_20261002.json`。

## 15. PDF 可用的里程碑/证据索引

| Commit | 真实交付 |
| --- | --- |
| c4203014 | main V1比较基准 |
| a3a50665 / 5aaee397 | DEV范围、UV运行时、事务迁移 |
| ad837321 / 4286c158 | Carbon引擎、服务起点与更换库存边界 |
| 1bcadd66 | CP-SAT约束排程 |
| 69b7a548 | 2400情景、16 Skill |
| 14ce6b8d | 微信TEST工程 |
| 0addea66 / 73ce2cd8 / a13d1a27 | 单Agent/Context、GEPA真实选择、回归底线/失败成本 |
| a54e67be / 7ac492c8 | Web、版本化后端闭环 |
| ce4f87fc / 956e5b59 | 多源研究、安全包、MATR续测寿命研究 |
| 6f9a9274 | 冻结云对照，包含全部成本和负结果 |
| 45def812 / cc8eb1ab | 数字引用验证、自动回归、数值群组、按包输入 |
| 4a4913bc | XJTU+MATR联合基准及MLP/LSTM/LightGBM对照 |
| 81e16a0d / d9cf67a3 | H-M1开发门槛与结构优化 |
| fa3273b9 | 温度有效性版本与九次开发重训 |
| 0d9a53de | 反馈/Memory/GEPA恢复/实验指标一致性修复，当前DEV |

数字与分数最终引用优先级：机器可读冻结结果/回执 > 同轮详细报告 > 总交付旧快照。必须把development、final/sealed、程序测试、合成fixture、云smoke、现场结果分别注明。不能用最近软件修复覆盖旧冻结成绩；不能为“结果好看”下调baseline；没有测量的提升写未证明。
