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
