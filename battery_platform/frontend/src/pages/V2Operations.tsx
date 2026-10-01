import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { type User, useData } from "../api";
import { Empty, Field, Notice, Panel, useAction } from "../components";
import {
  api,
  canDispatch,
  Evidence,
  listItems,
  numberValue,
  State,
  textValue,
  useV2Data,
  V2Job,
  V2Read,
  Version,
} from "../v2";

export function V2Operations({ user }: { user: User }) {
  const proposals = useV2Data(
      user.role !== "technician" ? "/v2/work-proposals?limit=50" : "",
      5000,
    ),
    orders = useData<any[]>("/orders", 5000),
    plans = useV2Data(
      user.role !== "technician" ? "/v2/dispatch/plans" : "",
      5000,
    ),
    resources = useV2Data(
      user.role !== "technician" ? "/v2/dispatch/resources" : "",
    );
  const [proposal, setProposal] = useState<any>(null),
    [note, setNote] = useState(""),
    [duration, setDuration] = useState(60),
    [maxRounds, setMaxRounds] = useState(3),
    [orderIds, setOrderIds] = useState<number[]>([]),
    [jobId, setJobId] = useState<number | null>(null),
    [planId, setPlanId] = useState<number | null>(null),
    [assignments, setAssignments] = useState<any[]>([]),
    [horizon, setHorizon] = useState(480),
    [resourceText, setResourceText] = useState(""),
    [showResource, setShowResource] = useState(false);
  const plan = useV2Data(planId ? `/v2/dispatch/plans/${planId}` : "", 3000),
    action = useAction(),
    p = plan.data;
  useEffect(() => {
    if (p?.result?.assignments)
      setAssignments(p.result.assignments.map((a: any) => ({ ...a })));
  }, [planId, p?.version, p?.status]);
  useEffect(() => {
    if (resources.data)
      setResourceText(
        JSON.stringify(
          resources.data.payload || resources.data.resources || resources.data,
          null,
          2,
        ),
      );
  }, [resources.data]);
  return (
    <>
      {user.role !== "technician" && (
        <>
          <Panel
            title="诊断提案与人工确认"
            subtitle="LLM 只能生成提案；审批创建正式工单，分配仍须另行确认。"
          >
            <V2Read resource={proposals}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>提案 / 报告</th>
                      <th>状态 / 版本</th>
                      <th>授权范围</th>
                      <th>确认</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listItems(proposals.data).map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.title}</strong>
                          <small>
                            报告 #{item.report_id} · 资产{" "}
                            {textValue(item.asset_ids || item.asset_id)}
                          </small>
                          <Link
                            to={`/diagnosis/${item.session_id || "new"}${item.run_id ? `?run=${item.run_id}` : ""}`}
                          >
                            查看诊断依据
                          </Link>
                        </td>
                        <td>
                          <State value={item.status} />
                          <Version value={item.version} />
                          {item.order_id && (
                            <Link
                              to={`/operations?tab=orders&order=${item.order_id}`}
                            >
                              工单 #{item.order_id}
                            </Link>
                          )}
                        </td>
                        <td>
                          <Evidence
                            title="测试、技能、工具、时长与截止时间"
                            value={item.payload || item}
                          />
                        </td>
                        <td>
                          <button
                            disabled={
                              !canDispatch(user.role) ||
                              action.busy ||
                              Boolean(item.order_id) ||
                              ![
                                "pending",
                                "PENDING",
                                "PROPOSED",
                                "proposed",
                                "PENDING_APPROVAL",
                              ].includes(item.status)
                            }
                            onClick={() => {
                              setProposal(item);
                              setDuration(
                                item.duration_minutes ||
                                  item.payload?.duration_minutes ||
                                  60,
                              );
                              setMaxRounds(
                                item.max_rounds ||
                                  item.payload?.max_rounds ||
                                  3,
                              );
                            }}
                          >
                            审阅并确认提案
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!listItems(proposals.data).length && (
                <Empty>没有待确认提案。</Empty>
              )}
            </V2Read>
            {proposal && (
              <form
                className="v2-record"
                onSubmit={(e) => {
                  e.preventDefault();
                  void action.run(async () => {
                    await api(
                      `/v2/work-proposals/${proposal.id}/approve`,
                      "POST",
                      {
                        version: proposal.version,
                        note,
                        duration_minutes: duration,
                        max_rounds: maxRounds,
                      },
                    );
                    setProposal(null);
                    setNote("");
                    await proposals.reload();
                    await orders.reload();
                  }, "提案已确认并创建正式工单；尚未派发");
                }}
              >
                <h3>确认提案 #{proposal.id}</h3>
                <div className="form-grid">
                  <Field label="预计执行分钟">
                    <input
                      required
                      type="number"
                      min={1}
                      max={1440}
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="最多授权轮次">
                    <input
                      required
                      type="number"
                      min={1}
                      max={20}
                      value={maxRounds}
                      onChange={(e) => setMaxRounds(Number(e.target.value))}
                    />
                  </Field>
                </div>
                <Field label="提案审批说明">
                  <textarea
                    required
                    minLength={3}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </Field>
                <Evidence
                  title="本次批准测试与必填要求"
                  value={
                    proposal.allowed_tests || proposal.payload?.allowed_tests
                  }
                />
                <div className="actions">
                  <button className="primary" disabled={action.busy}>
                    确认并创建正式工单
                  </button>
                  <button type="button" onClick={() => setProposal(null)}>
                    取消审阅
                  </button>
                </div>
              </form>
            )}
          </Panel>
          <Panel
            title="约束排程与人员负载"
            subtitle="先求解可编辑草案，再由调度员确认；输入版本或接单状态变化会产生冲突。"
            actions={
              <button
                disabled={!canDispatch(user.role)}
                onClick={() => setShowResource(!showResource)}
              >
                排班与工具资源
              </button>
            }
          >
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  const result = await api("/v2/dispatch/plans", "POST", {
                    order_ids: orderIds,
                    horizon_start: new Date().toISOString(),
                    horizon_minutes: horizon,
                    time_limit_seconds: 10,
                  });
                  setPlanId(result.plan_id);
                  setJobId(result.job_id);
                  await plans.reload();
                }, "排程求解已提交；没有自动派发");
              }}
            >
              <div className="checks">
                {orders.data
                  ?.filter(
                    (o) =>
                      !["CLOSED", "CANCELLED", "VERIFIED"].includes(o.status),
                  )
                  .map((o) => (
                    <label key={o.id}>
                      <input
                        type="checkbox"
                        checked={orderIds.includes(o.id)}
                        onChange={(e) =>
                          setOrderIds(
                            e.target.checked
                              ? [...orderIds, o.id]
                              : orderIds.filter((id) => id !== o.id),
                          )
                        }
                      />
                      工单 #{o.id} {o.title} · {o.status}
                    </label>
                  ))}
              </div>
              <div className="v2-form-inline">
                <Field label="排程范围 / 分钟">
                  <input
                    type="number"
                    required
                    min={30}
                    max={10080}
                    value={horizon}
                    onChange={(e) => setHorizon(Number(e.target.value))}
                  />
                </Field>
                <button
                  className="primary"
                  disabled={
                    !canDispatch(user.role) || !orderIds.length || action.busy
                  }
                >
                  求解排程草案
                </button>
              </div>
            </form>
            {showResource && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void action.run(async () => {
                    await api("/v2/dispatch/resources", "PUT", {
                      version: resources.data.version,
                      payload: JSON.parse(resourceText),
                    });
                    await resources.reload();
                  }, "排班资源版本已更新");
                }}
              >
                <Field label="排班、工程师分钟容量、工具数量与路程时间">
                  <textarea
                    className="v2-code-input"
                    required
                    value={resourceText}
                    onChange={(e) => setResourceText(e.target.value)}
                  />
                </Field>
                <p>
                  时间为相对求解起点的分钟；工程师 ID 为服务端用户
                  ID，资格仍由人员档案决定。
                </p>
                <button disabled={!canDispatch(user.role) || action.busy}>
                  保存资源新版本
                </button>
              </form>
            )}
            <V2Read resource={plans}>
              <div className="v2-summary">
                {listItems(plans.data).map((item) => (
                  <button key={item.id} onClick={() => setPlanId(item.id)}>
                    草案 #{item.id} · {item.status} · v{item.version}
                  </button>
                ))}
              </div>
              {!listItems(plans.data).length && <Empty>尚无排程草案。</Empty>}
            </V2Read>
            {p && (
              <>
                <div className="v2-summary">
                  <State value={p.status} reason={p.job_error} />
                  <Version value={p.version} />
                  <span>求解 {p.result?.status || "等待作业"}</span>
                  <span>
                    {p.result?.lexicographic_complete === false
                      ? "超时得到可行解，后续目标未完成"
                      : "目标完成状态见求解依据"}
                  </span>
                </div>
                <ScheduleTimeline
                  assignments={assignments}
                  horizon={p.input_snapshot?.horizon_minutes || horizon}
                />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>工单</th>
                        <th>工程师 ID</th>
                        <th>开始 / 分钟</th>
                        <th>结束 / 分钟</th>
                        <th>锁定</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignments.map((a, i) => (
                        <tr key={a.order_id}>
                          <td>#{a.order_id}</td>
                          {["engineer_id", "start", "end"].map((field) => (
                            <td key={field}>
                              <input
                                aria-label={`工单 ${a.order_id} ${field}`}
                                type="number"
                                min={0}
                                disabled={
                                  !canDispatch(user.role) ||
                                  p.status !== "DRAFT" ||
                                  a.locked
                                }
                                value={a[field]}
                                onChange={(e) =>
                                  setAssignments(
                                    assignments.map((v, j) =>
                                      i === j
                                        ? {
                                            ...v,
                                            [field]: Number(e.target.value),
                                          }
                                        : v,
                                    ),
                                  )
                                }
                              />
                            </td>
                          ))}
                          <td>{a.locked ? "已接单锁定" : "可调整"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="actions">
                  <button
                    disabled={
                      !canDispatch(user.role) ||
                      p.status !== "DRAFT" ||
                      action.busy
                    }
                    onClick={() =>
                      void action.run(async () => {
                        await api(`/v2/dispatch/plans/${p.id}`, "PATCH", {
                          version: p.version,
                          assignments: assignments.map(
                            ({ order_id, engineer_id, start, end }) => ({
                              order_id,
                              engineer_id,
                              start,
                              end,
                            }),
                          ),
                        });
                        await plan.reload();
                      }, "草案已重新校验并保存")
                    }
                  >
                    校验并保存调整
                  </button>
                  <button
                    className="primary"
                    disabled={
                      !canDispatch(user.role) ||
                      p.status !== "DRAFT" ||
                      action.busy ||
                      !assignments.length
                    }
                    onClick={() =>
                      void action.run(async () => {
                        await api(
                          `/v2/dispatch/plans/${p.id}/confirm`,
                          "POST",
                          { version: p.version },
                        );
                        await plan.reload();
                        await orders.reload();
                        await plans.reload();
                      }, "排程已由人员确认并派发")
                    }
                  >
                    人工确认排程
                  </button>
                  <button onClick={() => void plan.reload()}>
                    刷新草案版本
                  </button>
                </div>
                {p.result?.unassigned?.length > 0 && (
                  <Notice>
                    <strong>未分配任务</strong>
                    {p.result.unassigned.map((u: any) => (
                      <p key={u.order_id}>
                        工单 #{u.order_id}：{textValue(u.reasons)}
                      </p>
                    ))}
                  </Notice>
                )}
                <Evidence
                  title="硬约束、目标与输入快照"
                  value={{ result: p.result, snapshot: p.input_snapshot }}
                />
              </>
            )}
          </Panel>
        </>
      )}
      {action.feedback}
      <V2Job
        user={user}
        id={jobId}
        canCancel={canDispatch(user.role)}
        onComplete={() => {
          void plans.reload();
          void plan.reload();
        }}
      />
      <V2Inspection user={user} orders={orders.data || []} />
    </>
  );
}

