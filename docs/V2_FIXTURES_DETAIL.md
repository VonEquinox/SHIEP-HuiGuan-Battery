# V2 派单与独立 Carbon 数学算例实施记录

本次交付 40 个派单 fixture 和 30 个 Carbon fixture，用于小规模约束求解、数学核算与界面回归。答案来自确定性数学程序和手算核对，未采用 LLM 生成答案验收求解器。所有记录均为虚构演示，带 `synthetic=true`、`origin=physics_simulated`、`data_scope=demo_synthetic`；这些算例不构成真实电池故障分布、正式碳因子、政府政策或已兑现收益。

实施日期：2026-10-02（Asia/Shanghai）。范围对应《02_Skills与合成数据规范》8.2、9、11 节及实施总方案 7.2、9.3–9.8、14.3 节。用户已授权合成内容；文档中的数学和审批边界按验收契约执行。

## 生成与验收

在仓库根目录完成 `uv sync --locked` 后运行：

```bash
uv run python -c 'from pathlib import Path; from tools.content.fixtures import generate_fixtures; print(generate_fixtures(Path("content_v1")))'
uv run python -c 'from pathlib import Path; from tools.content.fixtures import validate_fixtures; r=validate_fixtures(Path("content_v1")); print(r); raise SystemExit(0 if r["valid"] else 1)'
uv run python -m pytest -q tests/content/test_fixtures.py
```

生成器只写入传入内容根目录中的 `fixtures/dispatch.jsonl` 与 `fixtures/carbon.jsonl`，不向 Agent 的知识索引发布答案。完整内容生成器可调用同一函数并将文件纳入内容版本和 SHA-256 清单。重复生成使用固定排序、固定 ID、非随机参数和严格 JSON 序列化，输出字节保持一致。

实际验证使用已配置的根 `.venv`：

```bash
.venv/bin/python -m pytest -q tests/content/test_fixtures.py
```

结果：`73 passed in 0.42s`。40 个派单问题均与实际 CP-SAT 求解器逐例对照全部八项字典序目标，并验证输出具体约束；Carbon 的 4 个鲁棒范围、3 个更新过程和 2 个 Pareto 算例直接对照实际 Carbon engine。其余 Carbon 算例给出独立、可手算的规范化数学契约，由数学断言与结构校验核对；此记录不宣称这 30 条均已通过正式 API 的完整入库/导出路径。

## 已修改的文件与接口

| 文件 | 内容 | 对接方式 |
|---|---|---|
| `tools/content/fixtures.py` | 两类算例、独立穷举调度、碳算术、通用结果比较、运行时调度适配器、覆盖校验 | 完整内容生成器调用 `generate_fixtures(output: Path)` |
| `tests/content/test_fixtures.py` | 手算、负收益、权限预处理、实际 CP-SAT/Carbon engine 对照、数据篡改检查 | 根 pytest 配置已包含 `tests/content` |
| `docs/V2_FIXTURES_DETAIL.md` | 本独立实施记录 | 主实施日志在提交时关联本文件和验证结果 |

公开函数及返回值：

| 函数 | 输入 | 返回 |
|---|---|---|
| `generate_fixtures(output)` | 内容根目录 `Path` | `dispatch_count`、`carbon_count`、两类 `coverage` |
| `validate_fixtures(content_root)` | 已生成内容根目录 | `valid`、数量、错误列表、覆盖表 |
| `validate_fixture(fixture)` | 一条 JSON 对象 | 错误字符串列表；空列表为通过 |
| `validate_dispatch_solution(inputs, assignments)` | 规范化资源与任意排程草案 | 资格/时间/工具/前置/锁定等错误列表 |
| `solve_dispatch(inputs)` | 小规模规范化资源 | 完整穷举 oracle、最优目标、示例安排、未分配/排除原因 |
| `dispatch_runtime_adapter(inputs)` | 规范化资源 | 实际求解器 `data`、任务/员工 ID 映射、边界排除列表 |
| `evaluate_carbon(kind, inputs)` | 算例类型与显式参数 | 独立数学结果 |
| `compare_expected(expected, actual)` | 两个结构化结果 | 数值容差/字段/类型错误列表 |

