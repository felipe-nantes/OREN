"""Blind union of venous and registered-arterial MR lesion candidates."""
from __future__ import annotations

import shutil
import statistics
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    _valid_localizer_run_schema,
    _validate_localizer,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    _input_index,
    _load,
    _registered_paths,
    _selection,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA,
    RUN_SCHEMA,
    TASK,
    Localizer,
    _save_mask_atomic,
    candidate_features,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

ALGORITHM_VERSION = "venous-registered-arterial-union-v22"


def combine_candidate_masks(
    *, venous_candidate_path: Path, arterial_candidate_path: Path, output_path: Path
) -> dict[str, int]:
    """Create an exact binary union after validating NIfTI geometry."""

    venous = nib.load(str(venous_candidate_path))
    arterial = nib.load(str(arterial_candidate_path))
    if venous.shape != arterial.shape or not np.allclose(
        venous.affine, arterial.affine, rtol=0, atol=1e-5
    ):
        raise PipelineError("Geometria dos candidatos multifasicos v22 divergiu.")
    venous_mask = np.asarray(venous.dataobj) > 0
    arterial_mask = np.asarray(arterial.dataobj) > 0
    union = venous_mask | arterial_mask
    _save_mask_atomic(union, venous, Path(output_path))
    return {
        "venous_voxels": int(venous_mask.sum()),
        "arterial_voxels": int(arterial_mask.sum()),
        "intersection_voxels": int((venous_mask & arterial_mask).sum()),
        "union_voxels": int(union.sum()),
        "new_arterial_voxels": int((arterial_mask & ~venous_mask).sum()),
    }


