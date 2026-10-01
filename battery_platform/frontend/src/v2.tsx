import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, date, labels, type User } from "./api";
import { Badge, Empty, Notice, Panel, Spinner, useAction } from "./components";
export type V2Row = Record<string, any>;
export const listItems = (data: any): V2Row[] =>
  Array.isArray(data) ? data : data?.items || [];
export const textValue = (value: any): string =>
  value == null
    ? "未提供"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export const numberValue = (value: any, digits = 3): string =>
  value == null || !Number.isFinite(Number(value))
    ? "未支持 / 未提供"
    : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
export function useV2Data(path: string, interval = 0) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState<Error | null>(null),
    [loading, setLoading] = useState(Boolean(path));
  const active = useRef(0);
  const reload = useCallback(async () => {
    const request = ++active.current;
    if (!path) {
      setLoading(false);
      setData(null);
      setError(null);
      return;
    }
    try {
      const value = await api(path);
      if (request === active.current) {
        setData(value);
        setError(null);
      }
    } catch (e) {
      if (request === active.current) setError(e as Error);
    } finally {
      if (request === active.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setData(null);
    setError(null);
    setLoading(Boolean(path));
    void reload();
    const timer = interval
      ? window.setInterval(() => void reload(), interval)
      : undefined;
    return () => {
      active.current++;
      if (timer) clearInterval(timer);
    };
  }, [reload, interval]);
  return { data, error, loading, reload };
}
export function V2Error({ error }: { error: Error | string | null }) {
  if (!error) return null;
  return (
    <Notice tone="error">
      <strong>{typeof error === "string" ? error : error.message}</strong>
      {error instanceof ApiError && (
        <>
          <p>
            错误码 {error.code} ·{" "}
            {error.retryable ? "可重试" : "请修正输入或权限后再试"}
            {error.requestId && ` · 请求 ${error.requestId}`}
          </p>
          {error.missingFields.length > 0 && (
            <p>缺少：{error.missingFields.join("、")}</p>
          )}
        </>
      )}
    </Notice>
  );
}
export function V2Read({
  resource,
  children,
  empty = "暂无记录；完成相应操作后刷新。",
}: {
  resource: ReturnType<typeof useV2Data>;
  children: ReactNode;
  empty?: string;
}) {
  if (resource.loading) return <Spinner />;
  if (!resource.data)
    return resource.error ? (
      <V2Error error={resource.error} />
    ) : (
      <Empty>{empty}</Empty>
    );
  return (
    <>
      <V2Error error={resource.error} />
      {children}
    </>
  );
}
export function Evidence({
  title = "原始记录与依据",
  value,
}: {
  title?: string;
  value: any;
}) {
  return (
    <details className="v2-evidence">
      <summary>{title}</summary>
      <pre>{value == null ? "未提供" : JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function State({
  value,
  stale = false,
  reason,
}: {
  value?: string;
  stale?: boolean;
  reason?: any;
}) {
  return (
    <div className="v2-state">
      <Badge value={value || "unknown"} />
      {stale && <Badge value="stale" />}
      {reason && <span>{textValue(reason)}</span>}
    </div>
  );
}
export function V2Job({
  id,
  onComplete,
  canCancel = false,
  user,
}: {
  id?: number | null;
  onComplete?: (job: V2Row) => void;
  canCancel?: boolean;
  user?: User;
}) {
  const job = useV2Data(id ? `/jobs/${id}` : "", 2000),
    action = useAction();
  const completed = useRef<number | null>(null);
  useEffect(() => {
    completed.current = null;
  }, [id]);
  useEffect(() => {
    if (
      id &&
      job.data &&
      !["queued", "running"].includes(job.data.status) &&
      completed.current !== id
    ) {
      completed.current = id;
      onComplete?.(job.data);
    }
  }, [id, job.data, onComplete]);
  if (!id) return null;
  return (
    <Panel
      title={`后台作业 #${id}`}
      subtitle="显示服务端执行状态；旧结果保留其版本。"
    >
      <V2Read resource={job}>
        <State value={job.data?.status} reason={job.data?.error} />
        {typeof job.data?.progress === "number" && (
          <p>实际进度 {job.data.progress}%</p>
        )}
        {canCancel &&
          (!user ||
            user.role === "admin" ||
            (user.role === "researcher" && job.data?.created_by === user.id)) &&
          ["queued", "running"].includes(job.data?.status) && (
            <button
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api(`/jobs/${id}/cancel`, "POST");
                  await job.reload();
                }, "取消请求已提交")
              }
            >
              取消本次作业
            </button>
          )}
        {action.feedback}
        <Evidence
          title="作业结果与日志"
          value={{ result: job.data?.result, logs: job.data?.logs }}
        />
      </V2Read>
    </Panel>
  );
}
export function V2Heading({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">V2 / EVIDENCE & VERSIONS</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="actions">{children}</div>
    </div>
  );
}
export function Provenance({
  value,
  scenario,
}: {
  value?: string;
  scenario?: string;
}) {
  return (
    <span className="v2-provenance">
      <Badge value={value || "declared_unverified"} />
      {scenario && <small>情景 {scenario}</small>}
    </span>
  );
}
export const canResearch = (role: string) =>
  ["admin", "researcher"].includes(role);
export const canDiagnose = (role: string) =>
  ["admin", "researcher", "dispatcher"].includes(role);
export const canDispatch = (role: string) =>
  ["admin", "dispatcher"].includes(role);
export function Version({
  value,
  label = "版本",
}: {
  value?: any;
  label?: string;
}) {
  return (
    <small>
      {label} {textValue(value)}
    </small>
  );
}
export { api, date, labels };
