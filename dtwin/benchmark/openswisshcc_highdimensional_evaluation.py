"""Avaliação tardia do batch 3D v13, após predições cegas completas."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.metrics import compute_benchmark_metrics
from dtwin.benchmark.models import (
    BenchmarkCaseResult,
    BenchmarkStatus,
    GroundTruthLabel,
    ModelResult,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_highdimensional_batch import (
    validate_highdimensional_blind_bundle,
)
from dtwin.benchmark.openswisshcc_highdimensional_batch_inference import (
    PREDICTION_SCHEMA,
    PROGRESS_SCHEMA,
    SUMMARY_SCHEMA,
    _load_batch_protocol,
    _validate_existing_prediction,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import _atomic_json
from dtwin.benchmark.reporting import write_run_outputs
from dtwin.core import PipelineError, now_utc, sha256_of


EVALUATION_SCHEMA = "argos-openswisshcc-highdimensional-evaluation-v1"
TIME_GATE_SECONDS = 180.0


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser um objeto JSON.")
    return value


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def validate_blind_highdimensional_run(
    *,
    bundle_root: Path,
    protocol_path: Path,
    inference_root: Path,
    expected_case_count: int = 87,
    max_case_seconds: float = TIME_GATE_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Valide toda a evidência cega antes de permitir a leitura do ground truth."""
    bundle_root = Path(bundle_root).resolve()
    inference_root = Path(inference_root).resolve()
    bundle = validate_highdimensional_blind_bundle(bundle_root)
    protocol = _load_batch_protocol(protocol_path)
    if (
        bundle.get("case_count") != expected_case_count
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != bundle.get("case_ids")
        or protocol.get("bundle_signature") != bundle.get("bundle_signature")
        or protocol.get("bundle_sha256") != sha256_of(bundle_root / "bundle.json")
        or float(protocol.get("time_gate_seconds_per_case", -1)) != float(max_case_seconds)
    ):
        raise PipelineError("Bundle ou protocolo v13 não corresponde à coorte congelada.")

    progress_path = inference_root / "progress.json"
    summary_path = inference_root / "summary.json"
    progress = _load_json(progress_path, "Progresso v13")
    summary = _load_json(summary_path, "Resumo v13")
    safe_false = ("ground_truth_read", "metrics_calculated", "holdout_opened")
    safe_true = ("research_only", "requires_human_review")
    if (
        progress.get("schema") != PROGRESS_SCHEMA
        or progress.get("status") != "complete"
        or progress.get("completed_case_count") != expected_case_count
        or progress.get("pending_case_count") != 0
        or summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("status") != "blind_predictions_complete"
        or summary.get("case_count") != expected_case_count
        or summary.get("progress_sha256") != sha256_of(progress_path)
        or summary.get("protocol_signature") != protocol.get("protocol_signature")
        or progress.get("protocol_signature") != protocol.get("protocol_signature")
        or any(
            progress.get(key) is not False or summary.get(key) is not False
            for key in safe_false
        )
        or any(
            progress.get(key) is not True or summary.get(key) is not True
            for key in safe_true
        )
        or progress.get("clinical_use_allowed") is not False
        or summary.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Run v13 não comprova conclusão cega e salvaguardas.")

    records = progress.get("predictions")
    case_ids = list(bundle["case_ids"])
    if (
        not isinstance(records, list)
        or [item.get("case_id") for item in records] != case_ids
        or len({item.get("case_id") for item in records}) != expected_case_count
    ):
        raise PipelineError("Progresso v13 não cobre exatamente a coorte congelada.")
    stack_by_case = {item["case_id"]: item for item in bundle["stacks"]}
    predictions: dict[str, dict[str, Any]] = {}
    for progress_record in records:
        case_id = progress_record["case_id"]
        path = inference_root / "predictions" / f"{case_id}.json"
        if sha256_of(path) != progress_record.get("prediction_sha256"):
            raise PipelineError(f"Hash da previsão diverge no caso {case_id}.")
        prediction = _validate_existing_prediction(
            path,
            protocol=protocol,
            stack_record=stack_by_case[case_id],
        )
        elapsed = prediction.get("request_elapsed_seconds")
        if (
            prediction.get("schema") != PREDICTION_SCHEMA
            or not isinstance(elapsed, (int, float))
            or float(elapsed) < 0
            or float(elapsed) > float(max_case_seconds)
            or prediction.get("research_only") is not True
            or prediction.get("clinical_use_allowed") is not False
            or prediction.get("requires_human_review") is not True
            or prediction.get("ground_truth_read") is not False
            or prediction.get("metrics_calculated") is not False
            or prediction.get("holdout_opened") is not False
        ):
            raise PipelineError(f"Previsão v13 viola tempo ou salvaguardas: {case_id}.")
        predictions[case_id] = prediction

    classes = {
        label: sum(item["classification"] == label for item in predictions.values())
        for label in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")
    }
    timings = [
        float(predictions[case_id]["request_elapsed_seconds"])
        for case_id in case_ids
    ]
    if (
        summary.get("classification_counts_without_ground_truth") != classes
        or summary.get("all_time_gates_passed") is not True
        or summary.get("request_seconds_min") != min(timings)
        or summary.get("request_seconds_median") != statistics.median(timings)
        or summary.get("request_seconds_max") != max(timings)
    ):
        raise PipelineError("Resumo v13 diverge das previsões individuais.")
    return bundle, protocol, predictions


def _load_development_labels(
    path: Path,
    *,
    expected_case_ids: list[str],
    expected_positive: int,
    expected_negative: int,
    expected_excluded_case_id: str | None = None,
) -> tuple[dict[str, dict[str, Any]], str]:
    resolved = Path(path).resolve()
    if (
        resolved.name != "development_labels.jsonl"
        or resolved.parent.name != "protected_ground_truth"
        or "holdout" in str(resolved).lower()
    ):
        raise PipelineError("Apenas development_labels.jsonl protegido é autorizado.")
    try:
        rows = [
            json.loads(line)
            for line in resolved.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Labels protegidos de desenvolvimento são inválidos.") from exc
    required = {
        "schema",
        "case_id",
        "public_subject_id",
        "label",
        "target_condition",
        "label_basis",
        "review_status",
    }
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != required
            or row.get("schema") != "argos-openswisshcc-ground-truth-v1"
            or row.get("label") not in {"POSITIVE", "NEGATIVE"}
            or row.get("target_condition") != "hcc_presence"
        ):
            raise PipelineError("Registro protegido de desenvolvimento incompatível.")
        case_id = str(row.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in by_id:
            raise PipelineError("Labels de desenvolvimento possuem ID inválido ou duplicado.")
        by_id[case_id] = row

    expected = set(expected_case_ids)
    if len(expected) != len(expected_case_ids) or any(
        case_id not in by_id for case_id in expected
    ):
        raise PipelineError("Labels protegidos não cobrem exatamente a coorte v13.")
    extras = set(by_id) - expected
    allowed_extras = {expected_excluded_case_id} if expected_excluded_case_id else set()
    if expected_excluded_case_id in expected if expected_excluded_case_id else False:
        raise PipelineError("O caso tecnicamente excluído ainda pertence ao bundle v13.")
    if extras != allowed_extras:
        raise PipelineError(
            "Labels protegidos contêm casos extras não autorizados pela exclusão técnica."
        )

    selected = [by_id[case_id] for case_id in expected_case_ids]
    positive = sum(row["label"] == "POSITIVE" for row in selected)
    negative = sum(row["label"] == "NEGATIVE" for row in selected)
    if (positive, negative) != (expected_positive, expected_negative):
        raise PipelineError(
            f"Contagem protegida inesperada: positive={positive}, negative={negative}."
        )
    return (
        {case_id: by_id[case_id] for case_id in expected_case_ids},
        sha256_of(resolved),
    )


def evaluate_highdimensional_development(
    *,
    bundle_root: Path,
    protocol_path: Path,
    inference_root: Path,
    protected_labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
    expected_positive: int = 39,
    expected_negative: int = 48,
    expected_excluded_case_id: str | None = None,
    max_case_seconds: float = TIME_GATE_SECONDS,
) -> dict[str, Any]:
    """Abra labels uma única vez, somente após validar o run v13 completo."""
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels v13 exige autorização explícita.")
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretório de avaliação v13 já existe; sobrescrita recusada.")

    bundle, protocol, predictions = validate_blind_highdimensional_run(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        inference_root=inference_root,
        expected_case_count=expected_case_count,
        max_case_seconds=max_case_seconds,
    )
    labels, labels_hash = _load_development_labels(
        protected_labels_path,
        expected_case_ids=list(bundle["case_ids"]),
        expected_positive=expected_positive,
        expected_negative=expected_negative,
        expected_excluded_case_id=expected_excluded_case_id,
    )
    results: list[BenchmarkCaseResult] = []
    for case_id in bundle["case_ids"]:
        prediction = predictions[case_id]
        model_result = ModelResult(prediction["classification"])
        truth = GroundTruthLabel(labels[case_id]["label"].lower())
        results.append(BenchmarkCaseResult(
            case_id=case_id,
            dataset="openswisshcc-development",
            input_format="NIFTI",
            truth=truth,
            status=(
                BenchmarkStatus.INCONCLUSIVE
                if model_result is ModelResult.INCONCLUSIVE
                else BenchmarkStatus.DECISIVE
            ),
            prediction=model_result,
            input_hashes={
                "stack_manifest_sha256": prediction["stack_manifest_sha256"]
            },
            protected_ground_truth_hashes={
                "development_labels.jsonl": labels_hash
            },
            durations_seconds={
                "total": float(prediction["request_elapsed_seconds"])
            },
            report_path=str(
                Path(inference_root).resolve()
                / "predictions"
                / f"{case_id}.json"
            ),
            target_condition="focal_liver_lesion_suspicion",
            positive_subtype=(
                "hcc_suspicious"
                if truth is GroundTruthLabel.POSITIVE
                else None
            ),
            label_basis=str(labels[case_id]["label_basis"]),
            review_status=str(labels[case_id]["review_status"]),
            extra={
                "source_target_condition": labels[case_id]["target_condition"],
                "requires_human_review": True,
            },
        ))
    metrics = compute_benchmark_metrics(
        results,
        minimum_sensitivity=0.75,
        minimum_specificity=0.75,
    )
    timings = [
        float(item["request_elapsed_seconds"])
        for item in predictions.values()
    ]
    timing = {
        "case_count": len(timings),
        "mean_seconds": statistics.fmean(timings),
        "median_seconds": statistics.median(timings),
        "p95_seconds": _quantile(timings, 0.95),
        "max_seconds": max(timings),
        "limit_seconds": float(max_case_seconds),
        "passed_case_count": sum(value <= max_case_seconds for value in timings),
        "passed": max(timings) <= max_case_seconds,
    }
    overall_passed = bool(metrics["gate"]["passed"] and timing["passed"])
    run_manifest = {
        "schema": EVALUATION_SCHEMA,
        "run_id": "openswisshcc-dev-v13-highdimensional",
        "created_at": now_utc(),
        "code_commit": None,
        "git_dirty": True,
        "model_id": protocol["model_id"],
        "model_parameter_scale": "4B",
        "experimental_strategy": "native_highdimensional_t1_venous_up_to_50_slices",
        "protocol_signature": protocol["protocol_signature"],
        "bundle_signature": bundle["bundle_signature"],
        "inference_progress_sha256": sha256_of(
            Path(inference_root) / "progress.json"
        ),
        "inference_summary_sha256": sha256_of(
            Path(inference_root) / "summary.json"
        ),
        "protected_ground_truth_sha256": labels_hash,
        "excluded_technical_case_id": expected_excluded_case_id,
        "ground_truth_opened_after_complete_inference_validation": True,
        "inconclusive_counts_as_error": True,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    staging = output_dir.with_name(
        f".{output_dir.name}.staging.{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True)
    try:
        write_run_outputs(staging, run_manifest, results, metrics)
        _atomic_json(staging / "timing_metrics.json", timing)
        evaluation = {
            "schema": EVALUATION_SCHEMA,
            "status": "development_evaluated",
            "case_count": expected_case_count,
            "excluded_technical_case_id": expected_excluded_case_id,
            "metrics": metrics,
            "timing": timing,
            "qualification_gate": {
                "sensitivity_specificity_gate": metrics["gate"],
                "time_gate": timing,
                "passed": overall_passed,
            },
            "ground_truth_opened_after_complete_inference_validation": True,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _atomic_json(staging / "evaluation.json", evaluation)
        _publish_directory(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "output_dir": str(output_dir),
        "metrics": metrics,
        "timing": timing,
        "passed": overall_passed,
        "holdout_opened": False,
    }

