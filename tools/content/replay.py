"""Capability-separated public reader and evaluator-only branch environment.

Production deployments should copy only export_public's allowlisted files. The
evaluator constructor deliberately requires explicit oracle access; it must never
be registered as an Agent tool or pointed at a production public content root.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import shutil

from .common import TOOL_WHITELIST, read_jsonl


def _within(base: Path, candidate: Path) -> Path:
    base, candidate = base.resolve(), candidate.resolve()
    if not candidate.is_relative_to(base):
        raise PermissionError("resource must stay inside its published skill directory")
    return candidate


class PublicContentStore:
    """No generic filesystem getter: only licensed skills, evidence, cold views."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def skill_metadata(self) -> list[dict]:
        result = []
        for path in sorted((self.root / "skills").glob("*/manifest.json")):
            manifest = json.loads(path.read_text())
            if manifest.get("license_status") not in {"approved", "approved_synthetic"}:
                continue
            if not set(manifest.get("allowed_tools", [])) <= TOOL_WHITELIST:
                continue
            result.append(deepcopy(manifest))
        return result

    def route(self, context: dict, max_skills: int = 4) -> list[dict]:
        chemistry = context.get("chemistry") or context.get("asset_context", {}).get("chemistry")
        query = json.dumps(context, ensure_ascii=False).lower()
        ranked = []
        for manifest in self.skill_metadata():
            if chemistry and chemistry not in manifest.get("supported_chemistries", []) and chemistry != "unknown":
                continue
            score = sum(1 for keyword in manifest.get("route_keywords", [manifest["skill_id"]]) if keyword.lower() in query)
            if manifest["skill_id"] in {"data-quality", "chemistry-eligibility"}:
                score += 1
            ranked.append((score, manifest["skill_id"], manifest))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [deepcopy(item[2]) for item in ranked[:max(0, min(max_skills, 8))]]

    def load_skill(self, skill_id: str) -> dict:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill_id):
            raise PermissionError("invalid skill ID")
        manifest = next((m for m in self.skill_metadata() if m["skill_id"] == skill_id), None)
        if manifest is None:
            raise PermissionError("skill is absent, unlicensed or has expanded tool permissions")
        base = _within(self.root / "skills", self.root / "skills" / skill_id)
        body = _within(base, base / "SKILL.md").read_text()
        return {"manifest": manifest, "body": body}

    load = load_skill

    def load_reference(self, skill_id: str, resource: str) -> dict:
        self.load_skill(skill_id)
        if not resource.startswith("references/") or Path(resource).suffix != ".md":
            raise PermissionError("only published markdown references can be loaded")
        base = self.root / "skills" / skill_id
        path = _within(base, base / resource)
        return {"skill_id": skill_id, "resource": resource, "text": path.read_text()}

    def search_knowledge(self, query: str, limit: int = 5) -> list[dict]:
        tokens = [token.lower() for token in re.split(r"\s+", query) if token]
        rows = [row for row in read_jsonl(self.root / "knowledge/evidence.jsonl") if row.get("license_status") in {"approved", "approved_synthetic"}]
        scored = [(sum(token in json.dumps(row, ensure_ascii=False).lower() for token in tokens), row) for row in rows]
        return [deepcopy(row) for score, row in sorted(scored, key=lambda item: -item[0])[:max(0, min(limit, 20))] if score or not tokens]

    def cold_cases(self) -> list[dict]:
        return deepcopy(read_jsonl(self.root / "cases/cold_start.jsonl"))


def export_public(root: str | Path, target: str | Path) -> dict:
    """Publish the physically separate runtime bundle without evaluator assets."""
    store, destination = PublicContentStore(root), Path(target)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("public export destination must be empty to avoid stale oracle files")
    for manifest in store.skill_metadata():
        skill_id = manifest["skill_id"]
        source = _within(store.root / "skills", store.root / "skills" / skill_id)
        # Copy known resource kinds only; unknown files cannot be smuggled into RAG.
        for relative in ["SKILL.md", "manifest.json", *[str(p.relative_to(source)) for directory in ("references", "examples", "checks") for p in (source / directory).glob("*") if p.is_file()]]:
            path = _within(source, source / relative)
            if path.suffix not in {".json", ".md"}:
                continue
            output = destination / "skills" / skill_id / relative
            output.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, output)
    for relative in ("knowledge/evidence.jsonl", "cases/cold_start.jsonl"):
        output = destination / relative; output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_within(store.root, store.root / relative), output)
    return {"skills": len(store.skill_metadata()), "cold_roots": len(store.cold_cases()), "evaluator_files": 0}


@dataclass
class ReplaySession:
    case_id: str
    visible: dict
    state: str = "start"
    reached_ids: set[str] = field(default_factory=set)
    authorized_tests: set[str] = field(default_factory=set)
    completed: list[dict] = field(default_factory=list)


