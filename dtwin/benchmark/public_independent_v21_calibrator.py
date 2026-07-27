"""Freeze and apply the v11 calibrator to label-blind external cohorts.

The module deliberately separates two moments:

* freezing reads the already completed *development* evaluation and the blind
  v11 signal bundle, but never reads the protected label file itself;
* scoring reads only raw external signals and the frozen calibrator.

This makes the operating point portable to LiverHccSeg and, after an explicit
future authorization, to the still-sealed OpenSwissHCC holdout.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v11_fusion import (
    EVALUATION_SCHEMA,
    WEIGHTS,
    _ecdf,
    _load_json,
    _load_jsonl,
    verify_fusion_protocol,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


CALIBRATOR_SCHEMA = "argos-public-independent-v21-v11-calibrator-v1"
RAW_SIGNAL_SCHEMA = "argos-public-independent-v21-raw-signals-v1"
SCORE_SCHEMA = "argos-public-independent-v21-calibrated-score-v1"
SCORE_SUMMARY_SCHEMA = "argos-public-independent-v21-calibrated-score-batch-v1"

_PROTECTED_EXTERNAL_KEYS = {
    "label",
    "labels",
    "diagnosis",
    "dataset",
    "dataset_id",
    "rag_class",
    "negative_subtype",
    "positive_subtype",
    "phenotype_tags",
    "target_condition",
    "lesion_mask",
    "tumor_mask",
}


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite(value: Any, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError("Sinal externo v21 nao e numerico.")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise PipelineError("Sinal externo v21 nao e finito ou viola o limite.")
    return result


def _contains_protected_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _PROTECTED_EXTERNAL_KEYS:
                return True
            if _contains_protected_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_protected_key(child) for child in value)
    return False


def freeze_v11_external_calibrator(
    *,
    bundle_root: Path,
    protocol_path: Path,
    development_evaluation_path: Path,
    output_path: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Freeze the full-development ECDF and already-declared v11 threshold."""

    protocol, rows = verify_fusion_protocol(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        expected_case_count=expected_case_count,
    )
    evaluation_path = Path(development_evaluation_path).resolve()
    evaluation = _load_json(evaluation_path)
    threshold = evaluation.get("apparent_threshold_for_future_calibrator_freeze")
    if (
        not isinstance(evaluation, dict)
        or evaluation.get("schema") != EVALUATION_SCHEMA
        or evaluation.get("case_count") != expected_case_count
        or evaluation.get("components") != WEIGHTS
        or evaluation.get("protocol_signature") != protocol["protocol_signature"]
        or evaluation.get("ground_truth_read") is not True
        or evaluation.get("metrics_calculated") is not True
        or evaluation.get("holdout_opened") is not False
        or evaluation.get("qualified") is not False
        or evaluation.get("research_only") is not True
        or evaluation.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Avaliacao de desenvolvimento v11 invalida para o freeze externo.")
    threshold_value = _finite(threshold)
    if not 0.0 <= threshold_value <= 1.0:
        raise PipelineError("Limiar externo v11 fora de [0, 1].")

    references = {
        name: sorted(_finite(row["signals"][name]) for row in rows)
        for name in WEIGHTS
    }
    if any(len(values) != expected_case_count for values in references.values()):
        raise PipelineError("Referencia ECDF externa incompleta.")

    payload: dict[str, Any] = {
        "schema": CALIBRATOR_SCHEMA,
        "status": "frozen_for_external_label_blind_scoring",
        "calibrator_name": "v11_full_development_weighted_ecdf",
        "development_case_count": expected_case_count,
        "components": WEIGHTS,
        "component_directions": {name: "higher_is_positive" for name in WEIGHTS},
        "reference_transform": "full_development_empirical_cdf_midrank_n_denominator",
        "reference_values": references,
        "threshold": threshold_value,
        "decision_rule": "POSITIVE iff weighted_ecdf_score >= threshold",
        "threshold_fitted_on_protected_development_labels": True,
        "development_gate_passed": bool(evaluation.get("development_gate_passed")),
        "development_qualified": False,
        "external_result_cannot_retroactively_qualify_development": True,
        "source": {
            "blind_bundle_summary_sha256": _sha256(Path(bundle_root).resolve() / "summary.json"),
            "blind_signals_sha256": _sha256(Path(bundle_root).resolve() / "signals.jsonl"),
            "fusion_protocol_sha256": _sha256(Path(protocol_path).resolve()),
            "fusion_protocol_signature": protocol["protocol_signature"],
            "development_evaluation_sha256": _sha256(evaluation_path),
            "protected_development_labels_sha256": evaluation.get("protected_development_labels_sha256"),
        },
        "time_gate_seconds": 180.0,
        "holdout_opened": False,
        "ground_truth_available_during_external_scoring": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["calibrator_signature"] = _canonical_sha(payload)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Calibrador externo v21 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, payload)
    return payload


def _load_calibrator(path: Path) -> dict[str, Any]:
    calibrator = _load_json(path)
    signed = (
        {key: value for key, value in calibrator.items() if key != "calibrator_signature"}
        if isinstance(calibrator, dict)
        else {}
    )
    references = calibrator.get("reference_values") if isinstance(calibrator, dict) else None
    if (
        not isinstance(calibrator, dict)
        or calibrator.get("schema") != CALIBRATOR_SCHEMA
        or calibrator.get("status") != "frozen_for_external_label_blind_scoring"
        or calibrator.get("calibrator_signature") != _canonical_sha(signed)
        or calibrator.get("components") != WEIGHTS
        or not isinstance(references, dict)
        or set(references) != set(WEIGHTS)
        or calibrator.get("holdout_opened") is not False
        or calibrator.get("ground_truth_available_during_external_scoring") is not False
    ):
        raise PipelineError("Calibrador externo v21 invalido ou adulterado.")
    count = calibrator.get("development_case_count")
    if not isinstance(count, int) or count <= 0:
        raise PipelineError("Calibrador externo sem tamanho de referencia.")
    for name in WEIGHTS:
        values = references[name]
        if (
            not isinstance(values, list)
            or len(values) != count
            or values != sorted(values)
        ):
            raise PipelineError("Distribuicao de referencia externa invalida.")
        for value in values:
            _finite(value)
    threshold = _finite(calibrator.get("threshold"))
    if not 0.0 <= threshold <= 1.0:
        raise PipelineError("Limiar do calibrador externo invalido.")
    return calibrator


def score_external_signals(
    *,
    calibrator_path: Path,
    signals_path: Path,
    output_dir: Path,
    expected_case_count: int | None = None,
) -> dict[str, Any]:
    """Apply a frozen v11 calibrator without opening any external labels."""

    calibrator_path = Path(calibrator_path).resolve()
    signals_path = Path(signals_path).resolve()
    calibrator = _load_calibrator(calibrator_path)
    rows = _load_jsonl(signals_path)
    if expected_case_count is not None and len(rows) != expected_case_count:
        raise PipelineError("Quantidade de sinais externos diverge do protocolo.")
    if not rows:
        raise PipelineError("Lote externo v21 vazio.")

    case_ids: list[str] = []
    results: list[dict[str, Any]] = []
    threshold = float(calibrator["threshold"])
    references = calibrator["reference_values"]
    for row in rows:
        case_id = str(row.get("case_id", ""))
        signals = row.get("signals")
        timings = row.get("component_elapsed_seconds", {})
        if (
            row.get("schema") != RAW_SIGNAL_SCHEMA
            or not case_id.startswith("anon-")
            or case_id in case_ids
            or not isinstance(signals, dict)
            or set(signals) != set(WEIGHTS)
            or not isinstance(timings, dict)
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("final_decision") is not None
            or row.get("holdout_opened") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or _contains_protected_key(row)
        ):
            raise PipelineError(f"Registro externo v21 invalido ou com dado protegido: {case_id!r}.")
        case_ids.append(case_id)
        raw = {name: _finite(signals[name]) for name in WEIGHTS}
        transformed = {name: _ecdf(raw[name], references[name]) for name in WEIGHTS}
        score = sum(float(WEIGHTS[name]) * transformed[name] for name in WEIGHTS)
        component_seconds = {str(name): _finite(value, minimum=0.0) for name, value in timings.items()}
        total_seconds = sum(component_seconds.values())
        results.append({
            "schema": SCORE_SCHEMA,
            "case_id": case_id,
            "raw_signals": raw,
            "transformed_signals": transformed,
            "weighted_ecdf_score": score,
            "threshold": threshold,
            "decision": "POSITIVE" if score >= threshold else "NEGATIVE",
            "component_elapsed_seconds": component_seconds,
            "total_component_seconds": total_seconds,
            "time_gate_180_seconds_passed": total_seconds <= 180.0,
            "calibrator_signature": calibrator["calibrator_signature"],
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        })

    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Score externo v21 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v21score_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        scores_path = staging / "scores.jsonl"
        scores_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in results),
            encoding="utf-8",
        )
        summary = {
            "schema": SCORE_SUMMARY_SCHEMA,
            "status": "complete_predictions_frozen_labels_still_closed",
            "case_count": len(results),
            "case_ids": case_ids,
            "scores_sha256": _sha256(scores_path),
            "source_signals_sha256": _sha256(signals_path),
            "calibrator_sha256": _sha256(calibrator_path),
            "calibrator_signature": calibrator["calibrator_signature"],
            "positive_prediction_count": sum(row["decision"] == "POSITIVE" for row in results),
            "negative_prediction_count": sum(row["decision"] == "NEGATIVE" for row in results),
            "all_time_gates_passed": all(row["time_gate_180_seconds_passed"] for row in results),
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
