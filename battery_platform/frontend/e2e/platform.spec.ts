import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
const PASSWORD = "Browser-test-only-password-2047";
const shotDir = "../runtime/acceptance/screenshots";
async function login(page: Page, name: string) {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill(name);
  await page.getByLabel("密码", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "安全登录" }).click();
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
  await expect(page.getByRole("button", { name: "安全登录" })).toHaveCount(0);
}
async function logout(page: Page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("button", { name: "安全登录" })).toBeVisible();
}

test("real inference → alert → assignment → technician evidence → independent verification → persisted close", async ({
  page,
}) => {
  mkdirSync(shotDir, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "admin");
  await expect(
    page.getByRole("button", { name: /纳管电芯槽位/ }),
  ).toContainText("21");
  await page.screenshot({
    path: shotDir + "/01-dashboard-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "模型中心", exact: true }).click();
  await page
    .getByLabel("源电芯 / 最多256条有序样本")
    .selectOption("Batch-4/R3_battery-1");
  await page.getByRole("button", { name: "提交真实计算任务" }).click();
  const job = page.getByRole("dialog");
  await expect(job).toBeVisible();
  await expect(job.getByText("已完成", { exact: true })).toBeVisible({
    timeout: 120000,
  });
  await expect(job.getByText(/含训练电芯/)).toBeVisible();
  await page.screenshot({
    path: shotDir + "/02-real-model-result.png",
    fullPage: true,
  });
  await job.getByRole("button", { name: "关闭弹窗" }).click();
  await page.getByRole("link", { name: "告警与工单", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "生成工单" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "生成工单" }).first().click();
  let dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("实验");
  await dialog.getByRole("button", { name: "派发 / 调整人员" }).click();
  await dialog
    .getByLabel("选择符合要求的维修人员")
    .selectOption({ label: "验收维修员 / 当前工单 0" });
  await dialog
    .getByLabel("操作说明 / 处理结果")
    .fill("根据技能与值班状态派发容量复核任务");
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await expect(dialog.getByText("状态已更新并写入审计")).toBeVisible();
  await dialog.getByRole("button", { name: "关闭弹窗" }).click();
  await logout(page);

  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "tech");
  await page.getByRole("button", { name: "展开导航" }).click();
  await page.getByRole("link", { name: "告警与工单", exact: true }).click();
  await page.getByRole("button", { name: "打开工单" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "接受工单" }).click();
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await dialog.getByRole("button", { name: "开始处理" }).click();
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await dialog
    .getByLabel("上传证据（PNG / JPEG / TXT，最多5MiB）")
    .setInputFiles({
      name: "inspection.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Automation evidence: simulated inspection, no physical asset control.",
      ),
    });
  await dialog.getByRole("button", { name: "上传证据", exact: true }).click();
  await expect(
    dialog.getByRole("link", { name: /inspection\.txt/ }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "提交处理结果" }).click();
  await dialog
    .getByLabel("操作说明 / 处理结果")
    .fill("完成模拟容量复核，提交检验记录；没有修改模型预测值。");
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await expect(dialog.getByRole("button", { name: "独立验收" })).toHaveCount(0);
  await expect(dialog.locator(".order-detail-head .badge")).toHaveText(
    "已处理",
  );
  await page.screenshot({
    path: shotDir + "/03-technician-resolution.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "关闭弹窗" }).click();
  await logout(page);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "dispatch");
  await page.getByRole("link", { name: "告警与工单", exact: true }).click();
  await page.getByRole("button", { name: /工单管理/ }).click();
  await page.getByRole("button", { name: "打开工单" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "独立验收" }).click();
  await dialog
    .getByLabel("操作说明 / 处理结果")
    .fill("已独立核对本次处理记录与附件，通过流程验收。");
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await dialog.getByRole("button", { name: "关闭工单", exact: true }).click();
  await dialog
    .getByLabel("操作说明 / 处理结果")
    .fill("流程归档，告警与模型健康状态不被自动改写。");
  await dialog.getByRole("button", { name: "确认操作" }).click();
  await dialog.getByRole("button", { name: "关闭弹窗" }).click();
  await page.reload();
  await page.getByRole("button", { name: /工单管理/ }).click();
  await expect(
    page.getByRole("table").getByText("已关闭", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: shotDir + "/04-closed-order-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
  await expect(
    page.getByRole("link", { name: "资产中心", exact: true }),
  ).not.toBeInViewport();
  await page.screenshot({
    path: shotDir + "/05-mobile-orders.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "展开导航" }).click();
  await expect(
    page.getByRole("link", { name: "资产中心", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("readonly observer sees genuine data with no enabled research controls", async ({
  page,
}) => {
  await login(page, "viewer");
  await page.getByRole("link", { name: "数据中心", exact: true }).click();
  await expect(page.getByText("2,058 条样本 · 21 个电芯")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "导入特征 CSV" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "查看观测" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Batch-4/");
  await page.getByRole("button", { name: "关闭弹窗" }).click();
  await page.getByRole("link", { name: "模型中心", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交真实计算任务" }),
  ).toBeDisabled();
});

test("all seven workspaces render at desktop and mobile without runtime errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "admin");
  for (const [route, name] of [
    ["/assets", "资产中心"],
    ["/data", "数据中心"],
    ["/models", "模型中心"],
    ["/health", "健康中心"],
    ["/operations", "告警与工单"],
    ["/system", "系统管理"],
  ]) {
    await page.goto(route);
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: `${shotDir}/workspace-${route.slice(1)}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "/",
    "/assets",
    "/data",
    "/models",
    "/health",
    "/operations",
    "/system",
  ]) {
    await page.goto(route);
    await expect(page.locator("main.content")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      route,
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});
