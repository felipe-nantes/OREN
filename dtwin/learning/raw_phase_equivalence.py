"""Auditable helpers for raw-vs-explicit phase pathway equivalence tests."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError, sha256_of

SCHEMA = "argos-raw-phase-equivalence-v1"


def verified_review(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        payload.get("schema") != "argos-raw-phase-review-gallery-v1"
        or payload.get("ground_truth_read") is not False
        or payload.get("lesion_masks_read") is not False
        or payload.get("inference_executed") is not False
        or not payload.get("protocol_signature")
    ):
        raise PipelineError("Manifesto da galeria de fases inválido ou contaminado.")
    for entry in payload.get("entries", []):
        image = Path(path).parent / str(entry.get("image") or "")
        if not image.is_file() or sha256_of(image) != entry.get("panel_sha256"):
            raise PipelineError(f"Painel de revisão ausente ou alterado: {entry.get('case_id')}")
    return payload


def selection_key(series_hashes: list[str]) -> str:
    return hashlib.sha256("\0".join(map(str, series_hashes)).encode("utf-8")).hexdigest()


def panel_hashes(paths: list[Path]) -> list[str]:
    return [sha256_of(Path(path)) for path in paths]


def _wilson(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def positive_arm_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    completed = sum(row.get("status") == "complete" for row in rows)
    positives = sum(
        row.get("status") == "complete"
        and row.get("prediction") == "POSITIVE"
        for row in rows
    )
    under_180 = sum(
        row.get("status") == "complete"
        and float(row.get("automatic_total_seconds") or float("inf")) <= 180.0
        for row in rows
    )
    equivalent = sum(row.get("panel_byte_equivalent") is True for row in rows)
    timings = sorted(
        float(row["automatic_total_seconds"])
        for row in rows
        if row.get("status") == "complete" and row.get("automatic_total_seconds") is not None
    )
    timing_summary = None if not timings else {
        "minimum": min(timings),
        "median": timings[len(timings) // 2],
        "mean": sum(timings) / len(timings),
        "maximum": max(timings),
    }
    return {
        "case_count": total,
        "completed_cases": completed,
        "completion_rate": completed / total if total else 0.0,
        "true_positives": positives,
        "false_negatives_or_failures": total - positives,
        "sensitivity": positives / total if total else 0.0,
        "sensitivity_ci95_wilson": _wilson(positives, total),
        "sensitivity_75_gate_passed": positives / total >= 0.75 if total else False,
        "within_180_seconds": under_180,
        "within_180_seconds_rate": under_180 / total if total else 0.0,
        "all_cases_within_180_seconds": under_180 == total and total > 0,
        "timing_seconds": timing_summary,
        "byte_equivalent_panel_sets": equivalent,
        "panel_equivalence_rate": equivalent / total if total else 0.0,
        "specificity": None,
        "specificity_unavailable_reason": "positive_only_arm",
        "simultaneous_75_75_gate_evaluable": False,
        "simultaneous_75_75_gate_passed": False,
    }


__all__ = ["SCHEMA", "panel_hashes", "positive_arm_metrics", "selection_key", "verified_review"]
