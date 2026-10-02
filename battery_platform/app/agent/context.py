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
import re
import threading
import unicodedata
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


def memory_retrieval_kind(item: dict[str, Any]) -> tuple[str, str]:
    """Classify recorded evidence, never prose sentiment or reward counters.

    'positive' means a supported applicable experience, not a verified diagnosis
    or a successful intervention. A conflicting bundle keeps both sides intact.
    """
    if item.get("state") == "conflicted":
        return "counterexample", "recorded_conflict"
    if item.get("source_trust") == "contradicted":
        return "counterexample", "source_contradicted"
    if isinstance(item.get("counterexamples"), list) and item["counterexamples"]:
        return "counterexample", "explicit_counterexamples"
    if isinstance(item.get("conflicts"), list) and item["conflicts"]:
        return "counterexample", "explicit_conflicting_sources"
    if (item.get("state") == "active" and item.get("source_trust") in ("measurement_supported", "independently_verified")
            and isinstance(item.get("supporting_case_ids"), list) and item["supporting_case_ids"]
            and all(isinstance(root, str) and root.strip() for root in item["supporting_case_ids"])):
        return "positive", "source_supported_applicable_experience"
    return "unclassified", "reported_or_category_not_established"


# This is a deterministic lexical gate, not an embedding similarity claim.
# Chinese bigrams allow an unspaced query such as "复测内阻升高" to match the
# independently recorded term "内阻" without matching individual common chars.
_CJK_RUNS = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_LATIN_TERMS = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")
_RETRIEVAL_STOP_TERMS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "was", "were", "are", "has", "have",
    "inspection", "inspect", "check", "feedback", "record", "records", "reported", "case", "cases",
    "observation", "observations", "review", "battery", "batteries", "电池",
    "本次", "此次", "现场", "反馈", "记录", "情况", "发现", "确认", "复核", "检查", "检测",
    "复测", "进行", "已经", "目前", "仍然", "需要", "是否", "结果", "相关", "经验", "案例",
})
_DOMAIN_ALIASES = {
    "内阻": "resistance", "电阻": "resistance", "resistance": "resistance",
    "电压": "voltage", "voltage": "voltage", "电流": "current", "current": "current",
    "温度": "temperature", "temperature": "temperature", "容量": "capacity", "capacity": "capacity",
    "采集": "sensor", "传感": "sensor", "sensor": "sensor", "偏差": "bias", "bias": "bias",
}


def _memory_terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    generic_chinese = sorted((term for term in _RETRIEVAL_STOP_TERMS if _CJK_RUNS.fullmatch(term)), key=len, reverse=True)
    normalized = re.sub("|".join(map(re.escape, generic_chinese)), " ", normalized)
    terms = {term for term in _LATIN_TERMS.findall(normalized) if len(term) > 1}
    for run in _CJK_RUNS.findall(normalized):
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    terms -= _RETRIEVAL_STOP_TERMS
    terms.update("concept:" + _DOMAIN_ALIASES[term] for term in list(terms) if term in _DOMAIN_ALIASES)
    return terms


def memory_relevance(query: str, item: dict[str, Any]) -> tuple[float, list[str]]:
    """Return query-token coverage and evidence terms; zero means no match.

    Numeric-only overlap and single Chinese characters cannot establish
    relevance. Complete retained facts and both sides of conflicts participate
    so a late measurement or counterexample can be retrieved by its content.
    Scope/availability are separate applicability gates applied by the store.
    """
    if not isinstance(query, str):
        raise ValueError("Memory query must be text")
    query_terms = _memory_terms(query)
    if not query_terms:
        return 0.0, []
    texts = [str(item.get("trigger", "")), str(item.get("insight", ""))]
    for field in ("fact_references", "counterexamples", "conflicts"):
        for fact in item.get(field, []) if isinstance(item.get(field, []), list) else []:
            if isinstance(fact, dict):
                texts.extend(str(fact.get(key, "")) for key in ("claim", "insight", "source_text"))
                for reference in fact.get("fact_references", []) if isinstance(fact.get("fact_references", []), list) else []:
                    if isinstance(reference, dict):
                        texts.extend(str(reference.get(key, "")) for key in ("claim", "source_text"))
    matches = sorted(query_terms & _memory_terms(" ".join(texts)))
    return len(matches) / len(query_terms), matches


_FACT_CLASSES = {"correction": 0, "measurement": 1, "counterevidence": 2,
                 "unknown": 3, "conclusion": 4, "reported_statement": 5}
_FACT_SUMMARY_LIMIT = 6
_FACT_SUMMARY_CHAR_BUDGET = 2400


