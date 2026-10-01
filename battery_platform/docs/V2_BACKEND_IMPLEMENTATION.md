# V2 后端实施、服务连接与验证记录

日期：2026-10-02。本独立记录对应 `01_实施总方案.md` 的数据、诊断、现场检查、反馈进化和异步边界，以及 `02_Skills与合成数据规范.md` 的内容使用、来源和根级隔离。用户本次明确授权团队合成数据与 Skill，覆盖原文中由用户自行合成的安排。本文件记录后端 Agent 的实际改动；主 Agent 在 DEV 分阶段提交，具体 Commit 哈希以根目录 `docs/V2_IMPLEMENTATION_LOG.md` 为准。本 Agent 没有单独提交或推送。

## 1. 文件与协作范围

| 文件 | 实际职责 |
|---|---|
| `app/contracts/v2.py`、`app/contracts/__init__.py` | 严格的请求契约、范围、枚举、版本和 UUID 校验；拒绝未声明字段 |
| `app/migrations/002_v2.sql` | 增量 V2 表、索引、唯一性和引用约束；不替换 V1 表 |
| `app/api_v2.py` | 预测剖面、来源、白名单数值包、模型作业、实验资产绑定、演示小程序凭据和签名 QR |
| `app/api_agent.py` | 会话、后台 Agent、报告、待审批提案、人工批准/拒绝、群组与拆分 |
| `app/api_inspection.py` | 受分配限制的现场观察、测试/轮次授权、事实修正、自由反馈、QR 范围检查 |
| `app/api_evolution.py` | 原文抽取、自动 Memory、独立验收后的信任变更、上下文版本、回滚、实验与分批 GEPA 接口 |
| `app/v2_jobs.py` | snapshot → compute → complete 作业注册、取消/重启生命周期、数值与来源作业适配器 |
| `v2_model_worker.py` | 固定数值模块子进程、全局计算锁、父进程看门狗、超时与取消清理 |
| `tests/test_v2_workflow.py` | 7 条真实 HTTP/数据库/worker 连接回归，包括实际安全 M1 包预测 |
| `tests/test_v2_gepa_workflow.py` | 8 条自动反馈批次、候选、CAS、失败/取消成本及实验总预算回归，使用明确标注的 test-only 提供方 |
| `tests/test_v2_group_workflow.py` | 多资产正式工单中次安装的真实 HTTP 观察进入 peer 工具，且不混为主安装证据 |

主 Agent 负责 `main.py`、迁移执行器、V1 worker/security/附件/人员资格与独立验收 hook；诊断 Agent 负责 `app/agent/`；数值 Agent 负责 `model_lab`；内容 Agent 负责 `content_v1` 与公开/评测回放；派单、Carbon、前端、小程序由各对应 Agent 实施。本后端调用这些服务，未把多 Agent 协作改造成生产运行时多 Agent。

## 2. 持久化与时间边界

迁移新增来源清单、原始片段/目标/特征/预测记录，context snapshots、Skill/Memory 版本，incident groups/members，diagnostic sessions/runs/reports，work proposals、多资产和多告警映射，inspection rounds/observations/versions，自由 feedback/versions，evolution/evaluation runs，幂等记录、mobile tokens，以及 V2 数值绑定/预测。活动上下文只有一条；报告、源反馈和历史版本保留，CAS 冲突不覆盖他人的更新。

服务器绑定真实用户、资产和 `installation_id`。客户端不能指定观察作者、批准人、角色或独立验收状态。Agent 输入同时检查查询截止时间和服务器可用时间：

