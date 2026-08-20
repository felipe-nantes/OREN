"""Label-free timing audit for the exact approved OpenSwissHCC v10 ROI path."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark import openswisshcc_localizer_enhancement_roi as enhancement
from dtwin.benchmark import openswisshcc_localizer_roi as morphology
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _validate_blind_run
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import verify_roi_freeze
from dtwin.benchmark.openswisshcc_localizer_roi_gate import verify_paired_review
from dtwin.benchmark.openswisshcc_localizer_roi_inference import (
    CASE_SCHEMA as SCORE_CASE_SCHEMA,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-localizer-roi-timing-case-v1"
RUN_SCHEMA = "argos-openswisshcc-localizer-roi-timing-run-v1"


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON do timing ROI v10 invalido: {path}") from exc


def _seconds(name: str, value: Any, maximum: float = 180.0) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= maximum:
        raise PipelineError(f"Tempo {name} ausente, invalido ou acima de {maximum}s.")
    return float(value)


def compose_case_timing(
    *, registration_seconds: float, localizer_seconds: float,
    morphology_render_seconds: float, enhancement_render_seconds: float,
    medgemma_scoring_seconds: float, limit_seconds: float = 180.0,
) -> dict[str, Any]:
    if not 0 < float(limit_seconds) <= 180:
        raise PipelineError("Limite do timing ROI v10 deve estar em (0,180].")
    stages = {
        "phase_registration": _seconds("phase_registration", registration_seconds),
        "lesion_localizer": _seconds("lesion_localizer", localizer_seconds),
        "morphology_roi_rendering": _seconds("morphology_roi_rendering", morphology_render_seconds),
        "enhancement_roi_rendering": _seconds("enhancement_roi_rendering", enhancement_render_seconds),
        "medgemma_4b_scoring": _seconds("medgemma_4b_scoring", medgemma_scoring_seconds),
    }
    total = sum(stages.values())
    return {
        "stages_seconds": stages,
        "prepared_benchmark_composite_seconds": total,
        "within_prepared_benchmark_180_seconds": total <= float(limit_seconds),
    }


def _assert_regeneration_matches(
    *, generated_manifest: dict[str, Any], approved_manifest_path: Path,
    generated_dir: Path, approved_dir: Path,
) -> str:
    approved = _load(approved_manifest_path)
    if generated_manifest != approved:
        raise PipelineError("Manifesto ROI regenerado divergiu do artefato aprovado.")
    for panel in approved.get("panels", []):
        name = str(panel.get("image", ""))
        generated = generated_dir / name
        original = approved_dir / name
        if (
            not name.endswith(".png")
            or not generated.is_file()
            or not original.is_file()
            or generated.stat().st_size != original.stat().st_size
            or _sha256(generated) != panel.get("sha256")
            or _sha256(original) != panel.get("sha256")
            or generated.read_bytes() != original.read_bytes()
        ):
            raise PipelineError(f"Painel ROI regenerado nao e byte-identico: {name}.")
    return _sha256(approved_manifest_path)


def profile_approved_roi_path(
    *, morphology_root: Path, enhancement_root: Path, review_path: Path,
    freeze_path: Path, config_path: Path, localizer_run: Path,
    scores_root: Path, input_manifest: Path, input_root: Path,
    registration_root: Path, output_root: Path,
    expected_case_count: int = 10, limit_seconds: float = 180.0,
) -> dict[str, Any]:
    """Regenerate approved panels and conservatively compose all measured stage times."""
    morphology_root = Path(morphology_root).resolve()
    enhancement_root = Path(enhancement_root).resolve()
    localizer_run = Path(localizer_run).resolve()
    scores_root = Path(scores_root).resolve()
    registration_root = Path(registration_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Relatorio de timing ROI v10 ja existe.")
    freeze = verify_roi_freeze(
        morphology_root=morphology_root, enhancement_root=enhancement_root,
        review_path=review_path, config_path=config_path, freeze_path=freeze_path,
        expected_case_count=expected_case_count,
    )
    review = verify_paired_review(
        morphology_root=morphology_root, enhancement_root=enhancement_root,
        review_path=review_path, expected_case_count=expected_case_count,
    )
    _score_summary, _features = _validate_blind_run(
        scores_root=scores_root, freeze=freeze, review=review,
        localizer_run=localizer_run, expected_case_count=expected_case_count,
    )
    morphology_sources = morphology._input_index(input_manifest, input_root)
    enhancement_sources = enhancement._inputs(input_manifest, input_root)
    case_ids = [case["case_id"] for case in review["cases"]]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v10time_{uuid.uuid4().hex[:8]}"
    scratch = output.parent / f"._v10render_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    scratch.mkdir()
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        for sequence, case_id in enumerate(case_ids, 1):
            alignment_path = registration_root / case_id / "alignment_manifest.json"
            alignment = _load(alignment_path)
            registered = enhancement._registered(case_id, registration_root)
            if (
                alignment.get("schema") != "argos-public-liver-mri-alignment-v1"
                or alignment.get("case_id") != case_id
                or alignment.get("cache_reused") is not False
                or alignment.get("research_only") is not True
                or alignment.get("clinical_use_allowed") is not False
            ):
                raise PipelineError(f"Registro original nao medido ou invalido: {case_id}.")
            localizer_path = localizer_run / case_id / "localizer_manifest.json"
            localizer_manifest = _load(localizer_path)
            score_path = scores_root / case_id / "mirrored_ab_manifest.json"
            score_manifest = _load(score_path)
            if (
                score_manifest.get("schema") != SCORE_CASE_SCHEMA
                or score_manifest.get("case_id") != case_id
                or score_manifest.get("end_to_end_measurement_complete") is not False
                or score_manifest.get("ground_truth_read") is not False
                or score_manifest.get("metrics_calculated") is not False
            ):
                raise PipelineError(f"Scoring cego invalido para timing: {case_id}.")

            case_scratch = scratch / case_id
            case_scratch.mkdir()
            morphology_destination = case_scratch / "morphology"
            enhancement_destination = case_scratch / "enhancement"

            render_started = time.perf_counter()
            generated_morphology = morphology._render_case(
                case_id=case_id, source=morphology_sources[case_id],
                localizer_dir=localizer_run / case_id, destination=morphology_destination,
                max_components=3, tile_size=448, roi_mm=80,
                max_image_pixels=4_000_000, max_input_bytes=8_000_000,
            )
            morphology_seconds = time.perf_counter() - render_started
            morphology_manifest_hash = _assert_regeneration_matches(
                generated_manifest=generated_morphology,
                approved_manifest_path=morphology_root / case_id / "roi_manifest.json",
                generated_dir=morphology_destination,
                approved_dir=morphology_root / case_id,
            )

            render_started = time.perf_counter()
            generated_enhancement = enhancement._render_case(
                case_id, enhancement_sources[case_id], registered,
                localizer_run / case_id, enhancement_destination,
                3, 448, 80, 4_000_000, 8_000_000,
            )
            enhancement_seconds = time.perf_counter() - render_started
            enhancement_manifest_hash = _assert_regeneration_matches(
                generated_manifest=generated_enhancement,
                approved_manifest_path=enhancement_root / case_id / "enhancement_roi_manifest.json",
                generated_dir=enhancement_destination,
                approved_dir=enhancement_root / case_id,
            )

            timing = compose_case_timing(
                registration_seconds=_seconds("phase_registration", alignment.get("elapsed_seconds")),
                localizer_seconds=_seconds("lesion_localizer", localizer_manifest.get("elapsed_seconds")),
                morphology_render_seconds=morphology_seconds,
                enhancement_render_seconds=enhancement_seconds,
                medgemma_scoring_seconds=_seconds("medgemma_4b_scoring", score_manifest.get("scoring_seconds")),
                limit_seconds=limit_seconds,
            )
            record = {
                "schema": CASE_SCHEMA, "sequence": sequence, "case_id": case_id, **timing,
                "registration_manifest_sha256": _sha256(alignment_path),
                "localizer_manifest_sha256": _sha256(localizer_path),
                "morphology_manifest_sha256": morphology_manifest_hash,
                "enhancement_manifest_sha256": enhancement_manifest_hash,
                "scoring_manifest_sha256": _sha256(score_path),
                "regenerated_panels_byte_identical": True,
                "composite_not_single_wall_clock_observation": True,
                "ground_truth_read": False, "metrics_calculated": False,
                "holdout_opened": False, "research_only": True,
                "clinical_use_allowed": False, "requires_human_review": True,
            }
            _write_json_atomic(staging / f"{case_id}.json", record)
            records.append(record)
            shutil.rmtree(case_scratch)

        totals = [record["prepared_benchmark_composite_seconds"] for record in records]
        summary = {
            "schema": RUN_SCHEMA,
            "status": "complete_prepared_benchmark_timing_audit",
            "case_count": len(records), "case_ids": case_ids,
            "experiment_signature": freeze["experiment_signature"],
            "review_signature": review["review_signature"],
            "scores_summary_sha256": _sha256(scores_root / "summary.json"),
            "mean_prepared_benchmark_composite_seconds": statistics.fmean(totals),
            "max_prepared_benchmark_composite_seconds": max(totals),
            "all_prepared_benchmark_cases_within_180_seconds": all(
                record["within_prepared_benchmark_180_seconds"] for record in records
            ),
            "prepared_benchmark_time_gate_evaluable": True,
            "production_end_to_end_time_gate_evaluable": False,
            "unmeasured_production_stages": ["dicom_ingestion", "liver_segmentation"],
            "shared_cohort_preflight_not_attributed_per_case": True,
            "timing_method": "conservative_sum_of_exact_case_stage_measurements",
            "regenerated_panels_byte_identical": True,
            "profile_wall_seconds": time.perf_counter() - started,
            "final_decision": None, "ground_truth_read": False,
            "metrics_calculated": False, "holdout_opened": False,
            "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
