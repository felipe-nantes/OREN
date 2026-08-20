"""Consolidate v21 single-class external arms without fabricating a combined metric."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.public_independent_v21_evaluation import (
    EVALUATION_SCHEMA as POSITIVE_SCHEMA,
)
from dtwin.benchmark.public_independent_v21_negative_evaluation import (
    EVALUATION_SCHEMA as NEGATIVE_SCHEMA,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CONSOLIDATION_SCHEMA = "argos-public-independent-v21-single-class-arms-consolidation-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Avaliacao externa v21 invalida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Avaliacao externa v21 deve ser objeto.")
    return value


def consolidate_v21_external_arms(
    *, positive_evaluation_path: Path, negative_evaluation_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Report both arms side by side and explicitly refuse a pooled matrix."""

    positive_path = Path(positive_evaluation_path).resolve()
    negative_path = Path(negative_evaluation_path).resolve()
    positive = _load(positive_path)
    negative = _load(negative_path)
    if (
        positive.get("schema") != POSITIVE_SCHEMA
        or positive.get("evaluation_scope") != "positive_only_external_sensitivity_stress"
        or positive.get("positive_count") != positive.get("case_count")
        or positive.get("negative_count") != 0
        or positive.get("specificity") is not None
        or positive.get("simultaneous_75_75_gate_evaluated") is not False
        or positive.get("qualified") is not False
        or positive.get("holdout_opened") is not False
        or positive.get("protected_public_ground_truth_read") is not True
    ):
        raise PipelineError("Braco positivo v21 invalido para consolidacao.")
    if (
        negative.get("schema") != NEGATIVE_SCHEMA
        or negative.get("evaluation_scope") != "negative_only_secondary_specificity_domain_shift_stress"
        or negative.get("negative_count") != negative.get("case_count")
        or negative.get("positive_count") != 0
        or negative.get("sensitivity") is not None
        or negative.get("dataset_class_confounding") is not True
        or negative.get("combined_primary_metric_allowed") is not False
        or negative.get("simultaneous_75_75_gate_evaluated") is not False
        or negative.get("qualified") is not False
        or negative.get("holdout_opened") is not False
        or negative.get("protected_public_ground_truth_read") is not True
    ):
        raise PipelineError("Braco negativo v21 invalido para consolidacao.")
    positive_calibrator = positive.get("source_hashes", {}).get("calibrator_sha256")
    negative_calibrator = negative.get("source_hashes", {}).get("calibrator_sha256")
    if not positive_calibrator or positive_calibrator != negative_calibrator:
        raise PipelineError("Bracos v21 nao compartilham o mesmo calibrador congelado.")
    sensitivity = float(positive["sensitivity"])
    specificity = float(negative["specificity"])
    sensitivity_ci = [float(value) for value in positive["sensitivity_95_wilson"]]
    specificity_ci = [float(value) for value in negative["specificity_95_wilson"]]
    positive_max = float(positive["timing_seconds"]["maximum"])
    negative_max = float(negative["timing_seconds"]["maximum"])
    result = {
        "schema": CONSOLIDATION_SCHEMA,
        "status": "external_single_class_arms_pass_point_gates_not_finally_qualified",
        "arms": {
            "liverhccseg_positive": {
                "case_count": positive["case_count"],
                "tp": positive["confusion_matrix_positive_arm"]["tp"],
                "fn": positive["confusion_matrix_positive_arm"]["fn"],
                "sensitivity": sensitivity,
                "sensitivity_95_wilson": sensitivity_ci,
                "time_maximum_seconds": positive_max,
                "evaluation_sha256": _sha256(positive_path),
            },
            "chaos_negative": {
                "case_count": negative["case_count"],
                "tn": negative["confusion_matrix_negative_arm"]["tn"],
                "fp": negative["confusion_matrix_negative_arm"]["fp"],
                "specificity": specificity,
                "specificity_95_wilson": specificity_ci,
                "time_maximum_seconds": negative_max,
                "evaluation_sha256": _sha256(negative_path),
                "human_quality_caveat": "quality inferior to prior galleries but technically approved",
            },
        },
        "point_estimate_gates": {
            "sensitivity_at_least_75": sensitivity >= 0.75,
            "specificity_at_least_75": specificity >= 0.75,
            "both_passed": sensitivity >= 0.75 and specificity >= 0.75,
        },
        "confidence_interval_lower_bound_gates": {
            "sensitivity_lower_at_least_75": sensitivity_ci[0] >= 0.75,
            "specificity_lower_at_least_75": specificity_ci[0] >= 0.75,
            "both_passed": sensitivity_ci[0] >= 0.75 and specificity_ci[0] >= 0.75,
        },
        "time_gate": {
            "threshold_seconds": 180.0,
            "maximum_across_arms_seconds": max(positive_max, negative_max),
            "both_arms_passed": (
                positive.get("time_gate_180_seconds_passed") is True
                and negative.get("time_gate_180_seconds_passed") is True
                and max(positive_max, negative_max) <= 180.0
            ),
        },
        "pooled_confusion_matrix": None,
        "pooled_metrics_forbidden": True,
        "pooled_metrics_forbidden_reason": "class is confounded with dataset and each arm is single-class",
        "simultaneous_same_domain_75_75_evaluated": False,
        "qualified": False,
        "qualification_reason": "requires one frozen balanced same-domain holdout evaluation",
        "next_required_evidence": "OpenSwissHCC subjects 045-088, label-blind inference then one authorized evaluation",
        "shared_calibrator_sha256": positive_calibrator,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Consolidacao externa v21 ja existe; recuso sobrescrever.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v21_consolidation_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "consolidation.json", result)
        report = (
            "# Consolidação v21 — braços públicos externos\n\n"
            f"- Sensibilidade LiverHccSeg: {100*sensitivity:.2f}% "
            f"(IC95% {100*sensitivity_ci[0]:.2f}%–{100*sensitivity_ci[1]:.2f}%)\n"
            f"- Especificidade CHAOS: {100*specificity:.2f}% "
            f"(IC95% {100*specificity_ci[0]:.2f}%–{100*specificity_ci[1]:.2f}%)\n"
            f"- Maior tempo: {max(positive_max, negative_max):.2f} s\n"
            "- Gates de ponto 75%/75%: PASS nos braços separados\n"
            f"- Gates dos limites inferiores dos IC95%: "
            f"{'PASS' if result['confidence_interval_lower_bound_gates']['both_passed'] else 'FAIL'}\n\n"
            "Não existe matriz combinada válida: classe e dataset estão confundidos. "
            "A qualificação final exige uma avaliação única, congelada e balanceada no mesmo domínio. "
            "O holdout OpenSwissHCC permanece fechado.\n"
        )
        (staging / "report.md").write_text(report, encoding="utf-8")
        _publish_directory(staging, output_dir)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
