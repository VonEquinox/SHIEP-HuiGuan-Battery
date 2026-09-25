import { useEffect, useState, type ReactNode } from "react";
import { X, LoaderCircle, ArrowUpRight, Info } from "lucide-react";
import { labels } from "./api";
export function Badge({
  value,
  children,
}: {
  value?: string;
  children?: ReactNode;
}) {
  return (
    <span className={`badge badge-${value || "neutral"}`}>
      {children || labels[value || ""] || value}
    </span>
  );
}
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <div className="actions">{actions}</div>
        </div>
      )}
      {children}
    </section>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={"notice " + tone}>
      <Info size={17} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  children = "暂无记录。完成上方操作后，真实结果会显示在这里。",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-mark">—</div>
      {children}
    </div>
  );
}
export function Spinner() {
  return (
    <div className="spinner">
      <LoaderCircle size={20} className="spin" />
      正在读取…
    </div>
  );
}
export function Metric({
  label,
  value,
  note,
  onClick,
}: {
  label: string;
  value: ReactNode;
  note: string;
  onClick?: () => void;
}) {
  return (
    <button className="metric" onClick={onClick}>
      <div>
        {label}
        <ArrowUpRight size={17} />
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </button>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = old;
    };
  }, [onClose]);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="关闭弹窗"
          >
            <X size={21} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Hash({ value }: { value?: string }) {
  return (
    <code title={value} className="hash">
      {value ? value.slice(0, 12) + "…" + value.slice(-6) : "—"}
    </code>
  );
}
export function LineChart({
  values,
  secondary,
  title = "SOH / %",
  labels: axisLabels = [],
}: {
  values: number[];
  secondary?: number[];
  title?: string;
  labels?: string[];
}) {
  const all = [...values, ...(secondary || [])].filter(Number.isFinite);
  if (!all.length) return <Empty />;
  const min = Math.min(...all),
    max = Math.max(...all),
    pad = Math.max((max - min) * 0.15, 1),
    lo = min - pad,
    hi = max + pad;
  const points = (v: number[]) =>
    v
      .map(
        (y, i) =>
          `${32 + (i * 568) / Math.max(1, v.length - 1)},${154 - ((y - lo) * 126) / (hi - lo)}`,
      )
      .join(" ");
  return (
    <div className="chart">
      <div className="chart-caption">{title}</div>
      <svg viewBox="0 0 640 186" role="img" aria-label={title + " 数据曲线"}>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line
              x1="32"
              x2="608"
              y1={28 + i * 42}
              y2={28 + i * 42}
              stroke="var(--line)"
            />
            <text x="1" y={32 + i * 42} fontSize="10" fill="var(--muted)">
              {(hi - (i * (hi - lo)) / 3).toFixed(1)}
            </text>
          </g>
        ))}
        <polyline
          points={points(values)}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.5"
        />
        {secondary?.length && (
          <polyline
            points={points(secondary)}
            fill="none"
            stroke="var(--amber)"
            strokeWidth="2"
            strokeDasharray="5 4"
          />
        )}
        <text x="32" y="179" fill="var(--muted)" fontSize="10">
          {axisLabels[0] || "起始样本"}
        </text>
        <text
          x="605"
          y="179"
          fill="var(--muted)"
          fontSize="10"
          textAnchor="end"
        >
          {axisLabels.at(-1) || `共 ${values.length} 个样本`}
        </text>
      </svg>
    </div>
  );
}
export function ResultMetrics({ metrics }: { metrics: any }) {
  if (!metrics || metrics.status === "no_ground_truth")
    return <Notice>未提供真实标签，不计算预测精度。</Notice>;
  return (
    <div>
      <Notice>
        {labels[metrics.scope] || metrics.scope || "评估范围以原报告为准"}
        。误差单位为 SOH 百分点。
      </Notice>
      <div className="mini-metrics">
        <div>
          <small>电芯宏平均 MAE</small>
          <strong>{metrics.cell_macro_mae_pp?.toFixed(4) ?? "—"}</strong>
        </div>
        <div>
          <small>电芯宏平均 RMSE</small>
          <strong>{metrics.cell_macro_rmse_pp?.toFixed(4) ?? "—"}</strong>
        </div>
        <div>
          <small>标签样本数 / 电芯数</small>
          <strong>
            {metrics.labelled_rows ?? "—"} / {metrics.cells ?? "—"}
          </strong>
        </div>
      </div>
      {metrics.per_cell?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>电芯</th>
                <th>样本</th>
                <th>MAE / pp</th>
                <th>RMSE / pp</th>
              </tr>
            </thead>
            <tbody>
              {metrics.per_cell.map((c: any) => (
                <tr key={c.cell_id}>
                  <td>{c.cell_id}</td>
                  <td>{c.rows}</td>
                  <td>{c.mae_pp.toFixed(4)}</td>
                  <td>{c.rmse_pp.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  async function run(fn: () => Promise<unknown>, success = "操作已保存") {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
      setMessage(success);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return {
    busy,
    message,
    error,
    run,
    feedback: (
      <>
        {error && <Notice tone="error">{error}</Notice>}
        {message && <Notice tone="success">{message}</Notice>}
      </>
    ),
  };
}
