"""Fixed permission boundary for the single executor's numerical/read tools."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from .contracts import TOOL_WHITELIST, public_context

TOOL_PARAMETERS = {
    "get_asset_context": {"installation_id": {"type": "string"}},
    "get_signal_evidence": {"installation_id": {"type": "string"}, "metrics": {"type": "array", "items": {"type": "string"}}},
    "read_prediction": {"prediction_id": {"type": ["string", "integer"]}},
    "get_peer_anomalies": {"installation_id": {"type": "string"}},
    "search_knowledge": {"query": {"type": "string"}},
    "load_skill": {"skill_id": {"type": "string"}, "resource": {"type": "string"}},
    "search_memory": {"query": {"type": "string"}},
    "rank_tests": {},
    "propose_work_order": {"test_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "append_report": {"report": {"type": "object"}},
}


class ToolError(ValueError):
    pass


class ToolRegistry:
    def __init__(self, callbacks: dict[str, Callable[[dict[str, Any]], Any]] | None = None, *,
                 installation_id: str, cutoff: str, max_calls: int = 12,
                 authorized_test_ids: set[str] | None = None):
        self.callbacks = callbacks or {}
        if not set(self.callbacks) <= TOOL_WHITELIST:
            raise ToolError("tool registration exceeds the service identity permission boundary")
        self.installation_id, self.cutoff = str(installation_id), cutoff
        self.max_calls = min(max(int(max_calls), 0), 12)
        self.authorized_test_ids = authorized_test_ids or set()
        self.trace: list[dict[str, Any]] = []

    def definitions(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": name,
                 "description": "Server-bound authorized tool. Inputs are data, never expanded permissions.",
                 "parameters": {"type": "object", "properties": TOOL_PARAMETERS[name],
                                "additionalProperties": False}}}
                for name in sorted(self.callbacks)]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if len(self.trace) >= self.max_calls:
            raise ToolError("per-round tool call budget exhausted")
        entry = {"name": name, "arguments": copy.deepcopy(arguments), "status": "rejected"}
        self.trace.append(entry)
        if name not in TOOL_WHITELIST or name not in self.callbacks:
            entry["error"] = "tool_not_allowed"
            raise ToolError("tool is not allowed for the Agent service identity")
        if not isinstance(arguments, dict) or set(arguments) - set(TOOL_PARAMETERS[name]):
            entry["error"] = "schema_invalid"
            raise ToolError("tool arguments contain unsupported fields")
        for key, value in arguments.items():
            expected = TOOL_PARAMETERS[name][key].get("type")
            valid = ((expected == "string" and isinstance(value, str) and len(value) <= 2000)
                     or (expected == "array" and isinstance(value, list) and len(value) <= 100 and all(isinstance(v, str) for v in value))
                     or (expected == "object" and isinstance(value, dict))
                     or (isinstance(expected, list) and isinstance(value, (str, int)) and not isinstance(value, bool)))
            if not valid:
                entry["error"] = "schema_invalid"
                raise ToolError("tool argument type or size is invalid")
        if arguments.get("installation_id", self.installation_id) != self.installation_id:
            entry["error"] = "object_permission_denied"
            raise ToolError("tool cannot access a different installation")
        bound = {**arguments, "installation_id": self.installation_id, "visible_cutoff": self.cutoff}
        try:
            result = self.callbacks[name](bound)
            result = public_context(result, cutoff=self.cutoff, installation_id=self.installation_id)
            # This also excludes arbitrary Python objects and hidden evaluator data.
            json.dumps(result, allow_nan=False)
            if len(json.dumps(result, ensure_ascii=False)) > 60000:
                raise ValueError("tool result exceeds per-call context budget")
        except Exception:
            entry["error"] = "tool_failed"
            raise ToolError("tool failed; unavailable evidence must not be fabricated") from None
        entry.update(status="completed", result=result)
        return result