def run_arterial_union_localizer(
    *,
    input_manifest_path: Path,
    input_root: Path,
    alignment_root: Path,
    selection_manifest_path: Path,
    venous_localizer_root: Path,
    output_root: Path,
    case_ids: list[str],
    localizer: Localizer,
    max_combined_seconds: float = 150.0,
    runtime_guard: str | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one extra arterial pass and union it with the frozen venous output."""

    if not 0 < float(max_combined_seconds) <= 180:
        raise PipelineError("Orcamento combinado do localizador deve estar em (0,180].")
    full_order, modes = _selection(selection_manifest_path)
    selected = list(case_ids)
    if (
        not selected
        or len(selected) != len(set(selected))
        or any(case_id not in full_order for case_id in selected)
    ):
        raise PipelineError("Selecao do localizador multifasico v22 invalida.")
    selected.sort(key=full_order.index)
    inputs = _input_index(input_manifest_path, input_root)
    venous_localizer_root = Path(venous_localizer_root).resolve()
    venous_summary_path = venous_localizer_root / "summary.json"
    venous_summary = _load(venous_summary_path)
    if (
        not _valid_localizer_run_schema(venous_summary)
        or venous_summary.get("status") != "complete_scores_only_no_decision"
        or venous_summary.get("ground_truth_read") is not False
        or venous_summary.get("ground_truth_lesion_mask_used") is not False
        or venous_summary.get("final_decision") is not None
        or any(case_id not in venous_summary.get("case_ids", []) for case_id in selected)
    ):
        raise PipelineError("Run venoso de origem invalido ou nao cego no v22.")

    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino do localizador multifasico v22 ja existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22multi_loc_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    manifests: list[dict[str, Any]] = []
    run_started = time.monotonic()
    try:
        for sequence, case_id in enumerate(selected, 1):
            source = inputs[case_id]
            liver_path = source["paths"]["liver_mask_venous"]
            venous = sitk.ReadImage(str(source["paths"]["t1_venous"]))
            (
                venous_manifest,
                venous_manifest_path,
                venous_candidate_path,
                _,
                _,
                _,
            ) = _validate_localizer(
                case_id, venous_localizer_root / case_id, venous
            )
            case_dir = staging / case_id
            case_dir.mkdir()
            arterial_seconds = 0.0
            arterial_hashes: dict[str, str | None] = {
                "registered_arterial": None,
                "registered_alignment_manifest": None,
                "arterial_candidate": None,
            }
            arterial_candidate_path: Path | None = None
            arterial_features: dict[str, Any] | None = None
            if modes[case_id] == "registered_to_venous":
                arterial_path, _, registered_hashes = _registered_paths(
                    case_id, alignment_root
                )
                started = time.monotonic()
                raw_path = Path(
                    localizer.localize(
                        arterial_path, liver_path, case_dir / "raw_model_output_arterial"
                    )
                ).resolve()
                if not raw_path.is_relative_to(case_dir) or not raw_path.is_file():
                    raise PipelineError("Localizador arterial retornou caminho inseguro.")
                arterial_candidate_path = case_dir / "arterial_candidates_in_liver.nii.gz"
                arterial_features = candidate_features(
                    raw_path, liver_path, arterial_candidate_path
                )
                arterial_seconds = time.monotonic() - started
                arterial_hashes = {
                    "registered_arterial": registered_hashes["art"],
                    "registered_alignment_manifest": registered_hashes["alignment_manifest"],
                    "arterial_candidate": _sha256(arterial_candidate_path),
                }

            union_raw_path = case_dir / "candidate_union_raw.nii.gz"
            if arterial_candidate_path is None:
                venous_nifti = nib.load(str(venous_candidate_path))
                _save_mask_atomic(
                    np.asarray(venous_nifti.dataobj) > 0,
                    venous_nifti,
                    union_raw_path,
                )
                union_stats = {
                    "venous_voxels": int(venous_manifest["features"]["inside_liver_voxels"]),
                    "arterial_voxels": 0,
                    "intersection_voxels": 0,
                    "union_voxels": int(venous_manifest["features"]["inside_liver_voxels"]),
                    "new_arterial_voxels": 0,
                }
            else:
                union_stats = combine_candidate_masks(
                    venous_candidate_path=venous_candidate_path,
                    arterial_candidate_path=arterial_candidate_path,
                    output_path=union_raw_path,
                )
            filtered_path = case_dir / "liver_lesion_candidates_in_liver.nii.gz"
            features = candidate_features(union_raw_path, liver_path, filtered_path)
            venous_seconds = float(venous_manifest.get("elapsed_seconds", 0.0))
            combined_seconds = venous_seconds + arterial_seconds
            if combined_seconds > float(max_combined_seconds):
                raise PipelineError(
                    f"Localizador multifasico excedeu {max_combined_seconds}s em {case_id}."
                )
            manifest: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "candidate_scores_only_no_decision",
                "sequence": sequence,
                "task": TASK,
                "algorithm_version": ALGORITHM_VERSION,
                "model_version": localizer.model_version,
                "runtime_guard": runtime_guard,
                "input_role": "t1_venous_plus_registered_arterial",
                "liver_mask_role": "liver_mask_venous",
                "liver_mask_sha256": source["hashes"]["liver_mask_venous"],
                "raw_candidate_mask_sha256": _sha256(union_raw_path),
                "filtered_candidate_mask_sha256": _sha256(filtered_path),
                "source_venous_manifest_sha256": _sha256(venous_manifest_path),
                "source_venous_candidate_sha256": _sha256(venous_candidate_path),
                "source_hashes": arterial_hashes,
                "phase_candidates": {
                    "venous": venous_manifest["features"],
                    "arterial": arterial_features,
                    "union": union_stats,
                },
                "features": features,
                "venous_seconds": round(venous_seconds, 4),
                "additional_arterial_seconds": round(arterial_seconds, 4),
                "elapsed_seconds": round(combined_seconds, 4),
                "within_90_seconds": combined_seconds <= 90.0,
                "within_180_seconds": combined_seconds <= 180.0,
                "candidate_mask_is_model_derived": True,
                "ground_truth_lesion_mask_used": False,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "final_decision": None,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            _write_json_atomic(case_dir / "localizer_manifest.json", manifest)
            manifests.append(manifest)
            if progress:
                progress(
                    {
                        "sequence": sequence,
                        "case_count": len(selected),
                        "case_id": case_id,
                        "additional_arterial_seconds": manifest["additional_arterial_seconds"],
                        "combined_seconds": manifest["elapsed_seconds"],
                        "new_arterial_voxels": union_stats["new_arterial_voxels"],
                    }
                )

        elapsed = [float(item["elapsed_seconds"]) for item in manifests]
        summary: dict[str, Any] = {
            "schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(manifests),
            "candidate_positive_count": sum(
                bool(item["features"]["candidate_present"]) for item in manifests
            ),
            "candidate_negative_count": sum(
                not bool(item["features"]["candidate_present"]) for item in manifests
            ),
            "case_ids": selected,
            "task": TASK,
            "model_version": localizer.model_version,
            "runtime_guard": runtime_guard,
            "input_role": "t1_venous_plus_registered_arterial",
            "liver_mask_role": "liver_mask_venous",
            "source_venous_summary_sha256": _sha256(venous_summary_path),
            "mean_case_seconds": statistics.fmean(elapsed),
            "max_case_seconds": max(elapsed),
            "all_cases_within_90_seconds": all(value <= 90.0 for value in elapsed),
            "all_cases_within_180_seconds": all(value <= 180.0 for value in elapsed),
            "total_wall_seconds_additional_arterial": round(
                time.monotonic() - run_started, 4
            ),
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "ALGORITHM_VERSION",
    "combine_candidate_masks",
    "run_arterial_union_localizer",
]
