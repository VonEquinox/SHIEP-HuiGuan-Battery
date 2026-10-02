"""Versioned, source-spanned feedback facts. Free text remains the authority."""
from __future__ import annotations

import hashlib
from typing import Any


_SENTENCE_TERMINATORS = frozenset("。！？!?")


def _numeric_period(text: str, index: int) -> bool:
    """Return whether ``text[index]`` is a numeric decimal separator.

    A period is a sentence boundary in ordinary prose, but it is part of a
    value in decimals, dotted dates, versions and scientific notation.  The
    immediate digit check intentionally keeps the rule small and auditable:
    ``1.2``, ``1.2e-3`` and ``2026.10.02`` stay in one source span while a
    final ``V.`` still terminates the sentence.
    """
    return (text[index] == "." and index + 1 < len(text) and text[index + 1].isdigit()
            and (index == 0 or text[index - 1].isdigit() or text[index - 1] in "+-−"
                 or text[index - 1].isspace() or "\u3400" <= text[index - 1] <= "\u9fff"))


def _feedback_spans(text: str) -> list[tuple[int, int]]:
    """Split feedback without cutting numeric tokens and retain raw spans.

    The returned offsets point into the original string.  Leading/trailing
    whitespace is excluded from each claim, but no characters inside a claim
    are rewritten.  Newlines act as soft sentence boundaries so each source
    span remains useful for later citation.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        boundary = char in _SENTENCE_TERMINATORS or (char == "." and not _numeric_period(text, index))
        if char == "\n" or boundary:
            end = index
            if boundary:
                # Keep a run such as "?!" attached to the same claim.
                while end + 1 < len(text) and text[end + 1] in _SENTENCE_TERMINATORS:
                    end += 1
                index = end
                end += 1
            left = start
            while left < end and text[left].isspace():
                left += 1
            right = end
            while right > left and text[right - 1].isspace():
                right -= 1
            if left < right:
                spans.append((left, right))
            start = index + 1
        index += 1
    left = start
    while left < len(text) and text[left].isspace():
        left += 1
    right = len(text)
    while right > left and text[right - 1].isspace():
        right -= 1
    if left < right:
        spans.append((left, right))
    return spans


def extract_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    text = str(feedback.get("free_text", ""))
    if len(text) > 20000:
        raise ValueError("feedback exceeds extraction budget")
    trust = feedback.get("verification_status", "reported")
    if trust not in ("reported", "measurement_supported", "independently_verified", "contradicted"):
        raise ValueError("invalid feedback verification status")
    author = str(feedback.get("author_id", "unknown"))
    candidates = []
    for begin, end in _feedback_spans(text):
        claim = text[begin:end]
        candidates.append({"fact_id": "feedback-fact-" + hashlib.sha256((author + str(begin) + claim).encode()).hexdigest()[:12],
                           "claim": claim, "span": {"start": begin, "end": end}, "source_text": text[begin:end],
                           "author_id": author, "extraction_model": "span-extractor-v2-numeric",
                           "trust": trust, "kind": "reported_statement"})
    measurements = feedback.get("measurements", [])
    for i, measurement in enumerate(measurements):
        if not isinstance(measurement, dict) or "value" not in measurement or not measurement.get("unit"):
            raise ValueError("measurements require metric/value/unit")
        candidates.append({"fact_id": f"measurement-{feedback.get('observation_id', 'feedback')}-{i}",
                           "claim": f"{measurement.get('metric', 'measurement')}={measurement['value']} {measurement['unit']}",
                           "measurement": measurement, "span": None, "author_id": author,
                           "extraction_model": "structured-measurement-v1", "trust": "measurement_supported",
                           "kind": "observation", "source_field": "measurements", "source_index": i})
    # These fields carry explicit human assertions, not inferred outcome labels.
    # Keep their source locations so a late exclusion/unknown survives summary
    # pressure without turning it into a verified diagnosis.
    for field, kind, prefix in (("excluded_hypotheses", "counterevidence", "Excluded hypothesis"),
                                ("unresolved_items", "unknown", "Unresolved item"),
                                ("confirmed_hypotheses", "conclusion", "Reported confirmed hypothesis")):
        for i, value in enumerate(feedback.get(field, []) or []):
            candidates.append({"fact_id": f"{field}-{feedback.get('observation_id', 'feedback')}-{i}",
                               "claim": f"{prefix}: {value}", "span": None, "source_field": field,
                               "source_index": i, "author_id": author, "extraction_model": "structured-assertion-v1",
                               "trust": trust, "kind": kind})
    return {"free_text": text, "candidate_facts": candidates, "author_id": author,
            "feedback_id": str(feedback.get("feedback_id", feedback.get("observation_id", ""))),
            "installation_id": feedback.get("installation_id"), "root_scenario_id": feedback.get("root_scenario_id"),
            "provenance": feedback.get("provenance", "declared_operational"),
            "version": int(feedback.get("version", 1)), "extraction_model": "span-extractor-v2-numeric",
            "label_guards": {"not_measured_is_not_negative": True,
                             "intervention_prevents_false_positive_label": bool(feedback.get("performed_actions")),
                             "unfinished_horizon_is_not_false_positive": not feedback.get("prediction_horizon_complete", False)}}
