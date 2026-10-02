# GEPA 来源消费与恢复协议（F04，2026-10-02）

GEPA 不再因为根事件曾出现于任意历史作业就永久跳过它。新作业固定来源三元组 `(root_id, feedback_id, feedback_version)`，并记录来源 ACE 事件、恢复周期、前序作业和 provider 配置摘要。Key 本身不写入作业或审计。

| 来源生命周期 | 调度行为 |
| --- | --- |
| queued / running | 预留同一来源版本，阻止重复入队 |
| 完成候选评估、active、普通 no_update、终结性拒绝 | 消费本版本；不会因没有发布更新而反复搜索 |
| 无 Key 的 no_update | deferred，不消费、不花云端费用；配置可用并变化后允许一次重新入队 |
| provider 生成失败、未建立有效 baseline 比较的 provider 失败、failed、Context/source CAS conflicted | 可重试；先等待 60 秒，下一次等待 120 秒；一个恢复周期最多 3 次尝试 |
| 用户 cancelled | 不自动重试；主动取消保持有效 |
| 服务重启/停止 interrupted | 不自动重放可能已计费的工作；需要显式恢复 |
| 新反馈版本完成安全抽取 | 新版本独立参与调度，旧版本作业不得读取新版内容 |

每次尝试仍有 `max_rollouts=200`、独立 dev selection 和既有队列上限。自动重试不绕过预算：每次实际 provider 请求、失败请求、未知费用、tokens 和保守 rollout 预留留在对应作业/进化记录中，前序作业通过 `retry_of_job_ids` 关联。一个周期最多 600 个 rollout 预留；显式恢复才开启下一周期。没有将失败费用冲销成成功，也没有把修复改成无界自动重试。

快照阶段检查入队时固定的反馈版本；完成阶段再次检查来源版本，包含不产生 activation_update 的 no_update。Context CAS 冲突、来源变化都会保留计算费用并拒绝发布旧候选。失败/取消/中断的生命周期回调保留原 validation 和 metrics，补充来源消费状态和固定来源。

## 显式恢复 API

`POST /api/v2/evolution/runs/{evolution_run_id}/retry`，必须提供新的合法 `Idempotency-Key`。允许 admin，或者恢复自己作业的 researcher。返回 202 与新 `job_id`、`evolution_run_id`、`resumed_from_job_id`；同一请求/幂等键重复调用返回同一作业。

无 Key 返回 503，且不入队。尚在运行、已有来源预留、当前来源版本已被其他作业消费时返回 409。恢复旧失败作业时若反馈已升级，会固定当前安全抽取版本；如果当前版本已经终结，不允许借旧失败作业再次消费。

旧作业没有明确来源版本，无法伪造出历史版本记录。兼容处理将同根、同反馈（若旧 payload 有反馈 ID）、并且 ACE 事件不晚于该作业的来源视为旧尝试；后来的 ACE 发布可形成新的来源修订。所有新作业都写明确版本。

## 验收

运行命令：

```sh
.venv/bin/python -m pytest battery_platform/tests/test_v2_gepa_recovery.py battery_platform/tests/test_v2_gepa_workflow.py battery_platform/tests/test_v2_gepa_service.py -q
```

结果：34 passed。新增 14 个隔离 DB/API 用例覆盖 provider 暂时失败的费用与尝试上限、executor 捕获错误后云报告无效但仍带 metrics 的失败基线、安全/权限拒绝保持终结、无 Key 配置恢复、Context CAS、排队反馈改版、no_update 完成时反馈 CAS、旧失败不能重消费新已终结版本、legacy root-only failed、取消/重启显式幂等恢复、failed/cancelled/interrupted 生命周期记录保留。其余 20 个既有 GEPA 服务/工作流用例覆盖候选发布、权限、封存隔离和取消费用。测试使用离线契约客户端；这不是新一轮云端质量实验，没有产生或宣称 Agent 质量提升。
