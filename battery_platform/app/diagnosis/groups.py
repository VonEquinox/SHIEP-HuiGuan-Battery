"""Small relation view with robust reference residuals and reversible grouping."""
from __future__ import annotations

import hashlib
import math
import statistics
from collections import defaultdict
from typing import Any


def residuals(values: list[float | None], reference: list[float], *, epsilon: float = 1e-9) -> tuple[list[float | None], list[str]]:
    clean = [float(v) for v in reference if v is not None and math.isfinite(float(v))]
    if len(clean) < 3:
        return [None] * len(values), ["reference_insufficient"]
    median = statistics.median(clean)
    mad = statistics.median(abs(v - median) for v in clean)
    if mad <= epsilon:
        return [None] * len(values), ["constant_reference_requires_separate_review"]
    result = [None if v is None or not math.isfinite(float(v)) else (float(v) - median) / (1.4826 * mad) for v in values]
    return result, (["missing_measurement"] if any(v is None for v in result) else [])


def correlation(a: list[float | None], b: list[float | None]) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    xv, yv = sum((x - xm) ** 2 for x in xs), sum((y - ym) ** 2 for y in ys)
    if xv <= 1e-12 or yv <= 1e-12:
        return None
    return sum((x - xm) * (y - ym) for x, y in pairs) / math.sqrt(xv * yv)


def analyze_groups(entities: list[dict[str, Any]], *, correlation_threshold: float = 0.8,
                   residual_threshold: float = 3.0, threshold_version: str = "group-dev-v1") -> dict[str, Any]:
    """Only comparable, aligned, adjacent channels can form a synchronous group.

    Values carry exact timestamps. Reference values come from a supplied normal
    window, never the current anomaly cohort. No causal claim is produced.
    """
    if not 0 <= correlation_threshold <= 1 or residual_threshold <= 0:
        raise ValueError("invalid frozen grouping thresholds")
    ids = [str(e["installation_id"]) for e in entities]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate installation identity")
    normalized, quality, pairs, adjacency = {}, {}, [], defaultdict(set)
    by_id = dict(zip(ids, entities))
    for iid, e in by_id.items():
        if len(e.get("timestamps", [])) != len(e.get("values", [])):
            raise ValueError("timestamps must match values")
        vals, flags = residuals(e.get("values", []), e.get("reference_values", []))
        normalized[iid] = dict(zip(e.get("timestamps", []), vals))
        quality[iid] = flags
    for index, aid in enumerate(ids):
        a = by_id[aid]
        for bid in ids[index + 1:]:
            b = by_id[bid]
            comparable = all(a.get(k) is not None and a.get(k) == b.get(k) for k in ("chemistry", "load_condition", "temperature_condition"))
            shared = [k for k in ("parent_id", "acquisition_channel", "environment_id") if a.get(k) and a.get(k) == b.get(k)]
            batch = bool(a.get("batch_id") and a.get("batch_id") == b.get("batch_id"))
            times = sorted(set(normalized[aid]) & set(normalized[bid]))
            av, bv = [normalized[aid][t] for t in times], [normalized[bid][t] for t in times]
            corr = correlation(av, bv) if comparable else None
            overlap = sum(x is not None and y is not None and abs(x) >= residual_threshold and abs(y) >= residual_threshold for x, y in zip(av, bv))
            connected = comparable and bool(shared) and corr is not None and corr >= correlation_threshold and overlap >= 2
            if connected:
                adjacency[aid].add(bid)
                adjacency[bid].add(aid)
            if connected or batch:
                pairs.append({"members": [aid, bid], "correlation": corr, "aligned_points": len(times),
                              "event_overlap": overlap, "shared_relations": shared,
                              "relation": "synchronous_association" if connected else "batch_association",
                              "causality": "not_established"})
    groups, seen = [], set()
    for iid in ids:
        if iid in seen or not adjacency[iid]:
            continue
        stack, members = [iid], []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            members.append(node)
            stack.extend(adjacency[node] - seen)
        members.sort()
        gid = "incident-" + hashlib.sha256("|".join(members).encode()).hexdigest()[:12]
        groups.append({"group_id": gid, "members": members, "state": "suspected_shared_condition",
                       "causality": "not_established", "threshold_version": threshold_version,
                       "topology_origin": "simulated" if any(by_id[m].get("topology_origin") == "simulated" for m in members) else "declared",
                       "alternative_explanations": ["shared acquisition issue", "shared environment", "coincident individual anomalies"],
                       "individual_anomalies_retained": True})
    return {"groups": groups, "pair_evidence": pairs, "quality_flags": quality,
            "threshold_version": threshold_version, "residuals": normalized}


def split_group(group: dict[str, Any], partitions: list[list[str]], *, reason: str) -> list[dict[str, Any]]:
    flattened = [m for part in partitions for m in part]
    if not reason or any(not part for part in partitions) or len(flattened) != len(set(flattened)) or set(flattened) != set(group["members"]):
        raise ValueError("split must partition every member exactly once with a reason")
    return [{**group, "group_id": f"{group['group_id']}/split-{i + 1}", "parent_group_id": group["group_id"],
             "members": sorted(part), "split_reason": reason, "state": "requires_individual_reassessment"}
            for i, part in enumerate(partitions)]
