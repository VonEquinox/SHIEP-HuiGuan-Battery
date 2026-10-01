import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { type User, useData, percent } from "../api";
import {
  Badge,
  Empty,
  Field,
  Metric,
  Notice,
  Panel,
  LineChart,
  useAction,
} from "../components";
import {
  api,
  canResearch,
  canDiagnose,
  Evidence,
  listItems,
  numberValue,
  Provenance,
  State,
  textValue,
  useV2Data,
  V2Heading,
  V2Job,
  V2Read,
  Version,
} from "../v2";

export function V2Overview() {
  const r = useV2Data("/v2/overview", 5000),
    navigate = useNavigate(),
    d = r.data;
  return (
    <Panel
      title="V2 研究与诊断概览"
      subtitle="真实实验、自行合成、公开生成分别计数；碳核算独立进入。"
    >
      <V2Read resource={r}>
        <div className="metrics">
          <Metric
            label="未确认提案"
            value={numberValue(d?.open_proposals, 0)}
            note="调度员确认后才成为工单"
            onClick={() => navigate("/operations?tab=v2")}
          />
          <Metric
            label="待测轮次"
            value={numberValue(d?.pending_rounds, 0)}
            note="只显示已创建的授权轮次"
            onClick={() => navigate("/operations?tab=v2")}
          />
          <Metric
            label="失败作业"
            value={numberValue(d?.agent_runs?.failed, 0)}
            note="查看具体失败原因与请求版本"
            onClick={() => navigate("/system?tab=jobs")}
          />
          <Metric
            label="未支持预测头"
            value={numberValue(d?.unsupported_heads, 0)}
            note="缺标签或适用性不满足时不补零"
            onClick={() => navigate("/models")}
          />
        </div>
        <div className="v2-summary">
          <span>真实实验 {numberValue(d?.source_counts?.experimental, 0)}</span>
          <span>
            自行合成 {numberValue(d?.source_counts?.self_synthetic, 0)}
          </span>
          <span>
            公开生成 {numberValue(d?.source_counts?.public_generated, 0)}
          </span>
          <Version value={d?.context_version} label="Context" />
          <Link className="button" to="/carbon">
            独立碳与成本摘要
          </Link>
          <Link className="button" to="/risk">
            风险与群组
          </Link>
          <Link className="button" to="/evolution">
            Context 进化
          </Link>
        </div>
        <Evidence title="覆盖率、状态与统计口径" value={d} />
      </V2Read>
    </Panel>
  );
}

