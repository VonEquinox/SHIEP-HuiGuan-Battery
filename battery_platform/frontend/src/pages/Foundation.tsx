import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Plus,
  Database,
  Boxes,
  Network,
  MapPin,
  Download,
  Upload,
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
  Metric,
  Badge,
  Modal,
  Field,
  Hash,
  LineChart,
  useAction,
} from "../components";

export function Dashboard({ user }: { user: User }) {
  const { data: d, error, loading, reload } = useData("/dashboard", 4000);
  const action = useAction();
  const navigate = useNavigate();
  const researcher = ["admin", "researcher"].includes(user.role),
    operator = ["admin", "dispatcher"].includes(user.role);
  if (loading) return <Spinner />;
  if (!d) return <Notice tone="error">{error}</Notice>;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">OPERATIONS OVERVIEW</div>
          <h1>从数据，到可信的行动。</h1>
          <p>每个健康结果、每次告警、每张工单，均可回到原始证据。</p>
        </div>
        <button onClick={() => void reload()}>
          <RefreshCw size={16} />
          刷新工作台
        </button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {action.feedback}
      <div className="metrics">
        <Metric
          label="纳管电芯槽位"
          value={d.cells}
          note={`${d.cabinet_count} 个模拟电池柜 · 不是实测设备规模`}
          onClick={() => navigate("/assets")}
        />
        <Metric
          label="有效观测覆盖"
          value={percent(d.coverage, 0)}
          note="有当前预测的槽位 / 全部有效槽位"
          onClick={() => navigate("/health")}
        />
        <Metric
          label="待处置告警"
          value={d.open_alerts}
          note="维护提醒与适用性复核事件"
          onClick={() => navigate("/operations?tab=alerts")}
        />
        <Metric
          label="运维进行中"
          value={d.active_orders}
          note={`累计 ${d.completed_orders} 张工单完成验收关闭`}
          onClick={() => navigate("/operations?tab=orders")}
        />
      </div>
      <Panel
        className="onboarding"
        title="工作流起点"
        subtitle="首次使用依次初始化；不会写入任何虚构模型预测。"
      >
        <div className="setup-grid">
          <div>
            <span className="step-num">01</span>
            <strong>建立模拟资产</strong>
            <p>固定位置、柜模组层级与电芯槽位。</p>
            <button
              disabled={!operator || action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api("/demo/seed", "POST");
                  await reload();
                }, "模拟资产已建立；不会宣称已接 BMS")
              }
            >
              <Boxes size={15} />
              初始化演示站
            </button>
          </div>
          <div>
            <span className="step-num">02</span>
            <strong>接入真实实验</strong>
            <p>只导入 21 个开发电芯，保护最终留出集。</p>
            <button
              disabled={!researcher || action.busy}
              onClick={() =>
                void action.run(async () => {
                  const r = await api("/datasets/import-xjtu", "POST");
                  navigate("/models?job=" + r.job_id);
                }, "导入任务已提交")
              }
            >
              <Database size={15} />
              导入 XJTU 开发数据
            </button>
          </div>
          <div>
            <span className="step-num">03</span>
            <strong>注册冻结模型</strong>
            <p>快速分支与完整混合模型分别列示。</p>
            <button
              disabled={!researcher || action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api("/models/register-frozen", "POST");
                  await reload();
                }, "冻结模型版本已注册")
              }
            >
              <Network size={15} />
              注册已验证产物
            </button>
          </div>
          <div>
            <span className="step-num">04</span>
            <strong>真实推理与处置</strong>
            <p>绑定实验回放，再创建真实计算任务。</p>
            <button className="primary" onClick={() => navigate("/models")}>
              进入模型工作区
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </Panel>
      <div className="two-col">
        <Panel
          title="健康观测分布"
          subtitle="显示适用范围与未知状态，不把缺失当正常。"
        >
          <div className="health-distribution">
            {Object.entries(d.health_states).map(([state, value]) => (
              <div key={state}>
                <span className={"status-dot " + state} />
                <span>{labels[state]}</span>
                <div className="bar-track">
                  <i
                    className={state}
                    style={{
                      width: `${d.cells ? ((value as number) / d.cells) * 100 : 0}%`,
                    }}
                  />
                </div>
                <strong>{value as number}</strong>
              </div>
            ))}
          </div>
          <div className="panel-foot">
            <Badge value="simulated" />
            资产与人员为仿真业务，预测来自真实模型执行。
          </div>
        </Panel>
        <Panel
          title="最新健康复核"
          subtitle="告警不会自动发出物理停机或更换指令。"
          actions={
            <button
              className="text-button"
              onClick={() => navigate("/operations")}
            >
              查看全部
              <ArrowRight size={15} />
            </button>
          }
        >
          {d.recent_alerts.length ? (
            <div className="list">
              {d.recent_alerts.map((a: Row) => (
                <button
                  className="list-item"
                  key={a.id}
                  onClick={() => navigate("/operations?alert=" + a.id)}
                >
                  <span className="event-icon">
                    <MapPin size={18} />
                  </span>
                  <div>
                    <strong>{a.asset_name}</strong>
                    <p>{a.reason}</p>
                    <small>{date(a.created_at)}</small>
                  </div>
                  <Badge value={a.status} />
                </button>
              ))}
            </div>
          ) : (
            <Empty>暂无告警。完成推理或使用单独标注的演示场景。</Empty>
          )}
        </Panel>
      </div>
      <div className="two-col">
        <Panel
          title="最近槽位预测"
          subtitle="不同槽位的最新估计，不是虚构的实时监控曲线。"
        >
          {d.recent_predictions.length ? (
            <>
              <LineChart
                values={d.recent_predictions.map((p: Row) => p.soh * 100)}
                labels={d.recent_predictions.map((p: Row) => p.asset_code)}
                title="最新 SOH 估计 / %"
              />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>槽位</th>
                      <th>SOH</th>
                      <th>适用状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.recent_predictions.slice(0, 5).map((p: Row) => (
                      <tr key={p.id}>
                        <td>{p.asset_name}</td>
                        <td>{percent(p.soh)}</td>
                        <td>
                          <Badge value={p.state} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <Empty>尚无模型结果。不会用随机数填充图表。</Empty>
          )}
        </Panel>
        <Panel title="操作记录" subtitle="服务端持久化的真实操作时间线。">
          <div className="timeline">
            {d.activity.map((a: Row) => (
              <div key={a.id}>
                <i />
                <div>
                  <strong>
                    {a.actor || "系统"} <span>{a.action}</span>
                  </strong>
                  <p>
                    {a.entity} #{a.entity_id}
                  </p>
                  <small>{date(a.created_at)}</small>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Notice>
        当前为研究和演示环境：SOH
        模型没有认证的安全报警能力，尚无生产设备连接，RUL 未启用。
      </Notice>
    </>
  );
}

function LocationMap({
  assets,
  onSelect,
}: {
  assets: Row[];
  onSelect: (id: number) => void;
}) {
  const located = assets.filter(
    (a) => a.latitude != null && a.longitude != null,
  );
  if (!located.length) return <Empty>尚未登记固定位置</Empty>;
  const lats = located.map((a) => a.latitude),
    lons = located.map((a) => a.longitude);
  const minLat = Math.min(...lats),
    maxLat = Math.max(...lats),
    minLon = Math.min(...lons),
    maxLon = Math.max(...lons);
  return (
    <div className="location-map">
      <span className="map-label">固定坐标示意 / 非在线地图</span>
      <div className="map-axis">N ↑</div>
      {located.map((a, i) => (
        <button
          key={a.id}
          className="map-pin"
          style={{
            left: `${15 + ((a.longitude - minLon) / Math.max(maxLon - minLon, 0.0001)) * 65}%`,
            top: `${72 - ((a.latitude - minLat) / Math.max(maxLat - minLat, 0.0001)) * 48}%`,
          }}
          onClick={() => onSelect(a.id)}
          title={`${a.name} · ${a.latitude}, ${a.longitude}`}
        >
          <MapPin size={18} />
          <span>{a.code}</span>
        </button>
      ))}
    </div>
  );
}

export function Assets({ user }: { user: User }) {
  const all = useData<Row[]>("/assets");
  const datasets = useData<Row[]>("/datasets");
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<number | null>(
    Number(params.get("id")) || null,
  );
  const detail = useData<Row>(selected ? "/assets/" + selected : "");
  const action = useAction();
  const [dialog, setDialog] = useState(""),
    [form, setForm] = useState<any>({
      kind: "site",
      code: "",
      name: "",
      parent_id: null,
      location: "",
      latitude: "",
      longitude: "",
    });
  const [bindDataset, setBindDataset] = useState(0),
    [bindCell, setBindCell] = useState("");
  const source = useData(
    bindDataset ? `/datasets/${bindDataset}/samples?limit=1` : "",
  );
  const edit = ["admin", "dispatcher"].includes(user.role),
    canBind = ["admin", "dispatcher", "researcher"].includes(user.role);
  useEffect(() => {
    if (!selected && all.data?.length) setSelected(all.data[0].id);
  }, [all.data, selected]);
  const refresh = async () => {
    await all.reload();
    await detail.reload();
  };
  const tree = (parent: number | null, depth = 0): React.ReactNode =>
    all.data
      ?.filter((a) => a.parent_id === parent)
      .map((a) => (
        <div key={a.id}>
          <button
            className={"tree-item " + (selected === a.id ? "selected" : "")}
            style={{ paddingLeft: 14 + depth * 15 }}
            onClick={() => setSelected(a.id)}
          >
            <ChevronRight size={12} />
            <span className={"asset-symbol " + a.kind}>
              {a.kind === "cell" ? "◉" : "▣"}
            </span>
            <span>
              {a.name}
              <small>{a.code}</small>
            </span>
            {a.health && <i className={"status-dot " + a.health.state} />}
          </button>
          {tree(a.id, depth + 1)}
        </div>
      ));
  const a = detail.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ASSET REGISTRY</div>
          <h1>资产中心</h1>
          <p>资产槽位、安装批次、实验数据绑定分别管理。</p>
        </div>
        <button
          className="primary"
          disabled={!edit}
          onClick={() => {
            setForm({
              kind: "site",
              code: "",
              name: "",
              parent_id: null,
              location: "",
              latitude: "",
              longitude: "",
            });
            setDialog("create");
          }}
        >
          <Plus size={16} />
          新建资产
        </button>
      </div>
      {action.feedback}
      {all.error && <Notice tone="error">{all.error}</Notice>}
      <div className="asset-layout">
        <Panel
          title="资产层级"
          subtitle={`${all.data?.length || 0} 个有效节点`}
        >
          <div className="tree">
            {all.loading ? (
              <Spinner />
            ) : all.data?.length ? (
              tree(null)
            ) : (
              <Empty>从总览初始化演示站，或创建站点。</Empty>
            )}
          </div>
        </Panel>
        <div>
          {a ? (
            <>
              <Panel
                title={a.name}
                subtitle={`${labels[a.kind]} / ${a.code}`}
                actions={
                  <>
                    <Badge value={a.provenance} />
                    {edit && (
                      <button
                        onClick={() => {
                          setForm({
                            ...a,
                            latitude: a.latitude ?? "",
                            longitude: a.longitude ?? "",
                          });
                          setDialog("edit");
                        }}
                      >
                        编辑档案
                      </button>
                    )}
                  </>
                }
              >
                <div className="detail-grid">
                  <div>
                    <small>位置</small>
                    <strong>{a.location || "未登记"}</strong>
                  </div>
                  <div>
                    <small>固定坐标</small>
                    <strong>
                      {a.latitude != null
                        ? `${a.latitude}, ${a.longitude}`
                        : "继承上级位置 / 未登记"}
                    </strong>
                  </div>
                  <div>
                    <small>安装身份</small>
                    <Hash value={a.installation_id} />
                  </div>
                  <div>
                    <small>当前健康</small>
                    <Badge value={a.health?.state || "unknown"} />
                  </div>
                </div>
                {a.health?.prediction && (
                  <div className="prediction-hero">
                    <div>
                      <small>最近 SOH 估计</small>
                      <strong>{percent(a.health.prediction.soh)}</strong>
                    </div>
                    <div>
                      <Badge value={a.health.prediction.applicability} />
                      <p>{a.health.prediction.model_name}</p>
                    </div>
                  </div>
                )}
                <div className="actions asset-actions">
                  {a.kind === "cell" && (
                    <>
                      <button
                        disabled={!canBind}
                        onClick={() => {
                          setBindDataset(
                            a.binding?.dataset_id ||
                              datasets.data?.[0]?.id ||
                              0,
                          );
                          setBindCell(a.binding?.cell_id || "");
                          setDialog("binding");
                        }}
                      >
                        绑定实验回放
                      </button>
                      <button
                        disabled={!a.binding}
                        onClick={() =>
                          window.location.assign("/models?asset=" + a.id)
                        }
                      >
                        为该槽位推理
                        <ArrowRight size={14} />
                      </button>
                      <button
                        disabled={!edit}
                        onClick={() => setDialog("replace")}
                      >
                        登记更换
                      </button>
                    </>
                  )}
                  <button
                    className="danger-text"
                    disabled={!edit}
                    onClick={() => setDialog("retire")}
                  >
                    退役节点
                  </button>
                </div>
                {a.binding && (
                  <Notice>
                    显式回放绑定：{a.binding.cell_id}
                    。这是实验记录在模拟槽位上的展示，不是该槽位的真实传感器采集。
                  </Notice>
                )}
              </Panel>
              {a.kind === "cell" ? (
                <Panel
                  title="预测历史"
                  subtitle="横轴为有序样本，不把源行号伪称为真实物理循环数。"
                >
                  <LineChart
                    values={[...a.history]
                      .reverse()
                      .filter(
                        (p: Row) => p.installation_id === a.installation_id,
                      )
                      .map((p: Row) => p.soh * 100)}
                    title="本次安装 · SOH / %"
                  />
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>源样本</th>
                          <th>SOH</th>
                          <th>模型</th>
                          <th>时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {a.history.slice(0, 20).map((p: Row) => (
                          <tr key={p.id}>
                            <td>{p.sample_key}</td>
                            <td>{percent(p.soh)}</td>
                            <td>{p.model_name}</td>
                            <td>{date(p.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              ) : (
                <Panel
                  title="子资产与观测覆盖"
                  subtitle="不把电芯平均健康度当作实测整柜 SOH。"
                >
                  {a.aggregate && (
                    <>
                      <div className="mini-metrics">
                        <div>
                          <small>有当前预测 / 全部电芯</small>
                          <strong>
                            {a.aggregate.fresh_prediction_cells} /{" "}
                            {a.aggregate.total_cells}
                          </strong>
                        </div>
                        <div>
                          <small>观测覆盖率</small>
                          <strong>{percent(a.aggregate.coverage, 0)}</strong>
                        </div>
                        <div>
                          <small>需复核 / 暂无预测</small>
                          <strong>
                            {a.aggregate.states.review +
                              a.aggregate.states.attention}{" "}
                            / {a.aggregate.states.unknown}
                          </strong>
                        </div>
                      </div>
                      {a.aggregate.lowest_estimated_cells.length > 0 && (
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>最低估计电芯（非整柜SOH）</th>
                                <th>估计值</th>
                                <th>适用状态</th>
                                <th />
                              </tr>
                            </thead>
                            <tbody>
                              {a.aggregate.lowest_estimated_cells.map(
                                (c: Row) => (
                                  <tr key={c.asset_id}>
                                    <td>{c.name}</td>
                                    <td>{percent(c.soh)}</td>
                                    <td>
                                      <Badge value={c.state} />
                                    </td>
                                    <td>
                                      <button
                                        className="text-button"
                                        onClick={() => setSelected(c.asset_id)}
                                      >
                                        查看证据
                                      </button>
                                    </td>
                                  </tr>
                                ),
                              )}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  )}
                  <div className="child-grid">
                    {a.children.map((c: Row) => (
                      <button key={c.id} onClick={() => setSelected(c.id)}>
                        <Boxes size={21} />
                        <strong>{c.name}</strong>
                        <small>{c.code}</small>
                      </button>
                    ))}
                  </div>
                </Panel>
              )}
            </>
          ) : (
            <Panel>
              <Empty>选择左侧资产查看档案、位置与预测记录。</Empty>
            </Panel>
          )}
          <Panel title="位置视图" subtitle="所有示范站位置均为固定模拟坐标。">
            <LocationMap assets={all.data || []} onSelect={setSelected} />
          </Panel>
        </div>
      </div>
      {(dialog === "create" || dialog === "edit") && (
        <Modal
          title={dialog === "create" ? "新建模拟资产" : "编辑资产档案"}
          onClose={() => setDialog("")}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                const body = {
                  name: form.name,
                  location: form.location,
                  latitude: form.latitude === "" ? null : Number(form.latitude),
                  longitude:
                    form.longitude === "" ? null : Number(form.longitude),
                };
                if (dialog === "create")
                  await api("/assets", "POST", {
                    ...body,
                    code: form.code,
                    kind: form.kind,
                    parent_id:
                      form.kind === "site" ? null : Number(form.parent_id),
                  });
                else
                  await api("/assets/" + selected, "PUT", {
                    ...body,
                    version: a?.version,
                  });
                setDialog("");
                await refresh();
              });
            }}
          >
            {dialog === "create" && (
              <>
                <Field label="资产类型">
                  <select
                    value={form.kind}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        kind: e.target.value,
                        parent_id: null,
                      })
                    }
                  >
                    {["site", "cabinet", "module", "cell"].map((k) => (
                      <option key={k} value={k}>
                        {labels[k]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="资产编号">
                  <input
                    required
                    pattern="[A-Za-z0-9_.-]+"
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                  />
                </Field>
                {form.kind !== "site" && (
                  <Field label="父节点">
                    <select
                      required
                      value={form.parent_id || ""}
                      onChange={(e) =>
                        setForm({ ...form, parent_id: Number(e.target.value) })
                      }
                    >
                      <option value="">选择上级</option>
                      {all.data
                        ?.filter(
                          (v) =>
                            v.kind ===
                            (
                              {
                                cabinet: "site",
                                module: "cabinet",
                                cell: "module",
                              } as any
                            )[form.kind],
                        )
                        .map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.name}
                          </option>
                        ))}
                    </select>
                  </Field>
                )}
              </>
            )}
            <Field label="名称">
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="机房 / 柜位位置">
              <input
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </Field>
            <div className="form-grid">
              <Field label="纬度">
                <input
                  type="number"
                  min="-90"
                  max="90"
                  step="any"
                  value={form.latitude}
                  onChange={(e) =>
                    setForm({ ...form, latitude: e.target.value })
                  }
                />
              </Field>
              <Field label="经度">
                <input
                  type="number"
                  min="-180"
                  max="180"
                  step="any"
                  value={form.longitude}
                  onChange={(e) =>
                    setForm({ ...form, longitude: e.target.value })
                  }
                />
              </Field>
            </div>
            <button className="primary" disabled={action.busy}>
              保存档案
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
      {dialog === "binding" && (
        <Modal title="显式绑定实验回放" onClose={() => setDialog("")}>
          <Notice>只改变演示绑定，不宣称实验电芯就是现场设备。</Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api("/assets/" + selected + "/binding", "POST", {
                  dataset_id: bindDataset,
                  cell_id: bindCell,
                });
                setDialog("");
                await refresh();
              });
            }}
          >
            <Field label="数据集">
              <select
                value={bindDataset}
                onChange={(e) => {
                  setBindDataset(Number(e.target.value));
                  setBindCell("");
                }}
              >
                {datasets.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="源电芯">
              <select
                required
                value={bindCell}
                onChange={(e) => setBindCell(e.target.value)}
              >
                <option value="">选择源电芯</option>
                {source.data?.cells.map((c: Row) => (
                  <option key={c.cell_id} value={c.cell_id}>
                    {c.cell_id}
                  </option>
                ))}
              </select>
            </Field>
            <button className="primary" disabled={action.busy}>
              保存回放绑定
            </button>
          </form>
        </Modal>
      )}
      {(dialog === "replace" || dialog === "retire") && (
        <Modal
          title={dialog === "replace" ? "登记电芯更换" : "退役资产"}
          onClose={() => setDialog("")}
        >
          <Notice>
            {dialog === "replace"
              ? "将创建新的安装身份，清空回放绑定；历史预测保留，不会把 SOH 自动重置为100%。"
              : "有活动子节点或未完成工单的资产不能退役。"}
          </Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const note = new FormData(e.currentTarget).get("note");
              void action.run(async () => {
                await api("/assets/" + selected + "/" + dialog, "POST", {
                  version: a?.version,
                  note,
                });
                setDialog("");
                await refresh();
              });
            }}
          >
            <Field label="原因 / 记录">
              <textarea name="note" required minLength={3} />
            </Field>
            <button className="primary" disabled={action.busy}>
              确认登记
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}

export function DataCenter({ user }: { user: User }) {
  const datasets = useData<Row[]>("/datasets", 5000);
  const [selected, setSelected] = useState(0),
    [cell, setCell] = useState(""),
    [offset, setOffset] = useState(0),
    [sampleId, setSampleId] = useState(0),
    [upload, setUpload] = useState(false),
    [showSchema, setShowSchema] = useState(false);
  const page = useData(
    selected
      ? `/datasets/${selected}/samples?cell_id=${encodeURIComponent(cell)}&offset=${offset}&limit=25`
      : "",
  );
  const sample = useData(sampleId ? "/samples/" + sampleId : "");
  const schema = useData("/schema");
  const action = useAction(),
    navigate = useNavigate();
  const edit = ["admin", "researcher"].includes(user.role);
  useEffect(() => {
    if (!selected && datasets.data?.length) setSelected(datasets.data[0].id);
  }, [datasets.data, selected]);
  const d = datasets.data?.find((x) => x.id === selected);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">DATA & PROVENANCE</div>
          <h1>数据中心</h1>
          <p>不可变的数据版本、可解释的特征契约、可核查的源样本。</p>
        </div>
        <div className="actions">
          <button onClick={() => setShowSchema(true)}>特征契约</button>
          <button
            disabled={!edit || action.busy}
            onClick={() =>
              void action.run(async () => {
                const r = await api("/datasets/import-xjtu", "POST");
                navigate("/models?job=" + r.job_id);
              })
            }
          >
            导入 XJTU
          </button>
          <button
            className="primary"
            disabled={!edit}
            onClick={() => setUpload(true)}
          >
            <Upload size={16} />
            导入特征 CSV
          </button>
        </div>
      </div>
      {action.feedback}
      {datasets.error && <Notice tone="error">{datasets.error}</Notice>}
      <div className="dataset-grid">
        {datasets.data?.map((row) => (
          <button
            className={
              "dataset-card " + (selected === row.id ? "selected" : "")
            }
            key={row.id}
            onClick={() => {
              setSelected(row.id);
              setCell("");
              setOffset(0);
            }}
          >
            <div>
              <Database size={21} />
              <Badge value={row.provenance} />
            </div>
            <h3>{row.name}</h3>
            <p>
              {row.sample_count.toLocaleString()} 条样本 · {row.cell_count}{" "}
              个电芯
            </p>
            <Hash value={row.source_hash} />
          </button>
        ))}
      </div>
      {!datasets.data?.length && (
        <Panel>
          <Empty>
            尚未导入实验数据。导入任务会从已有研究数据中排除保护电芯。
          </Empty>
        </Panel>
      )}
      {d && (
        <>
          <Panel
            title={d.name}
            subtitle={d.source}
            actions={
              <>
                <button
                  disabled={!edit}
                  onClick={() =>
                    void action.run(async () => {
                      const result = await api("/demo/bind/" + d.id, "POST");
                      await datasets.reload();
                      return result;
                    }, "已为演示槽位建立实验回放绑定")
                  }
                >
                  批量绑定演示槽位
                </button>
                {edit && (
                  <a className="button" href={`/api/datasets/${d.id}/export`}>
                    <Download size={15} />
                    导出 CSV
                  </a>
                )}
                <button
                  className="danger-text"
                  disabled={!edit}
                  onClick={() =>
                    void action.run(async () => {
                      await api("/datasets/" + d.id, "DELETE");
                      setSelected(0);
                      await datasets.reload();
                    })
                  }
                >
                  删除未使用版本
                </button>
              </>
            }
          >
            <div className="detail-grid">
              <div>
                <small>数据版本 / SHA256</small>
                <Hash value={d.source_hash} />
              </div>
              <div>
                <small>特征维度</small>
                <strong>71 × 当前 / 参考</strong>
              </div>
              <div>
                <small>来源核验</small>
                <strong>
                  {d.quality.verified
                    ? "源哈希已校验"
                    : "用户声明 / 尚未独立核验"}
                </strong>
              </div>
              <div>
                <small>观测窗口</small>
                <strong>3.7–4.1 V / 恒流</strong>
              </div>
            </div>
            <Notice>
              {d.quality.scope || d.quality.note || "请以源数据标签契约为准"}
              。源行号不代表物理循环数，不能跨电芯混切训练与测试。
            </Notice>
          </Panel>
          <Panel
            title="样本浏览"
            subtitle="真实标签只用于评估，不进入推理特征。"
            actions={
              <select
                aria-label="筛选源电芯"
                value={cell}
                onChange={(e) => {
                  setCell(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">全部电芯</option>
                {page.data?.cells.map((c: Row) => (
                  <option key={c.cell_id} value={c.cell_id}>
                    {c.cell_id} · {c.sample_count}
                  </option>
                ))}
              </select>
            }
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>源电芯</th>
                    <th>不可变样本 ID</th>
                    <th>标签 SOH</th>
                    <th>输入快照</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {page.data?.items.map((s: Row) => (
                    <tr key={s.id}>
                      <td>{s.cell_id}</td>
                      <td>{s.sample_key}</td>
                      <td>{percent(s.truth)}</td>
                      <td>
                        <Hash value={s.input_hash} />
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setSampleId(s.id)}
                        >
                          查看观测
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                共 {page.data?.total || 0} 条 · {offset + 1}–
                {Math.min(offset + 25, page.data?.total || 0)}
              </span>
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                上一页
              </button>
              <button
                disabled={offset + 25 >= (page.data?.total || 0)}
                onClick={() => setOffset(offset + 25)}
              >
                下一页
              </button>
            </div>
            {cell && (
              <LineChart
                values={(page.data?.items || []).map(
                  (s: Row) => (s.truth ?? NaN) * 100,
                )}
                title="当前页真实 SOH 标签 / %（非模型预测）"
              />
            )}
          </Panel>
        </>
      )}
      {sampleId > 0 && (
        <Modal title="充电窗口观测" wide onClose={() => setSampleId(0)}>
          {sample.data ? (
            <>
              <Notice>
                {sample.data.cell_id} / {sample.data.sample_key} ·
                当前观测与初始参考，不含未来容量标签。
              </Notice>
              <LineChart
                values={sample.data.current
                  .slice(16, 32)
                  .map((v: number) => 100 * v)}
                secondary={sample.data.reference
                  .slice(16, 32)
                  .map((v: number) => 100 * v)}
                title="16 个电压局部区间电量占比 / %：实线当前，虚线参考"
              />
              <div className="detail-grid">
                <div>
                  <small>观测电流</small>
                  <strong>{sample.data.current[66]?.toFixed(3)} A</strong>
                </div>
                <div>
                  <small>起点温度</small>
                  <strong>
                    {sample.data.current[69]?.toFixed(2) ?? "缺失"} °C
                  </strong>
                </div>
                <div>
                  <small>真实标签</small>
                  <strong>{percent(sample.data.truth)}</strong>
                </div>
                <div>
                  <small>快照</small>
                  <Hash value={sample.data.input_hash} />
                </div>
              </div>
            </>
          ) : (
            <Spinner />
          )}
        </Modal>
      )}
      {upload && (
        <Modal title="导入声明特征 CSV" onClose={() => setUpload(false)}>
          <Notice>
            8MiB / 5000 行上限；必须含 71 维当前、71
            维参考和局部电量比。不会把任意原始BMS表格自动解释成模型输入。
          </Notice>
          {d && (
            <a className="button" href={`/api/datasets/${d.id}/export?limit=3`}>
              下载当前数据的3行格式示例
            </a>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              void action.run(async () => {
                await api("/datasets/upload", "POST", form);
                setUpload(false);
                await datasets.reload();
              });
            }}
          >
            <Field label="数据集名称">
              <input name="name" required maxLength={100} />
            </Field>
            <Field label="UTF-8 CSV 文件">
              <input type="file" name="file" accept=".csv" required />
            </Field>
            <button className="primary" disabled={action.busy}>
              校验并导入
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
      {showSchema && (
        <Modal title="71维观测契约" wide onClose={() => setShowSchema(false)}>
          <Notice>
            {schema.data?.input_window}
            。完整放电容量只可作为评估标签，不能进入预测特征。
          </Notice>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>索引</th>
                  <th>物理表示</th>
                  <th>缺失约束</th>
                </tr>
              </thead>
              <tbody>
                {schema.data?.features.map((f: any) => (
                  <tr key={f.index}>
                    <td>{f.index}</td>
                    <td>{f.description}</td>
                    <td>
                      {f.temperature_optional
                        ? "可缺失，使用训练期填补"
                        : "必须有限"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </>
  );
}
