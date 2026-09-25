import { useEffect, useState } from "react";
import { ModelComparison } from "./ModelComparison";
import { useSearchParams } from "react-router-dom";
import {
  Play,
  Plus,
  Network,
  ShieldCheck,
  Clock,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import {
  api,
  useData,
  type Row,
  type User,
  date,
  percent,
  labels,
} from "../api";
import {
  Panel,
  Notice,
  Empty,
  Spinner,
  Badge,
  Modal,
  Field,
  Hash,
  ResultMetrics,
  LineChart,
  useAction,
} from "../components";

export function JobDetail({
  id,
  onClose,
  user,
}: {
  id: number;
  onClose: () => void;
  user: User;
}) {
  const job = useData<Row>("/jobs/" + id, 2000),
    action = useAction();
  const j = job.data;
  return (
    <Modal title={"计算任务 #" + id} onClose={onClose} wide>
      {j ? (
        <>
          {action.feedback}
          <div className="detail-grid">
            <div>
              <small>任务类型</small>
              <strong>{labels[j.kind]}</strong>
            </div>
            <div>
              <small>执行状态</small>
              <Badge value={j.status} />
            </div>
            <div>
              <small>开始 / 完成</small>
              <strong>
                {date(j.started_at)} / {date(j.finished_at)}
              </strong>
            </div>
            <div>
              <small>实际进度</small>
              <strong>{j.progress}%</strong>
            </div>
          </div>
          <div className="job-progress">
            <i style={{ width: j.progress + "%" }} />
          </div>
          {["queued", "running"].includes(j.status) &&
            ["admin", "researcher"].includes(user.role) &&
            (user.role === "admin" || j.created_by === user.id) && (
              <button
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    await api("/jobs/" + id + "/cancel", "POST");
                    await job.reload();
                  }, "取消请求已提交")
                }
              >
                取消任务
              </button>
            )}
          {j.error && <Notice tone="error">{j.error}</Notice>}
          {j.result?.dataset_id && (
            <Notice tone="success">
              已导入数据集 #{j.result.dataset_id}：{j.result.rows} 条样本 /{" "}
              {j.result.cells} 个电芯。
            </Notice>
          )}
          {j.result?.model_id && (
            <Notice tone="success">
              已保存新模型 #{j.result.model_id}
              。训练与验证电芯隔离，未触及原始保护测试集。
            </Notice>
          )}
          {j.result?.metrics && <ResultMetrics metrics={j.result.metrics} />}
          <h3 className="section-title">执行日志</h3>
          <div className="log-view">
            {j.logs.length ? (
              j.logs
                .slice()
                .reverse()
                .map((l: Row) => (
                  <div key={l.id}>
                    <span>{date(l.at)}</span> {l.message}
                  </div>
                ))
            ) : (
              <span>等待计算进程输出，不生成假进度。</span>
            )}
          </div>
        </>
      ) : (
        <Spinner />
      )}
    </Modal>
  );
}

