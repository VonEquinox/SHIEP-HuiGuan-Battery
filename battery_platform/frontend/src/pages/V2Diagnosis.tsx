import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { type User, useData } from "../api";
import type { IncidentNumericEvidence } from "../contracts/v2";
import {
  Badge,
  Empty,
  Field,
  Notice,
  Panel,
  LineChart,
  useAction,
} from "../components";
import {
  api,
  canDiagnose,
  canDispatch,
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

export function RiskCenter({ user }: { user: User }) {
  const [severity, setSeverity] = useState(""),
    [cursor, setCursor] = useState<number | null>(null),
    [expanded, setExpanded] = useState<any>(null),
    [jobId, setJobId] = useState<number | null>(null),
    [assetIds, setAssetIds] = useState<number[]>([]);
  const assets = useData<any[]>("/assets");
  const r = useV2Data(
      `/v2/incidents?limit=30${severity ? `&severity=${severity}` : ""}${cursor ? `&cursor=${cursor}` : ""}`,
      5000,
    ),
    detail = useV2Data(expanded ? `/v2/incidents/${expanded.id}` : ""),
    action = useAction(),
    navigate = useNavigate();
  const selected = detail.data || expanded;
  const [splitIds, setSplitIds] = useState<number[]>([]),
    [splitNote, setSplitNote] = useState("");
  return (
    <>
      <V2Heading
        title="风险与群组"
        subtitle="聚合共享证据、重复事件与数据质量问题；诊断完成后由人员确认提案。"
      >
        <button
          disabled={
            !canDiagnose(user.role) || action.busy || assetIds.length < 2
          }
          onClick={() =>
            void action.run(async () => {
              const result = await api("/v2/incidents/analyze", "POST", {
                asset_ids: assetIds,
                visible_cutoff: new Date().toISOString(),
                window_minutes: 60,
              });
              setJobId(result.job_id);
              await r.reload();
            }, "风险分析已提交")
          }
        >
          分析当前风险
        </button>
      </V2Heading>
      {action.feedback}
      <Panel title="分析范围">
        <div className="checks">
          {assets.data
            ?.filter((a) => a.kind === "cell")
            .map((a) => (
              <label key={a.id}>
                <input
                  type="checkbox"
                  checked={assetIds.includes(a.id)}
                  onChange={(e) =>
                    setAssetIds(
                      e.target.checked
                        ? [...assetIds, a.id]
                        : assetIds.filter((id) => id !== a.id),
                    )
                  }
                />
                {a.name}
              </label>
            ))}
        </div>
        <p>选择至少两个资产，聚合当前截止时间之前的结构化证据。</p>
      </Panel>
      <Panel
        title="资产与群组事件"
        actions={
          <Field label="风险严重性筛选">
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setCursor(null);
              }}
            >
              <option value="">全部</option>
              {["critical", "high", "medium", "low", "unknown"].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
        }
      >
        <V2Read resource={r}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>事件 / 群组</th>
                  <th>严重性 / 状态</th>
                  <th>共享证据与不足</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {listItems(r.data).map((i) => (
                  <tr key={i.id}>
                    <td>
                      <strong>{i.title || i.name || `事件 #${i.id}`}</strong>
                      <small>{textValue(i.group_key || i.asset_id)}</small>
                      <Provenance
                        value={i.provenance}
                        scenario={i.synthetic_scenario_id}
                      />
                    </td>
                    <td>
                      <Badge value={i.severity} />
                      <State value={i.status} stale={i.stale} />
                    </td>
                    <td>
                      {textValue(i.reason || i.evidence_status)}
                      <small>
                        重复 {textValue(i.duplicate_of || i.repeat_count)} ·
                        数据问题 {textValue(i.data_quality_issues)}
                      </small>
                    </td>
                    <td>
                      <button onClick={() => setExpanded(i)}>
                        展开群组与依据
                      </button>
                      <button
                        disabled={
                          !canDiagnose(user.role) ||
                          !(i.asset_id || i.members?.[0]?.asset_id)
                        }
                        onClick={() =>
                          navigate(
                            `/diagnosis/new?asset=${i.asset_id || i.members?.[0]?.asset_id}&incident=${i.id}`,
                          )
                        }
                      >
                        创建诊断
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!listItems(r.data).length && (
            <Empty>暂无风险事件。缺少观测的资产不会显示为正常。</Empty>
          )}
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
      </Panel>
      {selected && (
        <Panel
          title={`群组详情 #${selected.id}`}
          actions={<button onClick={() => setExpanded(null)}>收起群组</button>}
        >
          <V2Read resource={detail}>
            <GroupNumericEvidence
              evidence={selected.evidence || {}}
              provenance={selected.provenance}
            />
            <Evidence title="共享证据、重复事件与数据问题" value={selected} />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  await api(`/v2/incidents/${selected.id}/split`, "POST", {
                    version: selected.version,
                    note: splitNote,
                    member_asset_ids: splitIds,
                  });
                  setExpanded(null);
                  setSplitIds([]);
                  await r.reload();
                }, "群组已拆分，单体原始告警保留");
              }}
            >
              <div className="checks">
                {selected.members?.map((member: any) => (
                  <label key={member.asset_id}>
                    <input
                      type="checkbox"
                      checked={splitIds.includes(member.asset_id)}
                      onChange={(e) =>
                        setSplitIds(
                          e.target.checked
                            ? [...splitIds, member.asset_id]
                            : splitIds.filter((id) => id !== member.asset_id),
                        )
                      }
                    />
                    拆出资产 #{member.asset_id}
                  </label>
                ))}
              </div>
              <Field label="群组拆分依据">
                <input
                  minLength={3}
                  required
                  value={splitNote}
                  onChange={(e) => setSplitNote(e.target.value)}
                />
              </Field>
              <button
                disabled={
                  !canDispatch(user.role) ||
                  !splitIds.length ||
                  splitIds.length === selected.members?.length ||
                  action.busy
                }
              >
                按证据拆分群组
              </button>
            </form>
            <div className="v2-summary">
              {(selected.members || selected.asset_ids || []).map(
                (a: any, index: number) => {
                  const id = typeof a === "object" ? a.asset_id || a.id : a;
                  return (
                    <Link className="button" key={index} to={`/assets/${id}`}>
                      成员资产 #{id}
                    </Link>
                  );
                },
              )}
            </div>
          </V2Read>
        </Panel>
      )}
      <V2Job
        user={user}
        id={jobId}
        canCancel={canDiagnose(user.role)}
        onComplete={() => void r.reload()}
      />
    </>
  );
}

