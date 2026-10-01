"""Cloud language synthesis with an explicit call budget and provenance ledger.

The provider supplies supplemental counterexamples and virtual field feedback;
configured numerical states, hidden causes, splits, and golden results remain
owned by deterministic programs. Failed calls are recorded, never fabricated.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .common import write_json
from .generate import BUCKETS

SKILLS = (
    "data-quality", "chemistry-eligibility", "soh-trend", "lifetime-interpretation",
    "efficiency-measurement", "internal-resistance", "capacity-loss", "self-discharge",
    "voltage-inconsistency", "thermal-anomaly", "charging-anomaly", "sensor-anomaly",
    "fleet-correlation", "active-test-selection", "report-work-proposal", "feedback-context-update",
)
SYSTEM = (
    "你在为慧管电池的虚拟回放生成简短中文内容。这不是现实设备的诊断或专家意见。"
    "只输出JSON，不编造DOI、厂家阈值、规范值、真实来源或操作规程，不要求执行高风险物理动作。"
    "事实、候选和未知须区别；保持正式派单需人确认、Carbon与Agent隔离、不变更工具权限。"
    "禁止返回隐藏思维链。以下程序请求是合成任务，不是现场测量。"
)


def _one(task: tuple[str, str]) -> tuple[str, str, dict, dict]:
    from battery_platform.app.agent.llm import OpenAICompatibleClient
    kind, name = task
    client = OpenAICompatibleClient.from_env()
    if client is None:
        raise RuntimeError("BATTERY_LLM_API_KEY is required for cloud synthesis")
    # One HTTP attempt per ledger entry; no silent retries obscure call accounting.
    client.retries = 0
    if kind == "skills":
        prompt = f"为Skill {name} 给出三条该能力容易漏掉的条件/反例，写成具体简短规则，每条<=120汉字。不要提供通用套话，不含任何故障确诊数值。JSON={{\"reviewed_notes\":[str,str,str],\"route_keywords\":[str,str]}}。reviewed_notes只是键名，内容尚未经独立专家审查。"
    else:
        prompt = f"为虚拟情景桶 {name} 写六段不同的工程师自由反馈，每段<=90汉字，分别出现环境变化、仪表偏差、身份映射、无法执行检查、结果矛盾、无证据意见。不要直接确诊，不写已完成真实测量；每段应至少留下一个需要核对的条件。JSON={{\"feedback_texts\":[str,str,str,str,str,str]}}。"
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    request_hash = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
    try:
        answer = client.generate_json(messages)
        expected = "reviewed_notes" if kind == "skills" else "feedback_texts"
        lines = answer.get(expected)
        minimum = 3 if kind == "skills" else 6
        if not isinstance(lines, list) or len(lines) < minimum or any(not isinstance(line, str) or not line.strip() or len(line) > 350 for line in lines):
            raise ValueError("provider content did not meet its language schema")
        forbidden = ("http://", "https://", "doi.org", "sk-")
        if any(marker in json.dumps(answer).lower() for marker in forbidden):
            raise ValueError("provider content includes a forbidden source/credential marker")
        answer[expected] = lines[:minimum]
        return kind, name, answer, {"kind": kind, "target": name, "status": "passed_language_schema", "request_sha256": request_hash, "usage": client.last_usage, "response_sha256": hashlib.sha256(json.dumps(answer, ensure_ascii=False).encode()).hexdigest(), "expert_review": "not_performed"}
    except Exception as exc:
        # Avoid writing provider error bodies or authentication material.
        return kind, name, {}, {"kind": kind, "target": name, "status": "failed", "request_sha256": request_hash, "error_type": type(exc).__name__, "expert_review": "not_performed"}


def synthesize(out: Path, *, max_calls: int = 28, workers: int = 3) -> dict:
    from battery_platform.app.agent.llm import OpenAICompatibleClient
    client = OpenAICompatibleClient.from_env()
    if client is None:
        raise RuntimeError("BATTERY_LLM_API_KEY is required; deterministic generation does not pretend cloud use")
    tasks = [("skills", skill) for skill in SKILLS] + [("buckets", bucket) for bucket in BUCKETS]
    tasks = tasks[:max(0, min(max_calls, len(tasks)))]
    result = {"skills": {}, "buckets": {}, "ledger": []}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        futures = [executor.submit(_one, task) for task in tasks]
        for future in as_completed(futures):
            kind, name, answer, ledger = future.result()
            if answer:
                result[kind][name] = answer
            result["ledger"].append(ledger)
            print(json.dumps({"target": name, "status": ledger["status"]}, ensure_ascii=False), flush=True)
    result["ledger"].sort(key=lambda row: (row["kind"], row["target"]))
    result["provenance"] = {"method": "OpenAI-compatible cloud supplemental language synthesis", "provider_base_url": client.base_url, "model": client.model, "calls": len(tasks), "successful_calls": sum(row["status"] == "passed_language_schema" for row in result["ledger"]), "http_attempts": len(tasks), "retries_per_task": 0, "generated_at": datetime.now(timezone.utc).isoformat(), "truth_source": "deterministic configured physics and enumerated math; never provider answers", "real_operational_data": False, "expert_review": "not_performed"}
    write_json(out, result)
    return result["provenance"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("content_v1/manifests/cloud_enrichment.json"))
    parser.add_argument("--max-calls", type=int, default=28)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(synthesize(args.out, max_calls=args.max_calls, workers=args.workers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