fixture 公共字段为 `fixture_id, schema_version, synthetic, origin, data_scope, generated_by, source_refs, kind, coverage_tags, inputs, oracle`。Carbon 额外给出 `tolerance`。`schema_version=mathematical-fixture-v1`，`generated_by=deterministic_fixture_oracle_v1`。来源 ID 指向用户提供的设计规范，不伪造外部文献或已授权厂商操作流程。

## 派单：先验证批准边界，再穷举资源安排

每条派单输入显式包含任务严重性、硬/软截止、时长、位置、检查集合、技能与资格、前置任务、工具，以及批准状态和内容版本；资源包含班次、请假时间、是否在场、初始位置、可出发时间、工时上限、工具数量/可用窗口、旅行矩阵和已开始的锁定任务。

未获人工批准、批准版本过期、输入快照过期、资产映射错误、安装身份不匹配或事件失效的任务先进入 `excluded`。它们不进入正式可排任务集合。完全一致的重复确认按任务 ID 去重；内容不同但同 ID 的重复会报错。群组算例安排已批准的组任务，并排除已经被组任务替代的两个单体提案。

注意：`dispatch_runtime_adapter` 的批准/版本/映射过滤属于 fixture 对服务边界的规范化预处理。40 条求解器对照证明调度数学相符，不能替代正式 API 对管理员身份、审批事务、并发版本和重复提交的独立测试。

这些问题的时间离散为 5 分钟格，分析期为 30 分钟，均为小问题。穷举器遍历每个任务的「不分配」以及全部合格员工和全部起始格，检查完整方案后选取严格字典序最优值。该结果是在声明的时间格上的全局最优；不将它称为无限精度连续时间调度的证明，也不用于生产规模求解。

八项优化顺序：严重任务未分配数、严重任务逾期分钟数、高等级未分配数、高等级逾期分钟数、一般任务未分配数、一般任务逾期分钟数、总旅行分钟数、员工工时差。工时包含任务作业与实际旅行，不包含返回初始地点。硬截止违规不得被其他目标抵消；软截止的逾期按级别计入目标。未分配属于合法显式结果。

约束检查使用半开区间 `[start,end)`，同一员工任务之间还须满足前一任务结束加旅行时间不晚于后一开始；同一工具在末端释放后可立即供下一任务使用。未知旅行路线禁止通行。任务作业须完整落在班次与工具窗口内且不穿过请假；本算例不额外定义旅行活动的独立班次窗口。开始任务保留原员工与起止时间，oracle 记录 `locked_tasks_preserved`。

| 覆盖 | 代表 fixture ID | 预期边界 |
|---|---|---|
| 技能、资格、多资格 | `dispatch-skill-routing`、`dispatch-missing-certificate`、`dispatch-multiple-qualifications` | 不使用优化目标覆盖资格约束 |
| 全忙、合格者不在场、临时请假 | `dispatch-all-busy`、`dispatch-qualified-absent`、`dispatch-temporary-leave` | 保留不可分配及具体原因 |
| 班次、时长、跨班间隙 | `dispatch-late-shift`、`dispatch-short-shift`、`dispatch-split-shift` | 完整时段必须可用 |
| 人員/工具互斥和窗口 | `dispatch-engineer-no-overlap`、`dispatch-equipment-conflict`、`dispatch-late-tool-window` | 不产生资源重叠 |
| 旅行和路线 | `dispatch-travel-order`、`dispatch-travel-impossible`、`dispatch-initial-travel` | 显式矩阵和初始位置约束 |
| 前置任务 | `dispatch-precedence`、`dispatch-missing-predecessor`、`dispatch-cyclic-precedence` | 前置未完成不能安排后续 |
| 已开始、锁定工具 | `dispatch-started-task-locked`、`dispatch-locked-tool` | 不重新分配已开始任务 |
| 优先级、截止和负载 | `dispatch-critical-priority`、`dispatch-hard-deadline`、`dispatch-load-limit` | 严格字典序；硬约束不可折算 |
| 人工批准与版本 | `dispatch-pending-approval`、`dispatch-stale-approval`、`dispatch-stale-snapshot` | 未获批准或过期任务不进集合 |
| 重复确认与群组任务 | `dispatch-duplicate-confirmation`、`dispatch-group-work-order` | 同一审批仅产生一个任务 |
| 资产/安装映射与时效 | `dispatch-invalid-mapping`、`dispatch-stale-installation`、`dispatch-expired-event` | 错误身份和旧事件不得正式派单 |

