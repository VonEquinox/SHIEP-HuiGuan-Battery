// Public V2 wire contracts. Credentials and numerical calculations stay on the server.
export type Chemistry =
  "LFP" | "NCM" | "NCA" | "LCO" | "LMO" | "LTO" | "unknown";
export type ObservationProvenance =
  "synthetic" | "experimental_replay" | "measured_declared";
export type ObservationResult =
  | "observed"
  | "inconclusive"
  | "failed"
  | "out_of_range"
  | "refused"
  | "requires_authorization";
export type CalibrationStatus =
  "calibrated" | "unknown" | "expired" | "not_applicable";

export interface ComparisonContext {
  chemistry: Chemistry;
  protocol_id: string;
  load_condition: string;
  temperature_condition: string;
  source_cohort_id: string;
  reference_status: "not_reference" | "declared_normal";
}

export interface ObservationCreate {
  asset_id?: number;
  installation_id: string;
  round: number;
  order_version: number;
  test_id: string;
  measured_at: string;
  instrument_id: string;
  calibration_status: CalibrationStatus;
  measurements: {
    metric: string;
    value: number;
    unit: string;
    method: string;
  }[];
  free_text: string;
  result: ObservationResult;
  provenance: ObservationProvenance;
  attachment_ids: number[];
  client_submission_id: string;
  comparison_context?: ComparisonContext | null;
}

export interface NumericPairEvidence {
  members: string[];
  correlation: number | null;
  aligned_points: number;
  event_overlap?: number;
  shared_relations?: string[];
  relation?: string;
  causality: "not_established";
}

export interface IncidentSourceReference {
  observation_id: number;
  version: number;
  asset_id: number;
  installation_id: string;
  role: "reference" | "analysis";
  measured_at: string;
  available_at: string;
  origin: ObservationProvenance;
  source_trust: string;
}

export interface IncidentNumericEvidence {
  numeric_correlation_supported?: boolean;
  numeric_support?: {
    status: string;
    reasons: string[];
    reference_kind?: string;
    causal_confirmation?: boolean;
  };
  numeric_analysis?: {
    threshold_version: string;
    residuals: Record<string, Record<string, number | null>>;
    pair_evidence: NumericPairEvidence[];
    qualified_pairs?: NumericPairEvidence[];
    quality_flags: Record<string, string[]>;
  };
  comparison?: Partial<ComparisonContext> & {
    metric?: string;
    unit?: string;
    method?: string;
    origin?: string;
  };
  source_refs?: IncidentSourceReference[];
  measurement_rejections?: Record<string, string[]>;
  confirmed_common_cause?: boolean;
  [key: string]: unknown;
}