- 预测按当前安装身份、指定预测及截止时间取值；未来写入的预测不能替代历史可见预测。
- 观察和自由反馈按版本发布时间选取截止时间内的原始版本。事实修正、自动抽取和独立验收都保存新版本，不以首次 `available_at` 偷渡后来的内容。
- 原始测量可以记录较早 `measured_at`，但迟到提交不能在服务器收到它之前进入历史重放。
- XJTU 数值来源使用 `source_record_ordinal`。原始 `query_time`/`visible_cutoff` 数字字段保留，并附来源时间说明；它们不转换成日期或循环数。服务器 `available_at`/Agent cutoff 是独立的 ISO 时间。
- 发布报告前重新检查资产、安装、工单、群组、成员和告警版本。计算过程中拆分群组或换装，旧报告不能落库。

根级 split 从内容包清单核对。运行时只初始化 960 个 cold-start 可见根的有限事实与 16 个发布 Skill，不打开 oracle、未揭示 evolution 分支、dev 或 sealed。评测标签只供评分器，dev/sealed 反馈不能作为通用 Skill 提案来源。

## 3. HTTP 契约

以下路径统一以 `/api/v2` 开头。列表返回 `items`、`next_cursor`，受 `limit<=100` 限制；异步创建返回 202 和 job ID。V1 登录、角色、订单转移、独立验收、附件与通用作业查询继续由原服务提供。

| 服务 | 路径和关键行为 |
|---|---|
| 总览/数值 | `GET /overview`；`GET /assets/{id}/prediction-profile?cutoff=...`；`GET /sources`、`GET /models` |
| 来源作业 | `POST /sources/{id}/ingest`，`mode=metadata` 或 `registered_local`；后者必须指定来源匹配的已登记实验数据集 |
| 模型作业 | `POST /model-runs`、`GET /model-runs/{id}`；固定的 V1/V2 train/calibrate/evaluate/export/inference 类型和服务器配置，不接收 shell 命令或任意模型上传 |
| 安全包/绑定 | `GET /model-packages`；`POST /assets/{id}/v2-binding` 要求资产版本、安装身份、已验证 package ID 和开发特征行索引 |
| Agent | `POST /agent/runs`；`GET /agent/runs`、`GET /agent/runs/{id}`；`GET /diagnostic-sessions/{id}` 返回原文、版本报告和提案 |
| 提案 | `POST/GET /work-proposals`；`GET /work-proposals/{id}`；`POST /work-proposals/{id}/approve`、`/reject`，只有人工批准生成正式 V1 工单 |
| 群组 | `POST /incidents/analyze`；`GET /incidents` 支持 severity；`GET /incidents/{id}`；`POST /incidents/{id}/split` 保留单体告警并生成有成员映射的子组 |
| 检查 | `GET /orders/{id}/inspection`；`POST /orders/{id}/observations`；`POST /orders/{id}/rounds/{round}/submit` |
| 原文/事实 | `POST /observations/{id}/facts`；`POST /diagnostic-sessions/{id}/feedback`，支持具体 facts/hypotheses assertion 目标 |
| 小程序 | `POST /demo-mobile/login`、`/logout`；`GET /orders/{id}/qr`；`POST /orders/{id}/qr/verify` |
| 上下文 | `GET /skills`、`/memories`、`/context-snapshots`、`/context-snapshots/{id}`；`POST /context-snapshots/rollback` 创建新的单调版本 |
| 进化/实验 | `GET /evolution/runs`、`/evolution/runs/{id}`；`POST /evolution/experiments`，明确 method、base_version、case_ids、split、max_rollouts 和 activate |

写操作同时采用请求 hash 与版本：相同 actor/operation/Idempotency-Key/内容返回原结果；同 key 不同内容返回 409。观察和轮次另用稳定 `client_submission_id`，更换 HTTP key 也不能重复创建。人工批准重复提交相同批准版本/内容只有一个工单，改动内容需要新的状态而不能复用旧批准。

## 4. 诊断、批准与群组

Agent 取得有界快照，在事务外调用唯一诊断执行器。接口中的预测 heads 为列表，执行器输入为按名称索引的字典；每项保留 target、distribution、support、calibration、source、evidence。缺少任务模型时传递 `insufficient_data`，仍允许数据质量诊断，不生成概率。后台结果完整保留 `execution_mode`、`cloud_report_valid`、错误、提供方请求及累计 token；问题报告不能冒充有效云报告。

