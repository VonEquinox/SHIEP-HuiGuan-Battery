import type {
  ExperimentMetricDefinition,
  ExperimentMetrics,
  ExperimentProtocol,
} from "./contracts/v2";

export interface ExperimentRun {
  id: number;
  status: string;
  experiment_metrics?: ExperimentMetrics;
  experiment_protocol?: ExperimentProtocol;
}

export function metricMeasurement(
  run: ExperimentRun,
  definition: ExperimentMetricDefinition,
): { value: number | null; denominator: number | null; reason?: string } {
  const measured = run.experiment_metrics;
  if (!measured || measured.schema_version !== "experiment-metrics.v1")
    return {
      value: null,
      denominator: null,
      reason: "未提供受支持的 ExperimentMetrics 契约。",
    };
  const raw = measured.values[definition.key];
  const valid =
    typeof raw === "number" &&
    Number.isFinite(raw) &&
    raw >= 0 &&
    (definition.kind !== "ratio" || raw <= 1) &&
    (definition.kind !== "count" || Number.isInteger(raw));
  const denominator = definition.denominator
    ? (measured.values.denominators[definition.denominator] ?? null)
    : null;
  return {
    value: valid && definition.kind !== "unsupported" ? raw : null,
    denominator,
    reason:
      measured.unsupported[definition.key] ||
      definition.unsupported_reason ||
      (!valid ? "本实验没有合格测量值。" : undefined),
  };
}

export function metricSeries(
  runs: ExperimentRun[],
  definition: ExperimentMetricDefinition,
) {
  const groups = new Map<
    string,
    {
      protocol: ExperimentProtocol;
      points: {
        id: number;
        value: number;
        denominator: number | null;
        status: string;
      }[];
    }
  >();
  for (const run of [...runs].sort((a, b) => a.id - b.id)) {
    const measurement = metricMeasurement(run, definition),
      protocol = run.experiment_protocol;
    if (measurement.value === null || !protocol) continue;
    const key = JSON.stringify([
      protocol.protocol_id,
      protocol.protocol_version,
      protocol.split,
      protocol.method,
      protocol.provenance,
      protocol.metric_version,
      protocol.cohort_sha256,
      protocol.execution_modes,
      protocol.llm_models,
      definition.key,
    ]);
    const group = groups.get(key) || { protocol, points: [] };
    group.points.push({
      id: run.id,
      value: measurement.value,
      denominator: measurement.denominator,
      status: run.status,
    });
    groups.set(key, group);
  }
  return [...groups.entries()];
}

export function metricValue(
  value: number,
  definition: ExperimentMetricDefinition,
) {
  return definition.kind === "count" ? String(value) : value.toFixed(4);
}
