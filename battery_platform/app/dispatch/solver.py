"""Bounded integer-minute CP-SAT scheduling with strict lexicographic objectives.

No LLM, carbon estimate, distance guess or qualification override enters here.
All times are offsets from the API's immutable, timezone-aware horizon start.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Callable

from ortools.sat.python import cp_model

OBJECTIVE_NAMES = (
    "critical_unassigned", "critical_lateness", "high_unassigned",
    "high_lateness", "routine_unassigned", "routine_lateness",
    "travel_minutes", "workload_spread_minutes",
)


def travel(data, origin, destination):
    if origin == destination:
        return 0
    return data.get("travel_minutes", {}).get(f"{origin}|{destination}")


def _qualified(task, engineer):
    if not task.get("locked") and not engineer.get("can_accept_new", True):
        return False
    return set(task.get("qualifications", [])) <= set(engineer.get("qualifications", []))


def validate_assignments(data, assignments):
    """Independent concrete schedule check, also used for human draft edits.

    Return all constraint violations. Missing assignments are allowed except
    immutable reservations; predecessors must be assigned or pre-completed.
    """
    errors = []
    tasks = {t["id"]: t for t in data["tasks"]}
    engineers = {e["id"]: e for e in data["engineers"]}
    assigned = {}
    by_engineer = defaultdict(list)
    for a in assignments:
        identifier = a["order_id"]
        if identifier in assigned:
            errors.append(f"duplicate_assignment:{identifier}")
            continue
        t, e = tasks.get(identifier), engineers.get(a["engineer_id"])
        if not t or not e:
            errors.append(f"unknown_order_or_engineer:{identifier}")
            continue
        assigned[identifier] = a
        start, end = a["start"], a["end"]
        if not isinstance(start, int) or not isinstance(end, int) or end - start != t["duration"]:
            errors.append(f"duration_mismatch:{identifier}")
        if start < max(0, t.get("release", 0)) or end > data["horizon_minutes"] or start % data.get("time_quantum_minutes", 1):
            errors.append(f"outside_horizon_or_release:{identifier}")
        if t.get("hard_deadline", False) and end > t.get("due", data["horizon_minutes"]):
            errors.append(f"hard_deadline_missed:{identifier}")
        if not _qualified(t, e):
            errors.append(f"qualification_missing:{identifier}")
        if not any(start >= s and end <= f for s, f in e.get("shifts", [])):
            errors.append(f"outside_shift:{identifier}")
        if t.get("locked") and (a["engineer_id"] != t["locked"]["engineer_id"] or start != t["locked"]["start"]):
            errors.append(f"locked_assignment_changed:{identifier}")
        by_engineer[e["id"]].append(a)
    for identifier, t in tasks.items():
        if t.get("locked") and identifier not in assigned:
            errors.append(f"locked_assignment_removed:{identifier}")
        if identifier in assigned:
            for pred in t.get("predecessors", []):
                if pred in data.get("completed_predecessors", []):
                    continue
                if pred not in assigned:
                    errors.append(f"predecessor_unassigned:{identifier}:{pred}")
                elif assigned[pred]["end"] > assigned[identifier]["start"]:
                    errors.append(f"predecessor_not_finished:{identifier}:{pred}")
    for eid, schedule in by_engineer.items():
        e = engineers[eid]
        schedule.sort(key=lambda a: (a["start"], a["order_id"]))
        location, ready = e.get("home_location", ""), e.get("available_from", 0)
        travel_total = 0
        for a in schedule:
            destination = tasks[a["order_id"]].get("location", "")
            minutes = travel(data, location, destination)
            if minutes is None:
                errors.append(f"travel_route_missing:{eid}:{location}:{destination}")
                minutes = 0
            if a["start"] < ready + minutes:
                errors.append(f"overlap_or_travel_conflict:{eid}:{a['order_id']}")
            travel_total += minutes
            location, ready = destination, a["end"]
        if len(schedule) + e.get("existing_load", 0) > e.get("max_tasks", 999):
            errors.append(f"task_limit_exceeded:{eid}")
        minutes = sum(a["end"] - a["start"] for a in schedule) + travel_total + e.get("existing_minutes", 0)
        if minutes > e.get("max_minutes", data["horizon_minutes"]):
            errors.append(f"work_minutes_exceeded:{eid}")
    tools = set(data.get("tool_capacities", {})) | {k for t in tasks.values() for k in t.get("tools", {})} | {k for r in data.get("tool_reservations", []) for k in r.get("tools", {})}
    for tool in tools:
        points = []
        for reservation in data.get("tool_reservations", []):
            demand = reservation.get("tools", {}).get(tool, 0)
            if demand:
                points += [(reservation["start"], demand), (reservation["end"], -demand)]
        for identifier, a in assigned.items():
            demand = tasks[identifier].get("tools", {}).get(tool, 0)
            if demand:
                if tool in data.get("tool_windows", {}) and not any(a["start"] >= s and a["end"] <= f for s, f in data["tool_windows"][tool]):
                    errors.append(f"tool_outside_availability:{tool}:{identifier}")
                points += [(a["start"], demand), (a["end"], -demand)]
        load = 0
        for minute, change in sorted(points, key=lambda x: (x[0], x[1])):
            load += change
            if load > data.get("tool_capacities", {}).get(tool, 0):
                errors.append(f"tool_capacity_exceeded:{tool}:{minute}")
                break
    return errors


def evaluate_objectives(data, assignments):
    """Recompute the published objective tuple from the concrete schedule."""
    amap = {a["order_id"]: a for a in assignments}
    output = []
    for severity in ("critical", "high", "routine"):
        group = [t for t in data["tasks"] if t.get("severity", "routine") == severity and not t.get("locked")]
        output.extend([
            sum(t["id"] not in amap for t in group),
            sum(max(0, amap[t["id"]]["end"] - t.get("due", data["horizon_minutes"])) for t in group if t["id"] in amap),
        ])
    total_travel = 0
    loads = []
    for e in data["engineers"]:
        itinerary = sorted((a for a in assignments if a["engineer_id"] == e["id"]), key=lambda a: (a["start"], a["order_id"]))
        location = e.get("home_location", "")
        em = e.get("existing_minutes", 0)
        for a in itinerary:
            destination = next(t.get("location", "") for t in data["tasks"] if t["id"] == a["order_id"])
            distance = travel(data, location, destination) or 0
            total_travel += distance
            em += a["end"] - a["start"] + distance
            location = destination
        loads.append(em)
    return output + [total_travel, max(loads, default=0) - min(loads, default=0)]


def _unassigned_reasons(data, task):
    skilled = [e for e in data["engineers"] if set(task.get("qualifications", [])) <= set(e.get("qualifications", []))]
    if not skilled:
        return ["qualification_missing"]
    qualified = [e for e in skilled if e.get("can_accept_new", True)]
    if not qualified:
        return ["qualified_engineer_unavailable"]
    if any(amount > data.get("tool_capacities", {}).get(tool, 0) for tool, amount in task.get("tools", {}).items()):
        return ["tool_capacity_missing"]
    if any(p not in {t["id"] for t in data["tasks"]} | set(data.get("completed_predecessors", [])) for p in task.get("predecessors", [])):
        return ["predecessor_unavailable"]
    if not any(f - max(s, task.get("release", 0)) >= task["duration"] for e in qualified for s, f in e.get("shifts", [])):
        return ["no_shift_fits_duration"]
    if all(e.get("existing_load", 0) >= e.get("max_tasks", 999) or e.get("existing_minutes", 0) + task["duration"] > e.get("max_minutes", data["horizon_minutes"]) for e in qualified):
        return ["workload_limit"]
    return ["resource_time_travel_or_dependency_conflict", "lexicographic_priority"]


def solve(data, time_limit_seconds=10.0, cancelled: Callable[[], bool] | None = None):
    started = time.monotonic()
    cancelled = cancelled or (lambda: False)
    model = cp_model.CpModel()
    horizon = data["horizon_minutes"]
    tasks = {t["id"]: t for t in data["tasks"]}
    engineers = {e["id"]: e for e in data["engineers"]}
    starts, ends, presence, variables, task_intervals = {}, {}, {}, {}, {}
    engineer_intervals = defaultdict(list)
    lateness = {}
    for tid, t in tasks.items():
        starts[tid] = model.new_int_var(0, horizon, f"start_{tid}")
        ends[tid] = model.new_int_var(0, horizon, f"end_{tid}")
        presence[tid] = model.new_bool_var(f"present_{tid}")
        model.add(ends[tid] == starts[tid] + t["duration"]).only_enforce_if(presence[tid])
        model.add(starts[tid] >= max(0, t.get("release", 0))).only_enforce_if(presence[tid])
        if data.get("time_quantum_minutes", 1) != 1:
            slot = model.new_int_var(0, horizon, f"slot_{tid}")
            model.add(starts[tid] == slot * data["time_quantum_minutes"])
        if t.get("hard_deadline", False):
            model.add(ends[tid] <= t.get("due", horizon)).only_enforce_if(presence[tid])
        model.add(starts[tid] == 0).only_enforce_if(presence[tid].Not())
        model.add(ends[tid] == 0).only_enforce_if(presence[tid].Not())
        task_intervals[tid] = model.new_optional_interval_var(starts[tid], t["duration"], ends[tid], presence[tid], f"tool_interval_{tid}")
        for tool in t.get("tools", {}):
            if tool in data.get("tool_windows", {}):
                windows = []
                for k, (s, f) in enumerate(data["tool_windows"][tool]):
                    window = model.new_bool_var(f"tool_window_{tid}_{tool}_{k}")
                    windows.append(window)
                    model.add(starts[tid] >= s).only_enforce_if(window)
                    model.add(ends[tid] <= f).only_enforce_if(window)
                model.add(sum(windows) == presence[tid])
        choices = []
        for eid, e in engineers.items():
            x = model.new_bool_var(f"assign_{tid}_{eid}")
            variables[tid, eid] = x
            choices.append(x)
            interval = model.new_optional_interval_var(starts[tid], t["duration"], ends[tid], x, f"engineer_interval_{tid}_{eid}")
            engineer_intervals[eid].append(interval)
            if not _qualified(t, e):
                model.add(x == 0)
            shift_choices = []
            for k, (s, f) in enumerate(e.get("shifts", [])):
                shift = model.new_bool_var(f"shift_{tid}_{eid}_{k}")
                shift_choices.append(shift)
                model.add(starts[tid] >= s).only_enforce_if(shift)
                model.add(ends[tid] <= f).only_enforce_if(shift)
            model.add(sum(shift_choices) == x)
        model.add(sum(choices) == presence[tid])
        if t.get("locked"):
            locked = t["locked"]
            model.add(presence[tid] == 1)
            if locked["engineer_id"] not in engineers:
                model.add(0 == 1)
            else:
                model.add(variables[tid, locked["engineer_id"]] == 1)
            model.add(starts[tid] == locked["start"])
        late = model.new_int_var(0, horizon + abs(min(0, t.get("due", horizon))), f"late_{tid}")
        model.add(late >= ends[tid] - t.get("due", horizon)).only_enforce_if(presence[tid])
        model.add(late == 0).only_enforce_if(presence[tid].Not())
        lateness[tid] = late
    for tid, t in tasks.items():
        for pred in t.get("predecessors", []):
            if pred in data.get("completed_predecessors", []):
                continue
            if pred not in tasks:
                model.add(presence[tid] == 0)
            else:
                model.add(presence[tid] <= presence[pred])
                model.add(starts[tid] >= ends[pred]).only_enforce_if(presence[tid])
    for tool in set(data.get("tool_capacities", {})) | {k for t in tasks.values() for k in t.get("tools", {})} | {k for r in data.get("tool_reservations", []) for k in r.get("tools", {})}:
        uses = [tid for tid, t in tasks.items() if t.get("tools", {}).get(tool, 0)]
        if uses or any(r.get("tools", {}).get(tool, 0) for r in data.get("tool_reservations", [])):
            intervals = [task_intervals[i] for i in uses]
            demands = [tasks[i]["tools"][tool] for i in uses]
            for k, reservation in enumerate(data.get("tool_reservations", [])):
                demand = reservation.get("tools", {}).get(tool, 0)
                if demand:
                    intervals.append(model.new_fixed_size_interval_var(reservation["start"], reservation["end"] - reservation["start"], f"existing_tool_{tool}_{k}"))
                    demands.append(demand)
            model.add_cumulative(intervals, demands, data.get("tool_capacities", {}).get(tool, 0))
    travel_terms, loads = [], []
    for eid, e in engineers.items():
        model.add_no_overlap(engineer_intervals[eid])
        model.add(sum(variables[t, eid] for t in tasks) + e.get("existing_load", 0) <= e.get("max_tasks", 999))
        # Circuit is one depot-rooted route. Self loops represent unassigned
        # jobs; each active arc carries only its actual immediate transition.
        ids = list(tasks)
        arcs = []
        empty = model.new_bool_var(f"empty_route_{eid}")
        model.add(sum(variables[t, eid] for t in tasks) == 0).only_enforce_if(empty)
        model.add(sum(variables[t, eid] for t in tasks) >= 1).only_enforce_if(empty.Not())
        arcs.append((0, 0, empty))
        etravel = []
        for i, tid in enumerate(ids, 1):
            arcs.append((i, i, variables[tid, eid].Not()))
            origin = model.new_bool_var(f"depot_{eid}_{tid}")
            end = model.new_bool_var(f"return_{eid}_{tid}")
            arcs += [(0, i, origin), (i, 0, end)]
            minutes = travel(data, e.get("home_location", ""), tasks[tid].get("location", ""))
            if minutes is None:
                model.add(origin == 0)
            else:
                model.add(starts[tid] >= e.get("available_from", 0) + minutes).only_enforce_if(origin)
                etravel.append(minutes * origin)
            for j, other in enumerate(ids, 1):
                if tid == other:
                    continue
                arc = model.new_bool_var(f"route_{eid}_{tid}_{other}")
                arcs.append((i, j, arc))
                minutes = travel(data, tasks[tid].get("location", ""), tasks[other].get("location", ""))
                if minutes is None:
                    model.add(arc == 0)
                else:
                    model.add(starts[other] >= ends[tid] + minutes).only_enforce_if(arc)
                    etravel.append(minutes * arc)
        model.add_circuit(arcs)
        travel_terms.extend(etravel)
        load = model.new_int_var(0, max(horizon, e.get("existing_minutes", 0)), f"load_{eid}")
        model.add(load == sum(tasks[t]["duration"] * variables[t, eid] for t in tasks) + sum(etravel) + e.get("existing_minutes", 0))
        model.add(load <= e.get("max_minutes", horizon))
        loads.append(load)
    objectives = []
    for severity in ("critical", "high", "routine"):
        group = [tid for tid, t in tasks.items() if t.get("severity", "routine") == severity and not t.get("locked")]
        objectives += [sum(1 - presence[t] for t in group), sum(lateness[t] for t in group)]
    objectives.append(sum(travel_terms))
    if loads:
        max_load = model.new_int_var(0, max(horizon, *(e.get("existing_minutes", 0) for e in engineers.values())), "max_load")
        min_load = model.new_int_var(0, horizon, "min_load")
        model.add_max_equality(max_load, loads)
        model.add_min_equality(min_load, loads)
        objectives.append(max_load - min_load)
    else:
        objectives.append(0)
    best = None
    stages = []
    final_status = "timeout"
    # Final tie-break gives useful earliest-start drafts, never overriding any
    # published priority. Every prior proven optimum is fixed as an equality.
    for index, objective in enumerate(objectives + [sum(starts.values())]):
        remaining = time_limit_seconds - (time.monotonic() - started)
        if remaining <= 0 or cancelled():
            break
        model.minimize(objective)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        done = threading.Event()
        def stop_when_cancelled():
            while not done.wait(0.1):
                if cancelled():
                    solver.stop_search()
                    break
        monitor = threading.Thread(target=stop_when_cancelled, daemon=True)
        monitor.start()
        try:
            status = solver.solve(model)
        finally:
            done.set()
            monitor.join(timeout=0.3)
        if status == cp_model.MODEL_INVALID:
            raise ValueError("Invalid scheduling model: " + solver.response_stats())
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best = [
                {"order_id": tid, "engineer_id": eid, "start": solver.value(starts[tid]), "end": solver.value(ends[tid]), "locked": bool(tasks[tid].get("locked"))}
                for (tid, eid), x in variables.items() if solver.value(x)
            ]
            value = round(solver.objective_value)
            if index < len(OBJECTIVE_NAMES):
                stages.append({"objective": OBJECTIVE_NAMES[index], "value": value, "proven_optimal": status == cp_model.OPTIMAL})
            final_status = "optimal" if status == cp_model.OPTIMAL else "feasible"
            if status != cp_model.OPTIMAL:
                break
            model.add(objective == value)
        elif status == cp_model.INFEASIBLE:
            final_status = "infeasible" if best is None else "feasible"
            break
        else:
            final_status = "feasible" if best is not None else "timeout"
            break
    complete = len(stages) == len(OBJECTIVE_NAMES) and all(s["proven_optimal"] for s in stages)
    if best is not None and not complete:
        final_status = "feasible"
    best = best or []
    violations = validate_assignments(data, best) if final_status in ("optimal", "feasible") else []
    if violations:
        raise RuntimeError("Solver produced invalid assignments: " + ",".join(violations))
    assigned = {a["order_id"] for a in best}
    return {
        "status": final_status, "assignments": sorted(best, key=lambda a: (a["start"], a["order_id"])),
        "unassigned": [{"order_id": tid, "reasons": ["locked_schedule_infeasible"] if t.get("locked") else _unassigned_reasons(data, t)} for tid, t in tasks.items() if tid not in assigned],
        "objectives": dict(zip(OBJECTIVE_NAMES, evaluate_objectives(data, best))) if final_status in ("optimal", "feasible") else None,
        "lexicographic_complete": complete, "stages": stages,
        "elapsed_seconds": round(time.monotonic() - started, 4), "cancelled": bool(cancelled()),
        "time_unit": "minute", "travel_includes_return_home": False,
    }