export function ModelCenter({ user }: { user: User }) {
  const models = useData<Row[]>("/models", 4000),
    jobs = useData<Row[]>("/jobs", 2000),
    datasets = useData<Row[]>("/datasets", 4000),
    assets = useData<Row[]>("/assets");
  const [params] = useSearchParams();
  const [jobId, setJobId] = useState(Number(params.get("job")) || 0),
    [detail, setDetail] = useState<Row | null>(null);
  const [kind, setKind] = useState("inference"),
    [datasetId, setDatasetId] = useState(0),
    [modelId, setModelId] = useState(0),
    [cell, setCell] = useState(""),
    [assetId, setAssetId] = useState(Number(params.get("asset")) || 0),
    [trees, setTrees] = useState(100),
    [leaf, setLeaf] = useState(3);
  const action = useAction();
  const source = useData(
    datasetId ? `/datasets/${datasetId}/samples?limit=1` : "",
  );
  const edit = ["admin", "researcher"].includes(user.role);
  useEffect(() => {
    if (!datasetId && datasets.data?.length) setDatasetId(datasets.data[0].id);
  }, [datasets.data, datasetId]);
  useEffect(() => {
    if (!modelId && models.data?.length)
      setModelId(
        models.data.find((m) => m.kind === "frozen_et")?.id ||
          models.data[0].id,
      );
  }, [models.data, modelId]);
  useEffect(() => {
    const a = assets.data?.find((a) => a.id === assetId);
    if (a?.dataset_id) {
      setDatasetId(a.dataset_id);
      setCell(a.source_cell_id);
    }
  }, [assetId, assets.data]);
  const selectedModel = models.data?.find((m) => m.id === modelId);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MODEL LIFECYCLE</div>
          <h1>模型中心</h1>
          <p>训练、评估、推理彼此独立；每次计算都有版本与数据血缘。</p>
        </div>
        <button
          disabled={!edit || action.busy}
          onClick={() =>
            void action.run(async () => {
              await api("/models/register-frozen", "POST");
              await models.reload();
            }, "模型已注册")
          }
        >
          <Plus size={16} />
          注册冻结研究模型
        </button>
      </div>
      {action.feedback}
      {models.error && <Notice tone="error">{models.error}</Notice>}
      <div className="model-grid">
        {models.data?.map((m) => (
          <Panel key={m.id} className="model-card">
            <div className="model-card-top">
              <span className="model-icon">
                <Network size={23} />
              </span>
              <Badge value={m.artifact_present ? m.status : "failed"}>
                {m.artifact_present ? labels[m.status] : "文件缺失"}
              </Badge>
            </div>
            <h3>{m.name}</h3>
            <p>
              {m.kind === "frozen_hybrid"
                ? "全量上下文 · 3 种子 × 8 视图 · 等权融合"
                : m.kind === "frozen_et"
                  ? "冻结快速分支 · 三种子树集成"
                  : "新训练版本 · 物理电芯分组验证"}
            </p>
            <div className="model-score">
              <strong>{m.metrics.cell_macro_mae_pp?.toFixed(4) ?? "—"}</strong>
              <span>
                MAE / SOH 百分点
                <small>{labels[m.metrics.scope] || m.metrics.scope}</small>
              </span>
            </div>
            <div className="card-actions">
              <button onClick={() => setDetail(m)}>版本详情</button>
              <button
                className="primary"
                disabled={
                  !edit || m.status !== "enabled" || !m.artifact_present
                }
                onClick={() => {
                  setModelId(m.id);
                  document
                    .getElementById("job-form")
                    ?.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
              >
                选择推理
              </button>
            </div>
          </Panel>
        ))}
      </div>
      {!models.data?.length && (
        <Panel>
          <Empty>尚未注册模型。原始冻结产物将以只读方式接入。</Empty>
        </Panel>
      )}
      <Panel
        title="创建计算任务"
        subtitle="独立进程执行，服务器持久化队列；推理不会阻塞其他业务。"
        className="job-form-panel"
      >
        <form
          id="job-form"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const r = await api("/jobs", "POST", {
                kind,
                dataset_id: datasetId,
                model_id: kind === "training" ? null : modelId,
                cell_id: kind === "training" ? null : cell || null,
                asset_id: kind === "training" ? null : assetId || null,
                sample_ids: [],
                n_estimators: trees,
                min_samples_leaf: leaf,
              });
              setJobId(r.job_id);
              await jobs.reload();
            }, "任务已进入真实计算队列");
          }}
        >
          <div className="form-grid four">
            <Field label="任务类型">
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  if (e.target.value === "training") {
                    setCell("");
                    setAssetId(0);
                  }
                }}
              >
                <option value="inference">模型推理 → 健康事件</option>
                <option value="evaluation">评估已有模型</option>
                <option value="training">训练 ExtraTrees 新版本</option>
              </select>
            </Field>
            <Field label="数据集">
              <select
                required
                value={datasetId || ""}
                onChange={(e) => {
                  setDatasetId(Number(e.target.value));
                  setCell("");
                  setAssetId(0);
                }}
              >
                <option value="">请选择数据集</option>
                {datasets.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
            {kind !== "training" ? (
              <>
                <Field label="明确选择模型">
                  <select
                    required
                    value={modelId || ""}
                    onChange={(e) => setModelId(Number(e.target.value))}
                  >
                    <option value="">请选择模型</option>
                    {models.data
                      ?.filter((m) => m.status === "enabled")
                      .map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="源电芯 / 最多256条有序样本">
                  <select
                    value={cell}
                    onChange={(e) => {
                      setCell(e.target.value);
                      setAssetId(0);
                    }}
                  >
                    <option value="">全部电芯（前256条）</option>
                    {source.data?.cells.map((c: Row) => (
                      <option key={c.cell_id} value={c.cell_id}>
                        {c.cell_id}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            ) : (
              <>
                <Field label="每种子树数量">
                  <input
                    type="number"
                    min={30}
                    max={300}
                    value={trees}
                    onChange={(e) => setTrees(Number(e.target.value))}
                  />
                </Field>
                <Field label="叶节点最小样本">
                  <input
                    type="number"
                    min={1}
                    max={16}
                    value={leaf}
                    onChange={(e) => setLeaf(Number(e.target.value))}
                  />
                </Field>
              </>
            )}
          </div>
          {kind !== "training" && (
            <Field label="可选：指定已绑定模拟槽位">
              <select
                value={assetId}
                onChange={(e) => setAssetId(Number(e.target.value))}
              >
                <option value={0}>未指定：仅使用无歧义的显式回放绑定</option>
                {assets.data
                  ?.filter(
                    (a) => a.kind === "cell" && a.dataset_id === datasetId,
                  )
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} / {a.source_cell_id}
                    </option>
                  ))}
              </select>
            </Field>
          )}
          <Notice>
            {kind === "training"
              ? "创建独立模型版本，使用确定性电芯级训练/验证划分和训练期标准化；固定三个种子，不接触研究保护测试集。"
              : selectedModel?.kind === "frozen_hybrid"
                ? "完整混合模型需要重新建立全量上下文缓存，通常明显慢于快速分支；不会静默降级，资源不足将明确失败。"
                : "快速分支是独立选择的真实模型，不冒充完整混合模型。冻结模型在开发电芯上的评估必须标注为含训练样本。"}
          </Notice>
          <div className="form-footer">
            <span>
              {source.data?.total || 0} 条可选记录 ·{" "}
              {source.data?.cells?.length || 0} 个开发电芯
            </span>
            <button
              className="primary"
              disabled={
                !edit ||
                action.busy ||
                !datasetId ||
                (kind !== "training" && !modelId)
              }
            >
              <Play size={16} />
              提交真实计算任务
            </button>
          </div>
        </form>
      </Panel>
      <ModelComparison />
      <Panel
        title="任务与运行记录"
        subtitle="失败、中断、取消都会留档；没有假成功或固定预测兜底。"
        actions={
          <button onClick={() => void jobs.reload()}>
            <RefreshCw size={14} />
            刷新
          </button>
        }
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>编号</th>
                <th>任务</th>
                <th>状态</th>
                <th>进度</th>
                <th>创建时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {jobs.data?.map((j) => (
                <tr key={j.id}>
                  <td>JOB-{j.id.toString().padStart(4, "0")}</td>
                  <td>{labels[j.kind]}</td>
                  <td>
                    <Badge value={j.status} />
                  </td>
                  <td>
                    <div className="inline-progress">
                      <i style={{ width: j.progress + "%" }} />
                    </div>
                    {j.progress}%
                  </td>
                  <td>{date(j.created_at)}</td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setJobId(j.id)}
                    >
                      日志与结果
                      <ChevronRight size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!jobs.data?.length && <Empty />}
      </Panel>
      {jobId > 0 && (
        <JobDetail
          id={jobId}
          user={user}
          onClose={() => {
            setJobId(0);
            void models.reload();
          }}
        />
      )}
      {detail && (
        <Modal title="模型版本与适用边界" wide onClose={() => setDetail(null)}>
          <h3>{detail.name}</h3>
          <div className="detail-grid">
            <div>
              <small>模型ID / 类型</small>
              <strong>
                #{detail.id} / {detail.kind}
              </strong>
            </div>
            <div>
              <small>权重 SHA256</small>
              <Hash value={detail.artifact_hash} />
            </div>
            <div>
              <small>训练电芯</small>
              <strong>{detail.train_cells.length} 个</strong>
            </div>
            <div>
              <small>状态</small>
              <Badge value={detail.status} />
            </div>
          </div>
          <Notice>
            {detail.metadata.model_card ||
              "平台内模型实验；不构成独立公开基准或工业现场验收。"}
            。无 RUL、无校准安全概率。
          </Notice>
          <ResultMetrics metrics={detail.metrics} />
          <details>
            <summary>训练电芯身份与版本信息</summary>
            <pre className="code-block">{detail.train_cells.join("\n")}</pre>
            <p>{detail.metadata.task}</p>
          </details>
          <button
            disabled={!edit}
            onClick={() =>
              void action.run(async () => {
                await api("/models/" + detail.id + "/toggle", "POST");
                setDetail(null);
                await models.reload();
              })
            }
          >
            {detail.status === "enabled" ? "停用此版本" : "重新启用此版本"}
          </button>
        </Modal>
      )}
    </>
  );
}

export function FeedbackForm({
  predictionId,
  orderId,
  onSaved,
}: {
  predictionId: number;
  orderId?: number;
  onSaved: () => void;
}) {
  const action = useAction();
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        void action.run(async () => {
          await api("/feedback", "POST", {
            prediction_id: predictionId,
            order_id: orderId || null,
            value: Number(f.get("value")) / 100,
            provenance: f.get("provenance"),
            source: f.get("source"),
            measured_at: new Date(String(f.get("measured_at"))).toISOString(),
            note: f.get("note"),
          });
          onSaved();
        }, "反馈已追加；原预测未改变，未自动加入训练集");
      }}
    >
      <Notice>
        反馈不是自动认可的训练真值。模拟维修必须选“模拟反馈”，声明实测也仍需复核。
      </Notice>
      <div className="form-grid">
        <Field label="反馈 SOH / %">
          <input
            name="value"
            type="number"
            step=".01"
            min=".01"
            max="200"
            required
          />
        </Field>
        <Field label="数据来源性质">
          <select name="provenance">
            <option value="simulated">模拟反馈（不计为实测）</option>
            <option value="measured_declared">声明实测（待核验）</option>
          </select>
        </Field>
      </div>
      <Field label="测量 / 模拟时间">
        <input
          name="measured_at"
          type="datetime-local"
          defaultValue={local}
          required
        />
      </Field>
      <Field label="来源与依据">
        <input
          name="source"
          minLength={3}
          required
          placeholder="容量复测记录编号，或演示场景编号"
        />
      </Field>
      <Field label="补充说明">
        <textarea name="note" />
      </Field>
      <button className="primary" disabled={action.busy}>
        追加反馈
      </button>
      {action.feedback}
    </form>
  );
}