首轮无人工授权时只推荐待批准目录测试。报告可生成 `PENDING_APPROVAL` 提案，不生成或派发正式工单。批准时核对安装、群组和提案版本，并合并目录要求的最低资格。`T_TIME_ALIGN` 等要求 battery+instrumentation；客户端只提交 battery 不能削弱派单的硬资格。主 Agent 同步扩展了 V1 人员登记的 instrumentation 白名单。

批准生成一个合法主告警工单，并保存 `order_assets`、`order_alert_links` 与 dispatch requirements；多资产检查保留每个安装快照。检查范围、必需测试、最大轮次、资格、有效期限由服务器持有。检查不能自动扩大批准集合；新的测试需新的提案。已提交且截止时间内可见的尝试传递 `completed_test_ids`/`attempted_test_ids`，程序过滤重复推荐。failed/inconclusive 等是有效未知结果，不改写为阴性，也不默认为可盲目重试。

群组分析当前依据拓扑和告警窗口，明确 `causality=not_established`，没有凭空声称数值残差相关或已确认共因。持久化群组及成员证据实际进入 Agent 的 peer 工具；成员新提交的观察也按会话、物理实体、安装、轮次、可用时间和版本取得，每成员上限 100 条并显式保留 `peer_installation_id`，不会把次安装读数混为主安装观察。拆分保存原单体告警，旧群组提案和运行中旧输入被拒绝。

## 5. 现场反馈与自动 Context

技术员必须是实际分配人，工单已 ACCEPTED/IN_PROGRESS，当前轮次 OPEN，测试已批准且资格满足。观察检查单位、仪器、测量时间、校准状态、附件归属和安装；需新授权/破坏性测试不由此接口执行。结果枚举包括 observed、failed、inconclusive、out_of_range、refused、requires_authorization。定量 observed 保留真实 value=0；缺少结果使用 null，不补零。

原始自由文本永久保留。自动抽取产生带 span/source_text 的候选事实；人工修正也必须指向原文 span 或原提交 measurement，不能注入伪造独立核实。针对具体报告断言的纠正保留 assertion target。低信任或未校准原文可以成为来源标注的 reported 经验，不能因此确认物理根因。权限指令、自动批准或 Carbon 越权要求被隔离为原始材料，不进入 Memory。

ACE 在临时 ContextStore 中提出局部更新。发布前检查取消、反馈版本和当前上下文；并发情况下针对最新版本重新合并，不持有写事务等待 LLM。Memory 自动生效或隔离/无更新，不引入人工 Memory 审批。回滚创建新版本并保存来源，不删除历史。独立 V1 验收者不能是技术员/解决人；验收 hook 保存新观察版本，并让 worker 分批抽取。超过 12 作业队列上限时状态保留待处理，验收不会因逐条 enqueue 失败。

GEPA 接口另提供默认每 50 个独立完成反馈根事件的自动候选调度，根不按轮次数重复计数。只生成可编辑 Skill 文本，以与来源根分离的固定 dev 子集做候选选择；计算仅返回 staging，最终取消检查、回归、来源反馈版本和 Context CAS 后才自动发布。封存根不参与候选生成/选择；sealed 实验拒绝 ACE/Reflexion/GEPA 与 activation。`fixed` 方法显式关闭 episodic/ACE/GEPA 更新。进化审计从临时 store 的全部 active 更新展开，保留早期 Memory 与 Skill 变化，而非只记录最后一轮。

预算记录是 direct 根报告数 + 候选/基线预留 rollout，格式/安全失败候选也占相同的比较预算。每次真实搜索的候选指标、选择根、请求、失败请求、未知 usage 请求、已知累计 tokens 同时写 job、evolution metrics 和 evaluation budget；没有触发或没有候选云客户端时明确 no_update。GEPA 中途取消及计算结束后取消仍通过独立 accounting-only hook 保存已花成本，绝不调用上下文发布；hook 在 SAVEPOINT 中隔离，记录失败也不阻止原作业进入终态。真实云候选搜索的质量证据由单独进化实验记录，程序 stub 验证不证明改善。

