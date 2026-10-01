"""Context-only incremental memory, immutable snapshots, CAS and rollback.

Database adapters may persist snapshots themselves. This optional file store
uses a short process lock and atomic rename; no lock is held across LLM calls.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import EDITABLE_SKILL_FIELDS, TOOL_WHITELIST, parse_time
from .feedback import extract_feedback


class ContextConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot(version: int, memories: list[dict[str, Any]], skills: dict[str, Any], *,
              parent: str | None, changes: list[dict[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256(json.dumps({"version": version, "memories": memories, "skills": skills},
                                      sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return {"context_snapshot_id": f"context-{version}-{digest}", "context_version": f"context_v{version}",
            "version": version, "memories": memories, "skills": skills, "created_at": now(),
            "changes": changes, "parent_snapshot_id": parent}


class ContextStore:
    def __init__(self, path: str | Path | None = None, *, initial_snapshot: dict[str, Any] | None = None):
        self.path = Path(path).resolve() if path is not None else None
        self._lock = threading.RLock()
        initial = copy.deepcopy(initial_snapshot) if initial_snapshot else _snapshot(0, [], {}, parent=None, changes=[])
        if not isinstance(initial.get("version"), int) or initial["version"] < 0 or not isinstance(initial.get("memories"), list):
            raise ValueError("invalid initial context snapshot")
        if any(m.get("source_scope", "operational") not in {"operational", "cold_start", "evolution"} for m in initial["memories"]):
            raise ValueError("evaluation labels cannot initialize runtime context")
        if any(not set(fields) <= EDITABLE_SKILL_FIELDS for fields in initial.get("skills", {}).values()):
            raise ValueError("initial context Skill overlay contains immutable fields")
        self._state = {"active": initial["context_snapshot_id"], "previous": None,
                       "snapshots": {initial["context_snapshot_id"]: initial}, "audit": []}
        with self._transaction():
            if self.path and not self.path.exists():
                self._save()

    @contextmanager
    def _transaction(self):
        with self._lock:
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with (self.path.with_suffix(self.path.suffix + ".lock")).open("a") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    try:
                        if self.path.exists():
                            self._state = json.loads(self.path.read_text(encoding="utf-8"))
                        yield
                    finally:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            else:
                yield

    def _save(self):
        if self.path:
            temp = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.tmp")
            temp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            os.replace(temp, self.path)

    def snapshot(self, snapshot_id: str | None = None) -> dict[str, Any]:
        with self._transaction():
            sid = snapshot_id or self._state["active"]
            if sid not in self._state["snapshots"]:
                raise ValueError("unknown context snapshot")
            return copy.deepcopy(self._state["snapshots"][sid])

    def audit(self) -> list[dict[str, Any]]:
        with self._transaction():
            return copy.deepcopy(self._state["audit"])

    def apply(self, updates: list[dict[str, Any]], *, expected_version: int,
              source_scope: str = "operational", regression: dict[str, Any] | None = None) -> dict[str, Any]:
        if source_scope not in {"operational", "cold_start", "evolution"}:
            raise ValueError("dev/selection/sealed labels may not enter runtime context")
        with self._transaction():
            old = self._state["snapshots"][self._state["active"]]
            if old["version"] != expected_version:
                raise ContextConflict("context changed; compare-and-swap activation rejected")
            memories, skills = copy.deepcopy(old["memories"]), copy.deepcopy(old["skills"])
            reason = None
            try:
                memory_by_id = {m["memory_id"]: m for m in memories}
                for update in updates:
                    operation = update.get("operation")
                    if operation == "NO_UPDATE":
                        continue
                    if operation == "SKILL_REVISE":
                        delta = update.get("fields", {})
                        if not delta or not set(delta) <= EDITABLE_SKILL_FIELDS:
                            raise ValueError("Skill candidate attempts to modify immutable fields")
                        if not regression or not regression.get("passed") or regression.get("hard_failures"):
                            raise ValueError("Skill candidate did not pass independent dev regression")
                        if regression.get("split") not in ("dev", "selection"):
                            raise ValueError("Skill candidate selection may only use dev/selection")
                        skills.setdefault(update["skill_id"], {}).update(delta)
                        continue
                    if operation not in {"ADD", "REVISE", "DEPRECATE", "CONFLICT"}:
                        raise ValueError("unknown ACE update operation")
                    item = copy.deepcopy(update.get("item", {}))
                    mid = update.get("memory_id", item.get("memory_id"))
                    if not mid:
                        raise ValueError("memory_id is required")
                    if operation == "ADD":
                        if mid in memory_by_id:
                            raise ValueError("duplicate memory; use a local revision")
                        if not item.get("insight") or not item.get("supporting_case_ids"):
                            raise ValueError("memory needs an insight and actual supporting case IDs")
                        if item.get("source_scope", source_scope) not in {"operational", "cold_start", "evolution"}:
                            raise ValueError("evaluation labels are not runtime memory")
                        if not set(item.get("allowed_tools", [])) <= TOOL_WHITELIST:
                            raise ValueError("memory cannot widen tool permissions")
                        trust = item.get("source_trust", "reported")
                        if trust not in {"reported", "measurement_supported", "independently_verified", "contradicted"}:
                            raise ValueError("invalid memory trust")
                        record = {"memory_id": mid, "version": 1, "scope": item.get("scope", {}),
                                  "trigger": item.get("trigger", ""), "insight": item["insight"],
                                  "supporting_case_ids": item["supporting_case_ids"],
                                  "counterexamples": item.get("counterexamples", []), "source_trust": trust,
                                  "helpful_count": 0, "harmful_count": 0, "last_used": None,
                                  "expires_at": item.get("expires_at"), "state": "active", "source_scope": source_scope,
                                  "raw_feedback_id": item.get("raw_feedback_id"),
                                  "available_at": item.get("available_at", now()), "origin": item.get("origin", "declared_operational")}
                        memory_by_id[mid] = record
                    else:
                        if mid not in memory_by_id:
                            raise ValueError("cannot revise absent memory")
                        record = memory_by_id[mid]
                        record["version"] += 1
                        if operation == "REVISE":
                            if not set(item) <= {"insight", "trigger", "scope", "source_trust", "counterexamples", "supporting_case_ids", "expires_at", "helpful_count", "harmful_count"}:
                                raise ValueError("revision contains immutable or permission fields")
                            if item.get("source_trust", record["source_trust"]) not in {"reported", "measurement_supported", "independently_verified", "contradicted"}:
                                raise ValueError("invalid revised memory trust")
                            record.update(item)
                        elif operation == "DEPRECATE":
                            record.update(state="deprecated", deprecation_reason=update.get("reason", "superseded"))
                        else:
                            record["state"] = "conflicted"
                            record.setdefault("conflicts", []).append({"insight": item.get("insight", ""),
                                                                       "source_trust": item.get("source_trust", "reported"),
                                                                       "supporting_case_ids": item.get("supporting_case_ids", [])})
                memories = list(memory_by_id.values())
            except (ValueError, KeyError, TypeError) as exc:
                reason = str(exc)
            changed = memories != old["memories"] or skills != old["skills"]
            event = {"created_at": now(), "updates": copy.deepcopy(updates), "source_scope": source_scope,
                     "parent_snapshot_id": old["context_snapshot_id"], "regression": regression}
            if reason:
                event.update(state="quarantined", reason=reason)
                self._state["audit"].append(event)
                self._save()
                return {"state": "quarantined", "reason": reason, "snapshot": copy.deepcopy(old)}
            if not changed:
                event.update(state="no_update", reason="No local validated change")
                self._state["audit"].append(event)
                self._save()
                return {"state": "no_update", "snapshot": copy.deepcopy(old)}
            latest = max(s["version"] for s in self._state["snapshots"].values())
            new = _snapshot(latest + 1, memories, skills, parent=old["context_snapshot_id"], changes=updates)
            self._state["previous"], self._state["active"] = self._state["active"], new["context_snapshot_id"]
            self._state["snapshots"][new["context_snapshot_id"]] = new
            event.update(state="active", context_snapshot_id=new["context_snapshot_id"])
            self._state["audit"].append(event)
            self._save()
            return {"state": "active", "snapshot": copy.deepcopy(new)}

    def rollback(self, *, reason: str, expected_version: int | None = None) -> dict[str, Any]:
        if not reason:
            raise ValueError("rollback trigger required")
        with self._transaction():
            current = self._state["snapshots"][self._state["active"]]
            if expected_version is not None and current["version"] != expected_version:
                raise ContextConflict("rollback compare-and-swap rejected")
            previous = self._state["previous"]
            if not previous:
                raise ValueError("no prior active snapshot")
            self._state["active"], self._state["previous"] = previous, None
            self._state["audit"].append({"state": "rolled_back", "created_at": now(), "reason": reason,
                                        "from": current["context_snapshot_id"], "to": previous})
            self._save()
            return copy.deepcopy(self._state["snapshots"][previous])

    def check_regression(self, metrics: dict[str, Any], *, expected_version: int) -> dict[str, Any]:
        if metrics.get("permission_violations", 0) or metrics.get("key_regression", False):
            return {"state": "rolled_back", "snapshot": self.rollback(reason="automatic permission/key-regression guard", expected_version=expected_version)}
        return {"state": "active", "snapshot": self.snapshot()}

    def search(self, query: str, *, scope: dict[str, Any] | None = None, cutoff: str | None = None,
               limit: int = 6, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        scope, scored = scope or {}, []
        for item in self.snapshot(snapshot_id)["memories"]:
            if item["state"] not in {"active", "conflicted"}:
                continue
            if any(scope.get(k) != v for k, v in item.get("scope", {}).items() if v is not None):
                continue
            if cutoff and item.get("available_at") and parse_time(item["available_at"]) > parse_time(cutoff):
                continue
            if item.get("expires_at") and parse_time(item["expires_at"]) < parse_time(cutoff or now()):
                continue
            score = sum(word.lower() in (item["trigger"] + " " + item["insight"]).lower() for word in query.split())
            scored.append((score, item["memory_id"], item))
        return [copy.deepcopy(item) for _, _, item in sorted(scored, key=lambda x: (-x[0], x[1]))[:min(limit, 6)]]


def evolve_context(store: ContextStore, feedback: dict[str, Any], previous_report: dict[str, Any] | None = None,
                   *, expected_version: int | None = None) -> dict[str, Any]:
    """Safe local ACE delta. No employee prose becomes a global Skill rule.

    Explicit corrections target a previous claim. Unresolved/conflicting events
    enter memory as such; labels derived from unmeasured or post-intervention
    absence are deliberately not accepted as diagnosis correctness.
    """
    extracted = extract_feedback(feedback)
    if feedback.get("candidate_facts") is not None:
        corrected = feedback["candidate_facts"]
        if not isinstance(corrected, list) or len(corrected) > 100 or any(not isinstance(f, dict) or not isinstance(f.get("claim"), str) or len(f["claim"]) > 2000 for f in corrected):
            raise ValueError("corrected feedback facts have invalid structure")
        extracted["candidate_facts"] = copy.deepcopy(corrected)
        extracted["structured_correction_preserved"] = True
    snapshot = store.snapshot()
    version = snapshot["version"] if expected_version is None else expected_version
    root_id = feedback.get("root_scenario_id", feedback.get("order_id", feedback.get("feedback_id")))
    if not root_id or not extracted["candidate_facts"]:
        updates = [{"operation": "NO_UPDATE", "reason": "No source-identifiable feedback facts"}]
    else:
        fid = str(feedback.get("feedback_id", feedback.get("observation_id", root_id)))
        mid = "memory-" + hashlib.sha256(str(root_id).encode()).hexdigest()[:16]
        insight = " | ".join(f["claim"] for f in extracted["candidate_facts"][:6])
        if feedback.get("performed_actions"):
            insight += " | Intervention occurred; absence after intervention is not a false-positive label."
        old = next((m for m in snapshot["memories"] if m["memory_id"] == mid), None)
        item = {"insight": insight, "source_trust": feedback.get("verification_status", "reported"),
                "supporting_case_ids": [str(root_id)]}
        if old:
            op = ("NO_UPDATE" if old["insight"] == insight and old["source_trust"] == item["source_trust"] and not feedback.get("contradicts_previous")
                  else "CONFLICT" if feedback.get("contradicts_previous") else "REVISE")
            updates = [{"operation": op, "memory_id": mid, "item": item}]
        else:
            item.update(memory_id=mid, scope=feedback.get("scope", {"installation_id": feedback.get("installation_id")}),
                        trigger=str(feedback.get("symptoms", "inspection feedback")), raw_feedback_id=fid,
                        available_at=feedback.get("available_at", feedback.get("measured_at", now())),
                        origin=feedback.get("provenance", "declared_operational"))
            updates = [{"operation": "ADD", "memory_id": mid, "item": item}]
    result = store.apply(updates, expected_version=version, source_scope=feedback.get("split", "operational"))
    return {**result, "updates": updates, "feedback": extracted,
            "compared_report_id": (previous_report or {}).get("report_id"),
            "targeted_claim_ids": feedback.get("corrected_claim_ids", feedback.get("assertion_targets", [])),
            "report_comparison": {"claimed_confirmed": [h.get("code") for h in (previous_report or {}).get("hypotheses", []) if h.get("level") == "confirmed"],
                                  "feedback_confirmed": feedback.get("confirmed_hypotheses", []),
                                  "feedback_excluded": feedback.get("excluded_hypotheses", []),
                                  "unresolved_items": feedback.get("unresolved_items", []),
                                  "finding_trust": feedback.get("verification_status", "reported")}}
