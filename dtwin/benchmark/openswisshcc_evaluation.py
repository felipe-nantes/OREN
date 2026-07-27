"""Avaliação pós-inferência OpenSwissHCC com abertura tardia do ground truth."""
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
from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.benchmark.openswisshcc_review import verify_panel_review
from dtwin.benchmark.reporting import write_run_outputs
from dtwin.core import PipelineError, now_utc


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


def _validate_inference_before_truth(
    *, inference_root: Path, frozen_ids: list[str], review_signature: str,
    experiment_signature: str, max_case_seconds: float
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = Path(inference_root).resolve()
    summary = _load_json(root / "inference_summary.json")
    if summary.get("schema") != "argos-openswisshcc-inference-batch-v1":
        raise PipelineError("Schema do resumo de inferência é incompatível.")
    if summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False:
        raise PipelineError("Resumo de inferência viola o isolamento pré-avaliação.")
    if summary.get("review_signature") != review_signature:
        raise PipelineError("Resumo não corresponde à revisão humana aprovada.")
    if summary.get("experiment_signature") != experiment_signature:
        raise PipelineError("Resumo não corresponde ao experimento congelado.")
    records = summary.get("records")
    if not isinstance(records, list) or summary.get("case_count") != len(records):
        raise PipelineError("Lista de casos da inferência é incompatível.")
    by_id = {str(item.get("case_id", "")): item for item in records}
    if len(by_id) != len(records) or sorted(by_id) != sorted(frozen_ids):
        raise PipelineError("Inferência não cobre exatamente a coorte congelada.")
    allowed_status = {"success_pending_human_review", "technical_failure", "timeout"}
    if any(item.get("status") not in allowed_status for item in records):
        raise PipelineError("Resumo contém status de inferência não autorizado.")
    for case_id, record in by_id.items():
        elapsed = record.get("elapsed_seconds")
        if not isinstance(elapsed, (int, float)) or elapsed < 0:
            raise PipelineError(f"Tempo inválido no caso {case_id}.")
        if record["status"] == "success_pending_human_review":
            case_dir = root / case_id
            report_path = case_dir / "medgemma_report.json"
            manifest_path = case_dir / "inference_manifest.json"
            if not report_path.is_file() or not manifest_path.is_file():
                raise PipelineError(f"Artefatos de sucesso ausentes no caso {case_id}.")
            manifest = _load_json(manifest_path)
            if _sha256(report_path) != record.get("report_sha256"):
                raise PipelineError(f"Hash do relatório diverge no caso {case_id}.")
            if manifest.get("ground_truth_read") is not False:
                raise PipelineError(f"Manifesto do caso {case_id} leu ground truth prematuramente.")
        if float(elapsed) > float(max_case_seconds) and record["status"] != "timeout":
            raise PipelineError(f"Caso {case_id} excede o teto sem status timeout.")
    return summary, by_id


def _load_labels_after_inference(
    path: Path, *, expected_ids: list[str], expected_positive: int, expected_negative: int
) -> tuple[dict[str, dict[str, Any]], str]:
    path = Path(path).resolve()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Ground truth protegido inválido: {exc}") from exc
    by_id: dict[str, dict[str, Any]] = {}
    required = {
        "schema", "case_id", "public_subject_id", "label", "target_condition",
        "label_basis", "review_status",
    }
    for row in rows:
        if set(row) != required or row.get("schema") != "argos-openswisshcc-ground-truth-v1":
            raise PipelineError("Registro protegido possui campos ou schema incompatíveis.")
        case_id = str(row.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in by_id:
            raise PipelineError("Ground truth contém case_id inválido ou duplicado.")
        if row.get("label") not in {"POSITIVE", "NEGATIVE"}:
            raise PipelineError("Ground truth contém label não autorizado.")
        if row.get("target_condition") != "hcc_presence":
            raise PipelineError("Ground truth não representa presença de HCC.")
        by_id[case_id] = row
    if sorted(by_id) != sorted(expected_ids):
        raise PipelineError("Ground truth não cobre exatamente a coorte inferida.")
    positive = sum(row["label"] == "POSITIVE" for row in rows)
    negative = sum(row["label"] == "NEGATIVE" for row in rows)
    if (positive, negative) != (int(expected_positive), int(expected_negative)):
        raise PipelineError(
            f"Contagem protegida inesperada: positive={positive}, negative={negative}."
        )
    return by_id, _sha256(path)


def _case_result(
    *, case_id: str, inference_root: Path, record: dict[str, Any],
    label: dict[str, Any], protected_hash: str
) -> BenchmarkCaseResult:
    truth = GroundTruthLabel(str(label["label"]).lower())
    status_raw = str(record["status"])
    prediction: ModelResult | None = None
    confidence: str | None = None
    report_path: str | None = None
    if status_raw == "success_pending_human_review":
        path = Path(inference_root) / case_id / "medgemma_report.json"
        envelope = _load_json(path)
        if envelope.get("case_id") != case_id or envelope.get("status") != "pending_review":
            raise PipelineError(f"Envelope final incompatível no caso {case_id}.")
        report = envelope.get("report")
        if not isinstance(report, dict):
            raise PipelineError(f"Relatório clínico estruturado ausente no caso {case_id}.")
        prediction = ModelResult(str(report.get("resultado_hipotese", "")))
        confidence = report.get("confianca")
        status = (
            BenchmarkStatus.INCONCLUSIVE
            if prediction is ModelResult.INCONCLUSIVE
            else BenchmarkStatus.DECISIVE
        )
        report_path = str(path.resolve())
    elif status_raw == "timeout":
        status = BenchmarkStatus.TIMEOUT
    else:
        status = BenchmarkStatus.FAILURE
    return BenchmarkCaseResult(
        case_id=case_id,
        dataset="openswisshcc-development",
        input_format="NIFTI",
        truth=truth,
        status=status,
        prediction=prediction,
        confidence=confidence,
        protected_ground_truth_hashes={"development_labels.jsonl": protected_hash},
        durations_seconds={"total": float(record["elapsed_seconds"])},
        error_type=(
            str(record.get("status"))
            if status in {BenchmarkStatus.FAILURE, BenchmarkStatus.TIMEOUT}
            else None
        ),
        error_message=record.get("error"),
        report_path=report_path,
        target_condition="focal_liver_lesion_suspicion",
        positive_subtype="hcc_suspicious" if truth is GroundTruthLabel.POSITIVE else None,
        label_basis=str(label.get("label_basis")),
        review_status=str(label.get("review_status")),
        extra={
            "source_target_condition": label.get("target_condition"),
            "requires_human_review": True,
        },
    )


def evaluate_reviewed_development_run(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    inference_root: Path, protected_labels_path: Path, output_dir: Path,
    multiphase_config: Path, fallback_config: Path,
    additional_configs: dict[str, Path] | None = None,
    expected_case_count: int = 88, expected_positive: int = 39,
    expected_negative: int = 49, max_case_seconds: float = 180.0,
) -> dict[str, Any]:
    """Valide toda a inferência antes de abrir os labels e produzir métricas."""
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretório de avaliação já existe; não será sobrescrito.")
    freeze = verify_experiment_freeze(
        freeze_path=freeze_path,
        panel_root=panel_root,
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        expected_case_count=expected_case_count,
        additional_configs=additional_configs,
    )
    review = verify_panel_review(review_path=review_path, panel_root=panel_root)
    frozen_ids = [str(item["case_id"]) for item in freeze["candidates"]]
    if sorted(str(item["case_id"]) for item in review["panels"]) != sorted(frozen_ids):
        raise PipelineError("Revisão e congelamento não cobrem a mesma coorte.")
    summary, inference = _validate_inference_before_truth(
        inference_root=inference_root,
        frozen_ids=frozen_ids,
        review_signature=review["review_signature"],
        experiment_signature=freeze["experiment_signature"],
        max_case_seconds=max_case_seconds,
    )

    labels, protected_hash = _load_labels_after_inference(
        protected_labels_path,
        expected_ids=frozen_ids,
        expected_positive=expected_positive,
        expected_negative=expected_negative,
    )
    results = [
        _case_result(
            case_id=case_id,
            inference_root=Path(inference_root).resolve(),
            record=inference[case_id],
            label=labels[case_id],
            protected_hash=protected_hash,
        )
        for case_id in sorted(frozen_ids)
    ]
    metrics = compute_benchmark_metrics(
        results,
        minimum_sensitivity=0.75,
        minimum_specificity=0.75,
    )
    elapsed = [float(record["elapsed_seconds"]) for record in inference.values()]
    timeouts = sum(record["status"] == "timeout" for record in inference.values())
    timing = {
        "case_count": len(elapsed),
        "mean_seconds": statistics.fmean(elapsed) if elapsed else None,
        "median_seconds": statistics.median(elapsed) if elapsed else None,
        "p95_seconds": _quantile(elapsed, 0.95),
        "max_seconds": max(elapsed) if elapsed else None,
        "limit_seconds": float(max_case_seconds),
        "timeout_count": timeouts,
        "passed": bool(
            elapsed and max(elapsed) <= float(max_case_seconds) and timeouts == 0
        ),
    }
    overall_passed = bool(metrics["gate"]["passed"] and timing["passed"])
    run_manifest = {
        "schema": "argos-openswisshcc-evaluation-v1",
        "run_id": freeze["experiment_version"],
        "created_at": now_utc(),
        "code_commit": None,
        "git_dirty": True,
        "model_id": "google/medgemma-1.5-4b-it",
        "model_parameter_scale": "4B",
        "experimental_strategy": json.dumps(
            {
                "candidate_kind_counts": {
                    kind: sum(
                        item["candidate_kind"] == kind for item in freeze["candidates"]
                    )
                    for kind in sorted({item["candidate_kind"] for item in freeze["candidates"]})
                },
                "config_raw_sha256": sorted(
                    {item["config_raw_sha256"] for item in freeze["candidates"]}
                ),
            },
            sort_keys=True,
        ),
        "review_signature": review["review_signature"],
        "experiment_signature": freeze["experiment_signature"],
        "inference_summary_sha256": _sha256(Path(inference_root) / "inference_summary.json"),
        "protected_ground_truth_sha256": protected_hash,
        "ground_truth_opened_after_complete_inference_validation": True,
        "inconclusive_counts_as_error": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        write_run_outputs(staging, run_manifest, results, metrics)
        (staging / "timing_metrics.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        final_gate = {
            "sensitivity_specificity_gate": metrics["gate"],
            "time_gate": timing,
            "passed": overall_passed,
            "claim": (
                "development_target_met"
                if overall_passed
                else "development_target_not_met"
            ),
            "holdout_not_evaluated": True,
        }
        (staging / "qualification_gate.json").write_text(
            json.dumps(final_gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "metrics": metrics,
        "timing": timing,
        "passed": overall_passed,
        "output_dir": str(output_dir),
        "ground_truth_opened_after_inference": True,
        "inference_case_count": summary["case_count"],
    }