派单 fixture 与数学求解器均不含碳排放、CO2 或减排优化字段。校验器对此显式扫描并拒绝跨域输入。最优方案仍标 `requires_human_schedule_confirmation=true`。

## Carbon：明确活动、服务量、误差和钱的口径

Carbon 文件与派单、诊断 Agent 的 Skills/Memory 分开。虚构政策仅使用 `TEST_RULE_001`，无真实政府文号或官方 URL。以下参数只属于演示算例。

| 规范要求 | fixture ID | 独立结果/拒算条件 |
|---|---|---|
| Wh/kWh、kg/t | `carbon-wh-to-kwh`、`carbon-kg-to-tonne` | 1,250 Wh=1.25 kWh；1,250 kg=1.25 t |
| 制造按块/按额定容量 | `carbon-manufacturing-per-pack`、`carbon-manufacturing-per-capacity` | 两种活动口径分别得到 200 kg；容量来自规格 |
| 缺来源 | `carbon-missing-factor-source` | `MISSING_FACTOR_SOURCE`；值为 null |
| 年度 CO2/生命周期 CO2e | `carbon-annual-co2-versus-lifecycle-co2e` | 气体/因子边界不兼容，拒算 |
| 简单用电 | `carbon-simple-electricity` | 100 kWh×0.5 kg/kWh=50 kg；无需寿命 ML |
| 辅助能耗重复 | `carbon-auxiliary-counted-once` | η 已包含辅助能耗时不再加；125 kWh、62.5 kg |
| 同服务量比较 | `carbon-same-service-positive-benefit` | 相同 1,000 kWh 输出，名义收益 275/9≈30.556 kg |
| 低效率抵消制造收益 | `carbon-inefficiency-offsets-manufacturing` | 名义收益 −445/9≈−49.444 kg，保留负号 |
| 延期不等于永久避免 | `carbon-delay-not-permanent-avoidance` | 期内延期一块，永久避免未建立 |
| 右删失寿命 | `carbon-right-censored-life` | 末次 1,000 周期只给寿命下界，不当 EOL |
| 零/一次/多次更换 | `carbon-zero-replacements`、`carbon-one-replacement`、`carbon-multiple-replacements` | 期末期望次数 0/1/3 |
| 换新重置 | `carbon-replacement-state-reset` | 进入新安装年龄 0；旧安装历史不修改 |
| 期末状态不同 | `carbon-terminal-state-mismatch` | 未定义共同终端处理时不能给比较收益 |
| Γ=0/1/小数/全维 | `carbon-gamma-0-0`、`carbon-gamma-1-0`、`carbon-gamma-1-5`、`carbon-gamma-2-0` | 名义 100，误差 20/10，最坏值 100/120/125/130 |
| 共享误差抵消 | `carbon-shared-error-cancels` | 对同源 z 作差，收益上下界均为 100 kg |
| 下界负收益 | `carbon-negative-robust-lower-benefit` | 名义 5、误差 20，下界 −15 kg；不能确认总占优 |
| Pareto 支配/并列 | `carbon-pareto-dominance`、`carbon-pareto-ties` | 排除被支配及不可行项，保留不同方案的相等点 |
| 影子价值无现金资格 | `carbon-shadow-value-no-cash` | 1 t×80 元/t=80 元影子值；信用现金 null |
| 已具备测试资格的收益分账 | `carbon-qualified-demo-income-split` | 模拟签发 0.8 t×100 元/t=80 元；与成本节约、影子值分列 |
| 纠错冲销与演示导出 | `carbon-correction-and-demo-export` | 原 40 kg加纠错 −10 kg=30 kg；正式导出为 0 |
| 非线性效率期望 | `carbon-nonlinear-efficiency-expectation` | E[D/η]=1,400/9 kWh，与 D/E[η] 不同 |
| 不可服务状态 | `carbon-stopped-state-unmet-service` | 可用概率 0.8，期望耗电 100 kWh、未满足服务 20 kWh |