export function HealthCenter({ user }: { user: User }) {
  const assets = useData<Row[]>("/assets"),
    [assetId, setAssetId] = useState(0),
    [predictionId, setPredictionId] = useState(0),
    [showPolicy, setShowPolicy] = useState(false),
    [tab, setTab] = useState("predictions");
  const predictions = useData<Row[]>(
      "/predictions" + (assetId ? "?asset_id=" + assetId : ""),
      4000,
    ),
    events = useData<Row[]>("/health-events", 4000),
    policies = useData<Row[]>("/policies"),
    detail = useData<Row>(predictionId ? "/predictions/" + predictionId : "");
  const action = useAction();
  const edit = ["admin", "researcher"].includes(user.role);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">HEALTH & APPLICABILITY</div>
          <h1>健康中心</h1>
          <p>SOH 估计、适用性检查与维护建议分开呈现。</p>
        </div>
        <button disabled={!edit} onClick={() => setShowPolicy(true)}>
          <ShieldCheck size={16} />
          新建维护策略版本
        </button>
      </div>
      {action.feedback}
      <Notice>
        超出训练范围和分支差异只是适用性诊断，不是“95%置信度”。SOH
        维护提醒与合成传感器告警分开，不能推断失效机理。
      </Notice>
      <div className="tabs">
        <button
          className={tab === "predictions" ? "active" : ""}
          onClick={() => setTab("predictions")}
        >
          预测台账
        </button>
        <button
          className={tab === "events" ? "active" : ""}
          onClick={() => setTab("events")}
        >
          健康事件
        </button>
        <button
          className={tab === "policies" ? "active" : ""}
          onClick={() => setTab("policies")}
        >
          策略历史
        </button>
      </div>
      {tab === "predictions" && (
        <Panel
          title="可追溯预测记录"
          subtitle="只展示实际执行的模型结果。"
          actions={
            <select
              aria-label="筛选资产预测"
              value={assetId}
              onChange={(e) => setAssetId(Number(e.target.value))}
            >
              <option value={0}>全部资产 / 样本</option>
              {assets.data
                ?.filter((a) => a.kind === "cell")
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </select>
          }
        >
          {predictions.error && (
            <Notice tone="error">{predictions.error}</Notice>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>源样本 / 资产</th>
                  <th>SOH</th>
                  <th>适用状态</th>
                  <th>出界特征比例</th>
                  <th>模型</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {predictions.data?.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.asset_name || p.cell_id}</strong>
                      <small>{p.sample_key}</small>
                    </td>
                    <td className="number">{percent(p.soh)}</td>
                    <td>
                      <Badge value={p.applicability} />
                    </td>
                    <td>{percent(p.outside_fraction, 1)}</td>
                    <td>
                      {p.model_name}
                      <small>{date(p.created_at)}</small>
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setPredictionId(p.id)}
                      >
                        证据与反馈
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!predictions.data?.length && (
            <Empty>尚无模型结果，请先创建真实推理任务。</Empty>
          )}
          {assetId > 0 && (
            <LineChart
              values={[...(predictions.data || [])]
                .reverse()
                .map((p) => p.soh * 100)}
              title="该资产的模型 SOH 记录 / %"
            />
          )}
        </Panel>
      )}
      {tab === "events" && (
        <Panel title="健康事件证据">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>资产</th>
                  <th>来源</th>
                  <th>原因</th>
                  <th>证据</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {events.data?.map((e) => (
                  <tr key={e.id}>
                    <td>{e.asset_name}</td>
                    <td>
                      <Badge value={e.provenance} />
                    </td>
                    <td>{e.reason}</td>
                    <td>
                      {e.prediction_id ? (
                        <button
                          className="text-button"
                          onClick={() => setPredictionId(e.prediction_id)}
                        >
                          预测 #{e.prediction_id}
                        </button>
                      ) : (
                        "合成场景 · 非模型结果"
                      )}
                    </td>
                    <td>{date(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!events.data?.length && <Empty />}
        </Panel>
      )}
      {tab === "policies" && (
        <Panel
          title="维护规则版本"
          subtitle="只追加新版本，不篡改过去事件的依据。"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>策略</th>
                  <th>阈值</th>
                  <th>连续样本</th>
                  <th>冷却 / 过期</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {policies.data?.map((p) => (
                  <tr key={p.id}>
                    <td>
                      #{p.id} {p.name}
                    </td>
                    <td>{percent(p.threshold, 0)}</td>
                    <td>{p.persistence} 个不同样本</td>
                    <td>
                      {p.cooldown_seconds}s / {p.stale_seconds}s
                    </td>
                    <td>
                      <Badge value={p.active ? "enabled" : "retired"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {predictionId > 0 && (
        <Modal
          title={"预测证据 #" + predictionId}
          wide
          onClose={() => setPredictionId(0)}
        >
          {detail.data ? (
            <>
              <div className="prediction-hero">
                <div>
                  <small>原始模型预测（不可覆盖）</small>
                  <strong>{percent(detail.data.soh)}</strong>
                </div>
                <Badge value={detail.data.applicability} />
              </div>
              <div className="detail-grid">
                <div>
                  <small>ExtraTrees 分支</small>
                  <strong>{percent(detail.data.extra_trees_soh)}</strong>
                </div>
                <div>
                  <small>TabICL 分支</small>
                  <strong>{percent(detail.data.tabicl_soh)}</strong>
                </div>
                <div>
                  <small>模型权重</small>
                  <Hash value={detail.data.model.artifact_hash} />
                </div>
                <div>
                  <small>输入快照</small>
                  <Hash value={detail.data.input_hash} />
                </div>
              </div>
              <Notice>
                {detail.data.input_snapshot.cell_id} /{" "}
                {detail.data.input_snapshot.sample_key} · 标签{" "}
                {percent(detail.data.input_snapshot.truth)}
                。标签可见不等于本次预测是独立测试。
              </Notice>
              {detail.data.feedback.length > 0 && (
                <div className="feedback-list">
                  {detail.data.feedback.map((f: Row) => (
                    <div key={f.id}>
                      <Badge value={f.provenance} />
                      <strong>{percent(f.value)}</strong>
                      <span>{f.source}</span>
                      <small>
                        {f.actor} · {date(f.created_at)}
                      </small>
                    </div>
                  ))}
                </div>
              )}
              {edit && (
                <>
                  <h3 className="section-title">追加真实值或模拟反馈</h3>
                  <FeedbackForm
                    predictionId={predictionId}
                    onSaved={() => void detail.reload()}
                  />
                </>
              )}
            </>
          ) : (
            <Spinner />
          )}
        </Modal>
      )}
      {showPolicy && (
        <Modal title="新建维护复核策略" onClose={() => setShowPolicy(false)}>
          <Notice>
            这些是可配置的研究演示阈值，不是工业安全标准。重复同一样本不会满足持续性条件。
          </Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void action.run(async () => {
                await api("/policies", "POST", {
                  name: f.get("name"),
                  threshold: Number(f.get("threshold")) / 100,
                  persistence: Number(f.get("persistence")),
                  cooldown_seconds: Number(f.get("cooldown")) * 60,
                  stale_seconds: Number(f.get("stale")) * 3600,
                });
                setShowPolicy(false);
                await policies.reload();
              }, "策略新版本已保存");
            }}
          >
            <Field label="策略名称">
              <input name="name" required defaultValue="维护复核策略" />
            </Field>
            <div className="form-grid">
              <Field label="SOH 阈值 / %">
                <input
                  type="number"
                  name="threshold"
                  defaultValue={85}
                  min={10}
                  max={150}
                  required
                />
              </Field>
              <Field label="连续不同样本数">
                <input
                  type="number"
                  name="persistence"
                  defaultValue={2}
                  min={1}
                  max={20}
                  required
                />
              </Field>
              <Field label="冷却分钟">
                <input
                  type="number"
                  name="cooldown"
                  defaultValue={60}
                  min={0}
                  max={10080}
                  required
                />
              </Field>
              <Field label="观测过期小时">
                <input
                  type="number"
                  name="stale"
                  defaultValue={24}
                  min={1}
                  max={8760}
                  required
                />
              </Field>
            </div>
            <button className="primary" disabled={action.busy}>
              创建新版本并启用
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}