def _fact_class(fact: dict[str, Any]) -> str:
    """Priority is a presentation hint, never a new truth/trust label."""
    kind = fact.get("kind", "reported_statement")
    claim = str(fact.get("claim", ""))
    if kind in {"correction", "corrected_assertion"} or re.search(r"更正|纠正|修正|correction|corrected", claim, re.I):
        return "correction"
    if fact.get("measurement") is not None or kind in {"observation", "measurement"}:
        return "measurement"
    if (fact.get("trust") == "contradicted" or kind in {"counterevidence", "contradiction", "counterexample"}
            or re.search(r"反证|排除|不支持|相矛盾|并非|未发现|contradict|counterevidence|excluded|not support", claim, re.I)):
        return "counterevidence"
    if kind == "unknown" or re.search(r"未知|未测|尚未|未核实|未确认|不确定|待复核|unknown|unresolved|not measured|uncertain", claim, re.I):
        return "unknown"
    if kind == "conclusion" or re.search(r"结论|最终|复核确认|conclusion|finally", claim, re.I):
        return "conclusion"
    return "reported_statement"


def _fact_projection(facts: list[dict[str, Any]], *, query: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bound model Context while preserving complete facts in the snapshot.

    Query relevance takes precedence during tool retrieval; otherwise explicit
    corrections, measurements, counterevidence and unknowns precede incidental
    prose. Equal-priority facts are newest-first, so late evidence is not hidden
    by earlier arrival/registration notes. Overflow remains query-retrievable.
    """
    ranked = []
    for index, fact in enumerate(facts):
        relevance = memory_relevance(query, {"insight": fact["claim"]})[0] if query else 0.0
        ranked.append((relevance, _FACT_CLASSES.get(fact.get("priority_class", _fact_class(fact)), 5), index, fact))
    ordered = sorted(ranked, key=lambda row: (-row[0], row[1], -row[2]))
    selected, used = [], 0
    for _, _, _, fact in ordered:
        if len(selected) >= _FACT_SUMMARY_LIMIT or used >= _FACT_SUMMARY_CHAR_BUDGET:
            break
        view = copy.deepcopy(fact)
        remaining = _FACT_SUMMARY_CHAR_BUDGET - used
        claim = view["claim"]
        offset = 0
        if len(claim) > remaining:
            # An oversized sentence still exposes an exact source excerpt, with
            # its full span retained for lookup rather than silently discarded.
            if query:
                literal = claim.lower().find(query.lower())
                if literal >= 0:
                    offset = max(0, literal - remaining // 3)
            excerpt = claim[offset:offset + remaining]
            view.update(claim=excerpt, claim_excerpt=True, claim_excerpt_offset=offset,
                        full_claim_length=len(claim))
        source = view.get("source_text")
        if isinstance(source, str) and len(source) > remaining:
            source_offset = offset if source == claim else 0
            if query and source != claim:
                literal = source.lower().find(query.lower())
                if literal >= 0:
                    source_offset = max(0, literal - remaining // 3)
            source_excerpt = source[source_offset:source_offset + remaining]
            view.update(source_text=source_excerpt, source_excerpt=True)
            if isinstance(view.get("span"), dict):
                span = copy.deepcopy(view["span"])
                view["full_source_span"] = span
                view["span"] = {"start": span["start"] + source_offset,
                                "end": span["start"] + source_offset + len(source_excerpt)}
        selected.append(view)
        used += max(len(view["claim"]), len(view.get("source_text", "")))
    return selected, {"policy": "corrections_measurements_counterevidence_unknowns_then_conclusions; query_first; newest_ties",
                      "max_facts": _FACT_SUMMARY_LIMIT, "max_chars": _FACT_SUMMARY_CHAR_BUDGET,
                      "total_fact_count": len(facts), "selected_fact_ids": [f["reference_id"] for f in selected],
                      "omitted_fact_count": len(facts) - len(selected), "projection": "bounded",
                      "detail_retrieval": "search_memory with a query for the omitted fact"}


def _feedback_references(extracted: dict[str, Any], feedback: dict[str, Any], fid: str) -> list[dict[str, Any]]:
    references = []
    available_at = feedback.get("available_at", feedback.get("measured_at", now()))
    for index, fact in enumerate(extracted["candidate_facts"]):
        # Do not copy arbitrary caller keys into runtime Context.
        record = {key: copy.deepcopy(fact[key]) for key in ("fact_id", "claim", "span", "source_text", "measurement",
                   "author_id", "extraction_model", "trust", "kind", "source_field", "source_index") if key in fact}
        record.setdefault("fact_id", f"corrected-fact-{index}")
        record.setdefault("kind", "reported_statement")
        record.setdefault("trust", feedback.get("verification_status", "reported"))
        record.update(feedback_id=fid, feedback_version=extracted["version"], available_at=available_at)
        record["priority_class"] = _fact_class(record)
        if feedback.get("contradicts_previous"):
            record["contradicts_previous"] = True
            if record["priority_class"] not in {"correction", "measurement"}:
                record["priority_class"] = "counterevidence"
        targets = feedback.get("corrected_claim_ids", feedback.get("assertion_targets", []))
        if targets:
            record["corrected_claim_ids"] = copy.deepcopy(targets)
        identity = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        record["reference_id"] = "feedback-ref-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        references.append(record)
    return references


def _retrieval_view(item: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    kind, basis = memory_retrieval_kind(item)
    view = copy.deepcopy(item)
    # A budget receives an already bounded view. Keep that query-selected view
    # and its original omitted count instead of re-projecting the six facts.
    if isinstance(item.get("fact_references"), list) and item.get("fact_summary", {}).get("projection") != "bounded":
        facts, summary = _fact_projection(item["fact_references"], query=query)
        view.update(fact_references=facts, fact_summary=summary,
                    insight=" | ".join(f["claim"] for f in facts))
        if item.get("source_label_guards", {}).get("intervention_prevents_false_positive_label"):
            view["insight"] += " | Intervention occurred; absence after intervention is not a false-positive label."
        if view.get("conflicts"):
            # Complete conflicting source bundles are retained in the immutable
            # snapshot. Avoid copying them all back into model Context through
            # the nested conflict list after bounding the primary fact view.
            view["conflict_summary"] = {"total_conflict_count": len(view["conflicts"]),
                                        "detail_retrieval": summary["detail_retrieval"]}
            bounded_conflicts = []
            for conflict in reversed(view["conflicts"]):
                refs = conflict.get("fact_references", [])
                visible_refs = [f for f in facts if f["reference_id"] in {r["reference_id"] for r in refs}]
                if not visible_refs:
                    continue
                bounded_conflicts.append({"insight": " | ".join(f["claim"] for f in visible_refs),
                    "source_trust": conflict.get("source_trust", "reported"),
                    "supporting_case_ids": conflict.get("supporting_case_ids", []),
                    "fact_reference_ids": [f["reference_id"] for f in visible_refs],
                    "source_label_guards": conflict.get("source_label_guards", {})})
                if len(bounded_conflicts) == 3:
                    break
            view["conflicts"] = bounded_conflicts
    return {**view, "retrieval_kind": kind, "retrieval_basis": basis}


class MemoryRetrievalBudget:
    """One round's initial Context and tool lookups share six unique entries."""
    def __init__(self):
        self._accepted: dict[str, dict[str, Any]] = {}
        self._excluded_by_budget = 0

    def summary(self) -> dict[str, Any]:
        counts = {kind: sum(item["retrieval_kind"] == kind for item in self._accepted.values())
                  for kind in ("positive", "counterexample", "unclassified")}
        return {"max_total": 6, "max_positive": 3, "max_counterexample": 3,
                "counts": counts, "unique_retrieved": len(self._accepted), "remaining_total": 6 - len(self._accepted),
                "excluded_by_budget": self._excluded_by_budget,
                "policy": "unclassified_fill_only; never_borrow_above_class_cap; next_round_for_more"}

    def admit(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise ValueError("Memory lookup must return a list")
        result, returned = [], set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("memory_id"), str) or not item["memory_id"]:
                raise ValueError("Memory lookup entry needs an identity")
            mid = item["memory_id"]
            if mid in returned:
                continue
            if mid not in self._accepted:
                view = _retrieval_view(item)
                kind, counts = view["retrieval_kind"], self.summary()["counts"]
                if len(self._accepted) >= 6 or kind != "unclassified" and counts[kind] >= 3:
                    self._excluded_by_budget += 1
                    continue
                self._accepted[mid] = view
            returned.add(mid)
            accepted = self._accepted[mid]
            stable_fields = ("version", "scope", "source_trust", "state", "supporting_case_ids", "raw_feedback_id", "available_at")
            alternate_fact_view = (accepted.get("fact_summary", {}).get("projection") == "bounded"
                and item.get("fact_summary", {}).get("projection") == "bounded"
                and accepted["fact_summary"]["total_fact_count"] == item["fact_summary"].get("total_fact_count")
                and all(accepted.get(field) == item.get(field) for field in stable_fields))
            # Repeated lookups may expose another bounded set of source facts
            # from the same immutable revision. They do not spend another
            # memory slot or replace the accepted snapshot with a new revision.
            result.append(_retrieval_view(item) if alternate_fact_view else copy.deepcopy(accepted))
        return result


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
                        for field in ("fact_references", "fact_summary", "source_label_guards"):
                            if field in item:
                                record[field] = copy.deepcopy(item[field])
                        memory_by_id[mid] = record
                    else:
                        if mid not in memory_by_id:
                            raise ValueError("cannot revise absent memory")
                        record = memory_by_id[mid]
                        record["version"] += 1
                        if operation == "REVISE":
                            if not set(item) <= {"insight", "trigger", "scope", "source_trust", "counterexamples", "supporting_case_ids", "expires_at", "helpful_count", "harmful_count", "available_at", "raw_feedback_id", "fact_references", "fact_summary", "source_label_guards"}:
                                raise ValueError("revision contains immutable or permission fields")
                            if item.get("source_trust", record["source_trust"]) not in {"reported", "measurement_supported", "independently_verified", "contradicted"}:
                                raise ValueError("invalid revised memory trust")
                            record["revision_provenance"] = {"previous_version": record["version"] - 1,
                                "previous_available_at": record.get("available_at"), "previous_feedback_id": record.get("raw_feedback_id")}
                            record.update(item)
                        elif operation == "DEPRECATE":
                            record.update(state="deprecated", deprecation_reason=update.get("reason", "superseded"))
                        else:
                            record["state"] = "conflicted"
                            conflict = {"insight": item.get("insight", ""),
                                        "source_trust": item.get("source_trust", "reported"),
                                        "supporting_case_ids": item.get("supporting_case_ids", [])}
                            for field in ("fact_references", "fact_summary", "source_label_guards"):
                                if field in item:
                                    conflict[field] = copy.deepcopy(item[field])
                                    record[field] = copy.deepcopy(item[field])
                            record.setdefault("conflicts", []).append(conflict)
                            # The view retains both source bundles; the summary
                            # includes late counterevidence instead of only the
                            # old assertion, without resolving the conflict.
                            if item.get("fact_references"):
                                record["insight"] = item.get("insight", record["insight"])
                            record["available_at"] = item.get("available_at", now())
                            record["raw_feedback_id"] = item.get("raw_feedback_id")
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

    @staticmethod
    def _retrieval_limit(limit: int) -> int:
        if type(limit) is not int or limit < 0:
            raise ValueError("Memory retrieval limit must be a nonnegative integer")
        return min(limit, 6)

    def _visible_memories(self, *, scope: dict[str, Any], cutoff: str | None,
                          snapshot_id: str | None) -> list[dict[str, Any]]:
        visible = []
        for item in self.snapshot(snapshot_id)["memories"]:
            if item["state"] not in {"active", "conflicted"}:
                continue
            if any(scope.get(k) != v for k, v in item.get("scope", {}).items() if v is not None):
                continue
            if cutoff and item.get("available_at") and parse_time(item["available_at"]) > parse_time(cutoff):
                continue
            if item.get("expires_at") and parse_time(item["expires_at"]) < parse_time(cutoff or now()):
                continue
            visible.append(item)
        return visible

    def history(self, *, scope: dict[str, Any], cutoff: str | None = None,
                root_id: str | None = None, root_ids: list[str] | None = None, limit: int = 6,
                snapshot_id: str | None = None) -> list[dict[str, Any]]:
        """Explicit same-installation event history, never similarity results.

        A supplied root narrows this to the current event's recorded history.
        Without a root this is an explicit installation-history lookup; the
        executor must not use that broad lookup as an implicit search fallback.
        """
        limit = self._retrieval_limit(limit)
        installation = scope.get("installation_id")
        if not limit or not installation:
            return []
        if root_ids is not None and (not isinstance(root_ids, list) or len(root_ids) > 100
                                    or any(not isinstance(root, str) or not root.strip() for root in root_ids)):
            raise ValueError("Event history roots must be bounded source identities")
        roots = set(root_ids) if root_ids is not None else ({str(root_id)} if root_id is not None else None)
        if roots == set():
            return []
        rows = [item for item in self._visible_memories(scope=scope, cutoff=cutoff, snapshot_id=snapshot_id)
                if item.get("scope", {}).get("installation_id") == installation
                and (roots is None or roots.intersection(item.get("supporting_case_ids", [])))]
        rows.sort(key=lambda item: (parse_time(item.get("available_at") or "1970-01-01T00:00:00Z"), item["memory_id"]), reverse=True)
        return [{**_retrieval_view(item), "retrieval_mode": "event_history"} for item in rows[:limit]]

    def search(self, query: str, *, scope: dict[str, Any] | None = None, cutoff: str | None = None,
               limit: int = 6, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        """Relevant, applicable lexical experience retrieval with empty results.

        History is available through history(), not zero-score quota filling.
        Relevance precedes all evidence-class balancing and retrieval budgets.
        """
        limit = self._retrieval_limit(limit)
        if not isinstance(query, str):
            raise ValueError("Memory query must be text")
        if not limit or not _memory_terms(query):
            return []
        scored = []
        for item in self._visible_memories(scope=scope or {}, cutoff=cutoff, snapshot_id=snapshot_id):
            score, matched_terms = memory_relevance(query, item)
            if score > 0:
                scored.append((score, item["memory_id"], item, matched_terms))
        ordered = sorted(scored, key=lambda x: (-x[0], x[1]))
        groups = {kind: [row for row in ordered if memory_retrieval_kind(row[2])[0] == kind]
                  for kind in ("positive", "counterexample", "unclassified")}
        selected, counts = [], {"positive": 0, "counterexample": 0}
        # Reserve evidence from both classes. For an odd/small total, keep the
        # counterexample first rather than letting high-score support crowd it out.
        while len(selected) < limit:
            added = False
            for kind in ("counterexample", "positive"):
                if len(selected) < limit and counts[kind] < 3 and groups[kind]:
                    selected.append(groups[kind].pop(0))
                    counts[kind] += 1
                    added = True
            if not added:
                break
        # Unknown/reported entries remain explicitly unclassified. A missing
        # class does not permit four positives or four counterexamples.
        selected += groups["unclassified"][:limit - len(selected)]
        return [{**_retrieval_view(item, query=query), "retrieval_mode": "similar_experience",
                 "relevance_score": score, "relevance_matched_terms": matched_terms,
                 "relevance_policy": "lexical_query_coverage_v1"}
                for score, _, item, matched_terms in sorted(selected, key=lambda x: (-x[0], x[1]))]


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
        if not isinstance(corrected, list) or any(not isinstance(f, dict) or not isinstance(f.get("claim"), str) or not f["claim"].strip() for f in corrected):
            raise ValueError("corrected feedback facts have invalid structure")
        # The compute API passes its source-spanned automatic extraction back
        # through this function (including calibrated-instrument trust
        # downgrades). It is bounded by the original feedback source budget,
        # not the smaller human-correction editor limits. A long source span or
        # many short source sentences must still be preserved and projected.
        generated = extracted["candidate_facts"]
        preserves_generated = len(corrected) == len(generated) and all(
            {key: value for key, value in fact.items() if key != "trust"}
            == {key: value for key, value in source.items() if key != "trust"}
            for fact, source in zip(corrected, generated))
        if not preserves_generated and (len(corrected) > 100 or any(len(f["claim"]) > 2000 for f in corrected)):
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
        old = next((m for m in snapshot["memories"] if m["memory_id"] == mid), None)
        available_at = feedback.get("available_at", feedback.get("measured_at"))
        if available_at is None:
            available_at = old.get("available_at") if old and old.get("raw_feedback_id") == fid else now()
        references = _feedback_references(extracted, {**feedback, "available_at": available_at}, fid)
        all_references = {f["reference_id"]: copy.deepcopy(f) for f in (old or {}).get("fact_references", [])}
        all_references.update({f["reference_id"]: f for f in references})
        references = list(all_references.values())
        selected_facts, summary = _fact_projection(references)
        insight = " | ".join(f["claim"] for f in selected_facts)
        if feedback.get("performed_actions"):
            insight += " | Intervention occurred; absence after intervention is not a false-positive label."
        item = {"insight": insight, "source_trust": feedback.get("verification_status", "reported"),
                "supporting_case_ids": [str(root_id)], "raw_feedback_id": fid,
                "fact_references": references, "fact_summary": {**summary, "projection": "stored_complete"},
                "source_label_guards": extracted["label_guards"],
                "available_at": available_at}
        if old:
            op = ("NO_UPDATE" if old["insight"] == insight and old["source_trust"] == item["source_trust"]
                  and old.get("fact_references") == references and not feedback.get("contradicts_previous")
                  else "CONFLICT" if feedback.get("contradicts_previous") else "REVISE")
            updates = [{"operation": op, "memory_id": mid, "item": item}]
        else:
            item.update(memory_id=mid, scope=feedback.get("scope", {"installation_id": feedback.get("installation_id")}),
                        trigger=str(feedback.get("symptoms", "inspection feedback")), raw_feedback_id=fid,
                        available_at=available_at,
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
