# V2 Agent 最后覆盖核验与接入补齐

日期：2026-10-02。范围为文档一 §§05–08、14.2 和文档二 Skills/回放验收。此记录核验当前软件接入；不读取新的 sealed 或 pilot artifact，不调用 LLM，不重新评分或修改此前冻结实验。原实验代码版本 `6f9a9274`、后置数字校验修复 `45def812` 和实验原始结论继续独立保存。

## 本轮补齐的真实服务链

| 检查发现 | 本轮实现与实际边界 |
| --- | --- |
| 自动回归/回滚以前只存在纯 ContextStore 接口 | `publish_snapshot` 自动创建 `context_regression` 作业；比较当前与前一完整 Context，在相同独立 dev 根上保持先前分数下限。当前结构/权限异常、当前 dev hard failure 或分数下降可触发新版本恢复与坏版本 quarantine。 |
| 缺少有效回归证据时容易误读“通过” | 无 prior、无云端配置、dev 不足、预算不足、旧版本本身无效或旧版本报告失败，返回明确 `no_check`，不制造分数。结构/权限检查可以在无云端时发现异常，但不会恢复至无效的旧快照。 |
| 发布与取消/并发版本保护 | 成功检查后仍由 worker 的取消屏障与 snapshot ID/version/content CAS 决定发布。延后的旧检查不能撤销新反馈；自动恢复不会再次排队检查自身。取消/失败/中断同步快照详情终态，且不覆盖新的检查标记。 |
| 费用与预算 | 默认 5 个 dev 根分别评价 previous/current，共 10 个 rollout；每报告最多一次 HTTP 请求，不启用工具交互或重试。已发生请求、失败、已知 token、未知用量及保守预留 rollout 在成功、取消与失败路径均保存；预留根预算不等于真实请求数。 |
| routing_description 未影响实际路由 | 在每轮冻结 Context 上复制元数据索引，再应用可编辑描述；英文词和中文相邻双字用于实际路由分数。仍先检查化学体系/必要输入，正文按需加载，原发布库与工具权限保持受程序约束。 |
| Memory.last_used 只有字段 | executor 记录真实检索的 Memory ID；后端在取消/CAS 屏障后记录镜像使用时间和审计。后续 Memory 发布保留该时间，不修改冻结 Context 文本或虚增 helpful/harmful。 |
| 正反例预算只有总6条 | `ContextStore.search` 按来源字段分组，正例/反例各最多3条、总最多6条；同一轮初始 Context 与后续 `search_memory` 工具共同使用6个不同 Memory ID 的预算。 |
| API 回放环境 eager 读取超范围案例/标签 | API 明确请求 `allowed_splits` 和根 ID；公开根级 membership 校验先于 oracle 加载。JSONL 先筛选所请求身份再解码。普通 evolution 不打开 sealed 案例文件、不解码其标签或观察；候选选择仍只使用独立 dev。 |

新增检查服务为 `app.agent.regression.ContextRegressionService`；API 作业接口位于 `api_evolution.py`，worker 注册/异常终态位于 `v2_jobs.py`。独立人工构造的 dev 样例和带用量计数的测试 client 验证旧/新版本分数变化，不能将这些测试称为真实云端诊断收益实验。

## 用户操作与证据限制

Context 发布后自动检查，不增加 Memory/Skill 人工审批。管理员或 researcher 可在云端/dev 就绪后重新请求当前版本检查：

```http
POST /api/v2/context-snapshots/check
Idempotency-Key: a-new-context-check-key
Content-Type: application/json

{"base_version": 3, "selection_count": 5, "max_rollouts": 10}
```

仍使用现有登录会话/CSRF。实际 `base_version` 从 Context 列表获取，重复键去重，旧版本返回 409。查看 `/api/v2/context-snapshots/{id}` 的 `validation.regression_check` 与 `/api/v2/evolution/runs/{id}` 的预算、费用和 dev protocol；检查结果不等于派单批准。队列满时发布保留明确 `no_check/compute_queue_full`，后续可重新检查。无 API key 时不会发云端请求。

dev 分数是预定义的状态、引用结构、可接受检查与检查数量指标，附带硬安全/格式检查。它不是独立专家语义盲评；来源和数值边界正确也不能证明所有自然语言推理正确。任何晚于 dev cutoff 的新增 Memory 继续被检索过滤，因此“未退化”不能当作该 Memory 的有效性或收益证据。

此前 A0–A4 pilot 是小样本合成流程实验；旧分数、费用、冻结 hash 和失败记录未回填。没有独立专业盲评、真实现场根因标签或统计泛化结论。文档一 §14.2 与文档二 §10.3 所要求的独立专业语义验收仍需要实际专业评审。

Memory 的 helpful/harmful 保持来源元数据，不依据 LLM 自评增加奖励。数值检查价值仅在有版本化似然证据时使用 Bayes/VOI；默认缺少此类证据的实际作业明确使用启发式排序。普通服务不可把这两项显示为已验证的学习效果。

正反例配额已在本轮补齐。反例由明确 `counterexamples/conflicts`、`state=conflicted` 或 `source_trust=contradicted` 识别；冲突 bundle 保留两侧原文与来源。正例是 `active`、有来源根且由测量/独立复核支持的适用经验，不能据此认定根因确诊或干预成功。普通 `reported` 或类别未建立的条目明确标为 `unclassified`；不使用文字情绪、helpful/harmful 或 LLM 自评判类。

权限/域/可见时间/过期/状态先过滤，再在各类别内按相关度和稳定 ID 排序。两类均存在时保留双方，奇数或较小总预算优先留反证；缺少某类不允许另一类超过3条，空位可由未分类条目补至总6条。只有正例或只有反例时最多返回3条，没有候选时返回空；未知类别全库可返回最多6条并保留 `reported` 信任。重复工具检索只复用已检索的冻结条目，不重置配额，不替换已经进入本轮的来源。预算摘要明确提示剩余容量与下一轮接续，不为填满预算编造案例或反证。

## 独立验证

本轮新增 Context 纯服务、真实 API、路由、来源周期时间与回放 scope 测试均使用手工输入或明确测试 fixture；数字校验回归亦使用手工文本。没有为这些修复使用 sealed 值或诊断分数。精确组合命令与最终结果在配套 `V2_AGENT_IMPLEMENTATION.md` 的本轮补齐记录中保存。
