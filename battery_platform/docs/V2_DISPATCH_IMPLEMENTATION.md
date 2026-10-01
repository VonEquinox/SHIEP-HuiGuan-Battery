# V2 排程实施记录

本文件独立记录总方案第 7.1–7.2 节的实现、协作接口与验证。提案审批由
`api_v2.py` 所属模块负责；本模块只接收已正式创建且尚未分配的工单。
原始两份需求文档保持原样。所有提交由主 Agent 在 DEV 分支统一执行；
本模块 Agent 不执行 Git 提交或推送。每批提交的实际 SHA 和全项目验证
由主实施记录汇总；这里记录可审查的最终内容。

| 日期（Asia/Shanghai） | 本批工作 | 验证/证据 |
|---|---|---|
| 2026-10-02 | CP-SAT 求解器、草案与资源 API、异步 worker 接口、migration 004、独立约束验证器 | `tests/test_v2_dispatch.py` 17 项通过；与 `tests/content/test_fixtures.py` 联合执行 90 项通过，其中 40 个排程实例与独立穷举 oracle 对比通过 |

## 实现与边界

- `app/dispatch/solver.py` 使用实际 OR-Tools CP-SAT，不使用 LLM 指派人员。
  Agent 可以写提案，只有管理员/调度员可以配置资源、创建/编辑草案和确认。
- 每项任务恰好分配给一位工程师或进入未分配集合。人员资格取服务器
  `personnel.skills`，要求为原工单 `required_skill` 与审批资格标签的并集。
  活跃账号、technician 角色和 on_call 均为新派单的必要条件。
- 工程师可选区间、班次选择和 `NoOverlap` 保证任务连续执行、不跨班次空档。
  前置工单须在当前草案中先完成，或者已有 VERIFIED/CLOSED 状态。
- 工具使用 `AddCumulative`，支持容量和可用时段。未知工具没有默认容量。
  任务时长、任务数上限、服务时间与旅行时间合计的工时上限都是硬约束。
- 每位工程师通过 depot circuit 表示实际任务顺序。只对直接相邻任务计旅行，
  使用已声明的分钟矩阵；缺少地点间路线则不可通行，同一明确地点为零分钟。
  所有行程时间参与可达性和工时约束，不把经纬度距离当作可达时间。
- 普通 due_at 默认用于逾期目标；`hard_deadline=true` 将期限升级为不可违反
  的硬限制。分钟级整数时间支持排程核验；求解器也支持 fixture 的离散时间网格。
- 已确认、仍未完成且与当前 assignee 一致的预定任务成为不可移动区间。
  即使所属人员退出本次候选集合或不再值班，其区间和工具仍被保留。
  没有时间安排的 V1 现场任务、计划已过期但仍未完成的任务不会被猜测为空闲：
  对应工程师停止接受新任务，已知工具需求保守占用本次整个窗口，并返回 warning。
  RESOLVED/VERIFIED 继续占 V1 工单数量负载，但不虚构未完成的现场区间。
- 群组 `order_assets` 的安装标识与当前资产进行校验，停用或已更换资产拒绝排程。
  任何工单、人员、资产、任务要求、群组映射、资源或已确认排班变化都使旧输入
  fingerprint 失效。现场接单不会被旧草案覆盖。

按独立求解阶段严格依次最小化以下值，每个已证明的最优值以等式固定后才进入
下一阶段：critical 未分配数、critical 逾期分钟、high 未分配数、high 逾期分钟、
routine 未分配数、routine 逾期分钟、旅行分钟、工程师工作分钟最大最小差。
最终只为方便编辑加最早开始的平局消解。不存在让普通任务数量抵消严重漏派的
随意权重，碳收益与碳成本完全不进入求解器。

返回 `optimal/feasible/infeasible/timeout`、逐阶段是否证明最优、
`lexicographic_complete` 和未分配原因。资源冲突的复合原因是可审查的分类，
并非最小不可满足核的数学证明。时间预算耗尽但有可行 incumbent 时保留
`feasible`，不冒充完成了全部优先级优化；无 incumbent 则返回 `timeout`。
Cancellation callback 在求解期间由短轮询线程调用 `stop_search()`。

