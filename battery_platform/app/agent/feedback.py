"""Versioned, source-spanned feedback facts. Free text remains the authority."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def extract_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    text = str(feedback.get("free_text", ""))
    if len(text) > 20000:
        raise ValueError("feedback exceeds extraction budget")
    trust = feedback.get("verification_status", "reported")
    if trust not in ("reported", "measurement_supported", "independently_verified", "contradicted"):
        raise ValueError("invalid feedback verification status")
    author = str(feedback.get("author_id", "unknown"))
    candidates = []
    for match in re.finditer(r"[^\n。！？.!?]+[。！？.!?]?", text):
        claim = match.group().strip()
        if not claim:
            continue
        begin = match.start() + len(match.group()) - len(match.group().lstrip())
        end = begin + len(match.group().lstrip().rstrip())
        candidates.append({"fact_id": "feedback-fact-" + hashlib.sha256((author + str(begin) + claim).encode()).hexdigest()[:12],
                           "claim": claim, "span": {"start": begin, "end": end}, "source_text": text[begin:end],
                           "author_id": author, "extraction_model": "span-extractor-v1",
                           "trust": trust, "kind": "reported_statement"})
    measurements = feedback.get("measurements", [])
    for i, measurement in enumerate(measurements):
        if not isinstance(measurement, dict) or "value" not in measurement or not measurement.get("unit"):
            raise ValueError("measurements require metric/value/unit")
        candidates.append({"fact_id": f"measurement-{feedback.get('observation_id', 'feedback')}-{i}",
                           "claim": f"{measurement.get('metric', 'measurement')}={measurement['value']} {measurement['unit']}",
                           "measurement": measurement, "span": None, "author_id": author,
                           "extraction_model": "structured-measurement-v1", "trust": "measurement_supported",
                           "kind": "observation"})
    return {"free_text": text, "candidate_facts": candidates, "author_id": author,
            "feedback_id": str(feedback.get("feedback_id", feedback.get("observation_id", ""))),
            "installation_id": feedback.get("installation_id"), "root_scenario_id": feedback.get("root_scenario_id"),
            "provenance": feedback.get("provenance", "declared_operational"),
            "version": int(feedback.get("version", 1)), "extraction_model": "span-extractor-v1",
            "label_guards": {"not_measured_is_not_negative": True,
                             "intervention_prevents_false_positive_label": bool(feedback.get("performed_actions")),
                             "unfinished_horizon_is_not_false_positive": not feedback.get("prediction_horizon_complete", False)}}