更新过程计算现有剩余寿命分布 R 与新电池寿命分布 L 的期望更换次数。零/一次/多次样例使用不同确定性支持点，程序同时输出 `old` 与 `new` 的逐期数组。额外手算断言用 R=1、L=3，证明不会误将两者互换。

预算鲁棒计算对绝对误差系数降序，取最大的 `floor(Γ)` 项加下一项的小数部分。比较时先按共享误差来源 ID 对基准和候选系数作差，再求同一个不确定集下的收益上下界；不使用「基准上界−候选下界」冒充保守收益。Γ 表示定义的误差预算，结果 `confidence_probability=null`，未宣称概率保证。

经济样例不把影子碳价值加进现金收入。无资格时 `credit_cash_rmb=null`、`cash_status=not_established`；有完整测试资格时仍标演示，采用模拟签发量和模拟合同价。纠错使用保留原记录的关联调整条目，不删除原账；演示导出保留 synthetic 标识，正式导出排除演示金额。

## 容差与失败行为

数值浮点使用绝对容差 `1e-9`、相对容差 `1e-9`；计数、字符串、布尔、null、字段集合和数组长度严格匹配。NaN/Infinity 不允许通过，生成时 `allow_nan=False`。未建立收益与拒算使用 null，不使用 0 伪装未知。

调度目标均为整数，须精确相等，允许多个员工/起始时刻共享相同最优目标。CP-SAT 输出仅比较目标与可行性，不强行要求与穷举器的固定字典序示例安排相同。小规模完整穷举不含随机采样或求解超时；它不能推广为大型排程的全局最优声明。

非线性效率样例计算显式有限状态求和，其 `exact_calculation_error=0`。所谓 `invalid_shortcut_error_kwh` 是两个公式之差，不是允许忽略的误差，也不作为实际产品线性近似容限。生成器未凭空指定真实效率/寿命模型误差。

`validate_fixtures` 检查 JSONL、稳定 ID 唯一性、最低数量、可检查覆盖集合、演示来源和重新计算值。缺文件、缺覆盖、错误答案、权限边界违规和跨域参数均产生明确错误列表。完整内容系统的 hash、split、源许可与 Agent 可见性检查由内容总校验器另行负责。

## 验证证据与提交记录

本文使用 docs-generator 的通用技术文档组织方式（`flavor=null`），不套安全攻击报告或厂商政策结论。

| Evidence ID | 观察时间 | 来源/复现 | 结果 |
|---|---|---|---|
| E-FIX-001 | 2026-10-02 | `tools/content/fixtures.py`；运行上方生成和校验命令 | 固定生成 40/30 条；覆盖集合与确定性字节检查通过 |
| E-FIX-002 | 2026-10-02 | `.venv/bin/python -m pytest -q tests/content/test_fixtures.py` | 73 项通过，包括 40 个实际 CP-SAT 对照 |
| E-FIX-003 | 2026-10-02 | `tests/content/test_fixtures.py` 手算与篡改断言 | 正负收益、共享误差、更新次数、现金边界及演示导出均被检查 |

Finding F-FIX-001（validated，证据 E-FIX-001/002）：这些小规模派单问题在指定格点上的八项最优目标与实际求解器一致，且符合独立具体约束检查。

Finding F-FIX-002（validated，证据 E-FIX-001/003）：规范要求的 Carbon 主题全部有显式演示参数和确定性结果，负收益、未建立现金和拒算不会被改写成正收益或零。

Path P-FIX-001：`generate_fixtures` 按固定 ID 建立 JSONL → `validate_fixtures` 检查数量/覆盖/数学结构（E-FIX-001）→ 手算断言与实际优化/核算函数对照（E-FIX-002/003）→ 内容总生成器将结果纳入内容版本与 hash 清单。剩余验证范围是正式 API 的身份鉴别、版本事务和完整台账导出，不由这些数学 fixture 自动证明。

提交准备范围为上述三个实现文件及由主内容生成器生成的 `content_v1/fixtures/*.jsonl`。协作 Agent 未单独执行 Git 提交，避免共享工作树并发提交；负责人按分块提交，在主实施日志记录具体 SHA、文件范围和验证命令，并关联本文。
