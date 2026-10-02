import { useState } from "react";
import { type User } from "../api";
import type {
  ExperimentMetricsContract,
  ExperimentMetricDefinition,
} from "../contracts/v2";
import {
  metricMeasurement,
  metricSeries,
  metricValue,
} from "../experimentMetrics";
import {
  Empty,
  Field,
  LineChart,
  Notice,
  Panel,
  useAction,
} from "../components";
import {
  api,
  canResearch,
  Evidence,
  listItems,
  Provenance,
  State,
  textValue,
  useV2Data,
  V2Heading,
  V2Job,
  V2Read,
  Version,
} from "../v2";

export function Evolution({ user }: { user: User }) {
  const skills = useV2Data("/v2/skills?limit=100", 5000),
    memories = useV2Data("/v2/memories?limit=100", 5000),
    runs = useV2Data("/v2/evolution/runs?limit=100", 5000),
    contexts = useV2Data("/v2/context-snapshots?limit=100", 5000),
    overview = useV2Data("/v2/overview");
  const [method, setMethod] = useState("ace"),
    [caseIds, setCaseIds] = useState(""),
    [budget, setBudget] = useState(20),
    [jobId, setJobId] = useState<number | null>(null),
    [left, setLeft] = useState(""),
    [right, setRight] = useState(""),
    [metric, setMetric] = useState("grounded_assertion_ratio"),
    [rollback, setRollback] = useState(""),
    [reason, setReason] = useState("");
  const action = useAction(),
    snapshots = listItems(contexts.data),
    base = overview.data?.context_version ?? 0;
  const runItems = listItems(runs.data),
    contract = runs.data?.metrics_contract as
      ExperimentMetricsContract | undefined,
    definitions =
      contract?.schema_version === "experiment-metrics.v1"
        ? contract.definitions
        : [],
    selectedMetric = definitions.find(
      (definition) => definition.key === metric,
    ),
    series = selectedMetric
      ? metricSeries(runItems as any, selectedMetric)
      : [];
  return (
    <>
      <V2Heading
        title="Context 自动进化"
        subtitle="查看 Memory / Skill 改动、固定预算实验与失败回滚；更新不进入强制专家批准队列。"
      >
        <button
          onClick={() => {
            void skills.reload();
            void memories.reload();
            void runs.reload();
            void contexts.reload();
          }}
        >
          刷新进化记录
        </button>
      </V2Heading>
      <div className="two-col">
        <Panel title="Skill 版本与修改内容">
          <V2Read resource={skills}>
            {listItems(skills.data).map((s) => (
              <article className="v2-record" key={s.id || s.skill_id}>
                <h3>{s.name || s.skill_id || s.id}</h3>
                <div className="v2-summary">
                  <State value={s.status || s.state} />
                  <Version value={s.version} />
                  <Provenance value={s.provenance || s.origin} />
                </div>
                <p>{s.routing_description || s.content?.routing_description}</p>
                <Evidence
                  title="具体段落、证据要求与版本差异"
                  value={s.instructions || s.content || s}
                />
                <Evidence
                  title="反馈来源 / 冲突 / 反例"
                  value={
                    s.diff ||
                    s.changes || {
                      sources: s.source_refs,
                      conflicts: s.conflicts,
                      counterexamples: s.counterexamples,
                    }
                  }
                />
              </article>
            ))}
            {!listItems(skills.data).length && (
              <Empty>没有已登记 Skill。</Empty>
            )}
          </V2Read>
        </Panel>
        <Panel title="Memory、冲突与来源">
          <V2Read resource={memories}>
            {listItems(memories.data).map((m) => (
              <article className="v2-record" key={m.id}>
                <h3>{m.title || m.type || `Memory #${m.id}`}</h3>
                <State value={m.status || m.state} />
                <Version value={m.version || m.base_version} />
                <p>{m.claim || m.insight || m.content?.claim || m.summary}</p>
                <details>
                  <summary>展开原始反馈</summary>
                  <p>
                    {m.raw_feedback ||
                      m.free_text ||
                      m.content?.raw_feedback ||
                      "原始反馈在关联来源记录中。"}
                  </p>
                </details>
                <Evidence title="修正断言、证据引用与适用边界" value={m} />
              </article>
            ))}
            {!listItems(memories.data).length && (
              <Empty>尚无从反馈提取的 Memory。</Empty>
            )}
          </V2Read>
        </Panel>
      </div>
      <Panel
        title="Context 版本对比"
        subtitle="展示新增、删除与更改的真实内容；冲突不会静默覆盖。"
      >
        <div className="form-grid">
          <Field label="基准 Context 版本">
            <select value={left} onChange={(e) => setLeft(e.target.value)}>
              <option value="">选择版本</option>
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} · v{s.version || s.context_version}
                </option>
              ))}
            </select>
          </Field>
          <Field label="对照 Context 版本">
            <select value={right} onChange={(e) => setRight(e.target.value)}>
              <option value="">选择版本</option>
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} · v{s.version || s.context_version}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {left && right ? (
          <ContextDiff
            left={snapshots.find((s) => String(s.id) === left)}
            right={snapshots.find((s) => String(s.id) === right)}
          />
        ) : (
          <Empty>选择两个保存的 Context 快照。</Empty>
        )}
      </Panel>
      <Panel
        title="固定预算离线实验"
        subtitle="ACE、Reflexion、GEPA、固定 Context、无 Memory 按同一案例预算比较。"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const result = await api("/v2/evolution/experiments", "POST", {
                method,
                base_version: base,
                case_ids: caseIds
                  .split(",")
                  .map((v) => v.trim())
                  .filter(Boolean),
                split: "dev",
                max_rollouts: budget,
                activate: false,
              });
              setJobId(result.job_id);
              await runs.reload();
            }, "离线实验已提交，不更改活动 Context");
          }}
        >
          <div className="form-grid">
            <Field label="进化实验方法">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                {["ace", "reflexion", "gepa", "fixed", "no_memory"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="评测案例 ID（逗号分隔）">
              <input
                required
                value={caseIds}
                onChange={(e) => setCaseIds(e.target.value)}
              />
            </Field>
            <Field label="最大回放预算">
              <input
                type="number"
                min={1}
                max={200}
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
            </Field>
            <Field label="实验指标">
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                {definitions.map((definition) => (
                  <option key={definition.key} value={definition.key}>
                    {definition.label} · {definition.unit}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button
            className="primary"
            disabled={!canResearch(user.role) || action.busy}
          >
            提交离线进化实验
          </button>
        </form>
        {action.feedback}
        <V2Read resource={runs}>
          {selectedMetric &&
            series.map(([key, group]) => (
              <div
                key={key}
                data-testid="experiment-series"
                data-protocol={group.protocol.protocol_id}
                data-split={group.protocol.split}
                data-method={group.protocol.method}
              >
                <Provenance value={group.protocol.provenance} />
                <LineChart
                  values={group.points.map((point) => point.value)}
                  labels={group.points.map((point) => String(point.id))}
                  title={`${selectedMetric.label} / ${group.protocol.protocol_version} / ${group.protocol.split} / ${group.protocol.method} / ${group.protocol.provenance} / ${selectedMetric.unit}`}
                />
                <p>
                  协议 {group.protocol.protocol_id.slice(0, 12)} · 口径{" "}
                  {group.protocol.metric_version} · 案例集{" "}
                  {group.protocol.cohort_sha256.slice(0, 12)}
                </p>
                <p>
                  实际执行：
                  {group.protocol.execution_modes?.join(" / ") || "未记录"}
                  {group.protocol.llm_models?.length
                    ? ` · 云模型 ${group.protocol.llm_models.join(" / ")}`
                    : ""}
                </p>
                <p>
                  仅连接协议、分割、方法、来源、案例集和指标口径一致的实验；保留实际下降。
                </p>
                <ul>
                  {group.points.map((point) => (
                    <li key={point.id}>
                      实验 #{point.id}：
                      {metricValue(point.value, selectedMetric)}{" "}
                      {selectedMetric.unit}
                      {selectedMetric.denominator_label &&
                        ` · ${selectedMetric.denominator_label} ${point.denominator ?? "未记录"}`}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          {!series.length && (
            <Empty>
              {selectedMetric?.unsupported_reason ||
                "暂无符合当前指标契约的实测数据。未测量的字段标为 unsupported。"}
            </Empty>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>实验 / 方法</th>
                  <th>状态 / 版本</th>
                  <th>当前指标 / 分母</th>
                  <th>结果与失败</th>
                </tr>
              </thead>
              <tbody>
                {runItems.map((run) => (
                  <tr key={run.id} data-testid={`experiment-run-${run.id}`}>
                    <td>
                      #{run.id} {run.method}
                      <Provenance value={run.provenance} />
                    </td>
                    <td>
                      <State value={run.status} />
                      <Version value={run.base_context_version} />
                    </td>
                    <td>
                      {selectedMetric ? (
                        <ExperimentMeasurement
                          run={run}
                          definition={selectedMetric}
                        />
                      ) : (
                        "unsupported · 指标契约未提供"
                      )}
                    </td>
                    <td>
                      <Evidence
                        title="预算、盲评、指标、差异与回滚"
                        value={run}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </V2Read>
      </Panel>
      <Panel
        title="恢复已验证的 Context 快照"
        subtitle="回滚使用活动 base_version 校验，版本冲突时刷新并重新审阅。"
      >
        <form
          className="v2-form-inline"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await api("/v2/context-snapshots/rollback", "POST", {
                base_version: base,
                snapshot_id: Number(rollback),
                reason,
              });
              await overview.reload();
              await contexts.reload();
              await skills.reload();
            }, "已记录 Context 回滚");
          }}
        >
          <Field label="需要恢复的快照">
            <select
              required
              value={rollback}
              onChange={(e) => setRollback(e.target.value)}
            >
              <option value="">选择保存快照</option>
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} v{s.version || s.context_version}
                </option>
              ))}
            </select>
          </Field>
          <Field label="回滚原因">
            <input
              required
              minLength={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <button disabled={!canResearch(user.role) || action.busy}>
            执行版本校验与回滚
          </button>
        </form>
      </Panel>
      <V2Job
        user={user}
        id={jobId}
        canCancel={canResearch(user.role)}
        onComplete={() => {
          void runs.reload();
          void contexts.reload();
        }}
      />
      <Notice>
        进化只能修改允许的说明、路由和证据要求。工具
        schema、审批权限、安全约束、数据划分与碳方法仍由服务器固定。
      </Notice>
    </>
  );
}
function ExperimentMeasurement({
  run,
  definition,
}: {
  run: any;
  definition: ExperimentMetricDefinition;
}) {
  const measurement = metricMeasurement(run, definition);
  return measurement.value === null ? (
    <span>unsupported · {measurement.reason}</span>
  ) : (
    <span>
      {metricValue(measurement.value, definition)} {definition.unit}
      <br />
      {definition.denominator_label &&
        `${definition.denominator_label}：${measurement.denominator ?? "未记录"}`}
    </span>
  );
}
function ContextDiff({ left, right }: { left: any; right: any }) {
  const a = JSON.stringify(
      left?.content || left?.context || left?.payload || left,
      null,
      2,
    ).split("\n"),
    b = JSON.stringify(
      right?.content || right?.context || right?.payload || right,
      null,
      2,
    ).split("\n");
  const leftOnly = a.filter((line) => !b.includes(line)),
    rightOnly = b.filter((line) => !a.includes(line));
  return (
    <div className="two-col">
      <div className="v2-diff removed">
        <h3>基准中被更改 / 移除的内容</h3>
        <pre>{leftOnly.join("\n") || "无差异"}</pre>
      </div>
      <div className="v2-diff added">
        <h3>对照中新增 / 更改的内容</h3>
        <pre>{rightOnly.join("\n") || "无差异"}</pre>
      </div>
    </div>
  );
}
