"""Small deterministic dispatch and Carbon golden cases.

These records belong to the evaluator, not to the diagnostic Agent's index.
The dispatch oracle exhausts a declared discrete time grid. Carbon answers are
computed from explicit arithmetic, renewal recursion, and budget support rules.
No LLM output is used as a mathematical reference answer.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any


TOLERANCE = {"absolute": 1e-9, "relative": 1e-9}
SCHEMA_VERSION = "mathematical-fixture-v1"


def compare_expected(expected: Any, actual: Any, path: str = "$", *, atol: float = 1e-9,
                     rtol: float = 1e-9) -> list[str]:
    """Compare a structured numerical result; bool/count/string values are exact."""
    errors: list[str] = []
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if type(actual) is not type(expected) or actual != expected:
            errors.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(expected, int):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or actual != expected:
            errors.append(f"{path}: expected exact {expected!r}, got {actual!r}")
    elif isinstance(expected, float):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual):
            errors.append(f"{path}: expected a finite number, got {actual!r}")
        elif not math.isclose(expected, actual, abs_tol=atol, rel_tol=rtol):
            errors.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object"]
        if set(expected) != set(actual):
            errors.append(f"{path}: object keys differ")
        for key in sorted(expected.keys() & actual.keys()):
            errors.extend(compare_expected(expected[key], actual[key], f"{path}.{key}", atol=atol, rtol=rtol))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [f"{path}: array lengths/types differ"]
        for index, (left, right) in enumerate(zip(expected, actual)):
            errors.extend(compare_expected(left, right, f"{path}[{index}]", atol=atol, rtol=rtol))
    elif expected != actual:
        errors.append(f"{path}: values differ")
    return errors


def _inside(start: int, end: int, windows: list[list[int]]) -> bool:
    return any(left <= start and end <= right for left, right in windows)


def _overlap(start: int, end: int, left: int, right: int) -> bool:
    return start < right and left < end


def _travel(inputs: dict, left: str, right: str) -> int | None:
    return inputs["travel_minutes"].get(left, {}).get(right)


def _qualified(task: dict, engineer: dict) -> bool:
    return (set(task["required_skills"]) <= set(engineer["skills"])
            and set(task["required_qualifications"]) <= set(engineer["qualifications"]))


def _dispatch_tasks(inputs: dict) -> tuple[list[dict], list[dict], list[str]]:
    """Resolve the proposal boundary before building a formal task set."""
    included: list[dict] = []
    excluded: list[dict] = []
    duplicate_ids: list[str] = []
    seen: dict[str, dict] = {}
    locked_ids = {row["task_id"] for row in inputs["locked_tasks"]}
    for task in inputs["tasks"]:
        tid = task["task_id"]
        if tid in seen:
            if seen[tid] != task:
                raise ValueError(f"conflicting duplicate task: {tid}")
            duplicate_ids.append(tid)
            continue
        seen[tid] = task
        if tid in locked_ids:
            continue
        reason = None
        if inputs["snapshot_version"] != inputs["current_snapshot_version"]:
            reason = "STALE_INPUT_VERSION"
        elif task["approval"]["status"] != "APPROVED":
            reason = "HUMAN_APPROVAL_REQUIRED"
        elif task["approval"]["version"] != task["approval"]["current_version"]:
            reason = "STALE_APPROVAL_VERSION"
        elif not task.get("asset_mapping_valid", True):
            reason = "INVALID_ASSET_MAPPING"
        elif task.get("observed_installation_id") not in (None, task.get("installation_id")):
            reason = "STALE_INSTALLATION_MAPPING"
        elif task.get("event_expires_at_minute", inputs["horizon_minutes"]) < 0:
            reason = "EXPIRED_EVENT"
        if reason:
            excluded.append({"task_id": tid, "reason": reason})
        else:
            included.append(task)
    return included, excluded, sorted(set(duplicate_ids))


def validate_dispatch_solution(inputs: dict, assignments: list[dict], *, complete: bool = True) -> list[str]:
    """Check an arbitrary draft against qualifications, travel, tools, and locks.

    Alternative optimal engineer names/start times are valid. Unassigned tasks
    are allowed: the objective/oracle records how good such a draft is.
    """
    errors: list[str] = []
    tasks, excluded, _ = _dispatch_tasks(inputs)
    task_map = {row["task_id"]: row for row in tasks}
    engineers = {row["engineer_id"]: row for row in inputs["engineers"]}
    tools = {row["tool_id"]: row for row in inputs["tools"]}
    locked_map = {row["task_id"]: row for row in inputs["locked_tasks"]}
    scheduled: dict[str, dict] = {}
    intervals: list[dict] = copy.deepcopy(inputs["locked_tasks"])
    excluded_ids = {row["task_id"] for row in excluded}
    for row in assignments:
        tid = row.get("task_id")
        if tid in scheduled:
            errors.append(f"duplicate_assignment:{tid}")
            continue
        scheduled[tid] = row
        if tid in locked_map:
            lock = locked_map[tid]
            if any(row.get(field) != lock[field] for field in ("engineer_id", "start", "end")):
                errors.append(f"locked_task_changed:{tid}")
            continue
        if tid not in task_map:
            errors.append(f"unapproved_or_unknown_task:{tid}" if tid in excluded_ids else f"unknown_task:{tid}")
            continue
        task = task_map[tid]
        eid = row.get("engineer_id")
        if eid not in engineers:
            errors.append(f"unknown_engineer:{tid}")
            continue
        engineer = engineers[eid]
        start, end = row.get("start"), row.get("end")
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                or not isinstance(end, int)):
            errors.append(f"invalid_time:{tid}")
            continue
        if (start < 0 or end > inputs["horizon_minutes"] or end - start != task["duration_minutes"]
                or start % inputs["time_quantum_minutes"]):
            errors.append(f"invalid_duration_or_grid:{tid}")
        if not engineer["available"]:
            errors.append(f"engineer_unavailable:{tid}")
        if not _qualified(task, engineer):
            errors.append(f"unqualified:{tid}")
        if not _inside(start, end, engineer["shift_windows"]):
            errors.append(f"outside_shift:{tid}")
        if any(_overlap(start, end, *window) for window in engineer.get("leave_windows", [])):
            errors.append(f"during_leave:{tid}")
        if task.get("hard_deadline", True) and end > task["deadline_minute"]:
            errors.append(f"deadline_missed:{tid}")
        for tool_id in task["tools"]:
            if tool_id not in tools or not _inside(start, end, tools[tool_id]["available_windows"]):
                errors.append(f"tool_unavailable:{tid}:{tool_id}")
        intervals.append({**row, "location": task["location"], "tools": task["tools"]})
    for eid, engineer in engineers.items():
        rows = sorted((row for row in intervals if row["engineer_id"] == eid), key=lambda row: (row["start"], row["task_id"]))
        travel_work = 0
        if rows:
            travel = _travel(inputs, engineer["initial_location"], rows[0]["location"])
            if travel is None or rows[0]["start"] < engineer.get("available_from_minute", 0) + travel:
                errors.append(f"initial_travel:{eid}")
            travel_work += travel or 0
        for left, right in zip(rows, rows[1:]):
            travel = _travel(inputs, left["location"], right["location"])
            if travel is None or left["end"] + travel > right["start"]:
                errors.append(f"overlap_or_travel:{eid}:{left['task_id']}:{right['task_id']}")
            travel_work += travel or 0
        if sum(row["end"] - row["start"] for row in rows) + travel_work > engineer["max_work_minutes"]:
            errors.append(f"workload_limit:{eid}")
    for tool_id, tool in tools.items():
        relevant = [row for row in intervals if tool_id in row.get("tools", [])]
        # End events sort before starts, so back-to-back use is permitted.
        events = sorted([(row["start"], 1) for row in relevant] + [(row["end"], -1) for row in relevant])
        usage = 0
        for _, delta in events:
            usage += delta
            if usage > tool["capacity"]:
                errors.append(f"tool_overlap:{tool_id}")
                break
    all_scheduled = {**locked_map, **scheduled}
    for tid, row in scheduled.items():
        if tid not in task_map:
            continue
        for predecessor in task_map[tid]["predecessors"]:
            if predecessor not in all_scheduled:
                if complete:
                    errors.append(f"predecessor_unassigned:{tid}:{predecessor}")
            elif all_scheduled[predecessor]["end"] > row["start"]:
                errors.append(f"precedence_violated:{tid}:{predecessor}")
    return sorted(set(errors))


def dispatch_objective(inputs: dict, assignments: list[dict]) -> list[int]:
    """Lexicographic severity/deadline service, then travel and load balance."""
    tasks, _, _ = _dispatch_tasks(inputs)
    assigned = {row["task_id"]: row for row in assignments}
    objective: list[int] = []
    for severity in (3, 2, 1):
        relevant = [task for task in tasks if task["severity"] == severity]
        objective.extend([
            sum(task["task_id"] not in assigned for task in relevant),
            sum(max(0, assigned[task["task_id"]]["end"] - task["deadline_minute"])
                for task in relevant if task["task_id"] in assigned),
        ])
    intervals = copy.deepcopy(inputs["locked_tasks"])
    task_map = {task["task_id"]: task for task in tasks}
    for row in assignments:
        if row["task_id"] in task_map:
            intervals.append({**row, "location": task_map[row["task_id"]]["location"]})
    total_travel, loads = 0, []
    for engineer in inputs["engineers"]:
        rows = sorted((row for row in intervals if row["engineer_id"] == engineer["engineer_id"]), key=lambda row: (row["start"], row["task_id"]))
        workload = sum(row["end"] - row["start"] for row in rows)
        location = engineer["initial_location"]
        for row in rows:
            travel = _travel(inputs, location, row["location"])
            total_travel += travel if travel is not None else inputs["horizon_minutes"] + 1
            workload += travel or 0
            location = row["location"]
        loads.append(workload)
    objective.extend([total_travel, max(loads, default=0) - min(loads, default=0)])
    return objective


def _unassigned_reason(task: dict, inputs: dict, assignments: list[dict]) -> str:
    qualified = [engineer for engineer in inputs["engineers"] if _qualified(task, engineer)]
    if not qualified:
        return "NO_QUALIFIED_ENGINEER"
    if not any(engineer["available"] for engineer in qualified):
        return "QUALIFIED_ENGINEER_UNAVAILABLE"
    assigned_ids = {row["task_id"] for row in assignments} | {row["task_id"] for row in inputs["locked_tasks"]}
    if any(predecessor not in assigned_ids for predecessor in task["predecessors"]):
        return "PREDECESSOR_UNASSIGNED"
    return "RESOURCE_OR_DEADLINE_CONFLICT"


def solve_dispatch(inputs: dict) -> dict:
    """Exhaustively enumerate all assignments/start slots for tiny fixtures."""
    tasks, excluded, duplicate_ids = _dispatch_tasks(inputs)
    options: list[list[dict | None]] = []
    for task in tasks:
        task_options: list[dict | None] = [None]
        for engineer in inputs["engineers"]:
            if not engineer["available"] or not _qualified(task, engineer):
                continue
            for start in range(0, inputs["horizon_minutes"] - task["duration_minutes"] + 1, inputs["time_quantum_minutes"]):
                task_options.append({"task_id": task["task_id"], "engineer_id": engineer["engineer_id"],
                                     "start": start, "end": start + task["duration_minutes"]})
        options.append(task_options)
    best: tuple | None = None
    best_rows: list[dict] = []
    feasible_count = 0

    def visit(index: int, rows: list[dict]) -> None:
        nonlocal best, best_rows, feasible_count
        if index == len(tasks):
            if validate_dispatch_solution(inputs, rows):
                return
            feasible_count += 1
            objective = tuple(dispatch_objective(inputs, rows))
            canonical = tuple((row["task_id"], row["engineer_id"], row["start"]) for row in rows)
            score = objective, canonical
            if best is None or score < best:
                best, best_rows = score, copy.deepcopy(rows)
            return
        for option in options[index]:
            next_rows = rows if option is None else [*rows, option]
            if not validate_dispatch_solution(inputs, next_rows, complete=False):
                visit(index + 1, next_rows)

    visit(0, [])
    assigned_ids = {row["task_id"] for row in best_rows}
    return {
        "method": "exhaustive_discrete_grid",
        "status": "optimal" if best is not None else "infeasible",
        "objective": list(best[0]) if best is not None else None,
        "assignments": best_rows,
        "unassigned": [{"task_id": task["task_id"], "reason": _unassigned_reason(task, inputs, best_rows)}
                       for task in tasks if task["task_id"] not in assigned_ids],
        "excluded": excluded,
        "idempotent_duplicate_task_ids": duplicate_ids,
        "locked_tasks_preserved": copy.deepcopy(inputs["locked_tasks"]),
        "feasible_assignment_count": feasible_count,
        "requires_human_schedule_confirmation": True,
    }


def dispatch_runtime_adapter(inputs: dict) -> dict:
    """Map normalized fixtures to ``app.dispatch.solver`` without sharing math.

    Approval/version/mapping filtering is fixture-side service preprocessing.
    Its existence here does not replace tests of the live API approval boundary.
    The returned dictionaries also let callers map solver IDs back to fixtures.
    """
    tasks, excluded, duplicates = _dispatch_tasks(inputs)
    task_names = list(dict.fromkeys([row["task_id"] for row in inputs["tasks"]]
                                   + [row["task_id"] for row in inputs["locked_tasks"]]
                                   + [predecessor for row in tasks for predecessor in row["predecessors"]]))
    task_ids = {name: index + 1 for index, name in enumerate(task_names)}
    engineer_ids = {row["engineer_id"]: index + 1 for index, row in enumerate(inputs["engineers"])}
    runtime_tasks = []
    for row in tasks:
        runtime_tasks.append({"id": task_ids[row["task_id"]], "duration": row["duration_minutes"], "release": 0,
                              "due": row["deadline_minute"], "hard_deadline": row.get("hard_deadline", True),
                              "severity": {3: "critical", 2: "high", 1: "routine"}[row["severity"]],
                              "qualifications": [f"skill:{value}" for value in row["required_skills"]]
                                                + [f"qualification:{value}" for value in row["required_qualifications"]],
                              "location": row["location"], "tools": {tool: 1 for tool in row["tools"]},
                              "predecessors": [task_ids[value] for value in row["predecessors"]], "locked": None})
    for row in inputs["locked_tasks"]:
        runtime_tasks.append({"id": task_ids[row["task_id"]], "duration": row["end"] - row["start"], "release": 0,
                              "due": inputs["horizon_minutes"], "severity": "routine", "qualifications": [],
                              "location": row["location"], "tools": {tool: 1 for tool in row["tools"]}, "predecessors": [],
                              "locked": {"engineer_id": engineer_ids[row["engineer_id"]], "start": row["start"]}})
    runtime_engineers = []
    for engineer in inputs["engineers"]:
        windows = copy.deepcopy(engineer["shift_windows"]) if engineer["available"] else []
        for leave_start, leave_end in engineer["leave_windows"]:
            remaining = []
            for start, end in windows:
                if not _overlap(start, end, leave_start, leave_end):
                    remaining.append([start, end])
                else:
                    if start < leave_start:
                        remaining.append([start, min(end, leave_start)])
                    if end > leave_end:
                        remaining.append([max(start, leave_end), end])
            windows = remaining
        runtime_engineers.append({"id": engineer_ids[engineer["engineer_id"]],
                                  "qualifications": [f"skill:{value}" for value in engineer["skills"]]
                                                    + [f"qualification:{value}" for value in engineer["qualifications"]],
                                  "shifts": windows, "max_minutes": engineer["max_work_minutes"], "max_tasks": 999,
                                  "existing_load": 0, "home_location": engineer["initial_location"],
                                  "available_from": engineer.get("available_from_minute", 0)})
    runtime = {"horizon_minutes": inputs["horizon_minutes"], "time_quantum_minutes": inputs["time_quantum_minutes"],
               "tasks": runtime_tasks, "engineers": runtime_engineers,
               "tool_capacities": {row["tool_id"]: row["capacity"] for row in inputs["tools"]},
               "tool_windows": {row["tool_id"]: row["available_windows"] for row in inputs["tools"]},
               "travel_minutes": {f"{left}|{right}": value for left, destinations in inputs["travel_minutes"].items()
                                  for right, value in destinations.items() if value is not None}}
    return {"data": runtime, "task_ids": task_ids, "engineer_ids": engineer_ids,
            "boundary_excluded": excluded, "idempotent_duplicate_task_ids": duplicates}


def budget_support(coefficients: list[float], gamma: float) -> float:
    """Exact support of |z|<=1, sum |z|<=Gamma for an affine expression."""
    if not math.isfinite(gamma) or not 0 <= gamma <= len(coefficients):
        raise ValueError("Gamma must be in [0, number of uncertainty sources]")
    ordered = sorted((abs(value) for value in coefficients), reverse=True)
    integer = math.floor(gamma)
    return sum(ordered[:integer]) + (gamma - integer) * (ordered[integer] if integer < len(ordered) else 0)


def renewal_counts(remaining: dict[str, float], lifetime: dict[str, float], horizon: int) -> dict:
    """Finite-horizon renewal expectations; tail mass is allowed to exceed H."""
    for pmf in (remaining, lifetime):
        if any(int(time) <= 0 or value < 0 for time, value in pmf.items()) or not math.isclose(sum(pmf.values()), 1, abs_tol=1e-12):
            raise ValueError("positive integer lifetimes and normalized PMFs required")
    new, old = [0.0] * (horizon + 1), [0.0] * (horizon + 1)
    for period in range(1, horizon + 1):
        new[period] = sum(prob for time, prob in lifetime.items() if int(time) <= period)
        new[period] += sum(prob * new[period - int(time)] for time, prob in lifetime.items() if int(time) <= period)
        old[period] = sum(prob for time, prob in remaining.items() if int(time) <= period)
        old[period] += sum(prob * new[period - int(time)] for time, prob in remaining.items() if int(time) <= period)
    return {"old": old, "new": new, "expected_replacements": old[-1]}


def evaluate_carbon(kind: str, inputs: dict) -> dict:
    """Calculate standalone normalized golden outputs without the product engine."""
    if kind == "unit_conversion":
        scales = {("Wh", "kWh"): .001, ("kWh", "Wh"): 1000., ("kg", "t"): .001, ("t", "kg"): 1000.}
        return {"value": inputs["value"] * scales[(inputs["from_unit"], inputs["to_unit"])], "unit": inputs["to_unit"]}
    if kind == "manufacturing":
        count = inputs["pack_count"]
        activity = count if inputs["factor_unit"] == "kgCO2e/pack" else count * inputs["capacity_kwh_per_pack"]
        return {"activity": activity, "emission_kg": activity * inputs["factor"], "gas_basis": "CO2e"}
    if kind == "factor_validation":
        if not inputs.get("source_ref"):
            return {"status": "rejected", "reason": "MISSING_FACTOR_SOURCE", "emission_kg": None}
        if (inputs["baseline_gas_basis"] != inputs["candidate_gas_basis"]
                or inputs["baseline_factor_boundary"] != inputs["candidate_factor_boundary"]):
            return {"status": "rejected", "reason": "INCOMPATIBLE_GAS_OR_FACTOR_BOUNDARY", "emission_kg": None}
        raise ValueError("validation fixture must define a rejection condition")
    if kind == "electricity":
        return {"emission_kg": inputs["energy_kwh"] * inputs["factor_kg_per_kwh"], "prediction_required": False}
    if kind == "auxiliary":
        auxiliary = 0. if inputs["aux_in_efficiency_boundary"] else inputs["aux_kwh"]
        energy = inputs["delivered_kwh"] / inputs["efficiency"] + auxiliary
        return {"input_energy_kwh": energy, "aux_added_kwh": auxiliary,
                "emission_kg": energy * inputs["factor_kg_per_kwh"]}
    if kind == "same_service":
        delivered = inputs["delivered_kwh"]
        baseline = delivered / inputs["baseline_efficiency"] * inputs["factor_kg_per_kwh"] + inputs["baseline_manufacturing_kg"]
        candidate = delivered / inputs["candidate_efficiency"] * inputs["factor_kg_per_kwh"] + inputs["candidate_manufacturing_kg"]
        return {"baseline_kg": baseline, "candidate_kg": candidate, "avoided_kg": baseline - candidate,
                "functional_unit_kwh": delivered, "permanent_avoidance_established": False}
    if kind == "delay":
        difference = inputs["baseline_replacements"] - inputs["candidate_replacements"]
        return {"replacements_delayed_within_horizon": difference,
                "within_horizon_manufacturing_difference_kg": difference * inputs["manufacturing_kg_per_pack"],
                "permanent_avoidance_established": False, "terminal_state_comparable": False}
    if kind == "censored_lifetime":
        return {"lifetime_lower_bound_cycles": inputs["last_observed_cycle"], "observed_eol": False,
                "expected_remaining_cycles": None, "status": "insufficient_evidence"}
    if kind == "renewal":
        return renewal_counts(inputs["remaining_pmf"], inputs["new_lifetime_pmf"], inputs["horizon"])
    if kind == "replacement_reset":
        initial = inputs["initial_distribution"]
        matrix = inputs["transition_matrix"]
        size = len(initial)
        if not math.isclose(sum(initial), 1, abs_tol=1e-12) or any(not math.isclose(sum(row), 1, abs_tol=1e-12) for row in matrix):
            raise ValueError("state distributions and transition rows must sum to one")
        distribution = [sum(initial[index] * matrix[index][target] for index in range(size)) for target in range(size)]
        replacements = sum(initial[index] * inputs["replacement_probability_by_state"][index] for index in range(size))
        age = sum(prob * inputs["state_age"][index] for index, prob in enumerate(distribution))
        return {"terminal_distribution": distribution, "probability_sum": sum(distribution),
                "expected_replacements": replacements, "terminal_expected_age": age,
                "old_installation_history_modified": False}
    if kind == "terminal_state":
        return {"status": "insufficient_evidence", "reason": "TERMINAL_STATE_MISMATCH",
                "avoided_kg": None, "required": "common_terminal_treatment_or_extended_service"}
    if kind == "robust_range":
        support = budget_support(inputs["coefficients"], inputs["gamma"])
        return {"nominal": inputs["nominal"], "lower_under_set": inputs["nominal"] - support,
                "upper_under_set": inputs["nominal"] + support, "gamma": inputs["gamma"],
                "approximation_error": 0.0, "confidence_probability": None}
    if kind == "robust_difference":
        source_ids = sorted(set(inputs["baseline_coefficients"]) | set(inputs["candidate_coefficients"]))
        coefficients = [inputs["baseline_coefficients"].get(key, 0) - inputs["candidate_coefficients"].get(key, 0) for key in source_ids]
        nominal = inputs["baseline_nominal"] - inputs["candidate_nominal"]
        support = budget_support(coefficients, inputs["gamma"])
        return {"nominal_avoided_kg": nominal, "lower_avoided_kg": nominal - support,
                "upper_avoided_kg": nominal + support, "shared_source_ids": source_ids,
                "robustly_better": nominal - support > 0}
    if kind == "pareto":
        feasible = [row for row in inputs["candidates"] if row.get("feasible", True)]
        front = sorted(row["candidate_id"] for row in feasible if not any(
            other["cost"] <= row["cost"] and other["carbon"] <= row["carbon"]
            and (other["cost"] < row["cost"] or other["carbon"] < row["carbon"])
            for other in feasible))
        return {"frontier_ids": front, "dominated_ids": sorted(row["candidate_id"] for row in feasible if row["candidate_id"] not in front),
                "infeasible_ids": sorted(row["candidate_id"] for row in inputs["candidates"] if not row.get("feasible", True))}
    if kind == "economic_split":
        shadow = inputs["avoided_kg"] / 1000 * inputs["shadow_price_rmb_per_t"]
        cash = inputs["issued_t"] * inputs["contract_price_rmb_per_t"] if inputs["test_qualification_established"] else None
        return {"operating_savings_rmb": inputs["operating_savings_rmb"], "shadow_value_rmb": shadow,
                "credit_cash_rmb": cash, "cash_status": "demo_issued" if cash is not None else "not_established",
                "total_cash_savings_rmb": inputs["operating_savings_rmb"] + (cash or 0),
                "synthetic_rule_id": inputs.get("rule_id"), "official_policy_claim": False}
    if kind == "ledger_export":
        ledger = inputs["entries"]
        ids = {row["entry_id"] for row in ledger}
        if len(ids) != len(ledger) or any(row.get("reversal_of") and row["reversal_of"] not in ids for row in ledger):
            raise ValueError("unique entries and resolved correction links required")
        demo = sum(row["emission_kg"] for row in ledger if row["data_scope"] == "demo_synthetic")
        formal = sum(row["emission_kg"] for row in ledger if row["data_scope"] == "operational" and row["basis"] == "settled")
        return {"corrected_demo_emission_kg": demo, "formal_export_emission_kg": formal,
                "demo_export_emission_kg": demo, "demo_export_marked_synthetic": True,
                "original_entry_retained": True, "correction_count": sum(bool(row.get("reversal_of")) for row in ledger)}
    if kind == "nonlinear_efficiency":
        exact = sum(prob * inputs["delivered_kwh"] / eta for prob, eta in zip(inputs["state_probabilities"], inputs["efficiencies"]))
        invalid = inputs["delivered_kwh"] / sum(prob * eta for prob, eta in zip(inputs["state_probabilities"], inputs["efficiencies"]))
        return {"expected_input_energy_kwh": exact, "inverse_mean_efficiency_energy_kwh": invalid,
                "invalid_shortcut_error_kwh": exact - invalid, "exact_calculation_error": 0.0}
    if kind == "unavailable_service":
        probabilities, efficiencies = inputs["state_probabilities"], inputs["efficiencies"]
        energy = sum(prob * inputs["delivered_kwh"] / eta for prob, eta in zip(probabilities, efficiencies) if eta is not None)
        unmet = sum(prob * inputs["delivered_kwh"] for prob, eta in zip(probabilities, efficiencies) if eta is None)
        return {"expected_input_energy_kwh": energy, "unmet_service_kwh": unmet, "service_feasible": unmet == 0}
    raise ValueError(f"unknown Carbon fixture kind: {kind}")


def _engineer(eid: str = "E1", **overrides: Any) -> dict:
    return {"engineer_id": eid, "skills": ["electrical", "instrumentation"], "qualifications": ["demo-inspection"],
            "shift_windows": [[0, 30]], "leave_windows": [], "available": True,
            "initial_location": "A", "available_from_minute": 0, "max_work_minutes": 30, **overrides}


def _task(tid: str = "T1", **overrides: Any) -> dict:
    return {"task_id": tid, "severity": 2, "deadline_minute": 25, "duration_minutes": 10,
            "hard_deadline": True, "location": "A", "checks": ["DEMO_CHANNEL_CHECK"],
            "required_skills": ["electrical"], "required_qualifications": ["demo-inspection"],
            "predecessors": [], "tools": ["meter"], "asset_ids": [f"demo-asset-{tid}"],
            "installation_id": "demo-installation-v1", "asset_mapping_valid": True,
            "approval": {"status": "APPROVED", "version": 1, "current_version": 1}, **overrides}


def _lock(tid: str = "LOCK1", **overrides: Any) -> dict:
    return {"task_id": tid, "engineer_id": "E1", "start": 0, "end": 30,
            "location": "A", "tools": [], "started": True, **overrides}


def _dispatch_fixture(name: str, topics: list[str], **overrides: Any) -> dict:
    inputs = {"horizon_minutes": 30, "time_quantum_minutes": 5, "time_unit": "minute",
              "snapshot_version": 1, "current_snapshot_version": 1,
              "tasks": [_task()], "engineers": [_engineer()],
              "tools": [{"tool_id": "meter", "capacity": 1, "available_windows": [[0, 30]]}],
              "travel_minutes": {"A": {"A": 0, "B": 5}, "B": {"A": 5, "B": 0}},
              "locked_tasks": [], **overrides}
    return {"fixture_id": f"dispatch-{name}", "schema_version": SCHEMA_VERSION,
            "synthetic": True, "origin": "physics_simulated", "data_scope": "demo_synthetic",
            "generated_by": "deterministic_fixture_oracle_v1", "source_refs": ["doc02-section-8.2"],
            "kind": "dispatch", "coverage_tags": topics, "inputs": inputs, "oracle": solve_dispatch(inputs)}


def dispatch_fixtures() -> list[dict]:
    """Forty distinct small constraint/boundary problems, each exhaustible."""
    rows = [
        _dispatch_fixture("basic", ["approved_task", "duration"]),
        _dispatch_fixture("skill-routing", ["qualification", "skills"], engineers=[_engineer("E1", skills=["mechanical"]), _engineer("E2")]),
        _dispatch_fixture("missing-skill", ["qualification", "unassigned_reason"], engineers=[_engineer(skills=["mechanical"])]),
        _dispatch_fixture("missing-certificate", ["qualification", "unassigned_reason"], engineers=[_engineer(qualifications=[])]),
        _dispatch_fixture("qualified-absent", ["qualified_not_present"], engineers=[_engineer(available=False), _engineer("E2", skills=["mechanical"])]),
        _dispatch_fixture("all-busy", ["all_engineers_busy", "locked_tasks"], locked_tasks=[_lock()]),
        _dispatch_fixture("temporary-leave", ["temporary_leave"], engineers=[_engineer(leave_windows=[[0, 20]])]),
        _dispatch_fixture("late-shift", ["shift_windows"], engineers=[_engineer(shift_windows=[[15, 30]], available_from_minute=15)]),
        _dispatch_fixture("short-shift", ["shift_windows", "infeasible_duration"], engineers=[_engineer(shift_windows=[[0, 5]])]),
        _dispatch_fixture("engineer-no-overlap", ["no_overlap"], tasks=[_task(), _task("T2")]),
        _dispatch_fixture("equipment-conflict", ["same_equipment_conflict", "severity"], tasks=[_task(deadline_minute=10, severity=3), _task("T2", deadline_minute=10)], engineers=[_engineer(), _engineer("E2")]),
        _dispatch_fixture("tool-unavailable", ["tool_availability"], tools=[{"tool_id": "meter", "capacity": 1, "available_windows": []}]),
        _dispatch_fixture("two-tools-required", ["multiple_tools"], tasks=[_task(tools=["meter", "tester"])], tools=[{"tool_id": "meter", "capacity": 1, "available_windows": [[0, 30]]}, {"tool_id": "tester", "capacity": 1, "available_windows": [[10, 30]]}]),
        _dispatch_fixture("travel-order", ["travel_times"], tasks=[_task(location="B", deadline_minute=30), _task("T2", deadline_minute=10)]),
        _dispatch_fixture("travel-impossible", ["travel_times", "unreachable_location"], tasks=[_task(location="B")], travel_minutes={"A": {"A": 0, "B": None}, "B": {"A": None, "B": 0}}),
        _dispatch_fixture("initial-travel", ["initial_location", "travel_times"], tasks=[_task(location="B", deadline_minute=15)]),
        _dispatch_fixture("precedence", ["precedence"], tasks=[_task(), _task("T2", predecessors=["T1"])]),
        _dispatch_fixture("missing-predecessor", ["precedence", "predecessor_unassigned"], tasks=[_task(predecessors=["MISSING"])]),
        _dispatch_fixture("cyclic-precedence", ["precedence", "cycle"], tasks=[_task(predecessors=["T2"]), _task("T2", predecessors=["T1"])]),
        _dispatch_fixture("started-task-locked", ["started_task_not_reassigned", "locked_tasks"], tasks=[_task("LOCK1", duration_minutes=15), _task("T2")], engineers=[_engineer(), _engineer("E2")], locked_tasks=[_lock(end=15)]),
        _dispatch_fixture("locked-tool", ["locked_tasks", "same_equipment_conflict"], engineers=[_engineer(), _engineer("E2")], locked_tasks=[_lock(tools=["meter"])]),
        _dispatch_fixture("load-limit", ["workload_limit"], tasks=[_task(), _task("T2")], engineers=[_engineer(max_work_minutes=10)]),
        _dispatch_fixture("critical-priority", ["lexicographic_severity"], tasks=[_task(severity=1, deadline_minute=10), _task("T2", severity=3, deadline_minute=10)]),
        _dispatch_fixture("high-priority", ["lexicographic_severity"], tasks=[_task(severity=1, deadline_minute=15), _task("T2", severity=2, deadline_minute=15)]),
        _dispatch_fixture("hard-deadline", ["deadline", "infeasible_deadline"], tasks=[_task(duration_minutes=15, deadline_minute=10)]),
        _dispatch_fixture("soft-deadline", ["deadline", "lateness"], tasks=[_task(duration_minutes=15, deadline_minute=10, hard_deadline=False)]),
        _dispatch_fixture("split-shift", ["shift_windows", "no_spanning_shift_gap"], tasks=[_task(duration_minutes=15)], engineers=[_engineer(shift_windows=[[0, 10], [20, 30]])]),
        _dispatch_fixture("deadline-boundary", ["deadline", "inclusive_end_boundary"], tasks=[_task(deadline_minute=10)]),
        _dispatch_fixture("pending-approval", ["human_approval_boundary"], tasks=[_task(approval={"status": "PENDING_APPROVAL", "version": 1, "current_version": 1})]),
        _dispatch_fixture("rejected-approval", ["human_approval_boundary"], tasks=[_task(approval={"status": "REJECTED", "version": 1, "current_version": 1})]),
        _dispatch_fixture("stale-approval", ["approval_version", "stale_input"], tasks=[_task(approval={"status": "APPROVED", "version": 1, "current_version": 2})]),
        _dispatch_fixture("stale-snapshot", ["stale_input", "optimistic_concurrency"], current_snapshot_version=2),
        _dispatch_fixture("duplicate-confirmation", ["duplicate_approval", "idempotency"], tasks=[_task(), _task()]),
        _dispatch_fixture("group-work-order", ["group_order_over_duplicate_individuals", "human_approval_boundary"], tasks=[_task("GROUP", asset_ids=["demo-a", "demo-b"], duration_minutes=15), _task("SINGLE_A", asset_ids=["demo-a"], approval={"status": "SUPERSEDED", "version": 1, "current_version": 1}), _task("SINGLE_B", asset_ids=["demo-b"], approval={"status": "SUPERSEDED", "version": 1, "current_version": 1})]),
        _dispatch_fixture("invalid-mapping", ["asset_mapping_error"], tasks=[_task(asset_mapping_valid=False)]),
        _dispatch_fixture("stale-installation", ["asset_mapping_error", "installation_identity"], tasks=[_task(installation_id="demo-new", observed_installation_id="demo-old")]),
        _dispatch_fixture("partial-leave-route", ["temporary_leave", "travel_times"], tasks=[_task(location="B")], engineers=[_engineer(leave_windows=[[10, 20]]), _engineer("E2", initial_location="B")]),
        _dispatch_fixture("late-tool-window", ["tool_availability", "deadline"], tools=[{"tool_id": "meter", "capacity": 1, "available_windows": [[20, 30]]}]),
        _dispatch_fixture("multiple-qualifications", ["qualification", "multiple_qualifications"], tasks=[_task(required_skills=["electrical", "instrumentation"], required_qualifications=["demo-inspection", "demo-calibration"])], engineers=[_engineer(), _engineer("E2", qualifications=["demo-inspection", "demo-calibration"])]),
        _dispatch_fixture("expired-event", ["stale_input", "event_expiry"], tasks=[_task(event_expires_at_minute=-1)]),
    ]
    assert len(rows) == 40
    return rows


def _carbon_fixture(name: str, kind: str, topics: list[str], inputs: dict) -> dict:
    return {"fixture_id": f"carbon-{name}", "schema_version": SCHEMA_VERSION, "synthetic": True,
            "origin": "physics_simulated", "data_scope": "demo_synthetic",
            "generated_by": "deterministic_fixture_oracle_v1", "source_refs": ["doc02-section-9"],
            "kind": kind, "coverage_tags": topics, "inputs": inputs,
            "oracle": evaluate_carbon(kind, inputs), "tolerance": TOLERANCE.copy()}


def carbon_fixtures() -> list[dict]:
    """Thirty examples including all twenty-four named doc02 topic groups."""
    case = _carbon_fixture
    service = {"delivered_kwh": 1000., "baseline_efficiency": .9, "candidate_efficiency": .8,
               "factor_kg_per_kwh": .5, "baseline_manufacturing_kg": 100., "candidate_manufacturing_kg": 0.}
    economics = {"avoided_kg": 1000., "shadow_price_rmb_per_t": 80., "operating_savings_rmb": 20.,
                 "test_qualification_established": False, "issued_t": 0., "contract_price_rmb_per_t": 100.}
    rows = [
        case("wh-to-kwh", "unit_conversion", ["unit_conversion", "Wh_kWh"], {"value": 1250., "from_unit": "Wh", "to_unit": "kWh"}),
        case("kg-to-tonne", "unit_conversion", ["unit_conversion", "kg_t"], {"value": 1250., "from_unit": "kg", "to_unit": "t"}),
        case("manufacturing-per-pack", "manufacturing", ["manufacturing_per_pack"], {"pack_count": 2, "factor": 100., "factor_unit": "kgCO2e/pack"}),
        case("manufacturing-per-capacity", "manufacturing", ["manufacturing_per_capacity"], {"pack_count": 2, "capacity_kwh_per_pack": 50., "factor": 2., "factor_unit": "kgCO2e/kWh_capacity"}),
        case("missing-factor-source", "factor_validation", ["missing_source"], {"source_ref": None}),
        case("annual-co2-versus-lifecycle-co2e", "factor_validation", ["incompatible_gas_boundary"], {"source_ref": "DEMO_FACTOR_001", "baseline_gas_basis": "CO2", "candidate_gas_basis": "CO2e", "baseline_factor_boundary": "annual_generation", "candidate_factor_boundary": "lifecycle"}),
        case("simple-electricity", "electricity", ["simple_electricity", "no_ml_required"], {"energy_kwh": 100., "factor_kg_per_kwh": .5}),
        case("auxiliary-counted-once", "auxiliary", ["auxiliary_double_count"], {"delivered_kwh": 100., "efficiency": .8, "aux_kwh": 10., "aux_in_efficiency_boundary": True, "factor_kg_per_kwh": .5}),
        case("same-service-positive-benefit", "same_service", ["same_service_comparison"], service),
        case("inefficiency-offsets-manufacturing", "same_service", ["low_efficiency_offsets_benefit", "negative_benefit"], {**service, "baseline_manufacturing_kg": 20.}),
        case("delay-not-permanent-avoidance", "delay", ["delay_not_permanent_avoidance"], {"horizon_years": 5, "baseline_replacements": 1, "candidate_replacements": 0, "manufacturing_kg_per_pack": 100.}),
        case("right-censored-life", "censored_lifetime", ["right_censored_lifetime"], {"last_observed_cycle": 1000, "eol_observed": False}),
        case("zero-replacements", "renewal", ["zero_replacements"], {"remaining_pmf": {"5": 1.}, "new_lifetime_pmf": {"4": 1.}, "horizon": 4}),
        case("one-replacement", "renewal", ["one_replacement"], {"remaining_pmf": {"2": 1.}, "new_lifetime_pmf": {"5": 1.}, "horizon": 4}),
        case("multiple-replacements", "renewal", ["multiple_replacements"], {"remaining_pmf": {"2": 1.}, "new_lifetime_pmf": {"2": 1.}, "horizon": 6}),
        case("replacement-state-reset", "replacement_reset", ["replacement_reset", "state_probability"], {"states": ["old_age_4", "new_age_0"], "initial_distribution": [1., 0.], "transition_matrix": [[0., 1.], [0., 1.]], "replacement_probability_by_state": [1., 0.], "state_age": [4, 0]}),
        case("terminal-state-mismatch", "terminal_state", ["different_terminal_states"], {"baseline_terminal": "new_age_0", "candidate_terminal": "old_age_5", "terminal_treatment": None}),
        *[case(f"gamma-{str(gamma).replace('.', '-')}", "robust_range", [topic], {"nominal": 100., "coefficients": [20., 10.], "gamma": gamma})
          for gamma, topic in [(0., "gamma_zero"), (1., "gamma_one"), (1.5, "gamma_fractional"), (2., "gamma_full_dimension")]],
        case("shared-error-cancels", "robust_difference", ["shared_error_cancellation"], {"baseline_nominal": 200., "candidate_nominal": 100., "baseline_coefficients": {"grid_factor": 20., "meter": 10.}, "candidate_coefficients": {"grid_factor": 20., "meter": 10.}, "gamma": 2.}),
        case("negative-robust-lower-benefit", "robust_difference", ["negative_lower_benefit"], {"baseline_nominal": 105., "candidate_nominal": 100., "baseline_coefficients": {"grid_factor": 20.}, "candidate_coefficients": {"grid_factor": 0.}, "gamma": 1.}),
        case("pareto-dominance", "pareto", ["pareto_dominance"], {"candidates": [{"candidate_id": "A", "cost": 10., "carbon": 10.}, {"candidate_id": "B", "cost": 15., "carbon": 15.}, {"candidate_id": "C", "cost": 20., "carbon": 5.}, {"candidate_id": "D", "cost": 0., "carbon": 0., "feasible": False}]}),
        case("pareto-ties", "pareto", ["pareto_ties"], {"candidates": [{"candidate_id": "A", "cost": 10., "carbon": 10.}, {"candidate_id": "B", "cost": 10., "carbon": 10.}]}),
        case("shadow-value-no-cash", "economic_split", ["shadow_value_without_cash_eligibility"], economics),
        case("qualified-demo-income-split", "economic_split", ["qualified_test_benefit_split"], {**economics, "test_qualification_established": True, "issued_t": .8, "rule_id": "TEST_RULE_001"}),
        case("correction-and-demo-export", "ledger_export", ["correction_reversal", "demo_export"], {"entries": [{"entry_id": "DEMO_ENTRY_1", "emission_kg": 40., "data_scope": "demo_synthetic", "basis": "settled"}, {"entry_id": "DEMO_CORRECTION_1", "reversal_of": "DEMO_ENTRY_1", "emission_kg": -10., "data_scope": "demo_synthetic", "basis": "settled"}]}),
        case("nonlinear-efficiency-expectation", "nonlinear_efficiency", ["nonlinear_efficiency", "approximation_tolerance"], {"delivered_kwh": 100., "state_probabilities": [.5, .5], "efficiencies": [.5, .9]}),
        case("stopped-state-unmet-service", "unavailable_service", ["unavailable_state", "same_service_comparison"], {"delivered_kwh": 100., "state_probabilities": [.8, .2], "efficiencies": [.8, None]}),
    ]
    assert len(rows) == 30
    return rows


DISPATCH_REQUIRED_TOPICS = {"qualification", "shift_windows", "duration", "deadline", "precedence", "locked_tasks",
                            "travel_times", "tool_availability", "all_engineers_busy", "qualified_not_present",
                            "same_equipment_conflict", "group_order_over_duplicate_individuals", "temporary_leave",
                            "started_task_not_reassigned", "duplicate_approval", "stale_input", "human_approval_boundary",
                            "asset_mapping_error"}
CARBON_REQUIRED_TOPICS = {"unit_conversion", "Wh_kWh", "kg_t", "manufacturing_per_pack", "manufacturing_per_capacity",
                          "missing_source", "incompatible_gas_boundary", "simple_electricity", "auxiliary_double_count",
                          "same_service_comparison", "low_efficiency_offsets_benefit", "delay_not_permanent_avoidance",
                          "right_censored_lifetime", "zero_replacements", "one_replacement", "multiple_replacements",
                          "replacement_reset", "different_terminal_states", "gamma_zero", "gamma_one", "gamma_fractional",
                          "gamma_full_dimension", "shared_error_cancellation", "negative_lower_benefit", "pareto_dominance",
                          "pareto_ties", "shadow_value_without_cash_eligibility", "qualified_test_benefit_split",
                          "correction_reversal", "demo_export"}


def validate_fixture(fixture: dict) -> list[str]:
    errors: list[str] = []
    if fixture.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_fixture_schema")
    if fixture.get("synthetic") is not True or fixture.get("data_scope") != "demo_synthetic":
        errors.append("missing_synthetic_demo_provenance")
    if fixture.get("generated_by") != "deterministic_fixture_oracle_v1":
        errors.append("oracle_must_not_be_llm_generated")
    try:
        if fixture["kind"] == "dispatch":
            # Dispatch inputs are forbidden from silently becoming Carbon objectives.
            if any(word in json.dumps(fixture["inputs"]).lower() for word in ("carbon", "co2", "emission")):
                errors.append("carbon_in_dispatch_fixture")
            computed = solve_dispatch(fixture["inputs"])
            errors.extend(validate_dispatch_solution(fixture["inputs"], fixture["oracle"]["assignments"]))
        else:
            computed = evaluate_carbon(fixture["kind"], fixture["inputs"])
            if not fixture["fixture_id"].startswith("carbon-"):
                errors.append("invalid_carbon_namespace")
        tolerance = fixture.get("tolerance", TOLERANCE)
        errors.extend(compare_expected(computed, fixture["oracle"], atol=tolerance["absolute"], rtol=tolerance["relative"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError) as exc:
        errors.append(f"invalid_fixture:{exc}")
    return errors


def validate_fixtures(content_root: Path) -> dict:
    report: dict[str, Any] = {"valid": True, "dispatch_count": 0, "carbon_count": 0, "errors": [], "coverage": {}}
    ids: set[str] = set()
    for domain, minimum, required in (("dispatch", 40, DISPATCH_REQUIRED_TOPICS), ("carbon", 24, CARBON_REQUIRED_TOPICS)):
        path = Path(content_root) / "fixtures" / f"{domain}.jsonl"
        topics: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            report["errors"].append(f"{path.name}:{exc}")
            continue
        for index, line in enumerate(lines, 1):
            try:
                fixture = json.loads(line)
                fid = fixture["fixture_id"]
                if fid in ids:
                    report["errors"].append(f"duplicate_fixture_id:{fid}")
                ids.add(fid)
                topics.update(fixture["coverage_tags"])
                report["errors"].extend(f"{fid}:{error}" for error in validate_fixture(fixture))
            except (ValueError, TypeError, KeyError) as exc:
                report["errors"].append(f"{path.name}:{index}:{exc}")
        report[f"{domain}_count"] = len(lines)
        report["coverage"][domain] = sorted(topics)
        if len(lines) < minimum:
            report["errors"].append(f"insufficient_{domain}_fixtures:{len(lines)}<{minimum}")
        report["errors"].extend(f"missing_{domain}_coverage:{topic}" for topic in sorted(required - topics))
    report["valid"] = not report["errors"]
    return report


def generate_fixtures(output: Path) -> dict:
    """Write fixtures below a content root and return counts and coverage."""
    directory = Path(output) / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    rows = {"dispatch": dispatch_fixtures(), "carbon": carbon_fixtures()}
    for domain, fixtures in rows.items():
        serialized = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) for row in fixtures) + "\n"
        (directory / f"{domain}.jsonl").write_text(serialized, encoding="utf-8")
    return {"dispatch_count": len(rows["dispatch"]), "carbon_count": len(rows["carbon"]),
            "coverage": {domain: sorted({tag for row in fixtures for tag in row["coverage_tags"]}) for domain, fixtures in rows.items()}}
