import { useEffect, useState } from "react";
import { AccountPassword } from "./AccountPassword";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Plus,
  ArrowRight,
  Check,
  UserRound,
  Paperclip,
  MapPin,
  Download,
  ShieldCheck,
  Bell,
  RefreshCw,
  Network,
  Boxes,
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
  useAction,
} from "../components";
import { FeedbackForm } from "./Intelligence";

function Personnel({ user }: { user: User }) {
  const people = useData<Row[]>("/personnel", 4000),
    canEdit = ["admin", "dispatcher"].includes(user.role),
    users = useData<Row[]>(canEdit ? "/users" : "");
  const [editing, setEditing] = useState<any>(null);
  const action = useAction();
  return (
    <>
      {action.feedback}
      <Panel
        title="维修人员与派单约束"
        subtitle="先检查技能、值班和工作量，再按工作量、距离排序；不使用虚构AI评分。"
        actions={
          <button
            className="primary"
            disabled={!canEdit}
            onClick={() =>
              setEditing({
                user_id: "",
                skills: ["battery"],
                on_call: true,
                latitude: "",
                longitude: "",
                max_workload: 4,
              })
            }
          >
            <Plus size={16} />
            登记维修人员
          </button>
        }
      >
        <div className="people-grid">
          {people.data?.map((p) => (
            <div className="person-card" key={p.id}>
              <div className="person-title">
                <span className="avatar">{p.display_name.slice(0, 1)}</span>
                <div>
                  <strong>{p.display_name}</strong>
                  <small>@{p.username}</small>
                </div>
                <Badge value={p.on_call ? "enabled" : "retired"}>
                  {p.on_call ? "值班中" : "非值班"}
                </Badge>
              </div>
              <div className="skill-tags">
                {p.skills.map((s: string) => (
                  <span key={s}>{s}</span>
                ))}
              </div>
              <p>
                当前工单 <strong>{p.workload}</strong> / 可承接上限{" "}
                {p.max_workload}
              </p>
              <small>
                固定模拟位置：{p.latitude ?? "未登记"},{" "}
                {p.longitude ?? "未登记"}
              </small>
              <button
                disabled={!canEdit}
                onClick={() =>
                  setEditing({
                    ...p,
                    latitude: p.latitude ?? "",
                    longitude: p.longitude ?? "",
                  })
                }
              >
                编辑值班与技能
              </button>
            </div>
          ))}
        </div>
        {!people.data?.length && (
          <Empty>先在系统管理创建“维修人员”账号，再登记值班和技能。</Empty>
        )}
      </Panel>
      {editing && (
        <Modal title="维修人员档案" onClose={() => setEditing(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api("/personnel", "POST", {
                  user_id: Number(editing.user_id),
                  skills: editing.skills,
                  on_call: editing.on_call,
                  latitude:
                    editing.latitude === "" ? null : Number(editing.latitude),
                  longitude:
                    editing.longitude === "" ? null : Number(editing.longitude),
                  max_workload: Number(editing.max_workload),
                });
                setEditing(null);
                await people.reload();
              });
            }}
          >
            <Field label="维修人员账号">
              <select
                required
                value={editing.user_id}
                onChange={(e) =>
                  setEditing({ ...editing, user_id: e.target.value })
                }
              >
                <option value="">选择账号</option>
                {users.data
                  ?.filter((u) => u.role === "technician" && u.active)
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.display_name} / {u.username}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="技能要求">
              <div className="checks">
                {["battery", "electrical", "sensor", "inspection"].map(
                  (skill) => (
                    <label key={skill}>
                      <input
                        type="checkbox"
                        checked={editing.skills.includes(skill)}
                        onChange={(e) =>
                          setEditing({
                            ...editing,
                            skills: e.target.checked
                              ? [...editing.skills, skill]
                              : editing.skills.filter(
                                  (s: string) => s !== skill,
                                ),
                          })
                        }
                      />
                      {skill}
                    </label>
                  ),
                )}
              </div>
            </Field>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={editing.on_call}
                onChange={(e) =>
                  setEditing({ ...editing, on_call: e.target.checked })
                }
              />
              目前处于值班状态
            </label>
            <div className="form-grid">
              <Field label="纬度（模拟固定位置）">
                <input
                  type="number"
                  step="any"
                  min="-90"
                  max="90"
                  value={editing.latitude}
                  onChange={(e) =>
                    setEditing({ ...editing, latitude: e.target.value })
                  }
                />
              </Field>
              <Field label="经度">
                <input
                  type="number"
                  step="any"
                  min="-180"
                  max="180"
                  value={editing.longitude}
                  onChange={(e) =>
                    setEditing({ ...editing, longitude: e.target.value })
                  }
                />
              </Field>
            </div>
            <Field label="同时承接上限">
              <input
                type="number"
                min="1"
                max="20"
                value={editing.max_workload}
                onChange={(e) =>
                  setEditing({ ...editing, max_workload: e.target.value })
                }
              />
            </Field>
            <button className="primary" disabled={action.busy}>
              保存人员档案
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}

function OrderDetail({
  id,
  user,
  onClose,
  onChanged,
}: {
  id: number;
  user: User;
  onClose: () => void;
  onChanged: () => void;
}) {
  const detail = useData<Row>("/orders/" + id, 5000),
    action = useAction();
  const [operation, setOperation] = useState(""),
    [note, setNote] = useState(""),
    [assignee, setAssignee] = useState(0),
    [feedback, setFeedback] = useState(false),
    [predictionId, setPredictionId] = useState(0);
  const d = detail.data;
  const admin = ["admin", "dispatcher"].includes(user.role),
    tech = user.role === "technician";
  const predictions = useData<Row[]>(
    d ? "/predictions?asset_id=" + d.asset_id : "",
  );
  const steps = [
    "CREATED",
    "ASSIGNED",
    "ACCEPTED",
    "IN_PROGRESS",
    "RESOLVED",
    "VERIFIED",
    "CLOSED",
  ];
  const choices = d
    ? admin
      ? (
          [
            ["assign", "派发 / 调整人员", ["CREATED", "ASSIGNED"]],
            ["verify", "独立验收", ["RESOLVED"]],
            ["close", "关闭工单", ["VERIFIED"]],
            ["reopen", "重新开启", ["RESOLVED", "VERIFIED", "CLOSED"]],
            [
              "cancel",
              "取消工单",
              [
                "CREATED",
                "ASSIGNED",
                "ACCEPTED",
                "IN_PROGRESS",
                "RESOLVED",
                "VERIFIED",
              ],
            ],
          ] as [string, string, string[]][]
        ).filter((c) => c[2].includes(d.status))
      : tech
        ? (
            [
              ["accept", "接受工单", ["ASSIGNED"]],
              ["start", "开始处理", ["ACCEPTED"]],
              ["resolve", "提交处理结果", ["IN_PROGRESS"]],
              ["reject", "退回派单", ["ASSIGNED", "ACCEPTED"]],
            ] as [string, string, string[]][]
          ).filter((c) => c[2].includes(d.status))
        : []
    : [];
  return (
    <Modal
      title={"工单 WO-" + id.toString().padStart(5, "0")}
      wide
      onClose={onClose}
    >
      {d ? (
        <>
          {action.feedback}
          <div className="order-detail-head">
            <div>
              <h3>{d.title}</h3>
              <p>
                {d.asset.code} / {d.asset.location || "位置继承上级"}
              </p>
            </div>
            <Badge value={d.status} />
          </div>
          <div className="steps">
            {steps.map((s, i) => (
              <div
                key={s}
                className={steps.indexOf(d.status) >= i ? "done" : ""}
              >
                <span>
                  {steps.indexOf(d.status) > i ? <Check size={12} /> : i + 1}
                </span>
                <small>{labels[s]}</small>
              </div>
            ))}
          </div>
          <Notice>
            <Badge value={d.source_event?.provenance} /> {d.alert.reason}
            。此流程只管理工作记录，不向设备下发控制命令。
          </Notice>
          {admin && ["CREATED", "ASSIGNED"].includes(d.status) && (
            <>
              <h3 className="section-title">可解释的人员推荐</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>人员</th>
                      <th>资格</th>
                      <th>工作量</th>
                      <th>距离</th>
                      <th>依据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.recommendations.map((p: Row) => (
                      <tr key={p.user_id}>
                        <td>{p.display_name}</td>
                        <td>
                          <Badge value={p.eligible ? "enabled" : "retired"}>
                            {p.eligible ? "可派发" : "不符合"}
                          </Badge>
                        </td>
                        <td>
                          {p.workload}/{p.max_workload}
                        </td>
                        <td>
                          {p.distance_km == null
                            ? "位置缺失"
                            : p.distance_km + " km"}
                        </td>
                        <td>{p.reasons.join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!d.recommendations.length && (
                <Notice>
                  没有维修人员档案；请先创建维修人员账号并登记技能与值班。
                </Notice>
              )}
            </>
          )}
          <div className="actions order-actions">
            {choices.map(([key, label]) => (
              <button
                className={
                  key === "cancel" || key === "reject"
                    ? "danger-text"
                    : "primary"
                }
                key={key}
                disabled={action.busy}
                onClick={() => {
                  setOperation(key);
                  setNote("");
                  setAssignee(
                    d.recommendations?.find((p: Row) => p.eligible)?.user_id ||
                      0,
                  );
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {operation && (
            <form
              className="action-form"
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  await api("/orders/" + id + "/transition", "POST", {
                    version: d.version,
                    action: operation,
                    assignee_id: operation === "assign" ? assignee : null,
                    note,
                  });
                  setOperation("");
                  await detail.reload();
                  onChanged();
                }, "状态已更新并写入审计");
              }}
            >
              <h3>
                {choices.find((c) => c[0] === operation)?.[1] || operation}
              </h3>
              {operation === "assign" && (
                <Field label="选择符合要求的维修人员">
                  <select
                    value={assignee || ""}
                    required
                    onChange={(e) => setAssignee(Number(e.target.value))}
                  >
                    <option value="">选择人员</option>
                    {d.recommendations
                      .filter((p: Row) => p.eligible)
                      .map((p: Row) => (
                        <option key={p.user_id} value={p.user_id}>
                          {p.display_name} / 当前工单 {p.workload}
                        </option>
                      ))}
                  </select>
                </Field>
              )}
              <Field label="操作说明 / 处理结果">
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  required={!["accept", "start", "assign"].includes(operation)}
                  minLength={
                    ["resolve", "reject"].includes(operation) ? 5 : undefined
                  }
                  placeholder={
                    operation === "resolve"
                      ? "描述实际处理过程；提交前须上传证据"
                      : "记录本次操作依据"
                  }
                />
              </Field>
              <div className="actions">
                <button className="primary" disabled={action.busy}>
                  确认操作
                </button>
                <button type="button" onClick={() => setOperation("")}>
                  取消
                </button>
              </div>
            </form>
          )}
          <div className="two-col">
            <div>
              <h3 className="section-title">证据附件</h3>
              <div className="attachment-list">
                {d.attachments.map((a: Row) => (
                  <a
                    key={a.id}
                    href={"/api/attachments/" + a.id}
                    className="attachment"
                  >
                    <Paperclip size={15} />
                    <span>
                      {a.file_name}
                      <small>
                        {(a.size / 1024).toFixed(1)} KiB · {date(a.created_at)}
                      </small>
                    </span>
                    <Download size={15} />
                  </a>
                ))}
              </div>
              {!d.attachments.length && (
                <p className="muted">尚无附件。处理完成必须提交证据。</p>
              )}
              {(admin || tech) &&
                !["CLOSED", "CANCELLED"].includes(d.status) && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const form = new FormData(e.currentTarget);
                      void action.run(async () => {
                        await api(
                          "/orders/" + id + "/attachments",
                          "POST",
                          form,
                        );
                        await detail.reload();
                      }, "证据已保存到服务器");
                    }}
                  >
                    <Field label="上传证据（PNG / JPEG / TXT，最多5MiB）">
                      <input
                        type="file"
                        name="file"
                        accept=".png,.jpg,.jpeg,.txt"
                        required
                      />
                    </Field>
                    <button disabled={action.busy}>上传证据</button>
                  </form>
                )}
              {d.resolution && (
                <div className="resolution">
                  <h4>已提交处理结果</h4>
                  <p>{d.resolution}</p>
                </div>
              )}
            </div>
            <div>
              <h3 className="section-title">状态时间线</h3>
              <div className="timeline">
                {d.events.map((e: Row) => (
                  <div key={e.id}>
                    <i />
                    <div>
                      <strong>
                        {labels[e.to_status]} <span>{e.actor}</span>
                      </strong>
                      <p>{e.note}</p>
                      <small>{date(e.created_at)}</small>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {(user.role === "admin" || tech) && (
            <details className="feedback-section">
              <summary>追加关联预测的处置反馈</summary>
              <Field label="选择本资产的原始预测">
                <select
                  value={predictionId || ""}
                  onChange={(e) => setPredictionId(Number(e.target.value))}
                >
                  <option value="">选择预测记录</option>
                  {predictions.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      #{p.id} / {p.sample_key} / {percent(p.soh)}
                    </option>
                  ))}
                </select>
              </Field>
              {predictionId > 0 && (
                <FeedbackForm
                  predictionId={predictionId}
                  orderId={id}
                  onSaved={() => void detail.reload()}
                />
              )}
            </details>
          )}
          {d.feedback.length > 0 && (
            <div className="feedback-list">
              {d.feedback.map((f: Row) => (
                <div key={f.id}>
                  <Badge value={f.provenance} />
                  <strong>{percent(f.value)}</strong>
                  <span>{f.source}</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : detail.error ? (
        <Notice tone="error">{detail.error}</Notice>
      ) : (
        <Spinner />
      )}
    </Modal>
  );
}

export function Operations({ user }: { user: User }) {
  const [params] = useSearchParams(),
    navigate = useNavigate();
  const [tab, setTab] = useState(
      params.get("tab") || (user.role === "technician" ? "orders" : "alerts"),
    ),
    [orderId, setOrderId] = useState(Number(params.get("order")) || 0),
    [scenario, setScenario] = useState(false),
    [status, setStatus] = useState("");
  const alerts = useData<Row[]>("/alerts", 3000),
    orders = useData<Row[]>(
      "/orders" + (status ? "?status=" + status : ""),
      3000,
    ),
    assets = useData<Row[]>("/assets");
  const action = useAction(),
    admin = ["admin", "dispatcher"].includes(user.role);
  const highlighted = Number(params.get("alert"));
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ALERTS & CLOSED-LOOP SERVICE</div>
          <h1>告警与工单</h1>
          <p>从证据到派单、处理和独立验收。工单关闭不等于电池已恢复健康。</p>
        </div>
        <button disabled={!admin} onClick={() => setScenario(true)}>
          <Plus size={16} />
          注入独立演示场景
        </button>
      </div>
      {action.feedback}
      <div className="tabs">
        <button
          className={tab === "alerts" ? "active" : ""}
          onClick={() => setTab("alerts")}
        >
          告警事件{" "}
          <span>
            {alerts.data?.filter((a) => a.status !== "RESOLVED").length || 0}
          </span>
        </button>
        <button
          className={tab === "orders" ? "active" : ""}
          onClick={() => setTab("orders")}
        >
          工单管理 <span>{orders.data?.length || 0}</span>
        </button>
        <button
          className={tab === "people" ? "active" : ""}
          onClick={() => setTab("people")}
        >
          维修人员
        </button>
      </div>
      {tab === "alerts" && (
        <Panel
          title="待处理事件"
          subtitle="重复证据合并为同一活动告警；所有演示注入单独标记。"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>编号 / 资产</th>
                  <th>来源</th>
                  <th>复核原因</th>
                  <th>状态</th>
                  <th>处置</th>
                </tr>
              </thead>
              <tbody>
                {alerts.data?.map((a) => (
                  <tr
                    className={highlighted === a.id ? "highlight" : ""}
                    key={a.id}
                  >
                    <td>
                      <strong>AL-{a.id.toString().padStart(4, "0")}</strong>
                      <small>{a.asset_name}</small>
                    </td>
                    <td>
                      <Badge value={a.provenance} />
                    </td>
                    <td className="reason">
                      {a.reason}
                      <small>
                        {date(a.created_at)} · 累计 {a.occurrence_count} 次
                      </small>
                    </td>
                    <td>
                      <Badge value={a.status} />
                    </td>
                    <td>
                      <div className="actions">
                        {a.status === "OPEN" && (
                          <button
                            disabled={!admin || action.busy}
                            onClick={() =>
                              void action.run(async () => {
                                await api(
                                  "/alerts/" + a.id + "/transition",
                                  "POST",
                                  {
                                    version: a.version,
                                    action: "acknowledge",
                                    note: "调度确认收到事件",
                                  },
                                );
                                await alerts.reload();
                              })
                            }
                          >
                            确认告警
                          </button>
                        )}
                        {a.order_id ? (
                          <button onClick={() => setOrderId(a.order_id)}>
                            查看工单
                          </button>
                        ) : (
                          a.status !== "RESOLVED" && (
                            <button
                              className="primary"
                              disabled={!admin || action.busy}
                              onClick={() =>
                                void action.run(async () => {
                                  const r = await api(
                                    "/alerts/" + a.id + "/work-order",
                                    "POST",
                                  );
                                  setOrderId(r.id);
                                  await alerts.reload();
                                  await orders.reload();
                                })
                              }
                            >
                              生成工单
                            </button>
                          )
                        )}
                        {admin && a.status !== "RESOLVED" && (
                          <button
                            onClick={() => {
                              const note = window.prompt(
                                "解除告警依据（至少3字；不会修改原预测）",
                              );
                              if (note)
                                void action.run(async () => {
                                  await api(
                                    "/alerts/" + a.id + "/transition",
                                    "POST",
                                    {
                                      version: a.version,
                                      action: "resolve",
                                      note,
                                    },
                                  );
                                  await alerts.reload();
                                });
                            }}
                          >
                            解除
                          </button>
                        )}
                        {admin && a.status === "RESOLVED" && (
                          <button
                            onClick={() => {
                              const note = window.prompt("重新开启告警的依据");
                              if (note)
                                void action.run(async () => {
                                  await api(
                                    "/alerts/" + a.id + "/transition",
                                    "POST",
                                    {
                                      version: a.version,
                                      action: "reopen",
                                      note,
                                    },
                                  );
                                  await alerts.reload();
                                });
                            }}
                          >
                            重开
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!alerts.data?.length && (
            <Empty>
              暂无事件。可通过实际预测触发维护复核，或显式注入合成场景。
            </Empty>
          )}
        </Panel>
      )}
      {tab === "orders" && (
        <Panel
          title={user.role === "technician" ? "我的获派工单" : "工单台账"}
          subtitle="服务器状态机与版本校验；维修人员不能验收自己提交的处理结果。"
          actions={
            <select
              aria-label="筛选工单状态"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">全部状态</option>
              {[
                "CREATED",
                "ASSIGNED",
                "ACCEPTED",
                "IN_PROGRESS",
                "RESOLVED",
                "VERIFIED",
                "CLOSED",
                "CANCELLED",
              ].map((s) => (
                <option key={s} value={s}>
                  {labels[s]}
                </option>
              ))}
            </select>
          }
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>工单</th>
                  <th>资产</th>
                  <th>状态</th>
                  <th>维修人员</th>
                  <th>更新时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.data?.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <strong>WO-{o.id.toString().padStart(5, "0")}</strong>
                      <small>{o.title}</small>
                    </td>
                    <td>{o.asset_code}</td>
                    <td>
                      <Badge value={o.status} />
                    </td>
                    <td>{o.assignee_name || "待派发"}</td>
                    <td>{date(o.updated_at)}</td>
                    <td>
                      <button
                        className="primary"
                        onClick={() => setOrderId(o.id)}
                      >
                        打开工单
                        <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!orders.data?.length && <Empty />}
        </Panel>
      )}
      {tab === "people" && <Personnel user={user} />}
      {orderId > 0 && (
        <OrderDetail
          id={orderId}
          user={user}
          onClose={() => setOrderId(0)}
          onChanged={() => {
            void orders.reload();
            void alerts.reload();
          }}
        />
      )}
      {scenario && (
        <Modal title="独立演示场景" onClose={() => setScenario(false)}>
          <Notice>
            只创建明确标注的合成事件；不会伪造模型预测、BMS连接或精度结果。
          </Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void action.run(async () => {
                await api("/demo/events", "POST", {
                  asset_id: Number(f.get("asset_id")),
                  scenario: f.get("scenario"),
                });
                setScenario(false);
                setTab("alerts");
                await alerts.reload();
              }, "已创建合成演示事件");
            }}
          >
            <Field label="模拟资产">
              <select name="asset_id" required>
                <option value="">请选择</option>
                {assets.data
                  ?.filter((a) => a.kind === "cell")
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="场景">
              <select name="scenario">
                <option value="capacity-review">
                  容量复核任务（非模型预测）
                </option>
                <option value="sensor-temperature">
                  温度监测异常（合成传感器）
                </option>
                <option value="communication-loss">
                  通讯中断（非真实BMS）
                </option>
              </select>
            </Field>
            <button className="primary" disabled={action.busy}>
              创建带标记的演示事件
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}

export function SystemPage({ user }: { user: User }) {
  const [params] = useSearchParams(),
    navigate = useNavigate();
  const [tab, setTab] = useState(
      params.get("tab") || (user.role === "admin" ? "users" : "notifications"),
    ),
    [add, setAdd] = useState(false),
    [filter, setFilter] = useState("");
  const admin = user.role === "admin",
    auditAllowed = ["admin", "researcher", "dispatcher"].includes(user.role);
  const users = useData<Row[]>(admin ? "/users" : ""),
    notifications = useData<Row[]>("/notifications", 5000),
    audit = useData(
      auditAllowed ? "/audit?action=" + encodeURIComponent(filter) : "",
    );
  const action = useAction();
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACCESS & AUDIT</div>
          <h1>系统管理</h1>
          <p>最小授权、追加审计与明确的系统边界。</p>
        </div>
        <div className="actions">
          <Badge value={user.role} />
          <AccountPassword user={user} />
        </div>
      </div>
      {action.feedback}
      <div className="tabs">
        {admin && (
          <button
            className={tab === "users" ? "active" : ""}
            onClick={() => setTab("users")}
          >
            用户与角色
          </button>
        )}
        {auditAllowed && (
          <button
            className={tab === "audit" ? "active" : ""}
            onClick={() => setTab("audit")}
          >
            审计日志
          </button>
        )}
        <button
          className={tab === "notifications" ? "active" : ""}
          onClick={() => setTab("notifications")}
        >
          站内通知{" "}
          <span>
            {notifications.data?.filter((n) => !n.read_at).length || 0}
          </span>
        </button>
        <button
          className={tab === "help" ? "active" : ""}
          onClick={() => setTab("help")}
        >
          运行与边界
        </button>
      </div>
      {tab === "users" && admin && (
        <Panel
          title="本地账户"
          subtitle="没有默认口令与注册后门。修改角色后撤销该用户已有会话。"
          actions={
            <button className="primary" onClick={() => setAdd(true)}>
              <Plus size={16} />
              创建用户
            </button>
          }
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.display_name}</strong>
                      <small>@{u.username}</small>
                    </td>
                    <td>
                      <select
                        aria-label={"角色 " + u.username}
                        value={u.role}
                        onChange={(e) => {
                          const role = e.target.value;
                          void action.run(async () => {
                            await api("/users/" + u.id, "PUT", {
                              version: u.version,
                              role,
                              active: !!u.active,
                            });
                            await users.reload();
                          });
                        }}
                      >
                        {[
                          "admin",
                          "researcher",
                          "dispatcher",
                          "technician",
                          "viewer",
                        ].map((r) => (
                          <option key={r} value={r}>
                            {labels[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <Badge value={u.active ? "enabled" : "retired"} />
                    </td>
                    <td>{date(u.created_at)}</td>
                    <td>
                      <button
                        disabled={action.busy}
                        onClick={() =>
                          void action.run(async () => {
                            await api("/users/" + u.id, "PUT", {
                              version: u.version,
                              role: u.role,
                              active: !u.active,
                            });
                            await users.reload();
                          })
                        }
                      >
                        {u.active ? "停用" : "启用"}
                      </button>
                      {u.id !== user.id && (
                        <AccountPassword user={user} target={u} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Notice>
            管理员和调度员管理流程；算法研究员管理数据和模型；维修人员只能处理获派工单；观察者只读。
          </Notice>
        </Panel>
      )}
      {tab === "audit" && auditAllowed && (
        <Panel
          title="不可通过页面修改的审计记录"
          subtitle="真实发生的操作，由服务端记录操作者与时间。"
          actions={
            <input
              aria-label="审计操作筛选"
              placeholder="筛选操作名称…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          }
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作者</th>
                  <th>操作</th>
                  <th>对象</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {audit.data?.items.map((a: Row) => (
                  <tr key={a.id}>
                    <td>{date(a.created_at)}</td>
                    <td>{a.actor || "系统"}</td>
                    <td>
                      <code>{a.action}</code>
                    </td>
                    <td>
                      {a.entity} #{a.entity_id}
                    </td>
                    <td className="reason">
                      <code>{a.details}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel-foot">
            共 {audit.data?.total || 0} 条 · 显示最新50条
          </div>
        </Panel>
      )}
      {tab === "notifications" && (
        <Panel
          title="站内通知"
          subtitle="仅本地站内送达，不伪称已发送短信、邮件或外部消息。"
        >
          <div className="notifications">
            {notifications.data?.map((n) => (
              <div className={n.read_at ? "read" : ""} key={n.id}>
                <Bell size={18} />
                <div>
                  <strong>{n.title}</strong>
                  <p>{n.body}</p>
                  <small>{date(n.created_at)}</small>
                </div>
                <div className="actions">
                  {!n.read_at && (
                    <button
                      onClick={() =>
                        void action.run(async () => {
                          await api("/notifications/" + n.id + "/read", "POST");
                          await notifications.reload();
                        })
                      }
                    >
                      标记已读
                    </button>
                  )}
                  <button onClick={() => navigate(n.target)}>查看</button>
                </div>
              </div>
            ))}
          </div>
          {!notifications.data?.length && <Empty />}
        </Panel>
      )}
      {tab === "help" && (
        <>
          <Panel title="本地交付运行方式">
            <pre className="code-block">
              {
                "cd battery_platform\n./manage.sh setup       # 独立安装依赖\n./manage.sh bootstrap   # 创建首个管理员\n./manage.sh build       # 构建前端\n./manage.sh serve       # 127.0.0.1:8787\n./manage.sh test        # 后端测试\n./manage.sh backup      # 本地备份"
              }
            </pre>
            <Notice>
              应用不读取旧业务代码、数据库或口令。模型研究文件只读接入；更换机器需保留
              model_lab 的已验证数据、权重和匹配 Python 环境。
            </Notice>
          </Panel>
          <Panel title="模型与工业边界">
            <div className="boundary-grid">
              <div>
                <ShieldCheck />
                <h3>已经实现</h3>
                <p>
                  真实实验数据、模型任务、持久化告警与工单、人员资格过滤、独立验收和反馈审计。
                </p>
              </div>
              <div>
                <Network />
                <h3>明确未连接</h3>
                <p>
                  真实工业
                  BMS、物理设备控制、外部消息服务、生产现场身份和地理轨迹。
                </p>
              </div>
              <div>
                <Boxes />
                <h3>不作推断</h3>
                <p>
                  不把模拟维修当训练标签，不以 SOH 推断失效机理，不声称已实现
                  RUL 或校准安全概率。
                </p>
              </div>
            </div>
          </Panel>
        </>
      )}
      {add && (
        <Modal title="创建本地用户" onClose={() => setAdd(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void action.run(async () => {
                await api("/users", "POST", Object.fromEntries(f));
                setAdd(false);
                await users.reload();
              }, "用户已创建，密码不会在页面回显或保存到浏览器");
            }}
          >
            <Field label="用户名">
              <input
                name="username"
                required
                pattern="[A-Za-z0-9_.-]+"
                autoComplete="off"
              />
            </Field>
            <Field label="显示名称">
              <input name="display_name" required />
            </Field>
            <Field label="初始密码（至少12字符）">
              <input
                name="password"
                type="password"
                minLength={12}
                maxLength={128}
                required
                autoComplete="new-password"
              />
            </Field>
            <Field label="角色">
              <select name="role" defaultValue="viewer">
                {[
                  "admin",
                  "researcher",
                  "dispatcher",
                  "technician",
                  "viewer",
                ].map((r) => (
                  <option key={r} value={r}>
                    {labels[r]}
                  </option>
                ))}
              </select>
            </Field>
            <button className="primary" disabled={action.busy}>
              创建账户
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}
