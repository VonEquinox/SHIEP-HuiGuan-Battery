import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { type User } from "../api";
import { Empty, Field, Notice, Panel, useAction } from "../components";
import {
  api,
  canResearch,
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
const recordData = (row: any) => ({ ...row?.payload, ...row });
const download = (name: string, value: any) => {
  const url = URL.createObjectURL(
      new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
};

export function CarbonCenter({ user }: { user: User }) {
  const factors = useV2Data("/v2/carbon/factors?limit=100", 6000),
    scenarios = useV2Data("/v2/carbon/scenarios?limit=100", 5000),
    ledger = useV2Data("/v2/carbon/ledger?limit=100", 5000),
    rules = useV2Data("/v2/carbon/policy-benefits?limit=100"),
    action = useAction(),
    navigate = useNavigate();
  const [showFactor, setShowFactor] = useState(false),
    [showScenario, setShowScenario] = useState(false),
    [showRule, setShowRule] = useState(false),
    [ruleText, setRuleText] = useState(""),
    [formal, setFormal] = useState(true),
    [exportData, setExportData] = useState<any>(null),
    [reverseId, setReverseId] = useState<number | null>(null),
    [reverseReason, setReverseReason] = useState("");
  return (
    <>
      <V2Heading
        title="独立碳与经济决策"
        subtitle="同一服务量、边界与期间下比较活动排放与货币成本；输入不来自运维 Agent。"
      >
        <button
          disabled={!canResearch(user.role)}
          onClick={() => setShowScenario(!showScenario)}
        >
          配置比较情景
        </button>
        <button
          disabled={user.role !== "admin"}
          onClick={() => setShowFactor(!showFactor)}
        >
          新增版本化因子
        </button>
      </V2Heading>
      <Notice>
        活动排放、产品足迹、比较减排分别核算。区间表示参数集范围；影子价值属于情景估值，现金收益必须有资格与凭据。负减排正常保留。
      </Notice>
      {showFactor && (
        <Panel title="登记因子来源、单位与范围">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void action.run(async () => {
                await api("/v2/carbon/factors", "POST", {
                  code: f.get("code"),
                  version: f.get("version"),
                  value: Number(f.get("value")),
                  activity_unit: f.get("activity_unit"),
                  gas_scope: f.get("gas_scope"),
                  boundary: f.get("boundary"),
                  source_url: f.get("source_url"),
                  source_title: f.get("source_title"),
                  jurisdiction: f.get("jurisdiction"),
                  valid_from: f.get("valid_from"),
                  valid_to: f.get("valid_to"),
                  deviation: Number(f.get("deviation") || 0),
                  uncertainty_key: f.get("uncertainty_key") || "",
                  provenance: f.get("provenance"),
                  synthetic_scenario_id: f.get("scenario") || null,
                  review_status: "unverified",
                });
                setShowFactor(false);
                await factors.reload();
              }, "因子版本已登记；仍须核验来源");
            }}
          >
            <div className="form-grid">
              {[
                ["code", "因子代码"],
                ["version", "因子版本"],
                ["source_url", "来源 URL"],
                ["source_title", "来源标题"],
                ["boundary", "适用边界"],
                ["jurisdiction", "地区"],
                ["uncertainty_key", "共享不确定变量"],
                ["scenario", "合成情景 ID（合成时必填）"],
              ].map(([name, label]) => (
                <Field key={name} label={label}>
                  <input
                    name={name}
                    required={!["scenario", "uncertainty_key"].includes(name)}
                    type={name === "source_url" ? "url" : "text"}
                  />
                </Field>
              ))}
              <Field label="因子值 / kg 气体每活动单位">
                <input type="number" required min={0} step="any" name="value" />
              </Field>
              <Field label="对称偏差 / 同单位">
                <input
                  type="number"
                  min={0}
                  step="any"
                  name="deviation"
                  defaultValue={0}
                />
              </Field>
              <Field label="活动单位">
                <select name="activity_unit">
                  {[
                    "kWh",
                    "kg",
                    "t_km",
                    "battery_unit",
                    "rated_kWh",
                    "test_unit",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="气体范围">
                <select name="gas_scope">
                  <option>kgCO2e</option>
                  <option>kgCO2</option>
                </select>
              </Field>
              <Field label="有效起始日">
                <input type="date" name="valid_from" required />
              </Field>
              <Field label="有效终止日">
                <input type="date" name="valid_to" required />
              </Field>
              <Field label="因子数据来源">
                <select name="provenance">
                  <option value="unverified">待核验</option>
                  <option value="real">真实来源</option>
                  <option value="synthetic">合成情景</option>
                </select>
              </Field>
            </div>
            <button
              className="primary"
              disabled={action.busy || user.role !== "admin"}
            >
              保存因子版本
            </button>
          </form>
        </Panel>
      )}
      {showScenario && (
        <ScenarioForm
          user={user}
          factors={listItems(factors.data).map(recordData)}
          onSaved={(id) => {
            setShowScenario(false);
            void scenarios.reload();
            navigate(`/carbon/scenarios/${id}`);
          }}
        />
      )}
      <Panel title="服务边界与基准 / 候选情景">
        <V2Read resource={scenarios}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>情景 / 版本</th>
                  <th>计算类型与来源</th>
                  <th>服务与边界</th>
                  <th>查看</th>
                </tr>
              </thead>
              <tbody>
                {listItems(scenarios.data).map((raw) => {
                  const s = recordData(raw);
                  return (
                    <tr key={s.id}>
                      <td>
                        <strong>{s.name}</strong>
                        <Version value={s.version} />
                      </td>
                      <td>
                        {s.claim_type} / {s.basis}
                        <Provenance
                          value={s.provenance}
                          scenario={s.synthetic_scenario_id}
                        />
                      </td>
                      <td>
                        <Evidence
                          title="共同服务量、基准与终端处理"
                          value={s.functional_unit}
                        />
                      </td>
                      <td>
                        <Link
                          className="button"
                          to={`/carbon/scenarios/${s.id}`}
                        >
                          打开情景比较
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!listItems(scenarios.data).length && (
            <Empty>
              没有比较情景。先登记有来源与单位的因子，再定义共同服务边界。
            </Empty>
          )}
        </V2Read>
      </Panel>
      <Panel title="排放因子与价格依据">
        <V2Read resource={factors}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>因子 / 版本</th>
                  <th>值与偏差</th>
                  <th>适用性</th>
                  <th>来源</th>
                </tr>
              </thead>
              <tbody>
                {listItems(factors.data).map((raw) => {
                  const f = recordData(raw);
                  return (
                    <tr key={f.id}>
                      <td>
                        {f.code}
                        <Version value={f.version} />
                        <Provenance
                          value={f.provenance}
                          scenario={f.synthetic_scenario_id}
                        />
                      </td>
                      <td>
                        {numberValue(f.value)} ± {numberValue(f.deviation)}{" "}
                        {f.gas_scope}/{f.activity_unit}
                      </td>
                      <td>
                        {f.boundary} · {f.jurisdiction}
                        <small>
                          {f.valid_from} – {f.valid_to} · {f.review_status}
                        </small>
                      </td>
                      <td>
                        {f.source_url && (
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {f.source_title}
                          </a>
                        )}
                        <Evidence
                          title="因子来源版本与共享误差变量"
                          value={f}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </V2Read>
      </Panel>
      <Panel
        title="政策 / 信用资格规则"
        subtitle="仅已生效且核验的规则与项目凭据可参与现金收益判断。"
        actions={
          <button
            disabled={user.role !== "admin"}
            onClick={() => setShowRule(!showRule)}
          >
            登记规则版本
          </button>
        }
      >
        <V2Read resource={rules}>
          {listItems(rules.data).map((rule) => (
            <Evidence
              key={rule.id}
              title={`${recordData(rule).rule_id} / ${recordData(rule).version}`}
              value={recordData(rule)}
            />
          ))}
        </V2Read>
        {showRule && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api(
                  "/v2/carbon/policy-benefits",
                  "POST",
                  JSON.parse(ruleText),
                );
                await rules.reload();
                setShowRule(false);
              }, "规则版本已登记");
            }}
          >
            <Field label="规则版本规范（官方依据、有效期间、资格主体、所需凭据和金额上限）">
              <textarea
                required
                className="v2-code-input"
                value={ruleText}
                onChange={(e) => setRuleText(e.target.value)}
                placeholder='{"rule_id":"…","version":"…","official_url":"https://…","jurisdiction":"…","eligible_entity":"…","valid_from":"2026-01-01","valid_to":"2026-12-31","cap":0,"required_documents":["…"]}'
              />
            </Field>
            <button disabled={user.role !== "admin" || action.busy}>
              保存规则版本
            </button>
          </form>
        )}
      </Panel>
      <Panel
        title="分类活动台账与可复算导出"
        subtitle="预测、结算、合成与正式结果分列；演示记录自动排除正式对外汇总。"
      >
        <V2Read resource={ledger}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>台账 / 类型</th>
                  <th>口径 / 审核</th>
                  <th>数值</th>
                  <th>依据 / 纠正</th>
                </tr>
              </thead>
              <tbody>
                {listItems(ledger.data).map((l) => (
                  <tr key={l.id}>
                    <td>
                      #{l.id} {l.claim_type}
                      <Provenance value={l.provenance} />
                    </td>
                    <td>
                      {l.basis} / {l.review_status}
                      <small>{l.accounting_period}</small>
                    </td>
                    <td>
                      {numberValue(l.emission_kg)} {l.gas_scope}
                    </td>
                    <td>
                      <Evidence title="输入、因子和记账依据" value={l} />
                      <button
                        disabled={
                          user.role !== "admin" || Boolean(l.reversal_of)
                        }
                        onClick={() => setReverseId(l.id)}
                      >
                        追加冲销纠正
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </V2Read>
        {reverseId && (
          <form
            className="v2-form-inline"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api(`/v2/carbon/ledger/${reverseId}/reverse`, "POST", {
                  reason: reverseReason,
                });
                setReverseId(null);
                setReverseReason("");
                await ledger.reload();
              }, "已追加冲销记录，原记录保留");
            }}
          >
            <Field label={`台账 #${reverseId} 纠正原因`}>
              <input
                required
                minLength={3}
                value={reverseReason}
                onChange={(e) => setReverseReason(e.target.value)}
              />
            </Field>
            <button disabled={action.busy}>提交冲销纠正</button>
            <button type="button" onClick={() => setReverseId(null)}>
              取消
            </button>
          </form>
        )}
        <div className="v2-form-inline">
          <Field label="导出资格">
            <select
              value={formal ? "formal" : "internal"}
              onChange={(e) => setFormal(e.target.value === "formal")}
            >
              <option value="formal">正式汇总（排除合成与未核验）</option>
              <option value="internal">内部演示与预测汇总</option>
            </select>
          </Field>
          <button
            onClick={() =>
              void action.run(async () => {
                const result = await api(`/v2/carbon/exports?formal=${formal}`);
                setExportData(result);
                download(
                  `carbon-${formal ? "formal" : "internal"}.json`,
                  result,
                );
              }, "分类报告已导出")
            }
          >
            导出可复算 JSON
          </button>
        </div>
        {exportData && (
          <Evidence title="汇总组、纳入记录与排除理由" value={exportData} />
        )}
      </Panel>
      {action.feedback}
    </>
  );
}

function ScenarioForm({
  user,
  factors,
  onSaved,
}: {
  user: User;
  factors: any[];
  onSaved: (id: number) => void;
}) {
  const action = useAction(),
    [advanced, setAdvanced] = useState(false),
    [json, setJson] = useState("");
  return (
    <Panel
      title="定义共同服务与两方案活动清单"
      subtitle="默认创建明确标注的合成情景；填写的是情景参数，不能当作实际测量或已实现减排。"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void action.run(async () => {
            let payload: any;
            if (advanced) payload = JSON.parse(json);
            else {
              const factor = factors.find(
                (x) => x.id === Number(f.get("factor")),
              );
              const candidate = (
                id: string,
                label: string,
                intervention: string,
                quantity: number,
                cost: number,
              ) => ({
                id,
                label,
                intervention,
                constraints: {
                  safety: true,
                  technical: true,
                  service: true,
                  personnel: true,
                  scenario: true,
                },
                functional_unit_matches: true,
                confirmed_by: user.display_name,
                confirmation_reference: String(f.get("basis")),
                activities: [
                  {
                    process: "service_electricity",
                    period: 1,
                    quantity,
                    unit: "kWh",
                    factor_id: factor.id,
                    basis: "projected",
                    provenance: "synthetic",
                    source_reference: String(f.get("basis")),
                    source_version: "1",
                  },
                ],
                costs: {
                  initial_cost: cost,
                  price_year: Number(String(f.get("date")).slice(0, 4)),
                  currency: "RMB",
                  quote_reference: String(f.get("basis")),
                  flows: [],
                },
              });
              payload = {
                name: f.get("name"),
                version: 1,
                functional_unit: {
                  output_kwh_per_period: [Number(f.get("service"))],
                  period_years: 1,
                  start_date: f.get("date"),
                  region: factor.jurisdiction,
                  usage_scenario: f.get("usage"),
                  service_requirements: f.get("requirements"),
                  start_state: f.get("start_state"),
                  terminal_handling: f.get("terminal"),
                  boundary: ["service_electricity"],
                  gas_scope: factor.gas_scope,
                  baseline_basis: f.get("basis"),
                  boundary_kind:
                    f.get("claim_type") === "activity_emission"
                      ? "activity_only"
                      : "prospective_decision",
                },
                baseline_id: "baseline",
                candidates: [
                  candidate(
                    "baseline",
                    "基准继续使用",
                    "continue",
                    Number(f.get("baseline_energy")),
                    Number(f.get("baseline_cost")),
                  ),
                  candidate(
                    "candidate",
                    "候选维修情景",
                    "repair",
                    Number(f.get("candidate_energy")),
                    Number(f.get("candidate_cost")),
                  ),
                ],
                basis: "projected",
                claim_type: f.get("claim_type"),
                provenance: "synthetic",
                synthetic_scenario_id: f.get("scenario_id"),
                gamma: Number(f.get("gamma")),
                gamma_scan: factor.deviation ? [0, 0.5, 1] : [0],
                epsilon_values: [],
                shadow_price_rmb_per_t: Number(f.get("shadow") || 0),
              };
              setJson(JSON.stringify(payload, null, 2));
            }
            const result = await api("/v2/carbon/scenarios", "POST", payload);
            onSaved(result.id || result.scenario_id);
          }, "共同服务情景已保存");
        }}
      >
        <label className="v2-checkbox">
          <input
            type="checkbox"
            checked={advanced}
            onChange={(e) => setAdvanced(e.target.checked)}
          />
          使用完整情景规范（支持寿命递推、材料与政策凭据）
        </label>
        {advanced ? (
          <Field label="完整比较情景 JSON">
            <textarea
              className="v2-code-input"
              required
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
          </Field>
        ) : (
          <>
            <div className="form-grid">
              {[
                ["name", "情景名称"],
                ["scenario_id", "合成情景 ID"],
                ["usage", "使用场景"],
                ["requirements", "共同服务要求"],
                ["start_state", "两方案起始状态"],
                ["terminal", "期末处理及延期说明"],
                ["basis", "基准与参数确认依据"],
              ].map(([name, label]) => (
                <Field key={name} label={label}>
                  <input required name={name} />
                </Field>
              ))}
              <Field label="服务开始日">
                <input required name="date" type="date" />
              </Field>
              <Field label="已登记电力因子">
                <select required name="factor">
                  <option value="">选择有来源与边界的因子</option>
                  {factors
                    .filter((f) => f.activity_unit === "kWh")
                    .map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.code} v{f.version} / {f.gas_scope}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="核算类型">
                <select name="claim_type">
                  <option value="comparative_avoided">比较减排</option>
                  <option value="activity_emission">活动排放</option>
                </select>
              </Field>
              {[
                ["service", "共同输出服务 / kWh"],
                ["baseline_energy", "基准活动用电 / kWh"],
                ["candidate_energy", "候选活动用电 / kWh"],
                ["baseline_cost", "基准成本 / RMB"],
                ["candidate_cost", "候选成本 / RMB"],
                ["gamma", "Γ 预算"],
                ["shadow", "内部碳影子价 / RMB每吨"],
              ].map(([name, label]) => (
                <Field key={name} label={label}>
                  <input
                    required
                    name={name}
                    type="number"
                    min={0}
                    step="any"
                  />
                </Field>
              ))}
            </div>
            <label className="v2-checkbox">
              <input required type="checkbox" />
              我确认本合成情景的安全、技术、服务、人员与场景条件满足；两方案服务量与边界可比。
            </label>
          </>
        )}
        <button
          className="primary"
          disabled={!canResearch(user.role) || action.busy}
        >
          保存独立比较情景
        </button>
      </form>
      {action.feedback}
    </Panel>
  );
}

export function CarbonScenario({ user }: { user: User }) {
  const { id } = useParams(),
    scenario = useV2Data(`/v2/carbon/scenarios/${id}`, 5000),
    s = recordData(scenario.data),
    [gamma, setGamma] = useState(0),
    [jobId, setJobId] = useState<number | null>(null),
    [pending, setPending] = useState(false),
    [resultId, setResultId] = useState<number | null>(null),
    [selected, setSelected] = useState<any>(null),
    [candidateId, setCandidateId] = useState(""),
    [evidence, setEvidence] = useState(""),
    [period, setPeriod] = useState("");
  const results = useV2Data(
      resultId ? `/v2/carbon/results/${resultId}` : "",
      4000,
    ),
    result = results.data?.result || results.data?.payload,
    action = useAction();
  useEffect(() => {
    if (scenario.data) {
      setGamma(s.gamma || 0);
      const latest =
        scenario.data.latest_result_id ||
        scenario.data.latest_result?.id ||
        scenario.data.results?.[0]?.id;
      if (latest) setResultId(latest);
    }
  }, [scenario.data?.id, scenario.data?.version]);
  return (
    <>
      <V2Heading
        title="碳与成本情景比较"
        subtitle="名义值和 Γ 下的最坏值来自独立数学计算，活动分解可追溯。"
      >
        <Link className="button" to="/carbon">
          返回因子与台账
        </Link>
      </V2Heading>
      <Panel title={s.name || `情景 #${id}`}>
        <V2Read resource={scenario}>
          <div className="v2-summary">
            <Version value={s.version} />
            <Provenance
              value={s.provenance}
              scenario={s.synthetic_scenario_id}
            />
            <span>
              {s.claim_type} / {s.basis}
            </span>
          </div>
          <Evidence
            title="共同服务、期间、边界、候选与价格依据"
            value={s.payload || s}
          />
          <div className="v2-form-inline">
            <Field label="Γ 不确定预算">
              <input
                aria-label="Γ 不确定预算"
                type="number"
                min={0}
                step={0.1}
                value={gamma}
                onChange={(e) => setGamma(Number(e.target.value))}
              />
            </Field>
            <button
              className="primary"
              disabled={!canResearch(user.role) || action.busy}
              onClick={() =>
                void action.run(async () => {
                  const response = await api(
                    `/v2/carbon/scenarios/${id}/solve`,
                    "POST",
                    { expected_version: s.version, gamma },
                  );
                  setJobId(response.job_id);
                  setPending(true);
                }, "碳求解已提交，旧结果保留并显示其 Γ")
              }
            >
              按当前 Γ 重算
            </button>
          </div>
          {result && (
            <p>
              当前展示结果 Γ={result.gamma} · 输入情景 v
              {results.data?.scenario_version} ·{" "}
              {pending ? "新作业进行时，下面保留上次冻结结果" : "冻结结果"}
            </p>
          )}
        </V2Read>
        {action.feedback}
      </Panel>
      <V2Job
        user={user}
        id={jobId}
        canCancel={canResearch(user.role)}
        onComplete={(job) => {
          setPending(false);
          if (job.status === "succeeded" && job.result?.result_id)
            setResultId(job.result.result_id);
          void scenario.reload();
        }}
      />
      {resultId && (
        <Panel title="名义 / 鲁棒碳与成本">
          <V2Read resource={results}>
            <Notice>
              参数集范围不表示统计置信度。碳排放不随货币折现。影子价值与可实现现金收入分账。
            </Notice>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>方案与可行性</th>
                    <th>碳排放 / kg</th>
                    <th>成本 / RMB</th>
                    <th>比较减排 / kg</th>
                    <th>影子估值 / RMB</th>
                  </tr>
                </thead>
                <tbody>
                  {result?.candidates?.map((c: any) => (
                    <tr key={c.id}>
                      <td>
                        <strong>{c.label}</strong>
                        <State
                          value={c.status}
                          reason={c.reasons?.length ? c.reasons : null}
                        />
                      </td>
                      {[
                        ["carbon", "nominal"],
                        ["cost", "nominal"],
                        ["benefit", "nominal"],
                      ].map(([key]) => (
                        <td key={key}>
                          <button
                            className="v2-number"
                            disabled={!c[key]}
                            onClick={() => setSelected(c)}
                          >
                            {numberValue(c[key]?.nominal)}
                          </button>
                          <small>
                            参数集范围 {numberValue(c[key]?.lower_under_set)}–
                            {numberValue(c[key]?.upper_under_set)}
                          </small>
                        </td>
                      ))}
                      <td>
                        {numberValue(c.shadow_value_rmb)}
                        <small>
                          现金资格收入 {numberValue(c.cost?.eligible_cash_npv)}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pareto result={result} />
            <Evidence
              title="ε 约束选择、Gamma 敏感性与共享因子抵消"
              value={{
                epsilon_solutions: result?.epsilon_solutions,
                sensitivity: result?.sensitivity,
                gamma_scan: result?.gamma_scan,
                uncertainty_set: result?.uncertainty_set,
              }}
            />
            {selected && (
              <Panel
                title={`${selected.label} 活动与依据`}
                actions={
                  <button onClick={() => setSelected(null)}>收起分解</button>
                }
              >
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>活动 / 期</th>
                        <th>活动量</th>
                        <th>排放 / kg</th>
                        <th>因子与依据</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.activities?.map((a: any, i: number) => (
                        <tr key={i}>
                          <td>
                            {a.process} / {a.period}
                          </td>
                          <td>
                            {numberValue(a.quantity)} {a.unit}
                          </td>
                          <td>{numberValue(a.emission_kg)}</td>
                          <td>
                            <Evidence title="因子、来源与版本" value={a} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Evidence
                  title="寿命状态、终端状态、政策资格与成本分解"
                  value={selected}
                />
              </Panel>
            )}
            <h3>冻结结果追加到分类台账</h3>
            <form
              className="v2-form-inline"
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  await api("/v2/carbon/ledger", "POST", {
                    result_id: resultId,
                    candidate_id: candidateId,
                    claim_type: result.claim_type || s.claim_type,
                    basis: result.basis || s.basis,
                    review_status: "pending",
                    evidence_reference: evidence,
                    accounting_period: period,
                  });
                }, "结果已追加到待审核台账；未转为已结算或正式减排");
              }}
            >
              <Field label="台账方案">
                <select
                  required
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                >
                  <option value="">选择可行方案</option>
                  {result?.candidates
                    ?.filter((c: any) => c.status === "feasible")
                    .map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="记账依据">
                <input
                  required
                  value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                />
              </Field>
              <Field label="核算期间">
                <input
                  required
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                />
              </Field>
              <button disabled={!canResearch(user.role) || action.busy}>
                追加分类台账
              </button>
            </form>
          </V2Read>
        </Panel>
      )}
      {!resultId && (
        <Empty>
          尚无冻结结果。提交求解后可查看名义值、参数集范围、活动分解与不可行原因。
        </Empty>
      )}
    </>
  );
}
function Pareto({ result }: { result: any }) {
  const candidates = (result?.candidates || []).filter(
      (c: any) => c.status === "feasible" && c.carbon && c.cost,
    ),
    maxX = Math.max(1, ...candidates.map((c: any) => c.cost.upper_under_set)),
    maxY = Math.max(1, ...candidates.map((c: any) => c.carbon.upper_under_set));
  if (!candidates.length) return <Empty>没有满足约束的 Pareto 候选。</Empty>;
  return (
    <Panel
      title="成本与碳 Pareto 比较"
      subtitle="圆点为名义值，方点为当前 Γ 的上界；两种前沿分别展示。"
    >
      <div className="chart">
        <svg
          viewBox="0 0 520 240"
          role="img"
          aria-label="名义和鲁棒成本碳 Pareto 图"
        >
          <line x1="40" x2="495" y1="205" y2="205" stroke="var(--line)" />
          <line x1="40" x2="40" y1="20" y2="205" stroke="var(--line)" />
          {candidates.map((c: any) => {
            const x = 40 + (430 * c.cost.nominal) / maxX,
              y = 205 - (170 * c.carbon.nominal) / maxY,
              xr = 40 + (430 * c.cost.upper_under_set) / maxX,
              yr = 205 - (170 * c.carbon.upper_under_set) / maxY;
            return (
              <g key={c.id}>
                <line x1={x} x2={xr} y1={y} y2={yr} stroke="#ccd8d1" />
                <circle
                  cx={x}
                  cy={y}
                  r={5}
                  fill={
                    result.nominal_frontier?.includes(c.id)
                      ? "var(--accent)"
                      : "#aaa"
                  }
                />
                <rect
                  x={xr - 4}
                  y={yr - 4}
                  width={8}
                  height={8}
                  fill={
                    result.robust_frontier?.includes(c.id)
                      ? "var(--amber)"
                      : "#aaa"
                  }
                />
                <text x={x + 8} y={y - 7} fontSize="10">
                  {c.label}
                </text>
              </g>
            );
          })}
          <text x="355" y="231" fontSize="11">
            成本 RMB（未缩为收益）
          </text>
          <text x="5" y="15" fontSize="11">
            碳 kg
          </text>
        </svg>
      </div>
      <p>
        名义前沿 {textValue(result.nominal_frontier)} · 鲁棒前沿{" "}
        {textValue(result.robust_frontier)}
      </p>
    </Panel>
  );
}
