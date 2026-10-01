"""Compose trusted observation snapshots for the existing MAD group baseline.

No database, model, labels or network are accessible in this adapter. Normal
references are explicitly declared earlier observations, never inferred from
the current anomaly cohort or extracted from unrelated experimental batteries.
"""
from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations

from .groups import analyze_groups, correlation

CONDITION_FIELDS = ("chemistry", "protocol_id", "load_condition", "temperature_condition", "source_cohort_id")
THRESHOLD_VERSION = "group-dev-v1"


def measurement_groups(members, *, window_start, cutoff, cancelled):
    cohorts, rejections = defaultdict(dict), defaultdict(set)
    for member in members:
        asset = member["asset"]
        iid = asset["installation_id"]
        series = defaultdict(lambda: {"reference": {}, "analysis": {}, "conflicted": set(), "refs": []})
        for observation in member.get("observations", []):
            reasons = []
            conditions = observation.get("comparison_context")
            if not isinstance(conditions, dict) or not all(conditions.get(k) for k in CONDITION_FIELDS):
                reasons.append("comparison_conditions_missing")
            elif any(str(conditions[k]).lower() in {"unknown", "not_recorded", "未记录", "未知"} for k in CONDITION_FIELDS):
                reasons.append("comparison_conditions_unknown")
            if observation.get("provenance") == "experimental_replay":
                reasons.append("independent_experimental_cells_not_station_channels")
            elif asset["provenance"] == "simulated" and observation.get("provenance") != "synthetic":
                reasons.append("simulated_topology_requires_explicit_synthetic_measurements")
            if observation.get("result") != "observed" or observation.get("calibration_status") != "calibrated" or observation.get("instrument_id") in (None, "not_recorded"):
                reasons.append("measurement_quality_or_calibration_unsupported")
            if not observation.get("_authorization_verified") or not (conditions or {}).get("qualification_evidence", {}).get("verified"):
                reasons.append("measurement_authorization_or_qualification_unverified")
            if observation.get("performed_actions"):
                reasons.append("intervention_requires_separate_reference_review")
            if reasons:
                rejections[str(asset["id"])].update(reasons)
                continue
            role = "reference" if conditions.get("reference_status") == "declared_normal" else "analysis"
            for measurement in observation.get("measurements", []):
                value = measurement.get("value")
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    rejections[str(asset["id"])].add("nonfinite_or_missing_measurement")
                    continue
                # Source, protocol, exact units/method and declared operating
                # conditions are part of the cohort; none are guessed.
                key = (asset["parent_id"], observation["provenance"], measurement["metric"], measurement["unit"], measurement["method"],
                       *(conditions[field] for field in CONDITION_FIELDS))
                sample = series[key]
                measured = observation["measured_at"]
                if measured in sample[role] and sample[role][measured] != value:
                    sample["conflicted"].add(measured)
                    rejections[str(asset["id"])].add("conflicting_duplicate_timestamp")
                sample[role][measured] = value
                sample["refs"].append({"observation_id": observation["id"], "version": observation["version"], "asset_id": asset["id"],
                    "installation_id": iid, "role": role, "measured_at": measured, "available_at": observation["available_at"],
                    "origin": observation["provenance"], "source_trust": observation.get("verification_status", "reported")})
        for key, sample in series.items():
            analysis = {time: value for time, value in sample["analysis"].items() if time not in sample["conflicted"] and window_start <= time <= cutoff}
            first = min(analysis) if analysis else cutoff
            reference = {time: value for time, value in sample["reference"].items() if time < first and time not in sample["conflicted"]}
            if len(reference) < 3 or len(analysis) < 3:
                rejections[str(asset["id"])].add("three_prior_normal_reference_and_analysis_points_required")
                continue
            times = sorted(analysis)
            cohorts[key][iid] = {"entity": {"installation_id": iid, "parent_id": asset["parent_id"], "chemistry": key[5],
                "load_condition": key[7], "temperature_condition": key[8], "timestamps": times, "values": [analysis[t] for t in times],
                "reference_values": [reference[t] for t in sorted(reference)], "topology_origin": asset["provenance"]},
                "member": member, "source_refs": [ref for ref in sample["refs"] if ref["measured_at"] in (reference if ref["role"] == "reference" else analysis)]}
    analyses, groups = [], []
    for key, records in sorted(cohorts.items(), key=lambda item: str(item[0])):
        if cancelled():
            raise RuntimeError("群组分析已取消")
        if len(records) < 2:
            for record in records.values():
                rejections[str(record["member"]["asset"]["id"])].add("no_comparable_peer_cohort")
            continue
        numeric = analyze_groups([record["entity"] for record in records.values()], threshold_version=THRESHOLD_VERSION)
        diagnostics = []
        for left, right in combinations(sorted(records), 2):
            a, b = numeric["residuals"][left], numeric["residuals"][right]
            aligned = sorted(set(a) & set(b))
            rho = correlation([a[t] for t in aligned], [b[t] for t in aligned])
            diagnostics.append({"members": [left, right], "correlation": rho, "aligned_points": len(aligned), "causality": "not_established"})
        numeric["qualified_pairs"] = diagnostics
        supported = any(pair["correlation"] is not None for pair in diagnostics)
        reasons = [] if supported else sorted({flag for flags in numeric["quality_flags"].values() for flag in flags} | {"insufficient_nonconstant_aligned_residuals"})
        comparison = dict(zip(("parent_id", "origin", "metric", "unit", "method", *CONDITION_FIELDS), key))
        support = {"status": "supported" if supported else "unsupported", "reasons": reasons,
                   "reference_kind": "operator_declared_normal_prior_window", "causal_confirmation": False}
        source_refs = [ref for record in records.values() for ref in record["source_refs"]]
        analysis = {"comparison": comparison, "numeric_analysis": numeric, "numeric_support": support,
                    "source_refs": source_refs, "numeric_algorithm_executed": True, "numeric_correlation_supported": supported}
        analyses.append(analysis)
        for group in numeric["groups"]:
            selected = [records[iid]["member"] for iid in group["members"]]
            groups.append({**analysis, "members": selected, "relation_type": "synchronous_association", "confirmed_common_cause": False,
                           "reason": "同源、同条件且对齐的 MAD 残差相关与异常重叠达到冻结阈值；关联不确认因果",
                           "group_state": group["state"], "alternative_explanations": group["alternative_explanations"]})
    return {"groups": groups, "analyses": analyses, "rejections": {asset: sorted(flags) for asset, flags in rejections.items()},
            "numeric_algorithm_executed": bool(analyses), "numeric_correlation_supported": any(item["numeric_correlation_supported"] for item in analyses)}
