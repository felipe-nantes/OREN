"""Deterministic enhancement-candidate shape branch for LLD-MMRI v23."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_panels import _safe
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_shape import (
    ALGORITHM_VERSION as SHAPE_ALGORITHM_VERSION,
    CASE_SCHEMA,
    COHORT_SCHEMA,
    compute_candidate_shape_features,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION as PROPOSAL_ALGORITHM_VERSION,
    build_enhancement_proposals,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import _compute_enhancement_state
from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import (
    ALGORITHM_VERSION as SELECTION_ALGORITHM_VERSION,
    MAX_COMPONENTS,
    THRESHOLD_KEY,
    select_top_components,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


BRANCH_ALGORITHM_VERSION = "lld-v23-t3-top5-physical-shape-v1"


def compute_lld_mmri_v23_candidate_shape(
    *,
    arterial: sitk.Image,
    venous: sitk.Image,
    delayed: sitk.Image,
    liver_mask: sitk.Image,
) -> tuple[sitk.Image, dict[str, Any]]:
    """Create the frozen t3/top-5 candidate and its physical shape features."""

    state = _compute_enhancement_state(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=liver_mask,
    )
    proposals = build_enhancement_proposals(
        joint_enhancement=state["joint_enhancement"],
        analysis_mask=state["analysis_mask"],
        spacing_xyz=venous.GetSpacing(),
    )
    if THRESHOLD_KEY not in proposals:
        raise PipelineError("Proposta t3 ausente no ramo externo v23.")
    selected, selection_records = select_top_components(
        proposals[THRESHOLD_KEY]["mask"], maximum=MAX_COMPONENTS
    )
    candidate = sitk.GetImageFromArray(np.asarray(selected, dtype=np.uint8))
    candidate.CopyInformation(venous)
    shape = compute_candidate_shape_features(candidate)
    return candidate, {
        **shape,
        "branch_algorithm_version": BRANCH_ALGORITHM_VERSION,
        "proposal_algorithm_version": PROPOSAL_ALGORITHM_VERSION,
        "proposal_threshold_key": THRESHOLD_KEY,
        "proposal_threshold": proposals[THRESHOLD_KEY]["threshold"],
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "maximum_components": MAX_COMPONENTS,
        "selection_records": selection_records,
        "analysis_mask_voxels": state["analysis_mask_voxels"],
        "liver_mask_voxels": state["liver_mask_voxels"],
        "valid_multiphase_voxels": state["valid_multiphase_voxels"],
        "valid_multiphase_liver_fraction": (
            float(state["valid_multiphase_voxels"])
            / float(state["liver_mask_voxels"])
        ),
        "normalization": state["normalization"],
    }


def _write_mask_atomic(image: sitk.Image, path: Path) -> None:
    temporary = path.with_name(f"._candidate_{uuid.uuid4().hex[:8]}.nii.gz")
    try:
        sitk.WriteImage(image, str(temporary), useCompression=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_lld_mmri_v23_shape_branch(
    *,
    context: dict[str, Any],
    prepared_root: Path,
    output_root: Path,
    progress: Callable[[int, int, str, float], None] | None = None,
) -> dict[str, Any]:
    """Build all shape signals after the signed technical review, without labels."""

    case_ids = context.get("case_ids")
    protocol_case_count = context.get("protocol_case_count")
    technical_failure_case_ids = context.get("technical_failure_case_ids")
    review_signature = context.get("review_signature")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or len(case_ids) != len(set(case_ids))
        or not isinstance(protocol_case_count, int)
        or not isinstance(technical_failure_case_ids, list)
        or context.get("technical_failure_case_count")
        != len(technical_failure_case_ids)
        or protocol_case_count != len(case_ids) + len(technical_failure_case_ids)
        or context.get("technical_failures_count_as_primary_metric_errors") is not True
        or not isinstance(review_signature, str)
        or len(review_signature) != 64
    ):
        raise PipelineError("Contexto revisado LLD-MMRI invalido para geometria v23.")
    prepared_root = Path(prepared_root).resolve()
    try:
        rows = [
            json.loads(line)
            for line in (prepared_root / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Inputs LLD-MMRI ausentes para geometria v23.") from exc
    if [row.get("case_id") for row in rows] != case_ids:
        raise PipelineError("Ordem dos inputs LLD-MMRI divergiu da revisao.")
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Ramo geometrico LLD-MMRI existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23shape_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records: list[dict[str, Any]] = []
    try:
        for index, row in enumerate(rows, 1):
            started = time.monotonic()
            case_id = str(row["case_id"])
            support = row.get("dynamic_liver_support_fraction")
            if (
                not isinstance(support, dict)
                or set(support)
                != {"t1_native", "t1_arterial", "t1_venous", "t1_delayed"}
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not np.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                    for value in support.values()
                )
            ):
                raise PipelineError("Cobertura dinâmica LLD-MMRI ausente no ramo geométrico.")
            by_role = {str(item.get("role", "")): item for item in row.get("files", [])}
            required = ("t1_arterial", "t1_venous", "t1_delayed", "liver_mask_venous")
            if any(role not in by_role for role in required):
                raise PipelineError("Fases dinamicas LLD-MMRI incompletas para geometria v23.")
            paths: dict[str, Path] = {}
            hashes: dict[str, str] = {}
            for role in required:
                item = by_role[role]
                path = _safe(prepared_root / "inputs", str(item.get("relative_path", "")))
                if (
                    not path.is_file()
                    or path.stat().st_size != item.get("bytes")
                    or _sha256(path) != item.get("sha256")
                ):
                    raise PipelineError("Input LLD-MMRI adulterado antes da geometria v23.")
                paths[role] = path
                hashes[role] = str(item["sha256"])
            candidate, result = compute_lld_mmri_v23_candidate_shape(
                arterial=sitk.ReadImage(str(paths["t1_arterial"])),
                venous=sitk.ReadImage(str(paths["t1_venous"])),
                delayed=sitk.ReadImage(str(paths["t1_delayed"])),
                liver_mask=sitk.ReadImage(str(paths["liver_mask_venous"])),
            )
            case_dir = staging / case_id
            case_dir.mkdir()
            candidate_path = case_dir / "deterministic_enhancement_t3_top5_candidate.nii.gz"
            _write_mask_atomic(candidate, candidate_path)
            elapsed = time.monotonic() - started
            records.append(
                {
                    "schema": CASE_SCHEMA,
                    "case_id": case_id,
                    "status": "complete_blind_shape_features",
                    "algorithm_version": SHAPE_ALGORITHM_VERSION,
                    **result,
                    "candidate_mask": f"{case_id}/{candidate_path.name}",
                    "candidate_mask_sha256": _sha256(candidate_path),
                    "source_hashes": hashes,
                    "dynamic_liver_support_fraction": {
                        role: float(value) for role, value in support.items()
                    },
                    "partial_dynamic_fov_roles": sorted(
                        role for role, value in support.items() if float(value) < 1.0
                    ),
                    "elapsed_seconds": elapsed,
                    "review_signature": review_signature,
                    "candidate_mask_is_deterministic_enhancement": True,
                    "ground_truth_read": False,
                    "ground_truth_lesion_mask_used": False,
                    "inference_executed": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                    "requires_human_review": True,
                }
            )
            if progress is not None:
                progress(index, len(rows), case_id, elapsed)
        features_path = staging / "features.jsonl"
        features_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
        )
        empty = [
            row["case_id"]
            for row in records
            if row["features"]["candidate_present"] == 0
        ]
        summary = {
            "schema": COHORT_SCHEMA,
            "status": "complete_blind_shape_features",
            "algorithm_version": SHAPE_ALGORITHM_VERSION,
            "branch_algorithm_version": BRANCH_ALGORITHM_VERSION,
            "protocol_case_count": protocol_case_count,
            "case_count": len(records),
            "case_ids": case_ids,
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "empty_candidate_count": len(empty),
            "empty_candidate_ids": empty,
            "features_sha256": _sha256(features_path),
            "review_signature": review_signature,
            "max_case_seconds": max(float(row["elapsed_seconds"]) for row in records),
            "labels_read": False,
            "ground_truth_lesion_masks_read": 0,
            "inference_executed": False,
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
    "BRANCH_ALGORITHM_VERSION",
    "build_lld_mmri_v23_shape_branch",
    "compute_lld_mmri_v23_candidate_shape",
]