export function V2Sources({ user }: { user: User }) {
  const [cursor, setCursor] = useState<number | null>(null),
    [source, setSource] = useState<any>(null),
    [jobId, setJobId] = useState<number | null>(null),
    [ingestMode, setIngestMode] = useState("metadata"),
    [datasetId, setDatasetId] = useState("");
  const datasets = useData<any[]>("/datasets");
  const r = useV2Data(
      `/v2/sources?limit=30${cursor ? `&cursor=${cursor}` : ""}`,
      6000,
    ),
    action = useAction();
  return (
    <>
      <Panel
        title="多源数据与锁定划分"
        subtitle="来源登记与本任务可用物理对象分开；未核验许可或目标标签不会伪装为可训练。"
        actions={<button onClick={() => void r.reload()}>刷新来源</button>}
      >
        {action.feedback}
        <div className="v2-form-inline">
          <Field label="来源作业方式">
            <select
              value={ingestMode}
              onChange={(e) => setIngestMode(e.target.value)}
            >
              <option value="metadata">来源元数据校验（不下载原始数据）</option>
              <option value="registered_local">关联已登记本地数据</option>
            </select>
          </Field>
          {ingestMode === "registered_local" && (
            <Field label="关联已登记数据集">
              <select
                required
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
              >
                <option value="">选择已导入数据集</option>
                {datasets.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} / #{d.id}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        <V2Read resource={r}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>来源 / 类型</th>
                  <th>许可 / 状态</th>
                  <th>对象与样本</th>
                  <th>标签 / 域 / 划分</th>
                  <th>解析作业</th>
                </tr>
              </thead>
              <tbody>
                {listItems(r.data).map((raw) => {
                  const s = { ...raw.manifest, ...raw };
                  return (
                    <tr key={s.id}>
                      <td>
                        <strong>{s.name || s.source_id || s.id}</strong>
                        <Provenance
                          value={s.provenance || s.origin_type}
                          scenario={s.synthetic_scenario_id}
                        />
                        {s.landing_url && (
                          <a
                            href={s.landing_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            官方来源
                          </a>
                        )}
                      </td>
                      <td>
                        {textValue(s.license_status || s.license)}
                        <State value={s.status} reason={s.blocked_reason} />
                      </td>
                      <td>
                        登记{" "}
                        {numberValue(
                          s.physical_object_count ?? s.object_count,
                          0,
                        )}{" "}
                        个物理对象
                        <br />
                        本任务有效{" "}
                        {numberValue(
                          s.eligible_object_count ?? s.task_object_count,
                          0,
                        )}
                        <br />
                        清洗排除 {numberValue(s.excluded_count, 0)}
                      </td>
                      <td>
                        <Evidence
                          title="标签覆盖 / 域分布 / split 锁定"
                          value={{
                            label_coverage: s.label_coverage,
                            domains: s.domain_distribution || s.domains,
                            split: s.split || s.split_manifest,
                            hash: s.sha256,
                            analysis_cell_count: s.analysis_cell_count,
                          }}
                        />
                      </td>
                      <td>
                        <button onClick={() => setSource(s)}>
                          查看来源详情
                        </button>
                        <button
                          disabled={
                            !canResearch(user.role) ||
                            action.busy ||
                            (ingestMode === "registered_local" && !datasetId)
                          }
                          title={
                            !canResearch(user.role)
                              ? "仅管理员和研究员可提交导入"
                              : "由服务端校验来源与许可"
                          }
                          onClick={() =>
                            void action.run(async () => {
                              const result = await api(
                                `/v2/sources/${s.id}/ingest`,
                                "POST",
                                {
                                  mode: ingestMode,
                                  dataset_id:
                                    ingestMode === "registered_local"
                                      ? Number(datasetId)
                                      : undefined,
                                },
                              );
                              setJobId(result.job_id);
                              await r.reload();
                            }, "解析任务已提交")
                          }
                        >
                          {ingestMode === "metadata"
                            ? "更新来源元数据"
                            : "关联已登记数据"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!listItems(r.data).length && <Empty>尚未登记多源数据。</Empty>}
          <div className="actions">
            <button disabled={cursor == null} onClick={() => setCursor(null)}>
              第一页
            </button>
            <button
              disabled={r.data?.next_cursor == null}
              onClick={() => setCursor(r.data.next_cursor)}
            >
              下一页
            </button>
          </div>
        </V2Read>
        {!canResearch(user.role) && (
          <Notice>当前角色仅能查看来源，导入操作由服务端校验研究权限。</Notice>
        )}
        {source && (
          <Evidence
            title={`来源 ${source.name || source.id} 的完整记录`}
            value={source}
          />
        )}
      </Panel>
      <V2Job
        user={user}
        id={jobId}
        canCancel={canResearch(user.role)}
        onComplete={() => void r.reload()}
      />
    </>
  );
}

export function V2Models({ user }: { user: User }) {
  const r = useV2Data("/v2/models", 6000),
    sources = useData<any[]>("/datasets"),
    action = useAction();
  const [jobId, setJobId] = useState<number | null>(null),
    [task, setTask] = useState("training"),
    [sourceId, setSourceId] = useState(""),
    [runId, setRunId] = useState(""),
    [family, setFamily] = useState("M1"),
    [seed, setSeed] = useState(0),
    [ablation, setAblation] = useState("joint");
  return (
    <>
      <Panel
        title="M0 / M1 / M2 任务支持矩阵"
        subtitle="区间、密度、生存和越阈概率保持各自语义；不支持的任务也保留在表中。"
      >
        <V2Read resource={r}>
          <div className="v2-summary">
            {r.data?.families?.map((f: any) => (
              <span key={f.id}>
                <strong>{f.id}</strong> · {f.support}
              </span>
            ))}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>模型与版本</th>
                  <th>任务 / 目标</th>
                  <th>支持条件</th>
                  <th>按物理对象与域的评估</th>
                </tr>
              </thead>
              <tbody>
                {listItems(r.data).map((m) => (
                  <tr key={m.id}>
                    <td>
                      <strong>{m.name || m.family || m.id}</strong>
                      <Version value={m.version || m.artifact_hash} />
                      <State value={m.status} />
                    </td>
                    <td>
                      <Evidence
                        title="各预测头与目标定义"
                        value={
                          m.heads ||
                          m.task_support ||
                          m.support_matrix ||
                          m.tasks
                        }
                      />
                    </td>
                    <td>
                      {textValue(m.support || m.metadata?.support)}
                      <Evidence
                        title="模型适用条件 / 拒判"
                        value={m.conditions || m.metadata}
                      />
                    </td>
                    <td>
                      {JSON.stringify(m.metrics || {}).includes(
                        "unbounded_insufficient_calibration_objects",
                      ) && (
                        <Notice tone="warning">
                          校准对象不足，区间无界；不能将覆盖率 1.0
                          当作有效保证。
                        </Notice>
                      )}
                      <Evidence
                        title="域指标、校准方法和样本数"
                        value={m.metrics || m.evaluation || m.calibration}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!listItems(r.data).length && (
            <Empty>没有注册 V2 模型。任务能力由训练结果和合法标签确定。</Empty>
          )}
        </V2Read>
        <form
          className="v2-form-inline"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const result = await api("/v2/model-runs", "POST", {
                kind: `v2_${task}`,
                dataset_id: sourceId ? Number(sourceId) : undefined,
                run_id: task !== "training" ? runId : undefined,
                family,
                seed,
                ablation,
              });
              setJobId(result.job_id);
            }, "数值模型任务已提交");
          }}
        >
          <Field label="V2 模型族">
            <select value={family} onChange={(e) => setFamily(e.target.value)}>
              <option>M1</option>
              <option>M2</option>
            </select>
          </Field>
          <Field label="实验随机种子">
            <select
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            >
              {[0, 1, 2].map((i) => (
                <option key={i}>{i}</option>
              ))}
            </select>
          </Field>
          <Field label="实验消融配置">
            <select
              value={ablation}
              onChange={(e) => setAblation(e.target.value)}
            >
              {["joint", "no_domain_adapter", "no_history", "single_task"].map(
                (v) => (
                  <option key={v}>{v}</option>
                ),
              )}
            </select>
          </Field>
          <Field label="V2 任务类型">
            <select value={task} onChange={(e) => setTask(e.target.value)}>
              <option value="training">训练</option>
              <option value="calibration">校准</option>
              <option value="evaluation">评测</option>
            </select>
          </Field>
          <Field label="已导入数据集">
            <select
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
            >
              <option value="">选择来源</option>
              {listItems(sources.data).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name || s.source_id || s.id}
                </option>
              ))}
            </select>
          </Field>
          {task !== "training" && (
            <Field label="服务器登记的 V2 运行 ID">
              <input
                required
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
              />
            </Field>
          )}
          <button
            className="primary"
            disabled={!canResearch(user.role) || action.busy}
          >
            提交 V2 数值任务
          </button>
        </form>
        {action.feedback}
        {!canResearch(user.role) && (
          <Notice>当前角色不能训练、校准或修改模型。</Notice>
        )}
      </Panel>
      <V2Job
        user={user}
        id={jobId}
        canCancel={canResearch(user.role)}
        onComplete={() => void r.reload()}
      />
    </>
  );
}

function Distribution({ head }: { head: any }) {
  const distribution = head.distribution || {},
    record = head.parameters || distribution.parameters || {},
    params = head.params || record.params || distribution.params || {};
  const quantiles =
    distribution.quantiles ||
    head.quantiles ||
    record.quantiles ||
    params.quantiles;
  const kind =
    distribution.kind ||
    distribution.distribution_kind ||
    head.distribution_kind;
  const calibration = head.calibrated_interval || record.calibrated_interval;
  if (head.support === "unsupported")
    return (
      <Empty>{head.reason || "该任务没有合法标签或适用的数值模型。"}</Empty>
    );
  const grid =
      distribution.survival_grid ||
      params.grid ||
      params.survival_grid ||
      record.grid ||
      head.survival_grid ||
      [],
    survival = params.survival || record.survival || [];
  const points: { x: number; y: number }[] = Array.isArray(grid)
    ? grid
        .map((p: any, i: number) =>
          typeof p === "number"
            ? { x: p, y: survival[i] }
            : { x: p.time ?? p.cycle ?? p.x, y: p.survival ?? p.value ?? p.y },
        )
        .filter((p: any) => Number.isFinite(p.x) && Number.isFinite(p.y))
    : [];
  const maxX = Math.max(1, ...points.map((p) => p.x));
  const q: number[] = quantiles
    ? [quantiles["0.05"], quantiles["0.5"], quantiles["0.95"]]
    : [];
  const mu = params.location,
    scale = params.scale,
    density: { x: number; y: number }[] = [];
  if (
    ["lognormal", "logit_normal"].includes(kind) &&
    Number.isFinite(mu) &&
    Number.isFinite(scale) &&
    scale > 0
  ) {
    for (let i = 0; i <= 120; i++) {
      const z = -4 + i / 15,
        x =
          kind === "lognormal"
            ? Math.exp(mu + scale * z)
            : 1 / (1 + Math.exp(-mu - scale * z)),
        jacobian = kind === "lognormal" ? x : x * (1 - x);
      density.push({
        x,
        y: Math.exp((-z * z) / 2) / (Math.sqrt(2 * Math.PI) * scale * jacobian),
      });
    }
  }
  const densityMin = Math.min(...density.map((p) => p.x)),
    densityMax = Math.max(...density.map((p) => p.x)),
    maxDensity = Math.max(...density.map((p) => p.y));
  return (
    <>
      <p>
        输出类型：{textValue(kind)} · {head.unit || "单位未提供"}
      </p>
      {calibration &&
        (calibration.lower == null || calibration.upper == null) && (
          <Notice tone="warning">
            校准样本不足或域未校准，区间无界。覆盖率不能被解释为有效校准保证。
            <Evidence title="校准方法、范围与样本状态" value={calibration} />
          </Notice>
        )}
      {q.length === 3 && q.every(Number.isFinite) && (
        <div className="chart">
          <svg
            viewBox="0 0 520 90"
            role="img"
            aria-label={`${head.head} 分位带`}
          >
            <line
              x1="35"
              x2="485"
              y1="35"
              y2="35"
              stroke="var(--accent)"
              strokeWidth="9"
              opacity="0.25"
            />
            <circle
              cx={35 + (450 * (q[1] - q[0])) / Math.max(1e-12, q[2] - q[0])}
              cy="35"
              r="5"
              fill="var(--accent)"
            />
            {q.map((v, i) => (
              <text
                key={i}
                x={i === 0 ? 35 : i === 1 ? 230 : 450}
                y="65"
                fontSize="11"
              >
                q{[5, 50, 95][i]}{" "}
                {head.unit === "ratio"
                  ? `${(100 * v).toFixed(2)}%`
                  : numberValue(v)}
              </text>
            ))}
          </svg>
        </div>
      )}
      {density.length > 0 && (
        <div className="chart">
          <svg
            viewBox="0 0 520 150"
            role="img"
            aria-label={`${head.head} 参数密度`}
          >
            <polyline
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              points={density
                .map(
                  (p) =>
                    `${25 + (470 * (p.x - densityMin)) / (densityMax - densityMin)},${130 - (110 * p.y) / maxDensity}`,
                )
                .join(" ")}
            />
            <text x="25" y="145" fontSize="10">
              {numberValue(densityMin)}
            </text>
            <text x="450" y="145" fontSize="10">
              {numberValue(densityMax)}
            </text>
          </svg>
          <p>
            按登记分布参数计算密度；图窗为变换域 ±4 个尺度，完整尾部由参数定义。
          </p>
        </div>
      )}
      {points.length > 0 && (
        <div className="chart">
          <svg
            viewBox="0 0 520 150"
            role="img"
            aria-label={`${head.head || head.name} 生存曲线`}
          >
            <line x1="25" x2="495" y1="130" y2="130" stroke="var(--line)" />
            <polyline
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              points={points
                .map((p) => `${25 + (470 * p.x) / maxX},${130 - 110 * p.y}`)
                .join(" ")}
            />
            <text x="25" y="146" fontSize="10">
              0 {head.unit}
            </text>
            <text x="450" y="146" fontSize="10">
              {maxX}
            </text>
          </svg>
        </div>
      )}
      <Evidence title="完整分布、条件与依据" value={head} />
    </>
  );
}

export function V2Prediction({
  user,
  detail = false,
}: {
  user: User;
  detail?: boolean;
}) {
  const params = useParams(),
    [search] = useSearchParams(),
    assets = useData<any[]>("/assets"),
    navigate = useNavigate();
  const [assetId, setAssetId] = useState(
      params.id || search.get("asset") || "",
    ),
    [cutoff, setCutoff] = useState(""),
    [packageId, setPackageId] = useState(""),
    [rowIndex, setRowIndex] = useState(""),
    [jobId, setJobId] = useState<number | null>(null);
  const packages = useV2Data(
      user.role !== "technician" ? "/v2/model-packages" : "",
    ),
    action = useAction();
  const assetDetail = useData<any>(assetId ? `/assets/${assetId}` : "");
  const profile = useV2Data(
    assetId
      ? `/v2/assets/${assetId}/prediction-profile${cutoff ? `?cutoff=${encodeURIComponent(new Date(cutoff).toISOString())}` : ""}`
      : "",
  );
  useEffect(() => {
    if (params.id) setAssetId(params.id);
  }, [params.id]);
  const p = profile.data,
    rawPrediction = useData<any>(
      p?.prediction_id ? `/predictions/${p.prediction_id}` : "",
    ),
    heads = Array.isArray(p?.heads)
      ? p.heads
      : Object.entries(p?.heads || {}).map(([head, value]) => ({
          head,
          ...(value as any),
        }));
  return (
    <>
      {detail && (
        <V2Heading
          title="安装身份与预测详情"
          subtitle="同一槽位的旧安装历史与当前安装分别查看。"
        />
      )}
      <Panel
        title="多头概率预测与拒判"
        subtitle="缺失值保持 null；区间不自动解释为完整密度，越阈概率显示指定 H。"
      >
        <div className="v2-form-inline">
          <Field label="查看 V2 资产">
            <select
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
            >
              <option value="">选择资产</option>
              {assets.data
                ?.filter((a) => a.kind === "cell")
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} / #{a.id}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="可见数据截止时间">
            <input
              type="datetime-local"
              value={cutoff}
              onChange={(e) => setCutoff(e.target.value)}
            />
          </Field>
          <button disabled={!assetId} onClick={() => void profile.reload()}>
            刷新各头
          </button>
          <button
            disabled={!assetId || !canDiagnose(user.role)}
            onClick={() =>
              navigate(
                `/diagnosis/new?asset=${assetId}${cutoff ? `&cutoff=${encodeURIComponent(new Date(cutoff).toISOString())}` : ""}`,
              )
            }
          >
            发起诊断
          </button>
          {assetId && (
            <Link className="button" to={`/assets/${assetId}`}>
              安装详情
            </Link>
          )}
        </div>
        {assetId && user.role !== "technician" && (
          <form
            className="v2-form-inline"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api(`/v2/assets/${assetId}/v2-binding`, "POST", {
                  version: assetDetail.data.version,
                  installation_id: p.installation_id,
                  package_id: packageId,
                  row_index: Number(rowIndex),
                });
                await assetDetail.reload();
                const response = await api("/v2/model-runs", "POST", {
                  kind: "v2_inference",
                  asset_id: Number(assetId),
                });
                setJobId(response.job_id);
              }, "实验回放绑定已保存，真实数值推理已提交");
            }}
          >
            <Field label="已验证的安全模型包">
              <select
                required
                value={packageId}
                onChange={(e) => setPackageId(e.target.value)}
              >
                <option value="">选择服务器验证过的包</option>
                {listItems(packages.data).map((item) => (
                  <option key={item.package_id} value={item.package_id}>
                    {item.package_id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="开发集源物理对象与观测">
              <select
                required
                value={rowIndex}
                onChange={(e) => setRowIndex(e.target.value)}
              >
                <option value="">选择已登记的源观测</option>
                {packages.data?.feature_rows?.map((row: any) => (
                  <option key={row.row_index} value={row.row_index}>
                    {row.physical_cell_id} / #{row.row_index} / {row.split} /
                    {typeof row.visible_cutoff === "number"
                      ? ` 源截止序号 ${row.visible_cutoff}`
                      : ` 源截止 ${textValue(row.visible_cutoff)}`}
                  </option>
                ))}
              </select>
            </Field>
            <button
              className="primary"
              title={
                !canResearch(user.role)
                  ? "仅管理员与研究员可执行数值模型作业"
                  : "由服务端校验资产版本、模型包与源物理身份"
              }
              disabled={
                !canResearch(user.role) ||
                !p?.installation_id ||
                !assetDetail.data?.version ||
                !listItems(packages.data).length ||
                action.busy
              }
            >
              绑定实验回放并执行 V2 推理
            </button>
            <Evidence
              title="包版本、域、哈希与实验身份"
              value={listItems(packages.data).find(
                (item) => item.package_id === packageId,
              )}
            />
          </form>
        )}
        {action.feedback}
        <V2Job
          user={user}
          id={jobId}
          canCancel={canResearch(user.role)}
          onComplete={() => void profile.reload()}
        />
        {assetId && (
          <Notice>
            源观察在模拟槽位上回放，不证明该槽位已有 BMS
            实测。改变物理电芯须登记更换，不能混合旧安装历史。
          </Notice>
        )}
        {packages.error && user.role !== "technician" && (
          <Notice tone="error">{packages.error.message}</Notice>
        )}
        {packages.data && !listItems(packages.data).length && (
          <Notice>没有可重新加载的登记安全包，实验回放绑定暂不可用。</Notice>
        )}
        {!assetId ? (
          <Empty>请选择资产，查看服务端计算的预测头。</Empty>
        ) : (
          <V2Read resource={profile}>
            <div className="v2-summary">
              <span>安装身份 {textValue(p?.installation_id)}</span>
              <span>
                体系 / 协议 {textValue(p?.chemistry || p?.query?.chemistry)} /{" "}
                {textValue(
                  p?.protocol || p?.protocol_id || p?.query?.protocol_id,
                )}
              </span>
              {p?.query?.physical_cell_id && (
                <span>源物理对象 {p.query.physical_cell_id}</span>
              )}
              {(p?.query?.query_time != null ||
                p?.query?.visible_cutoff != null) && (
                <span>
                  源观测 / 源截止 {textValue(p?.query?.query_time)} /{" "}
                  {textValue(p?.query?.visible_cutoff)}{" "}
                  {p?.query?.time_basis === "source_record_ordinal" &&
                    "（源记录序号，非现场时间）"}
                </span>
              )}
              <Version
                value={
                  p?.model_version ||
                  p?.model_id ||
                  p?.heads?.find((h: any) => h.model_version)?.model_version
                }
                label="模型"
              />
              <State value={p?.status} stale={p?.stale} />
            </div>
            <div className="v2-head-grid">
              {heads.map((head: any) => (
                <article className="v2-head" key={head.head}>
                  <h3>{head.head || head.name}</h3>
                  <State value={head.support} reason={head.reason} />
                  <strong>
                    {head.support === "unsupported" || head.value == null
                      ? "未支持 / 未提供"
                      : head.unit === "ratio" || head.unit === "probability"
                        ? percent(head.value)
                        : `${numberValue(head.value)} ${head.unit || ""}`}
                  </strong>
                  <p>
                    目标{" "}
                    {textValue(
                      head.target_definition_id || head.target_definition,
                    )}
                    {head.horizon != null && ` · H=${textValue(head.horizon)}`}
                  </p>
                  <Version value={head.calibration_version} label="校准" />
                  <Distribution head={head} />
                </article>
              ))}
            </div>
            {!heads.length && (
              <Empty>尚未生成预测。后台没有提供数值时不会补零。</Empty>
            )}
            <Evidence
              title="安装历史、原始片段与支持条件"
              value={{ profile: p, asset: assetDetail.data }}
            />
            {rawPrediction.data?.input_snapshot && (
              <>
                <LineChart
                  values={
                    rawPrediction.data.input_snapshot.current
                      ?.slice(16, 32)
                      .map((v: number) => v * 100) || []
                  }
                  secondary={rawPrediction.data.input_snapshot.reference
                    ?.slice(16, 32)
                    .map((v: number) => v * 100)}
                  title="原始充电片段 / 电压区间电量占比 %"
                />
                <Evidence
                  title="可见片段输入快照（标签不作为诊断事实）"
                  value={{
                    sample_key: rawPrediction.data.input_snapshot.sample_key,
                    current: rawPrediction.data.input_snapshot.current,
                    reference: rawPrediction.data.input_snapshot.reference,
                  }}
                />
              </>
            )}
          </V2Read>
        )}
      </Panel>
    </>
  );
}

export function V2System({ user }: { user: User }) {
  const r = useV2Data("/v2/overview", 5000),
    jobs = useData<any[]>("/jobs", 4000);
  return (
    <Panel
      title="V2 服务连接与后台作业"
      subtitle="云端 LLM 凭证仅在服务器配置；页面不保存或显示测试 Key。"
    >
      <V2Read resource={r}>
        <div className="v2-summary">
          <span>
            生产连接{" "}
            {r.data?.production_connected === true ? "已连接" : "未连接"}
          </span>
          <Version value={r.data?.context_version} label="活动 Context" />
          <Badge value={user.role} />
        </div>
        <Evidence
          title="服务器连接与能力状态"
          value={
            r.data?.connections ||
            r.data?.capabilities || {
              agent: r.data?.agent_runs,
              model: r.data?.model_runs,
            }
          }
        />
      </V2Read>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>任务</th>
              <th>类型</th>
              <th>状态</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data
              ?.filter((j) =>
                /agent|carbon|evolution|dispatch|v2|model_run|source/.test(
                  j.kind,
                ),
              )
              .map((j) => (
                <tr key={j.id}>
                  <td>#{j.id}</td>
                  <td>{j.kind}</td>
                  <td>
                    <State value={j.status} />
                  </td>
                  <td>{j.error || "—"}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <Notice>
        角色与生产模式由服务端权限决定。普通用户不能开启自动审批或生产控制。
      </Notice>
      <Link className="button" to="/carbon">
        管理独立碳因子与规则
      </Link>
    </Panel>
  );
}
