"""Metadata routing then progressive Skill/resource loading."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .contracts import TOOL_WHITELIST


class SkillLibrary:
    def __init__(self, root: str | Path, *, max_skills: int = 4, max_body_chars: int = 24000):
        self.root = Path(root).resolve()
        self.max_skills = min(max_skills, 4)
        self.max_body_chars = max_body_chars
        self._metadata: dict[str, dict[str, Any]] = {}
        # Index reads only metadata files. SKILL bodies remain unloaded until route.
        for file in sorted((self.root / "skills").glob("*/manifest.json")):
            manifest = json.loads(file.read_text(encoding="utf-8"))
            if manifest.get("license_status") not in {"approved", "approved_synthetic"}:
                continue
            sid = manifest.get("skill_id", file.parent.name)
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", sid):
                raise ValueError("invalid Skill identifier")
            if not set(manifest.get("allowed_tools", [])) <= TOOL_WHITELIST:
                raise ValueError("Skill manifest requests forbidden tools")
            frontmatter = {}
            skill_file = file.parent / "SKILL.md"
            if skill_file.exists():
                # Read only the header, keeping the instructions/resources unloaded.
                with skill_file.open(encoding="utf-8") as handle:
                    if handle.readline().strip() == "---":
                        header = []
                        for _ in range(64):
                            line = handle.readline()
                            if not line or line.strip() == "---":
                                break
                            header.append(line)
                        import yaml
                        frontmatter = yaml.safe_load("".join(header)) or {}
            self._metadata[sid] = {**manifest, "skill_id": sid,
                                   "name": manifest.get("name", frontmatter.get("name", sid)),
                                   "description": manifest.get("description", frontmatter.get("description", manifest.get("routing_description", sid)))}

    def skill_metadata(self) -> list[dict[str, Any]]:
        return list(self._metadata.values())

    def route(self, context: dict[str, Any], max_skills: int | None = None) -> list[dict[str, Any]]:
        limit = min(self.max_skills, max_skills if max_skills is not None else self.max_skills)
        text = json.dumps(context.get("symptoms", context.get("observations", [])), ensure_ascii=False).lower()
        chemistry = context.get("chemistry", context.get("asset", {}).get("chemistry"))
        scored = []
        for sid, manifest in self._metadata.items():
            supported = manifest.get("supported_chemistries", [])
            if supported and chemistry and chemistry not in supported and "any" not in supported and "*" not in supported:
                continue
            required = manifest.get("required_inputs", [])
            if required and any(k not in context or context[k] in (None, [], {}) for k in required):
                continue
            keywords = manifest.get("route_keywords", sid.split("-"))
            score = sum(str(k).lower() in text for k in keywords)
            if score or not keywords:
                scored.append((score, sid, manifest))
        return [{"skill_id": sid, "name": m["name"], "description": m["description"],
                 "version": m.get("version", "1"), "route_score": score}
                for score, sid, m in sorted(scored, key=lambda x: (-x[0], x[1]))[:limit]]

    def load_skill(self, skill_id: str) -> dict[str, Any]:
        if skill_id not in self._metadata:
            raise ValueError("unknown Skill")
        path = self.root / "skills" / skill_id / "SKILL.md"
        body = path.read_text(encoding="utf-8")
        if len(body) > self.max_body_chars:
            raise ValueError("Skill body exceeds context budget; use separate resources")
        return {"manifest": self._metadata[skill_id], "body": body}

    load = load_skill

    def load_reference(self, skill_id: str, resource: str) -> dict[str, Any]:
        manifest = self._metadata.get(skill_id)
        if not manifest:
            raise ValueError("unknown Skill")
        base = (self.root / "skills" / skill_id).resolve()
        target = (base / resource).resolve()
        if not target.is_relative_to(base) or target.suffix not in (".md", ".json", ".txt"):
            raise ValueError("unauthorized resource path")
        references = manifest.get("references", [])
        paths = {r.get("path", r.get("resource")) if isinstance(r, dict) else r for r in references}
        published_hash = manifest.get("files", {}).get(resource)
        if resource not in paths and not (resource.startswith("references/") and published_hash):
            raise ValueError("resource is not in the authorized Skill manifest")
        if published_hash and hashlib.sha256(target.read_bytes()).hexdigest() != published_hash:
            raise ValueError("authorized reference hash mismatch")
        return {"resource": resource, "skill_id": skill_id, "version": manifest.get("version"),
                "text": target.read_text(encoding="utf-8"), "source_trust": "authorized_reference"}

    def search_knowledge(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        path = self.root / "knowledge" / "evidence.jsonl"
        if not path.exists():
            return []
        tokens = query.lower().split()
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("license_status") not in {"approved", "approved_synthetic"}:
                continue
            score = sum(token in json.dumps(row, ensure_ascii=False).lower() for token in tokens)
            if score or not tokens:
                rows.append((score, row))
        return [row for _, row in sorted(rows, key=lambda x: -x[0])[:min(limit, 5)]]