function ScheduleTimeline({
  assignments,
  horizon,
}: {
  assignments: any[];
  horizon: number;
}) {
  if (!assignments.length) return null;
  const engineers = [...new Set(assignments.map((a) => a.engineer_id))];
  return (
    <div className="v2-schedule" role="img" aria-label="排程甘特与人员负载">
      {engineers.map((id) => {
        const tasks = assignments.filter((a) => a.engineer_id === id),
          load = tasks.reduce((sum, a) => sum + a.end - a.start, 0);
        return (
          <div className="v2-schedule-row" key={id}>
            <strong>
              工程师 #{id}
              <small>负载 {load} 分钟</small>
            </strong>
            <div className="v2-schedule-track">
              {tasks.map((a) => (
                <span
                  title={`工单 #${a.order_id} ${a.start}–${a.end} 分钟`}
                  key={a.order_id}
                  style={{
                    left: `${(a.start / horizon) * 100}%`,
                    width: `${((a.end - a.start) / horizon) * 100}%`,
                  }}
                >
                  #{a.order_id}
                </span>
              ))}
            </div>
          </div>
        );
      })}
      <p>相对起点 0–{horizon} 分钟；只展示服务端已求解的真实草案。</p>
    </div>
  );
}

function V2Inspection({ user, orders }: { user: User; orders: any[] }) {
  const [search] = useSearchParams(),
    [orderId, setOrderId] = useState(search.get("order") || ""),
    inspection = useV2Data(
      orderId ? `/v2/orders/${orderId}/inspection` : "",
      5000,
    ),
    action = useAction();
  const [testId, setTestId] = useState(""),
    [result, setResult] = useState("inconclusive"),
    [freeText, setFreeText] = useState(""),
    [metric, setMetric] = useState(""),
    [value, setValue] = useState(""),
    [unit, setUnit] = useState(""),
    [method, setMethod] = useState(""),
    [instrument, setInstrument] = useState(""),
    [calibration, setCalibration] = useState("unknown"),
    [provenance, setProvenance] = useState("synthetic"),
    [attachmentIds, setAttachmentIds] = useState(""),
    [jobId, setJobId] = useState<number | null>(null);
  const d = inspection.data,
    o = d?.order || d,
    round =
      (typeof d?.current_round === "object"
        ? d.current_round?.round
        : d?.current_round) ||
      d?.round ||
      1,
    tests = d?.allowed_tests || d?.authorization?.allowed_tests || [];
  const editable = ["technician", "admin", "dispatcher"].includes(user.role);
  return (
    <Panel
      title="授权测试与检查轮次"
      subtitle="仅正式工单可回填；失败、拒测与未测保持未知，提交轮次检查要求。"
    >
      <Field label="查看检查轮次的工单">
        <select value={orderId} onChange={(e) => setOrderId(e.target.value)}>
          <option value="">选择正式工单</option>
          {orders.map((o) => (
            <option key={o.id} value={o.id}>
              #{o.id} {o.title} · {o.status}
            </option>
          ))}
        </select>
      </Field>
      {orderId && (
        <V2Read resource={inspection}>
          <div className="v2-summary">
            <Version value={o?.version || d?.order_version} label="工单" />
            <span>
              安装 {textValue(d?.installation_id || o?.installation_id)}
            </span>
            <State value={d?.status || o?.status} />
            <span>第 {textValue(round)} 轮</span>
          </div>
          <Evidence title="授权测试、轮次必填项与原报告" value={d} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                const response = await api(
                  `/v2/orders/${orderId}/observations`,
                  "POST",
                  {
                    installation_id: d.installation_id || o.installation_id,
                    round,
                    order_version: o.version || d.order_version,
                    test_id: testId,
                    measured_at: new Date().toISOString(),
                    instrument_id: instrument || "not_recorded",
                    calibration_status: calibration,
                    measurements:
                      value === ""
                        ? []
                        : [{ metric, value: Number(value), unit, method }],
                    free_text: freeText,
                    result,
                    provenance,
                    attachment_ids: attachmentIds
                      .split(",")
                      .filter((v) => v.trim())
                      .map(Number),
                    client_submission_id: crypto.randomUUID(),
                  },
                );
                setJobId(
                  response.rejudgment_job_id ||
                    response.job_id ||
                    response.extraction_job_id,
                );
                setFreeText("");
                await inspection.reload();
              }, "观察事实已保存；重判由后台处理");
            }}
          >
            <div className="form-grid">
              <Field label="已授权测试">
                <select
                  required
                  value={testId}
                  onChange={(e) => setTestId(e.target.value)}
                >
                  <option value="">选择测试</option>
                  {tests.map((t: any, i: number) => (
                    <option
                      key={i}
                      value={typeof t === "string" ? t : t.test_id || t.id}
                    >
                      {typeof t === "string" ? t : t.name || t.test_id || t.id}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="测试结果状态">
                <select
                  value={result}
                  onChange={(e) => setResult(e.target.value)}
                >
                  {[
                    "observed",
                    "inconclusive",
                    "failed",
                    "out_of_range",
                    "refused",
                    "requires_authorization",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="测量指标">
                <input
                  value={metric}
                  onChange={(e) => setMetric(e.target.value)}
                  required={value !== ""}
                />
              </Field>
              <Field label="测量数值（未测留空）">
                <input
                  type="number"
                  step="any"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </Field>
              <Field label="测量单位">
                <input
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  required={value !== ""}
                />
              </Field>
              <Field label="规程 / 方法 ID">
                <input
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  required={value !== ""}
                />
              </Field>
              <Field label="仪器身份">
                <input
                  value={instrument}
                  onChange={(e) => setInstrument(e.target.value)}
                />
              </Field>
              <Field label="仪器校准状态">
                <select
                  value={calibration}
                  onChange={(e) => setCalibration(e.target.value)}
                >
                  {["calibrated", "unknown", "expired", "not_applicable"].map(
                    (v) => (
                      <option key={v}>{v}</option>
                    ),
                  )}
                </select>
              </Field>
              <Field label="观察来源">
                <select
                  value={provenance}
                  onChange={(e) => setProvenance(e.target.value)}
                >
                  <option value="synthetic">合成演示</option>
                  <option value="experimental_replay">实验回放</option>
                  <option value="measured_declared">声明实测·未复核</option>
                </select>
              </Field>
              <Field label="本工单已上传附件 ID（逗号分隔）">
                <input
                  value={attachmentIds}
                  onChange={(e) => setAttachmentIds(e.target.value)}
                />
              </Field>
            </div>
            <Field label="检查原始自由文字">
              <textarea
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
              />
            </Field>
            <div className="actions">
              <button className="primary" disabled={!editable || action.busy}>
                提交本次观察
              </button>
              <button
                type="button"
                disabled={!editable || action.busy}
                onClick={() =>
                  void action.run(async () => {
                    const response = await api(
                      `/v2/orders/${orderId}/rounds/${round}/submit`,
                      "POST",
                      {
                        order_version: o.version || d.order_version,
                        installation_id: d.installation_id || o.installation_id,
                        client_submission_id: crypto.randomUUID(),
                      },
                    );
                    setJobId(response.job_id || response.rejudgment_job_id);
                    await inspection.reload();
                  }, "本轮已提交，仍需独立验收")
                }
              >
                完成本轮并检查要求
              </button>
            </div>
          </form>
          {!editable && (
            <Notice>技术员回填授权工单；调度员在既有工单流程独立验收。</Notice>
          )}
          {(d?.observations || []).map((obs: any) => (
            <article className="v2-record" key={obs.id}>
              <details>
                <summary>原始观察 #{obs.id}</summary>
                <p>{obs.free_text || "无自由文字"}</p>
              </details>
              <Evidence title="结构化测量、抽取事实与来源" value={obs} />
              <ObservationCorrection
                observation={obs}
                enabled={
                  editable &&
                  (user.role !== "technician" || obs.author_id === user.id)
                }
                onSaved={() => void inspection.reload()}
              />
            </article>
          ))}
        </V2Read>
      )}
      {action.feedback}
      <V2Job
        user={user}
        id={jobId}
        onComplete={() => void inspection.reload()}
      />
    </Panel>
  );
}

function ObservationCorrection({
  observation,
  enabled,
  onSaved,
}: {
  observation: any;
  enabled: boolean;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false),
    [index, setIndex] = useState(-1),
    [claim, setClaim] = useState(""),
    [quote, setQuote] = useState(""),
    [trust, setTrust] = useState("reported"),
    [note, setNote] = useState(""),
    action = useAction();
  const facts = observation.candidate_facts || [];
  return (
    <>
      <button disabled={!enabled} onClick={() => setOpen(!open)}>
        修正抽取事实 #{observation.id}
      </button>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const start = observation.free_text.indexOf(quote);
              if (start < 0 || !quote)
                throw new Error("来源片段必须与原始自由文字完全一致");
              const fact = {
                  claim,
                  span: { start, end: start + quote.length },
                  source_text: quote,
                  trust,
                },
                candidate_facts =
                  index < 0
                    ? [...facts, fact]
                    : facts.map((f: any, i: number) =>
                        i === index ? fact : f,
                      );
              await api(`/v2/observations/${observation.id}/facts`, "POST", {
                version: observation.version,
                candidate_facts,
                note,
              });
              setOpen(false);
              onSaved();
            }, "事实纠正已版本化保存；原始文字保留");
          }}
        >
          <div className="form-grid">
            <Field label="需要修正的抽取项">
              <select
                value={index}
                onChange={(e) => {
                  const i = Number(e.target.value);
                  setIndex(i);
                  setClaim(facts[i]?.claim || "");
                  setQuote(facts[i]?.source_text || "");
                  setTrust(facts[i]?.trust || "reported");
                }}
              >
                <option value={-1}>追加遗漏事实</option>
                {facts.map((f: any, i: number) => (
                  <option key={i} value={i}>
                    {f.claim}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="事实确定性">
              <select value={trust} onChange={(e) => setTrust(e.target.value)}>
                <option value="reported">原文报告</option>
                <option value="measurement_supported">测量支持</option>
                <option value="contradicted">已有反证</option>
              </select>
            </Field>
            <Field label="修正后的具体断言">
              <input
                required
                value={claim}
                onChange={(e) => setClaim(e.target.value)}
              />
            </Field>
            <Field label="原始文字中的准确片段">
              <input
                required
                value={quote}
                onChange={(e) => setQuote(e.target.value)}
              />
            </Field>
            <Field label="抽取纠正说明">
              <input
                required
                minLength={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </Field>
          </div>
          <button disabled={!enabled || action.busy}>保存抽取纠正版本</button>
        </form>
      )}
      {action.feedback}
    </>
  );
}
