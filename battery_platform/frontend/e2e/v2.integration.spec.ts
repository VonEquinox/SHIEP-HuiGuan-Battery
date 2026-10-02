import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { readFileSync } from "node:fs";

// Actual isolated browser-server database and numerical packages. No API interception.
test("actual safe package binding → numerical heads → cutoff-bound diagnostic report", async ({
  page,
}) => {
  test.setTimeout(120000);
  const jsErrors: string[] = [],
    serverErrors: string[] = [];
  page.on("pageerror", (e) => jsErrors.push(e.message));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500)
      serverErrors.push(`${r.status()} ${new URL(r.url()).pathname}`);
  });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Browser-test-only-password-2047");
  await page.getByRole("button", { name: "安全登录", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "退出登录", exact: true }),
  ).toBeVisible();
  const packagesResponse = await page.request.get("/api/v2/model-packages");
  expect(packagesResponse.status()).toBe(200);
  const packages = await packagesResponse.json();
  expect(packages.production_activated).toBe(false);
  expect(packages.items.length).toBeGreaterThan(0);
  expect(packages.feature_rows.length).toBeGreaterThan(0);
  const assets = await (await page.request.get("/api/assets")).json();
  const asset = assets.find(
    (a: any) =>
      a.kind === "cell" &&
      a.source_cell_id &&
      packages.feature_rows.some(
        (r: any) => r.physical_cell_id === `xjtu:${a.source_cell_id}`,
      ),
  );
  expect(
    asset,
    "Existing V1 mapping must match a registered development source physical object",
  ).toBeTruthy();
  const row = packages.feature_rows.find(
      (r: any) => r.physical_cell_id === `xjtu:${asset.source_cell_id}`,
    ),
    model =
      packages.items.find(
        (p: any) =>
          p.package_id.startsWith("M1_") &&
          p.package_id.includes("joint_seed0"),
      ) || packages.items[0];
  expect(row.split).not.toBe("sealed_test");
  expect((await page.goto(`/assets/${asset.id}`))?.status()).toBe(200);
  await page
    .getByLabel("已验证的安全模型包", { exact: true })
    .selectOption(model.package_id);
  await page
    .getByLabel("开发集源物理对象与观测", { exact: true })
    .selectOption(String(row.row_index));
  await page
    .getByRole("button", { name: "绑定实验回放并执行 V2 推理", exact: true })
    .click();
  await expect(
    page.getByText("实验回放绑定已保存，真实数值推理已提交", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".v2-head")
      .filter({ has: page.getByRole("heading", { name: "soh", exact: true }) })
      .locator(">strong"),
  ).not.toHaveText("未支持 / 未提供", { timeout: 60000 });
  const prediction = await (
    await page.request.get(`/api/v2/assets/${asset.id}/prediction-profile`)
  ).json();
  expect(prediction.installation_id).toBe(asset.installation_id);
  expect(prediction.v2_profile_id).toBeGreaterThan(0);
  expect(prediction.heads.find((h: any) => h.head === "soh").support).toBe(
    "supported",
  );
  for (const head of ["rul", "threshold_risk", "efficiency", "fault"]) {
    const output = prediction.heads.find((h: any) => h.head === head);
    expect(output.support, head).toBe("unsupported");
    expect(output.value, head).toBeNull();
  }
  await expect(
    page.getByText(/校准样本不足或域未校准，区间无界/),
  ).toBeVisible();
  mkdirSync("../runtime/acceptance/v2-live-screenshots", { recursive: true });
  await page.screenshot({
    path: "../runtime/acceptance/v2-live-screenshots/actual-numeric-profile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "发起诊断", exact: true }).click();
  const runResponse = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/v2/agent/runs" &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "生成诊断报告", exact: true }).click();
  const created = await (await runResponse).json();
  expect(created.session_id).toBeGreaterThan(0);
  expect(created.run_id).toBeGreaterThan(0);
  await expect(page.locator(".v2-diagnosis-columns")).toBeVisible({
    timeout: 60000,
  });
  const run = await (
    await page.request.get(`/api/v2/agent/runs/${created.run_id}`)
  ).json();
  expect(run.report.report.installation_id).toBe(asset.installation_id);
  expect(run.job.result.execution_mode).toBe("rule_baseline");
  expect(run.report.provenance).toBe("self_synthetic");
  await expect(
    page.getByText("实际执行 rule_baseline", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../runtime/acceptance/v2-live-screenshots/actual-diagnostic-report.png",
    fullPage: true,
  });
  expect(jsErrors).toEqual([]);
  expect(serverErrors).toEqual([]);
});