function GroupNumericEvidence({
  evidence,
  provenance,
}: {
  evidence: IncidentNumericEvidence;
  provenance?: string;
}) {
  const numeric = evidence.numeric_analysis,
    comparable = evidence.comparison,
    support = evidence.numeric_support,
    pairs = numeric?.qualified_pairs?.length
      ? numeric.qualified_pairs.map((pair) => ({
          ...pair,
          ...numeric.pair_evidence?.find(
            (candidate) =>
              candidate.members.join("|") === pair.members.join("|"),
          ),
        }))
      : numeric?.pair_evidence || [],
    sources = Array.isArray(evidence.source_refs) ? evidence.source_refs : [],
    residuals = Object.entries(numeric?.residuals || {}).flatMap(
      ([installation, values]) =>
        Object.entries(values).map(([timestamp, residual]) => ({
          installation,
          timestamp,
          residual,
        })),
    );
  return (
    <section aria-label="同工况残差关联与来源资格">
      <h3>同工况残差关联</h3>
      <div className="v2-summary">
        <State
          value={
            support?.status ||
            (evidence.numeric_correlation_supported === true
              ? "supported"
              : "unsupported")
          }
        />
        <Version value={numeric?.threshold_version} label="比较阈值" />
        <Provenance value={provenance} />
      </div>
      <Notice>
        残差相关只表示同步关联，不能确认共同根因；仍须检查采集通道、环境和单体原因。
      </Notice>
      {support?.reasons?.length ? (
        <ul>
          {support.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : evidence.numeric_correlation_supported !== true ? (
        <p>
          缺少合格的同工况参考或精确对齐测量，数值关联未支持；拓扑关联不代表因果。
        </p>
      ) : null}
      {comparable && (
        <div className="v2-summary">
          <span>
            指标 / 单位 / 方法 {textValue(comparable.metric)} /{" "}
            {textValue(comparable.unit)} / {textValue(comparable.method)}
          </span>
          <span>
            体系 / 协议 {textValue(comparable.chemistry)} /{" "}
            {textValue(comparable.protocol_id)}
          </span>
          <span>负载 {textValue(comparable.load_condition)}</span>
          <span>温度 {textValue(comparable.temperature_condition)}</span>
          <span>同源批次 {textValue(comparable.source_cohort_id)}</span>
          {comparable.origin && <Provenance value={comparable.origin} />}
        </div>
      )}
      <p>
        后台仅在当前安装、授权测量、有效校准与可比条件成立时比较。正常参考须明确声明并早于分析点；实验回放不参加站内比较，合成来源只用于演示。
      </p>
      {pairs.length > 0 && (
        <div className="table-wrap">
          <table aria-label="残差相关与精确对齐点">
            <thead>
              <tr>
                <th>安装对</th>
                <th>残差相关</th>
                <th>精确对齐点</th>
                <th>异常重叠点</th>
                <th>关联依据</th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((pair, i) => (
                <tr key={i}>
                  <td>{pair.members.join(" / ")}</td>
                  <td>
                    {pair.correlation == null
                      ? "未支持"
                      : numberValue(pair.correlation)}
                  </td>
                  <td>{textValue(pair.aligned_points)}</td>
                  <td>{textValue(pair.event_overlap)}</td>
                  <td>
                    {pair.shared_relations?.length
                      ? pair.shared_relations.join("、")
                      : "未达到群组阈值 / 未提供共享依据"}{" "}
                    · 未确认因果
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {numeric?.quality_flags &&
        Object.keys(numeric.quality_flags).length > 0 && (
          <div className="v2-record">
            <strong>参考窗口与测量质量</strong>
            {Object.entries(numeric.quality_flags).map(
              ([installation, flags]) => (
                <p key={installation}>
                  安装 {installation}：
                  {flags.length ? flags.join("、") : "未报告质量问题"}
                </p>
              ),
            )}
          </div>
        )}
      {evidence.measurement_rejections &&
        Object.keys(evidence.measurement_rejections).length > 0 && (
          <div className="v2-record">
            <strong>未满足比较资格的观察</strong>
            {Object.entries(evidence.measurement_rejections).map(
              ([asset, reasons]) => (
                <p key={asset}>
                  资产 #{asset}：
                  {reasons.length ? reasons.join("、") : "未报告不合格原因"}
                </p>
              ),
            )}
          </div>
        )}
      {residuals.length > 0 && (
        <details>
          <summary>查看按正常参考中位数与 MAD 计算的残差</summary>
          <div className="table-wrap">
            <table aria-label="服务端计算的标准化残差">
              <thead>
                <tr>
                  <th>安装</th>
                  <th>对齐时间</th>
                  <th>标准化残差</th>
                </tr>
              </thead>
              <tbody>
                {residuals.map((row) => (
                  <tr key={`${row.installation}-${row.timestamp}`}>
                    <td>{row.installation}</td>
                    <td>{row.timestamp}</td>
                    <td>
                      {row.residual == null
                        ? "未支持"
                        : numberValue(row.residual)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {sources.length > 0 && (
        <div className="table-wrap">
          <table aria-label="比较观察的来源与参考资格">
            <thead>
              <tr>
                <th>原始观察 / 安装</th>
                <th>参考资格</th>
                <th>记录 / 可见时间</th>
                <th>来源与信任</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source, i) => (
                <tr key={`${source.observation_id}-${i}`}>
                  <td>
                    #{source.observation_id} · v{source.version}
                    <small>{source.installation_id}</small>
                  </td>
                  <td>
                    {source.role === "reference"
                      ? "使用者声明的早期正常参考"
                      : "分析观察"}
                  </td>
                  <td>
                    {source.measured_at}
                    <small>可见于 {source.available_at}</small>
                  </td>
                  <td>
                    <Provenance value={source.origin} />
                    {source.source_trust === "reported"
                      ? "声明证据 · 未独立复核"
                      : textValue(source.source_trust)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Evidence title="来源与参考窗口资格" value={evidence.source_refs} />
    </section>
  );
}

export function Diagnosis({ user }: { user: User }) {
  const { session = "new" } = useParams(),
    [search] = useSearchParams(),
    navigate = useNavigate(),
    assets = useData<any[]>("/assets");
  const [assetId, setAssetId] = useState(search.get("asset") || ""),
    [cutoff, setCutoff] = useState(
      search.get("cutoff") || new Date().toISOString(),
    ),
    [runId, setRunId] = useState<number | null>(
      Number(search.get("run")) || null,
    ),
    [jobId, setJobId] = useState<number | null>(null);
  const recentRuns = useV2Data(
    session === "new" ? "/v2/agent/runs?limit=30" : "",
    5000,
  );
  const r = useV2Data(
      session !== "new" ? `/v2/diagnostic-sessions/${session}` : "",
      5000,
    ),
    run = useV2Data(runId ? `/v2/agent/runs/${runId}` : "", 3000),
    profile = useV2Data(
      assetId
        ? `/v2/assets/${assetId}/prediction-profile?cutoff=${encodeURIComponent(cutoff)}`
        : "",
    ),
    action = useAction();
  const sessionData = r.data,
    runData = run.data,
    reportRecord =
      runData?.report || sessionData?.reports?.[sessionData.reports.length - 1],
    report =
      reportRecord?.report ||
      runData?.result?.report ||
      sessionData?.latest_report ||
      reportRecord;
  useEffect(() => {
    if (sessionData?.asset_id) setAssetId(String(sessionData.asset_id));
    if (!runId && (sessionData?.latest_run_id || sessionData?.runs?.length))
      setRunId(
        sessionData.latest_run_id ||
          sessionData.runs[sessionData.runs.length - 1].id,
      );
  }, [sessionData, runId]);
  const runMeta =
      runData?.job?.result?.run || runData?.result?.run || runData?.run || {},
    orderId =
      sessionData?.order_id ||
      sessionData?.proposals?.find((p: any) => p.order_id)?.order_id;
  const installationId =
      sessionData?.installation_id || profile.data?.installation_id,
    rawPrediction = useData<any>(
      profile.data?.prediction_id
        ? `/predictions/${profile.data.prediction_id}`
        : "",
    );
  const facts = report?.facts || [],
    hypotheses = report?.hypotheses || [],
    tests = report?.suggested_tests || [],
    rounds =
      sessionData?.rounds ||
      sessionData?.inspection_rounds ||
      [
        ...new Set((sessionData?.observations || []).map((o: any) => o.round)),
      ].map((n) => ({
        round: n,
        observations: sessionData.observations.filter(
          (o: any) => o.round === n,
        ),
      }));
  return (
    <>
      <V2Heading
        title="诊断工作区"
        subtitle="曲线与事实、候选与反证、授权补测和检查轮次分别展示。"
      >
        {orderId && (
          <Link
            className="button"
            to={`/operations?order=${orderId}&tab=orders`}
          >
            打开正式工单 #{orderId}
          </Link>
        )}
      </V2Heading>
      <Panel
        title={session === "new" ? "创建有截止时间的诊断" : "本轮诊断"}
        subtitle="云端接口从服务器读取；数值结果来自工具，LLM 只组织证据。"
      >
        <form
          className="v2-form-inline"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const result = await api("/v2/agent/runs", "POST", {
                asset_id: Number(assetId),
                installation_id: installationId,
                visible_cutoff: cutoff,
                session_id: session === "new" ? undefined : Number(session),
                round: sessionData?.round || 1,
                incident_group_id: search.get("incident")
                  ? Number(search.get("incident"))
                  : undefined,
              });
              setRunId(result.run_id || result.id);
              setJobId(result.job_id);
              const id = result.session_id || session;
              if (id !== "new")
                navigate(`/diagnosis/${id}?run=${result.run_id || result.id}`);
            }, "诊断作业已提交");
          }}
        >
          <Field label="诊断资产">
            <select
              required
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
          <Field label="诊断可见截止时间（含时区）">
            <input
              required
              value={cutoff}
              onChange={(e) => setCutoff(e.target.value)}
            />
          </Field>
          <button
            className="primary"
            disabled={!canDiagnose(user.role) || !installationId || action.busy}
          >
            {session === "new" ? "生成诊断报告" : "生成本轮更新"}
          </button>
        </form>
        {action.feedback}
        <p>
          安装身份 {textValue(installationId)} · 会话 {session}{" "}
          <Version value={report?.context_version} label="Context" />
        </p>
        {!canDiagnose(user.role) && (
          <Notice>当前角色可读取授权记录，不能发起运维 Agent。</Notice>
        )}
        {profile.error && <Notice tone="error">{profile.error.message}</Notice>}
      </Panel>
      {session === "new" && (
        <Panel title="已保存的诊断会话">
          <V2Read resource={recentRuns}>
            <div className="v2-summary">
              {listItems(recentRuns.data).map((item) => (
                <Link
                  className="button"
                  key={item.id}
                  to={`/diagnosis/${item.session_id}?run=${item.id}`}
                >
                  会话 #{item.session_id} · 运行 #{item.id} · {item.status}
                </Link>
              ))}
            </div>
            {!listItems(recentRuns.data).length && (
              <Empty>尚无已保存诊断。</Empty>
            )}
          </V2Read>
        </Panel>
      )}
      <V2Job
        user={user}
        id={jobId || runData?.job_id || runData?.job?.id}
        canCancel={canDiagnose(user.role)}
        onComplete={() => {
          void run.reload();
          void r.reload();
        }}
      />
      {run.error && <Notice tone="error">{run.error.message}</Notice>}
      {r.error && <Notice tone="error">{r.error.message}</Notice>}
      {!report ? (
        <Empty>
          等待有证据的诊断结果。未生成报告时不展示候选概率或人工编造的风险数值。
        </Empty>
      ) : (
        <>
          <div className="v2-summary">
            <State
              value={report.status}
              stale={runData?.stale || sessionData?.stale}
            />
            <Version value={report.agent_version} label="Agent" />
            <Version value={report.context_version} label="Context" />
            <Provenance
              value={
                report.provenance ||
                reportRecord?.provenance ||
                runData?.provenance
              }
              scenario={report.synthetic_scenario_id}
            />
            <span>
              实际执行{" "}
              {runData?.execution_mode ||
                runData?.job?.result?.execution_mode ||
                runMeta.execution_mode ||
                report.execution_mode ||
                "未提供"}
            </span>
            <Evidence
              title="Token 使用与调用证据"
              value={
                runData?.token_metrics ||
                runData?.usage ||
                runMeta.llm_usage ||
                report.usage
              }
            />
          </div>
          <div className="v2-diagnosis-columns">
            <Panel title="事实、原始曲线与引用">
              {rawPrediction.data?.input_snapshot && (
                <LineChart
                  values={
                    rawPrediction.data.input_snapshot.current
                      ?.slice(16, 32)
                      .map((v: number) => v * 100) || []
                  }
                  secondary={rawPrediction.data.input_snapshot.reference
                    ?.slice(16, 32)
                    .map((v: number) => v * 100)}
                  title="可见充电片段 / 区间电量占比 %"
                />
              )}
              {facts.length ? (
                facts.map((f: any, i: number) => (
                  <article className="v2-record" key={i}>
                    <strong>{f.claim}</strong>
                    <p>{textValue(f.evidence_ids)}</p>
                    <Evidence title="事实来源与确定性" value={f} />
                  </article>
                ))
              ) : (
                <Empty>没有已核验事实。</Empty>
              )}
              <Evidence
                title="原始片段、工具结果与引用"
                value={{
                  profile: profile.data,
                  citations: report.citations,
                  tool_trace:
                    runData?.tool_trace || runData?.result?.tool_trace,
                }}
              />
            </Panel>
            <Panel title="候选、反证与仍未知">
              {hypotheses.map((h: any, i: number) => (
                <article className="v2-record" key={i}>
                  <strong>
                    {h.code} · {h.level}
                  </strong>
                  <p>支持 {textValue(h.supports)}</p>
                  <p>反证 {textValue(h.contradicts)}</p>
                  {h.probability != null && (
                    <p>似然条件下概率 {h.probability}</p>
                  )}
                  <Evidence title="候选证据与假设" value={h} />
                </article>
              ))}
              <h3>仍未知</h3>
              <ul>
                {(report.unknowns || []).map((v: any, i: number) => (
                  <li key={i}>{textValue(v)}</li>
                ))}
              </ul>
              <Evidence title="风险排序依据" value={report.priority} />
            </Panel>
            <Panel title="授权补测">
              {tests.map((t: any, i: number) => (
                <article className="v2-record" key={i}>
                  <strong>{t.test_id}</strong>
                  <State value={t.authorization} />
                  <p>{t.reason}</p>
                  <Evidence title="成本、结果区间与授权条件" value={t} />
                </article>
              ))}
              {!tests.length && <Empty>暂无可授权测试。</Empty>}
              <p>未经人员审批与排程，不形成可执行的工单。</p>
              <button
                disabled={
                  !canDiagnose(user.role) ||
                  action.busy ||
                  Boolean(report.proposal_id) ||
                  !tests.length ||
                  !reportRecord?.id
                }
                onClick={() =>
                  void action.run(async () => {
                    await api("/v2/work-proposals", "POST", {
                      report_id: reportRecord.id,
                      title: "诊断补测提案",
                      asset_ids: [Number(assetId)],
                      allowed_tests: [
                        ...new Set(tests.map((t: any) => t.test_id)),
                      ],
                      note: report.priority?.reason || "基于诊断证据申请补测",
                    });
                    await r.reload();
                    await run.reload();
                  }, "提案已提交，等待调度员确认")
                }
              >
                {report.proposal_id ? "报告已有提案" : "生成补测提案"}
              </button>
              <Link className="button" to="/operations?tab=v2">
                查看提案与排程
              </Link>
            </Panel>
          </div>
          <Panel
            title="检查轮次与原始反馈"
            subtitle="没有测到保持未知；定点纠正断言，不将整份报告粗暴评价为对或错。"
          >
            {rounds.length ? (
              rounds.map((round: any, i: number) => (
                <article className="v2-record" key={round.id || i}>
                  <h3>第 {round.round || round.number || i + 1} 轮</h3>
                  <State value={round.status} />
                  <Evidence
                    title="上一轮 / 本轮差异"
                    value={round.diff || round.report_diff}
                  />
                  {(round.observations || []).map((o: any, j: number) => (
                    <div className="v2-record" key={o.id || j}>
                      <details>
                        <summary>展开原始自由文字</summary>
                        <p>{o.free_text || "无原始自由文字"}</p>
                      </details>
                      <Evidence
                        title="抽取事实、来源与确定性"
                        value={o.structured_facts || o.measurements || o}
                      />
                    </div>
                  ))}
                </article>
              ))
            ) : (
              <Empty>
                尚无已提交检查轮次。提案批准后在正式工单提交结构化观察。
              </Empty>
            )}
            <Evidence title="完整诊断报告与版本差异" value={report} />
            <Evidence
              title="上一版本与本轮具体断言变化"
              value={{
                previous:
                  sessionData?.reports?.[sessionData.reports.length - 2]
                    ?.report,
                current: report,
              }}
            />
            {sessionData?.feedback?.map((f: any) => (
              <article className="v2-record" key={f.id}>
                <details>
                  <summary>展开原始断言反馈 #{f.id}</summary>
                  <p>{f.free_text}</p>
                </details>
                <Evidence title="抽取的事实、来源与确定性" value={f} />
              </article>
            ))}
            <DiagnosticFeedback
              user={user}
              session={session}
              reportId={reportRecord?.id}
              report={report}
              orderId={orderId}
              onSaved={() => void r.reload()}
            />
          </Panel>
        </>
      )}
    </>
  );
}

function DiagnosticFeedback({
  user,
  session,
  reportId,
  report,
  orderId,
  onSaved,
}: {
  user: User;
  session: string;
  reportId?: number;
  report: any;
  orderId?: number;
  onSaved: () => void;
}) {
  const [target, setTarget] = useState(""),
    [feedback, setFeedback] = useState(""),
    [provenance, setProvenance] = useState("synthetic"),
    [jobId, setJobId] = useState<number | null>(null),
    action = useAction();
  return (
    <>
      <h3>纠正具体断言</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            const result = await api(
              `/v2/diagnostic-sessions/${session}/feedback`,
              "POST",
              {
                report_id: reportId,
                order_id: orderId,
                free_text: feedback,
                assertion_targets: [target],
                confirmed_hypotheses: [],
                excluded_hypotheses: [],
                unresolved_items: [],
                provenance,
                client_submission_id: crypto.randomUUID(),
              },
            );
            setJobId(result.extraction_job_id || result.job_id);
            setFeedback("");
            onSaved();
          }, "原始反馈已保存，事实抽取在后台进行");
        }}
      >
        <div className="form-grid">
          <Field label="需要纠正的断言">
            <select
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">选择具体断言</option>
              {["facts", "hypotheses"].flatMap((kind) =>
                (report[kind] || []).map((item: any, index: number) => (
                  <option
                    key={`${kind}-${index}`}
                    value={`r${report.round || 1}.${kind}[${index}]`}
                  >
                    {item.claim || item.code}
                  </option>
                )),
              )}
            </select>
          </Field>
          <Field label="反馈数据来源">
            <select
              value={provenance}
              onChange={(e) => setProvenance(e.target.value)}
            >
              <option value="synthetic">合成演示</option>
              <option value="experimental_replay">实验回放</option>
              <option value="measured_declared">声明实测·未复核</option>
            </select>
          </Field>
        </div>
        <Field label="原始反馈与纠正依据">
          <textarea
            required
            minLength={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
        </Field>
        <button disabled={!reportId || user.role === "viewer" || action.busy}>
          提交断言反馈
        </button>
      </form>
      {action.feedback}
      <V2Job user={user} id={jobId} onComplete={onSaved} />
    </>
  );
}
