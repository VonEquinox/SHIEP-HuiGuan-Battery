import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
const screenshotDir = "../runtime/acceptance/v2-contract-screenshots";
async function screenshot(page: Page, name: string) {
  mkdirSync(screenshotDir, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${screenshotDir}/${name}.png`,
    fullPage: true,
  });
}

// Contract fixtures only. These are synthetic browser acceptance inputs, never production/demo model metrics.
const user = (role = "admin") => ({
  id: 1,
  username: "contract-user",
  display_name: "合同验收员",
  role,
  csrf: "contract-csrf",
  version: 1,
});
const assets = [
  {
    id: 11,
    name: "合同电芯 A",
    kind: "cell",
    installation_id: "ins-contract-A",
  },
  {
    id: 12,
    name: "合同电芯 B",
    kind: "cell",
    installation_id: "ins-contract-B",
  },
];
const profile = {
  asset_id: 11,
  installation_id: "ins-contract-A",
  heads: [
    {
      head: "soh",
      value: null,
      unit: "ratio",
      support: "unsupported",
      reason: "没有合法标签",
      distribution: { kind: "none" },
    },
    {
      head: "rul",
      value: null,
      unit: "cycles",
      support: "unsupported",
      reason: "缺少物理寿命标签",
      distribution: { kind: "none" },
    },
    {
      head: "threshold_risk",
      value: null,
      unit: "probability",
      support: "unsupported",
      reason: "缺少 horizon",
      distribution: { kind: "none" },
    },
    {
      head: "efficiency",
      value: null,
      unit: "ratio",
      support: "unsupported",
      reason: "无效率测量",
      distribution: { kind: "none" },
    },
  ],
};
const report = {
  round: 1,
  status: "insufficient_evidence",
  facts: [{ claim: "合同观察：通道差异", evidence_ids: ["ev-contract"] }],
  hypotheses: [
    {
      code: "channel_fault",
      level: "suspected",
      supports: ["ev-contract"],
      contradicts: ["独立通道尚未测量"],
      probability: null,
    },
  ],
  unknowns: ["独立通道未复核"],
  suggested_tests: [
    {
      test_id: "T_CHANNEL_CHECK",
      reason: "区分观测误差与接头原因",
      authorization: "required",
    },
  ],
  priority: { class: "routine", reason: "证据不足，申请授权复核" },
  agent_version: "contract-v1",
  context_version: 2,
  citations: ["ev-contract"],
};
const scenario = {
  id: 1,
  name: "合同碳比较",
  version: 1,
  payload: {
    name: "合同碳比较",
    version: 1,
    provenance: "synthetic",
    synthetic_scenario_id: "contract-carbon",
    basis: "projected",
    claim_type: "comparative_avoided",
    gamma: 0,
    functional_unit: {
      output_kwh_per_period: [100],
      boundary: ["service_electricity"],
      gas_scope: "kgCO2e",
    },
  },
  results: [] as any[],
};
const carbonResult = {
  scenario_version: 1,
  baseline_id: "baseline",
  gamma: 0,
  provenance: "synthetic",
  claim_type: "comparative_avoided",
  basis: "projected",
  candidates: [
    {
      id: "baseline",
      label: "基准",
      status: "feasible",
      reasons: [],
      carbon: { nominal: 10, lower_under_set: 10, upper_under_set: 10 },
      cost: {
        nominal: 20,
        lower_under_set: 20,
        upper_under_set: 20,
        eligible_cash_npv: 0,
      },
      benefit: { nominal: 0, lower_under_set: 0, upper_under_set: 0 },
      shadow_value_rmb: 0,
      activities: [],
    },
    {
      id: "candidate",
      label: "候选",
      status: "feasible",
      reasons: [],
      carbon: { nominal: 15, lower_under_set: 14, upper_under_set: 16 },
      cost: {
        nominal: 18,
        lower_under_set: 17,
        upper_under_set: 19,
        eligible_cash_npv: 0,
      },
      benefit: { nominal: -5, lower_under_set: -6, upper_under_set: -4 },
      shadow_value_rmb: -0.5,
      activities: [
        {
          process: "service_electricity",
          period: 1,
          quantity: 30,
          unit: "kWh",
          emission_kg: 15,
          factor_snapshot: {
            code: "contract-factor",
            source_url: "https://example.org/contract",
          },
        },
      ],
    },
  ],
  nominal_frontier: ["baseline", "candidate"],
  robust_frontier: ["baseline", "candidate"],
  sensitivity: [],
  gamma_scan: [],
};
async function stub(
  page: Page,
  role = "admin",
  override?: (path: string, method: string, body: any) => any,
) {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname.replace("/api", ""),
      method = request.method();
    let body: any = null;
    try {
      body = request.postDataJSON();
    } catch {}
    const custom = override?.(path, method, body);
    if (custom !== undefined) {
      await route.fulfill({
        status: typeof custom.status === "number" ? custom.status : 200,
        json: custom.body ?? custom,
      });
      return;
    }
    const responses: Record<string, any> = {
      "/auth/me": user(role),
      "/assets": assets,
      "/assets/11": assets[0],
      "/v2/assets/11/prediction-profile": profile,
      "/v2/model-packages": { items: [], feature_rows: [], next_cursor: null },
      "/v2/agent/runs": { items: [], next_cursor: null },
      "/v2/overview": {
        open_proposals: 0,
        pending_rounds: 0,
        agent_runs: { failed: 0 },
        context_version: 2,
        source_counts: {
          experimental: 2,
          self_synthetic: 3,
          public_generated: 1,
        },
        unsupported_heads: 4,
        production_connected: false,
      },
      "/v2/carbon/scenarios/1": scenario,
      "/v2/carbon/results/7": {
        id: 7,
        scenario_version: 1,
        result: carbonResult,
      },
      "/v2/carbon/factors": [],
      "/v2/carbon/policy-benefits": [],
      "/v2/carbon/scenarios": [scenario],
      "/v2/carbon/ledger": [],
      "/v2/incidents": {
        items: [
          {
            id: 9,
            title: "合同群组",
            severity: "medium",
            status: "ACTIVE",
            version: 1,
            provenance: "synthetic",
            members: [{ asset_id: 11 }, { asset_id: 12 }],
            evidence: { missing: ["独立通道"] },
          },
        ],
        next_cursor: null,
      },
      "/v2/diagnostic-sessions/3": {
        id: 3,
        asset_id: 11,
        installation_id: "ins-contract-A",
        round: 1,
        status: "OPEN",
        runs: [{ id: 4 }],
        reports: [{ id: 5, report_version: 1, report }],
        proposals: [],
        observations: [],
        feedback: [],
      },
      "/v2/agent/runs/4": {
        id: 4,
        asset_id: 11,
        session_id: 3,
        status: "succeeded",
        execution_mode: "cloud",
        report: { id: 5, report_version: 1, report },
      },
      "/v2/skills": { items: [], next_cursor: null },
      "/v2/memories": { items: [], next_cursor: null },
      "/v2/context-snapshots": {
        items: [
          {
            id: 1,
            context_version: 1,
            context: { instructions: "old statement" },
          },
          {
            id: 2,
            context_version: 2,
            context: { instructions: "corrected statement" },
          },
        ],
        next_cursor: null,
      },
      "/v2/evolution/runs": {
        items: [
          {
            id: 2,
            method: "ace",
            status: "failed",
            provenance: "synthetic",
            metrics: { score: 0.4 },
          },
          {
            id: 1,
            method: "ace",
            status: "succeeded",
            provenance: "synthetic",
            metrics: { score: 0.8 },
          },
        ],
        next_cursor: null,
      },
      "/orders": [],
      "/alerts": [],
      "/jobs": [],
      "/users": [],
      "/personnel": [],
      "/notifications": [],
      "/v2/work-proposals": { items: [], next_cursor: null },
      "/v2/dispatch/plans": [],
      "/v2/dispatch/resources": {
        version: 1,
        payload: { engineers: [], tool_capacities: {}, travel_minutes: {} },
      },
    };
    await route.fulfill({
      status: path in responses ? 200 : 404,
      json: responses[path] || {
        detail: {
          code: "NO_CONTRACT_FIXTURE",
          message: `No fixture ${path}`,
          missing_fields: [],
          retryable: false,
        },
      },
    });
  });
  return pageErrors;
}

test("preserves seven workspaces and unsupported null heads without substituting zero", async ({
  page,
}) => {
  const errors = await stub(page);
  await page.goto("/assets/11");
  for (const name of [
    "总览",
    "资产中心",
    "数据中心",
    "模型中心",
    "健康中心",
    "告警与工单",
    "系统管理",
  ])
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  await expect(page.getByText("没有合法标签", { exact: true })).toBeVisible();
  await expect(page.locator(".v2-head > strong")).toHaveText(
    Array(4).fill("未支持 / 未提供"),
  );
  await expect(page.getByText("0.00%", { exact: true })).toHaveCount(0);
  await screenshot(page, "assets-unsupported");
  expect(errors).toEqual([]);
});

test("creates cutoff-bound diagnosis and report-bound proposal, then preserves targeted feedback", async ({
  page,
}) => {
  let submitted: any = null,
    proposal: any = null,
    feedback: any = null;
  const errors = await stub(page, "admin", (path, method, body) => {
    if (path === "/v2/agent/runs" && method === "POST") {
      submitted = body;
      return { run_id: 4, session_id: 3, job_id: 8 };
    }
    if (path === "/jobs/8")
      return {
        id: 8,
        status: "succeeded",
        progress: 100,
        result: { run_id: 4 },
        logs: [],
      };
    if (path === "/v2/work-proposals" && method === "POST") {
      proposal = body;
      return { id: 6, status: "PENDING_APPROVAL" };
    }
    if (path === "/v2/diagnostic-sessions/3/feedback" && method === "POST") {
      feedback = body;
      return { feedback_id: 1 };
    }
  });
  await page.goto("/diagnosis/new?asset=11&cutoff=2026-10-01T08:00:00Z");
  await page.getByRole("button", { name: "生成诊断报告", exact: true }).click();
  await expect(
    page
      .locator(".v2-diagnosis-columns strong")
      .getByText("合同观察：通道差异", { exact: true }),
  ).toBeVisible();
  expect(submitted).toMatchObject({
    asset_id: 11,
    installation_id: "ins-contract-A",
    visible_cutoff: "2026-10-01T08:00:00Z",
    round: 1,
  });
  expect(submitted).not.toHaveProperty("execution_mode");
  await page.getByRole("button", { name: "生成补测提案", exact: true }).click();
  await expect(
    page.getByText("提案已提交，等待调度员确认", { exact: true }),
  ).toBeVisible();
  expect(proposal).toMatchObject({
    report_id: 5,
    asset_ids: [11],
    allowed_tests: ["T_CHANNEL_CHECK"],
  });
  await page
    .getByLabel("需要纠正的断言", { exact: true })
    .selectOption("r1.hypotheses[0]");
  await page
    .getByLabel("原始反馈与纠正依据", { exact: true })
    .fill("独立复核未发现原断言中的接头异常，保留未知项。");
  await page.getByRole("button", { name: "提交断言反馈", exact: true }).click();
  await expect(
    page.getByText("原始反馈已保存，事实抽取在后台进行", { exact: true }),
  ).toBeVisible();
  expect(feedback.assertion_targets).toEqual(["r1.hypotheses[0]"]);
  expect(feedback.provenance).toBe("synthetic");
  await screenshot(page, "diagnosis-feedback");
  expect(errors).toEqual([]);
});

test("Gamma request carries frozen version and negative avoided emissions stay negative", async ({
  page,
}) => {
  let solve: any = null;
  const errors = await stub(page, "admin", (path, method, body) => {
    if (path === "/v2/carbon/scenarios/1/solve" && method === "POST") {
      solve = body;
      return { job_id: 8 };
    }
    if (path === "/jobs/8")
      return {
        id: 8,
        status: "succeeded",
        progress: 100,
        result: { result_id: 7 },
        logs: [],
      };
  });
  await page.goto("/carbon/scenarios/1");
  await page.getByLabel("Γ 不确定预算", { exact: true }).fill("0.5");
  await page
    .getByRole("button", { name: "按当前 Γ 重算", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "-5", exact: true }),
  ).toBeVisible();
  expect(solve).toEqual({ expected_version: 1, gamma: 0.5 });
  await screenshot(page, "carbon-negative");
  await page.getByRole("button", { name: "-5", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "候选 活动与依据", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "service_electricity / 1", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("structured version conflict is visible with missing fields and request id", async ({
  page,
}) => {
  await stub(page, "admin", (path, method) =>
    path === "/v2/carbon/scenarios/1/solve" && method === "POST"
      ? {
          status: 409,
          body: {
            request_id: "conflict-contract",
            code: "STALE_INPUT",
            message: "情景版本已改变，请刷新",
            missing_fields: ["expected_version"],
            retryable: false,
            detail: "情景输入版本冲突",
          },
        }
      : undefined,
  );
  await page.goto("/carbon/scenarios/1");
  await page
    .getByRole("button", { name: "按当前 Γ 重算", exact: true })
    .click();
  await expect(page.getByText(/情景版本已改变，请刷新/)).toBeVisible();
  await expect(
    page.getByText("缺少：expected_version", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/请求 conflict-contract/)).toBeVisible();
});

test("readonly controls remain disabled and evolution curve can decline", async ({
  page,
}) => {
  const errors = await stub(page, "viewer");
  await page.goto("/evolution");
  await expect(
    page.getByRole("button", { name: "提交离线进化实验", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("实验指标", { exact: true }).selectOption("score");
  const line = page.locator(
    'svg[aria-label="score / synthetic / 原始量纲 数据曲线"] polyline',
  );
  await expect(line).toBeVisible();
  const points = (await line.getAttribute("points"))!
    .split(" ")
    .map((p) => Number(p.split(",")[1]));
  expect(points[1]).toBeGreaterThan(points[0]);
  await page.getByLabel("基准 Context 版本", { exact: true }).selectOption("1");
  await page.getByLabel("对照 Context 版本", { exact: true }).selectOption("2");
  await expect(page.locator(".removed pre")).toContainText("old statement");
  await expect(page.locator(".added pre")).toContainText("corrected statement");
  await page.goto("/carbon/scenarios/1");
  await expect(
    page.getByRole("button", { name: "按当前 Γ 重算", exact: true }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});

test("specialist workspaces render without mobile overflow", async ({
  page,
}) => {
  const errors = await stub(page);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "/risk",
    "/diagnosis/3?run=4",
    "/evolution",
    "/carbon",
    "/carbon/scenarios/1",
    "/assets/11",
  ]) {
    await page.goto(route);
    await expect(page.locator("main.content")).toBeVisible();
    await expect(page.locator(".spinner")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      route,
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test("group analysis uses selected scope and unassigned risk never dispatches directly", async ({
  page,
}) => {
  let analyzed: any = null;
  await stub(page, "admin", (path, method, body) => {
    if (path === "/v2/incidents/analyze" && method === "POST") {
      analyzed = body;
      return { job_id: 13 };
    }
    if (path === "/jobs/13")
      return {
        id: 13,
        status: "failed",
        progress: 0,
        error: "合同数据不足，不能形成群组",
        logs: [],
      };
  });
  await page.goto("/risk");
  await expect(
    page.getByRole("button", { name: "分析当前风险", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("合同电芯 A", { exact: true }).check();
  await page.getByLabel("合同电芯 B", { exact: true }).check();
  await page.getByRole("button", { name: "分析当前风险", exact: true }).click();
  await expect(
    page.getByText("合同数据不足，不能形成群组", { exact: true }),
  ).toBeVisible();
  expect(analyzed.asset_ids).toEqual([11, 12]);
  expect(Date.parse(analyzed.visible_cutoff)).not.toBeNaN();
  await expect(page.getByRole("button", { name: /派发|生成工单/ })).toHaveCount(
    0,
  );
});

test("dispatch edits carry version and confirmation conflict cannot silently assign", async ({
  page,
}) => {
  const draft = {
    id: 2,
    status: "DRAFT",
    version: 1,
    input_snapshot: { horizon_minutes: 480 },
    result: {
      status: "feasible",
      lexicographic_complete: false,
      assignments: [
        { order_id: 42, engineer_id: 3, start: 10, end: 60, locked: false },
      ],
      unassigned: [{ order_id: 43, reasons: ["缺少工具容量"] }],
    },
  };
  let patch: any = null,
    confirmed: any = null;
  const errors = await stub(page, "admin", (path, method, body) => {
    if (path === "/v2/dispatch/plans") return [draft];
    if (path === "/v2/dispatch/plans/2" && method === "GET") return draft;
    if (path === "/v2/dispatch/plans/2" && method === "PATCH") {
      patch = body;
      draft.version = 2;
      draft.result.assignments = body.assignments;
      return draft;
    }
    if (path === "/v2/dispatch/plans/2/confirm" && method === "POST") {
      confirmed = body;
      return {
        status: 409,
        body: {
          detail: {
            code: "STALE_PLAN",
            message: "人员已接单，请刷新重新求解",
            retryable: false,
          },
        },
      };
    }
  });
  await page.goto("/operations?tab=v2");
  await page
    .getByRole("button", { name: "草案 #2 · DRAFT · v1", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "排程甘特与人员负载", exact: true }),
  ).toBeVisible();
  await page.getByLabel("工单 42 start", { exact: true }).fill("20");
  await page
    .getByRole("button", { name: "校验并保存调整", exact: true })
    .click();
  await expect(
    page.getByText("草案已重新校验并保存", { exact: true }),
  ).toBeVisible();
  expect(patch).toEqual({
    version: 1,
    assignments: [{ order_id: 42, engineer_id: 3, start: 20, end: 60 }],
  });
  await page.getByRole("button", { name: "人工确认排程", exact: true }).click();
  await expect(
    page.getByText("人员已接单，请刷新重新求解", { exact: true }),
  ).toBeVisible();
  expect(confirmed).toEqual({ version: 2 });
  await screenshot(page, "dispatch-conflict");
  expect(errors).toEqual([]);
});

test("comparison metadata stays optional and normal reference requires an explicit fresh declaration", async ({
  page,
}) => {
  const observations: any[] = [],
    order = {
      id: 42,
      title: "合同检查工单",
      status: "IN_PROGRESS",
      version: 4,
    };
  const errors = await stub(page, "admin", (path, method, body) => {
    if (path === "/orders") return [order];
    if (path === "/v2/orders/42/inspection")
      return {
        order,
        installation_id: "ins-contract-A",
        current_round: 1,
        allowed_tests: [{ test_id: "T_CHANNEL_CHECK", name: "独立通道检查" }],
        observations: [],
        reports: [],
        rounds: [],
      };
    if (path === "/v2/orders/42/observations" && method === "POST") {
      observations.push(body);
      return { id: observations.length };
    }
  });
  await page.goto("/operations?tab=v2");
  await page
    .getByLabel("查看检查轮次的工单", { exact: true })
    .selectOption("42");
  await page
    .getByLabel("已授权测试", { exact: true })
    .selectOption("T_CHANNEL_CHECK");
  await expect(
    page.getByLabel("提供本次观察的可比条件", { exact: true }),
  ).not.toBeChecked();
  await page.getByRole("button", { name: "提交本次观察", exact: true }).click();
  await expect.poll(() => observations.length).toBe(1);
  expect(observations[0]).not.toHaveProperty("comparison_context");
  expect(observations[0].measurements).toEqual([]);
  await page.getByLabel("提供本次观察的可比条件", { exact: true }).check();
  await page
    .getByLabel("测量记录时间（含时区，可选）", { exact: true })
    .fill("2026-10-01T18:00:00+08:00");
  const normal = page.getByLabel("本次观察声明为正常参考（须有依据）", {
    exact: true,
  });
  await expect(normal).not.toBeChecked();
  await page.getByLabel("比较化学体系", { exact: true }).selectOption("LFP");
  await page.getByLabel("比较运行协议", { exact: true }).fill("合同协议1");
  await page.getByLabel("比较负载条件", { exact: true }).fill("0.5C恒流");
  await page.getByLabel("比较温度条件", { exact: true }).fill("25°C恒温箱");
  await page
    .getByLabel("同源比较批次", { exact: true })
    .fill("contract-cohort");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "提交本次观察", exact: true }).click();
  await expect.poll(() => observations.length).toBe(2);
  expect(observations[1].comparison_context).toEqual({
    chemistry: "LFP",
    protocol_id: "合同协议1",
    load_condition: "0.5C恒流",
    temperature_condition: "25°C恒温箱",
    source_cohort_id: "contract-cohort",
    reference_status: "not_reference",
  });
  expect(observations[1].measured_at).toBe("2026-10-01T10:00:00.000Z");
  await normal.check();
  await page
    .getByLabel("测量记录时间（含时区，可选）", { exact: true })
    .fill("2026-10-01T18:01:00+08:00");
  await page
    .getByLabel("检查原始自由文字", { exact: true })
    .fill("参考依据：同一批次早期已记录的正常窗口，仍待独立复核。");
  await page.getByRole("button", { name: "提交本次观察", exact: true }).click();
  await expect.poll(() => observations.length).toBe(3);
  expect(observations[2].comparison_context.reference_status).toBe(
    "declared_normal",
  );
  await expect(normal).not.toBeChecked();
  expect(errors).toEqual([]);
});

for (const supported of [false, true]) {
  test(`residual group evidence keeps ${supported ? "supported correlation" : "unsupported data"} separate from causal confirmation`, async ({
    page,
  }) => {
    const errors = await stub(page, "viewer", (path) => {
      if (path === "/v2/incidents/9")
        return {
          id: 9,
          version: 1,
          members: [{ asset_id: 11 }, { asset_id: 12 }],
          provenance: "self_synthetic",
          evidence: {
            numeric_correlation_supported: supported,
            numeric_support: {
              status: supported ? "supported" : "unsupported",
              reasons: supported ? [] : ["normal_reference_insufficient"],
            },
            numeric_analysis: {
              threshold_version: "contract-MAD-v1",
              quality_flags: {
                "ins-contract-A": supported ? [] : ["reference_insufficient"],
              },
              residuals: {
                "ins-contract-A": {
                  "2026-10-01T10:00:00Z": supported ? 3.5 : null,
                },
              },
              pair_evidence: supported
                ? [
                    {
                      members: ["ins-contract-A", "ins-contract-B"],
                      correlation: 0.91,
                      aligned_points: 3,
                      event_overlap: 2,
                      shared_relations: ["parent_id"],
                      relation: "synchronous_association",
                      causality: "not_established",
                    },
                  ]
                : [],
              qualified_pairs: supported
                ? [
                    {
                      members: ["ins-contract-A", "ins-contract-B"],
                      correlation: 0.91,
                      aligned_points: 3,
                      causality: "not_established",
                    },
                  ]
                : [],
            },
            comparison: {
              chemistry: "LFP",
              protocol_id: "合同协议1",
              metric: "voltage",
              unit: "V",
              method: "contract-method",
              load_condition: "0.5C",
              temperature_condition: "25°C",
              source_cohort_id: "contract-cohort",
              origin: "synthetic",
            },
            source_refs: [
              {
                observation_id: 101,
                version: 1,
                asset_id: 11,
                installation_id: "ins-contract-A",
                role: "reference",
                measured_at: "2026-10-01T09:00:00Z",
                available_at: "2026-10-01T09:01:00Z",
                origin: "synthetic",
                source_trust: "reported",
              },
            ],
            confirmed_common_cause: false,
          },
        };
    });
    await page.goto("/risk");
    await page
      .getByRole("button", { name: "展开群组与依据", exact: true })
      .click();
    const evidence = page.getByRole("region", {
      name: "同工况残差关联与来源资格",
      exact: true,
    });
    await expect(evidence.getByText(/不能确认共同根因/)).toBeVisible();
    await expect(evidence.getByText(/contract-cohort/)).toBeVisible();
    await expect(evidence.getByText(/合成来源只用于演示/)).toBeVisible();
    if (supported) {
      await expect(
        evidence.getByRole("table", {
          name: "残差相关与精确对齐点",
          exact: true,
        }),
      ).toContainText("0.91");
    } else {
      await expect(
        evidence.getByText("normal_reference_insufficient", { exact: true }),
      ).toBeVisible();
      await expect(
        evidence.getByRole("table", {
          name: "残差相关与精确对齐点",
          exact: true,
        }),
      ).toHaveCount(0);
    }
    await evidence
      .getByText("查看按正常参考中位数与 MAD 计算的残差", { exact: true })
      .click();
    await expect(
      evidence.getByRole("table", {
        name: "服务端计算的标准化残差",
        exact: true,
      }),
    ).toContainText(supported ? "3.5" : "未支持");
    await evidence.getByText("来源与参考窗口资格", { exact: true }).click();
    await expect(evidence.locator("pre")).toContainText("observation_id");
    await expect(
      evidence.getByRole("table", {
        name: "比较观察的来源与参考资格",
        exact: true,
      }),
    ).toContainText("使用者声明的早期正常参考");
    await expect(
      evidence.getByRole("table", {
        name: "比较观察的来源与参考资格",
        exact: true,
      }),
    ).toContainText("未独立复核");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("verified physical cycle coordinates do not replace ordinal history or become calendar dates", async ({
  page,
}) => {
  await stub(page, "viewer", (path) => {
    if (path === "/v2/assets/11/prediction-profile")
      return {
        ...profile,
        query: {
          query_time: 120,
          visible_cutoff: 120,
          time_basis: "verified_physical_cycle",
          physical_cycles_known: true,
          source_time: {
            query_cycle: 120,
            visible_cutoff_cycle: 120,
            feature_max_cycle: 119,
            reference_cutoff_cycle: 5,
          },
        },
      };
  });
  await page.goto("/assets/11");
  await expect(page.getByText(/已核实物理循环编号，非日历时间/)).toBeVisible();
  await expect(page.getByText(/物理循环编号：查询 120/)).toBeVisible();
  await expect(page.getByText(/特征截止 119/)).toBeVisible();
});

test("switching safe packages uses each package input cohort and clears the prior observation", async ({
  page,
}) => {
  const errors = await stub(page, "admin", (path) => {
    if (path === "/assets/11") return { ...assets[0], version: 1 };
    if (path === "/v2/model-packages")
      return {
        items: [
          {
            package_id: "package-A",
            feature_rows: [
              {
                row_index: 4,
                physical_cell_id: "source:A",
                split: "dev",
                visible_cutoff: 120,
              },
            ],
            binding_input_source: "package_development_sample",
          },
          {
            package_id: "package-B",
            feature_rows: [
              {
                row_index: 7,
                physical_cell_id: "source:B",
                split: "dev",
                visible_cutoff: 140,
                time_basis: "verified_physical_cycle",
                physical_cycles_known: true,
              },
            ],
            binding_input_source: "label_free_package_development_examples",
          },
          {
            package_id: "package-empty",
            feature_rows: [],
            binding_input_source: "unavailable",
          },
          { package_id: "legacy" },
        ],
        feature_rows: [
          {
            row_index: 0,
            physical_cell_id: "xjtu:legacy",
            split: "train",
            visible_cutoff: 0,
          },
        ],
      };
  });
  await page.goto("/assets/11");
  const model = page.getByLabel("已验证的安全模型包", { exact: true }),
    observation = page.getByLabel("开发集源物理对象与观测", { exact: true });
  await model.selectOption("package-A");
  await expect(observation).toContainText("源截止序号 120");
  await observation.selectOption("4");
  await model.selectOption("package-B");
  await expect(observation).toHaveValue("");
  await expect(observation.locator("option")).toHaveCount(2);
  await expect(observation).toContainText("source:B");
  await expect(observation).toContainText("源物理循环截止 140");
  await expect(observation).not.toContainText("source:A");
  await model.selectOption("package-empty");
  await expect(observation.locator("option")).toHaveCount(1);
  await expect(
    page.getByRole("button", {
      name: "绑定实验回放并执行 V2 推理",
      exact: true,
    }),
  ).toBeDisabled();
  await model.selectOption("legacy");
  await expect(observation).toContainText("xjtu:legacy");
  expect(errors).toEqual([]);
});
