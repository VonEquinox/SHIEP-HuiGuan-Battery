"""Job extension: snapshot/publish in short transactions; computation outside."""
from __future__ import annotations

from ..db import obj
from .engine import solve_scenario
from .schemas import Factor, PolicyRule, Scenario
from .storage import content_hash, input_snapshot, publish_result, require


def snapshot(c, job):
    payload = obj(job["payload"])
    scenario = require(c, "carbon_scenarios", payload["scenario_id"])
    if scenario["version"] != payload["expected_version"]:
        raise ValueError("carbon scenario version conflict")
    request = input_snapshot(c, scenario, payload.get("gamma"))
    if content_hash(obj(scenario["payload"])) != scenario["content_hash"]:
        raise ValueError("carbon scenario content hash differs from frozen version")
    return request


def compute(request, cancelled=None):
    return solve_scenario(
        Scenario.model_validate(request["scenario"]),
        {int(i): Factor.model_validate(v["payload"]) for i, v in request["factors"].items()},
        {int(i): PolicyRule.model_validate(v["payload"]) for i, v in request["rules"].items()},
        cancelled,
    )


def complete(c, job, result, request):
    return publish_result(c, job, result, request)