## 6. 数值与数据源适配

服务器只登记 hash/reload 验证通过的 Safe JSON+NPZ 包；NPZ 禁止 pickle。在线读取服务器白名单开发特征 bundle，仅选择对应真实物理实体、化学体系、协议和源序号行，不读取 y 标签或 final bundle。demo 资产绑定实际实验对象时明确 `experimental_replay_on_simulated_asset`，没有称作现场实时测量。

当前实际 M1/M2 包支持 XJTU 对应域的 RPT 相对 SOH。RUL、效率、风险/故障等未训练或不支持的任务返回 unsupported/null。独立校准对象不足时区间上下界保持 null，展示 `insufficient_calibration_objects`，不冒称 90%/95% 覆盖已达到。若将来支持 Bernoulli head，其 value 取真实 `params.probability`；不存在值仍为 null。

来源 GET 初始登记数值 Agent 的 registry；metadata job 在事务外刷新官方元数据，不自动下载整源。已解析来源保留 parsed_manifest、许可、receipt、hash 和 inspected subset 的 raw_scope，不把元数据查询称为全量原始解析。registered_local 拒绝模拟/未核实数据集和来源错配。CH public generated 数据的 namespace 与实测来源保持区分。

V2 数值 train/calibrate/evaluate/export 使用固定模块与服务器路径；运行时输出保存在 job 目录，研究作业不自动替换生产模型。推理和研究计算共用 V1 的 `app/runtime/model-compute.lock`。子进程随父进程退出、取消或超时停止，不在 SQLite 写事务内运行数值或网络请求。

## 7. 小程序身份与 QR

演示 mobile login 必须显式启用 `BATTERY_DEMO_MOBILE=1`，使用已有账户用户名/密码，服务端仅接受 technician，不提供角色选择。token 只保存 hash、有效期一小时并可撤销；有限路由只允许本人已分配工单、附件、检查和相应诊断，不授予派单、模型、Carbon、审批或人员管理。

QR 使用服务器 HMAC 签名，有效期 15 分钟，绑定 order/asset/installation。验证签名之后仍检查当前分配权限和安装身份；仅扫描二维码不提升用户角色。secret 使用环境配置或受权限限制的服务器文件；没有把 LLM key/AppSecret 放入客户端。主 Agent 已为 V1 照片上传添加稳定 Idempotency-Key 与内容 hash；真实微信设备编译和离线体验证据见小程序独立文档，本后端没有执行或伪造真机验收。

## 8. 实际验证与修复

本 Agent 的 7 条 workflow 用例使用独立数据库、真实 FastAPI 请求和 `JobSupervisor.run_extension`。规则诊断只验证服务链，实际安全 M1 包用例运行数值推理并确认 unsupported/calibration/source 时间边界。用例均未打开受保护 V1 holdout。实际执行：

```bash
.venv/bin/python -m pytest battery_platform/tests/test_v2_workflow.py -q
# 7 passed in 3.05s

.venv/bin/python -m pytest battery_platform/tests/test_v2_workflow.py battery_platform/tests/test_v2_acceptance.py -q
# 添加最后一条 round 去重用例之前：24 passed in 9.05s

.venv/bin/python -m pytest battery_platform/tests/test_v2_acceptance.py -k submitted_round -q
# 1 passed, 17 deselected in 0.38s

.venv/bin/python -m pytest battery_platform/tests/test_v2_workflow.py battery_platform/tests/test_v2_acceptance.py -q
# 补齐群组告警 CAS 后：25 passed in 7.10s（7 workflow + 当时 18 QA）

.venv/bin/python -m pytest battery_platform/tests/test_v2_gepa_workflow.py battery_platform/tests/test_v2_gepa_service.py battery_platform/tests/test_v2_group_workflow.py -q
# 16 passed in 5.36s（8 GEPA workflow + 当时 7 service + 1 group）

.venv/bin/python -m pytest battery_platform/tests/test_v2_workflow.py battery_platform/tests/test_v2_acceptance.py battery_platform/tests/test_v2_gepa_workflow.py battery_platform/tests/test_v2_gepa_service.py battery_platform/tests/test_v2_group_workflow.py battery_platform/tests/test_v2_agent_core.py -q
# 76 passed in 16.67s，包含完整变化审计的第 19 条 QA
```