test("actual replay experiment API → run list → grouped chart uses measured metric contract", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("/evolution");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Browser-test-only-password-2047");
  await page.getByRole("button", { name: "安全登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Context 自动进化", exact: true }),
  ).toBeVisible();
  const cases = readFileSync(
    "../../content_v1/evaluation/dev/cases.jsonl",
    "utf8",
  )
    .split("\n")
    .filter(Boolean)
    .slice(0, 2)
    .map((line) => JSON.parse(line).case_id);
  const csrf = (await (await page.request.get("/api/auth/me")).json()).csrf;
  const base = (await (await page.request.get("/api/v2/overview")).json())
    .context_version;
  const submit = async (method: string) => {
    const response = await page.request.post("/api/v2/evolution/experiments", {
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `browser-metrics-${method}-${Date.now()}`,
      },
      data: {
        method,
        base_version: base,
        case_ids: cases,
        split: "dev",
        max_rollouts: 2,
        activate: false,
      },
    });
    expect(response.status()).toBe(202);
    const created = await response.json();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/jobs/${created.job_id}`)).json())
            .status,
        { timeout: 60000 },
      )
      .toBe("succeeded");
    return created;
  };
  // Actual worker/scorer with cloud intentionally unavailable in the isolated
  // browser runtime. We validate measured rule output, never fabricated scores.
  const fixed = await submit("fixed"),
    noMemory = await submit("no_memory");
  const response = await page.request.get("/api/v2/evolution/runs?limit=100");
  expect(response.status()).toBe(200);
  const listed = await response.json();
  const fixedRun = listed.items.find((run: any) => run.id === fixed.id);
  const noMemoryRun = listed.items.find((run: any) => run.id === noMemory.id);
  const definitions = listed.metrics_contract.definitions;
  expect(fixedRun.experiment_metrics.values.diagnosis_accuracy).not.toBeNull();
  expect(fixedRun.experiment_protocol.execution_modes).toEqual([
    "rule_baseline",
  ]);
  expect(fixedRun.experiment_protocol.llm_models).toEqual([]);
  expect(fixedRun.experiment_protocol.protocol_id).not.toBe(
    noMemoryRun.experiment_protocol.protocol_id,
  );
  await page.getByRole("button", { name: "刷新进化记录", exact: true }).click();
  await page
    .getByLabel("实验指标", { exact: true })
    .selectOption("diagnosis_accuracy");
  await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
    fixedRun.experiment_metrics.values.diagnosis_accuracy.toFixed(4),
  );
  await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
    `已评估根事件数：${fixedRun.experiment_metrics.values.denominators.diagnosis_roots}`,
  );
  await expect(
    page.locator('[data-testid="experiment-series"][data-method="fixed"] svg'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-testid="experiment-series"][data-method="fixed"]'),
  ).toContainText("实际执行：rule_baseline");
  await expect(
    page.locator(
      '[data-testid="experiment-series"][data-method="no_memory"] svg',
    ),
  ).toHaveCount(1);
  await page
    .getByLabel("实验指标", { exact: true })
    .selectOption("false_alarms");
  const alarmDefinition = definitions.find(
    (definition: any) => definition.key === "false_alarms",
  );
  expect(alarmDefinition.kind).toBe("count");
  if (fixedRun.experiment_metrics.values.false_alarms === null) {
    await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
      "unsupported",
    );
  } else {
    await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
      `${fixedRun.experiment_metrics.values.false_alarms} 根事件`,
    );
    await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
      `${alarmDefinition.denominator_label}：${fixedRun.experiment_metrics.values.denominators[alarmDefinition.denominator]}`,
    );
  }
  await page
    .getByLabel("实验指标", { exact: true })
    .selectOption("unsafe_test_count");
  await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
    `${fixedRun.experiment_metrics.values.unsafe_test_count} 项`,
  );
  await page.getByLabel("实验指标", { exact: true }).selectOption("score");
  await expect(page.getByTestId(`experiment-run-${fixed.id}`)).toContainText(
    "unsupported",
  );
  await expect(page.getByTestId("experiment-series")).toHaveCount(0);
});
