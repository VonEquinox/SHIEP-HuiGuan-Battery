import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";

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