## 持久化与 HTTP 接口

迁移文件为 `app/migrations/004_dispatch.sql`：
`dispatch_resources`（单节点资源版本）、`dispatch_requirements`（审批/人工要求）、
`dispatch_plans`（完整输入快照、hash、求解结果与确认信息）、
`dispatch_assignments`（正式工单的确认时段）。不修改 V1 `orders` 状态定义。

| 方法与路径 | 行为 |
|---|---|
| GET/PUT `/api/v2/dispatch/resources` | 读取/按 version 修改资源；人员 id 绑定已有维修人员，班次为 horizon 起点的相对分钟；模拟资源必须有 scenario_id |
| GET/PUT `/api/v2/dispatch/orders/{id}/requirements` | 读取/修改尚未分配工单的资格、时长、release、due、工具和前置要求；version=0 表示尚无记录 |
| POST `/api/v2/dispatch/plans` | `order_ids,horizon_start,horizon_minutes,time_limit_seconds`；返回 202 与 plan_id/job_id；必须提供 Idempotency-Key |
| GET `/api/v2/dispatch/plans` 与 `/{id}` | 读取草案、约束输入、solver 状态、未分配原因和 job_status/job_error |
| PATCH `/api/v2/dispatch/plans/{id}` | `version,assignments[{order_id,engineer_id,start,end}]`；完整重新检查硬约束，保留锁定区间；编辑后不再宣称最优 |
| POST `/api/v2/dispatch/plans/{id}/confirm` | `version` 与 Idempotency-Key；原子写工单 ASSIGNED、区间、order_events、站内通知和审计 |

`horizon_start` 必须带时区，服务端统一 UTC；窗口最多 10080 分钟，最多 40 个
新工单、30 个显式候选工程师、30 秒计算预算。资源班次是针对给定起点的
声明时段，尚无外部值班日历自动同步。现有任务合并后最多 100 个区间。
location 与 home_location 的语义和路线由管理员/调度员声明，系统不从地址
自动推导交通信息。当前旅行包括从起始位置到首任务及任务之间的旅行，
不计最后返回基地，结果显式标注 `travel_includes_return_home=false`。

所有读取遵循角色边界；technician 通过原有本人工单 API 查看获派任务，
不能读取其他人员整个排班。确认与编辑只允许人类 admin/dispatcher 权限，
继续使用原有认证、CSRF、来源校验。研究员/观察员可读但不能派单。
相同创建幂等键和请求返回同一 job/plan；相同确认幂等键和确认版本返回同一
已确认计划。复用幂等键提交不同内容，旧 version，或失效 fingerprint 均返回 409。

`app/dispatch/jobs.py` 导出主 worker 使用的 `snapshot(c,job)`、
`compute(request,cancelled)`、`complete(c,job,result,request)`。读取和落库使用
短事务，CP-SAT 在事务外执行；完成时再次检查输入版本，失效结果保存为 STALE，
绝不分配工单。失败/取消作业在草案查询中直接显示终态与 job_error。

## 已执行验证

```sh
.venv/bin/python -m pytest battery_platform/tests/test_v2_dispatch.py -q
.venv/bin/python -m pytest tests/content/test_fixtures.py -q
```

模块测试覆盖资格、班次空档、工具、依赖、未知路线、工时、硬期限、严重等级
不抵消、锁定任务、infeasible/timeout/cancel、草案不派单、真实确认、幂等确认、
编辑硬约束、stale 冲突、RBAC 与 CSRF。`tools/content/fixtures.py` 的穷举参考
实现没有调用 CP-SAT；40 个小窗口实例逐一比较全部目标值并核验具体区间。
Fixtures 的批准状态、资产映射与 stale 情形由明确的 fixture 预处理映射到求解器，
并不将预处理测试冒充全部 live API 服务权限验证；真实接口边界由上述 API 测试验证。

实现依据：[OR-Tools scheduling](https://developers.google.com/optimization/scheduling/employee_scheduling)
与 [CP-SAT status/time limits](https://developers.google.com/optimization/cp/cp_solver)，
于 2026-10-02 核对。整体集成、浏览器截图和提交 SHA 以主实施记录的实际证据为准。