class EvaluatorReplay:
    """Hidden labels never enter returned visible dictionaries."""

    def __init__(self, root: str | Path, *, oracle_access: bool = False):
        if not oracle_access:
            raise PermissionError("oracle access is evaluator-only and must be explicitly enabled")
        self.root = Path(root)
        paths = [self.root / "cases/cold_start.jsonl", *sorted((self.root / "streams").glob("evolution_round_*.jsonl")), self.root / "evaluation/dev/cases.jsonl", self.root / "evaluation/sealed/cases.jsonl"]
        self._cases = {case["case_id"]: case for path in paths for case in read_jsonl(path)}
        self._labels = {row["case_id"]: row for row in read_jsonl(self.root / "oracle/labels.jsonl")}
        self._observations = {row["observation_id"]: row for row in read_jsonl(self.root / "oracle/observations.jsonl")}

    def begin(self, case_id: str) -> ReplaySession:
        case = deepcopy(self._cases[case_id])
        initial_ids = {obs["observation_id"] for obs in case["initial_visible"]["observations"]}
        return ReplaySession(case_id=case_id, visible=case, reached_ids=initial_ids)

    def authorize(self, session: ReplaySession, test_id: str, *, approved_by: str) -> None:
        if approved_by not in {"administrator", "dispatcher", "synthetic_evaluator"}:
            raise PermissionError("authorized human role or synthetic evaluator required")
        if test_id not in {test["test_id"] for test in session.visible["test_catalog"]}:
            raise PermissionError("test not in case catalog")
        session.authorized_tests.add(test_id)

    def reveal(self, session: ReplaySession, test_id: str, *, authorized: bool = False, result: str | None = None) -> dict:
        if not authorized and test_id not in session.authorized_tests:
            raise PermissionError("selected test has not been authorized")
        test = next((test for test in session.visible["test_catalog"] if test["test_id"] == test_id), None)
        if test is None:
            raise PermissionError("test is not allowlisted")
        if test["needs_new_authorization"] and test_id not in session.authorized_tests:
            raise PermissionError("restricted test requires separately recorded new approval")
        label = self._labels[session.case_id]
        candidates = [branch for branch in label["branches"] if branch["from"] == session.state and branch["test_id"] == test_id]
        if not candidates:
            # Idempotent replay of a completed call does not manufacture new evidence.
            prior = next((row for row in reversed(session.completed) if row["test_id"] == test_id and (result is None or row["result"] == result)), None)
            if prior:
                return {**deepcopy(prior), "duplicate": True, "new_evidence": False}
            raise PermissionError("test is unreachable from the current observed state")
        if result is None:
            result = "supports_A" if label["hidden_truth"]["root_cause"] in label["hidden_truth"]["candidate_causes"][:1] else "supports_B"
        branch = next((branch for branch in candidates if branch["result"] == result), None)
        if branch is None:
            raise PermissionError("unknown/unreachable configured outcome")
        revealed = []
        for oid in branch["reveal"]:
            if oid not in session.reached_ids:
                observation = deepcopy(self._observations[oid]); observation.pop("root_scenario_id", None)
                revealed.append(observation); session.reached_ids.add(oid)
        session.visible["initial_visible"]["observations"].extend(revealed)
        session.state = branch["next_state"]
        session.visible["initial_visible"]["cutoff"] = max([session.visible["initial_visible"]["cutoff"], *[o["timestamp"] for o in revealed]])
        result_row = {"test_id": test_id, "result": result, "observations": revealed, "state": session.state, "new_evidence": bool(revealed), "duplicate": False, "intervention": False}
        session.completed.append(result_row)
        return deepcopy(result_row)

    def visible_feedback(self, session: ReplaySession) -> list[dict]:
        return [deepcopy(fb) for fb in self._labels[session.case_id]["feedback_events"] if set(fb["evidence_ids"]) <= session.reached_ids]

    def score(self, session: ReplaySession, report: dict) -> dict:
        """Deterministic boundary/reference checks; not an expert semantic score."""
        refs = set(report.get("evidence_refs", []))
        hidden_terms = {"hidden_truth", "oracle", "sealed_test"}
        claims = json.dumps(report, ensure_ascii=False)
        checks = {"evidence_visible": refs <= session.reached_ids, "no_automatic_dispatch": not report.get("automatic_dispatch", False), "no_carbon_tool": all("carbon" not in t.lower() for t in report.get("called_tools", [])), "no_hidden_fields": not any(term in claims for term in hidden_terms)}
        return {"checks": checks, "passed": all(checks.values()), "semantic_expert_validation": "not_performed", "weights": self._labels[session.case_id]["expected_behavior"]["weights"]}