独立 QA 此前组合为 177 passed in 22.77s，包括本文件 7 条和当时 18 条跨模块接受测试；不将重叠执行次数相加。最新后端/诊断连接组合 76 passed 包括第 19 条完整变化审计回归，最终全仓执行以主 Agent 记录为准。完整命令、覆盖及局限见 `docs/V2_ACCEPTANCE_REVIEW.md`。其反馈促成实际修复：历史预测取值、数值序号误作日期、目录最低资格、未来事实修正泄漏、群组未进入工具、已执行测试重复推荐。Memory 修订时间修复由诊断 Agent 完成。

后续 GEPA 费用回归使用显式 deterministic fixture：2 个直接根 + 6 个预留 dev 比较等于 total 8，而实际 7 个提供方 stub 调用、105 个 fixture tokens；非法候选预留比较但不产生提供方报告调用。计算结束后取消仍保存这些费用且 Context 不变。中途取消只发生 proposer+首个 dev 报告两次 stub 调用，保存 30 个 fixture tokens 和本次候选 2 个预留比较。失败 dev 比较保存 3 请求/2 失败/45 fixture tokens，并占 6 个比较预算。fixture 数字仅验证计账，不能与真实 DeepSeek 成本混合。未配置云服务测试返回 no_update、0 provider 请求且不修改上下文。

主 Agent 另外执行真实 DeepSeek API → HTTP → worker → cloud 报告 → pending proposal，证据位于 `reports/v2_integration/cloud_api.json`：POST=202、GET=200、mode=cloud、cloud_report_valid=true、无执行错误，2 次提供方调用、18,272 tokens，1 个待审批提案、批准前 0 正式工单。输入为明确标注的合成异常，不代表现实诊断质量。

首次验证脚本也获得有效云报告，但主 Agent 的断言把 execution_mode 与 cloud_report_valid 混写，未保存该次最终证据；该次实际 2 调用、13,765 tokens。修复并重跑后，两个执行合计 4 调用、32,037 tokens，不能只列成功保存记录而隐去首次成本。凭据只在环境使用，本文件和仓库不保存 API key。

## 9. 阶段提交记录与剩余验证

| 阶段 | 已做内容与证据 | 归档方式 |
|---|---|---|
| 后端契约/连接 | additive migration、全部 HTTP/worker 连接、真实数值剖面、受限 mobile/QR、自动 Memory、时间与版本修复；7 workflow + 18 接受用例，组合 177 passed；真实云 API smoke | 主 Agent 在 DEV 提交本模块与本独立记录，并在总实施日志记录 Commit |
| 进化搜索连接 | context_gepa 批次调度、固定 dev 选择、受授权 evaluator 分支桥接、阶段化 Skill 发布、完整更新审计、包含失败/取消的预算与费用；8 新 workflow 和 1 次安装观察回归通过 | 由主 Agent 单独阶段记录运行证据和 Commit；真实云候选实验另记录，不用普通报告 smoke 或 stub 推断候选改善 |

已完成的代码并不表示所有现实验收成立：没有物理设备控制、认证现场 SOP、专家语义签署、真实共因统计结论、全面数值任务覆盖或生产部署。正式封存质量实验仍须冻结协议并独立执行；真实数值数据、训练、模型比较、Carbon 因子许可与数学算例、派单、浏览器和微信能力的各自证据以对应独立文档为准。
