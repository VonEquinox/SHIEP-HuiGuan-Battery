import { useCallback, useEffect, useState } from "react";
export type Row = { id: number; [key: string]: any };
export type User = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  csrf: string;
  version: number;
};
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") {
    headers["X-CSRF-Token"] = csrf;
    headers["Idempotency-Key"] = crypto.randomUUID();
  }
  if (body !== undefined && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers,
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const error = await response.json();
      message =
        typeof error.detail === "string"
          ? error.detail
          : JSON.stringify(error.detail);
    } catch {}
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(message);
  }
  return response.json();
}
export function useData<T = any>(path: string, interval = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) {
      setLoading(false);
      setData(null);
      return;
    }
    try {
      setData(await api<T>(path));
      setError("");
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setLoading(true);
    void reload();
    if (interval) {
      const timer = setInterval(() => void reload(), interval);
      return () => clearInterval(timer);
    }
  }, [reload, interval]);
  return { data, error, loading, reload };
}
export const date = (value?: string) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
export const percent = (value?: number | null, digits = 2) =>
  value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
export const labels: Record<string, string> = {
  admin: "管理员",
  researcher: "算法研究员",
  dispatcher: "运维调度",
  technician: "维修人员",
  viewer: "只读观察者",
  site: "站点",
  cabinet: "电池柜",
  module: "模组",
  cell: "电芯",
  simulated: "模拟业务",
  experimental: "真实实验",
  experimental_replay: "实验回放",
  declared_unverified: "来源待核验",
  measured_declared: "声明实测·未复核",
  OPEN: "待确认",
  ACKNOWLEDGED: "已确认",
  RESOLVED: "已处理",
  CREATED: "待派发",
  ASSIGNED: "已派发",
  ACCEPTED: "已接单",
  IN_PROGRESS: "处理中",
  VERIFIED: "已验收",
  CLOSED: "已关闭",
  CANCELLED: "已取消",
  queued: "排队中",
  running: "执行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
  normal: "观测范围内",
  attention: "维护复核",
  review: "适用性复核",
  stale: "数据过期",
  unknown: "暂无预测",
  enabled: "可调用",
  retired: "已停用",
  within_observed_range: "训练观测范围内",
  out_of_training_range: "超出训练观测范围",
  missing_temperature: "温度观测缺失",
  inference: "模型推理",
  evaluation: "模型评估",
  training: "训练实验",
  import: "数据导入",
  WARNING: "维护提醒",
  REVIEW: "人工复核",
  historical_adaptive_development: "历史开发评估（非最终测试）",
  in_sample_or_mixed: "含训练电芯（非独立测试）",
  unseen_cells_declared: "未见电芯（身份待核验）",
  within_platform_cell_holdout_validation_not_final_test:
    "平台内按电芯验证（非最终测试）",
};
