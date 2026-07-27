"""Blind top-volume selection from frozen whole-liver enhancement proposals."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import _validate_localizer
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION as SOURCE_ALGORITHM,
    CASE_SCHEMA as SOURCE_CASE_SCHEMA,
    COHORT_SCHEMA as SOURCE_COHORT_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import _input_index, _load, _selection
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA,
    RUN_SCHEMA,
    _save_mask_atomic,
    candidate_features,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


ALGORITHM_VERSION = "joint-enhancement-t3-top5-volume-v1"
THRESHOLD_KEY = "t3"
MAX_COMPONENTS = 5


def select_top_components(mask: np.ndarray, maximum: int = MAX_COMPONENTS) -> tuple[np.ndarray, list[dict[str, int]]]:
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 3 or maximum < 1:
        raise PipelineError("Mascara/limite invalido na selecao de propostas v22.")
    labels, count = ndimage.label(
        binary, structure=ndimage.generate_binary_structure(3, 2)
    )
    sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
    ordered = sorted(range(1, int(count) + 1), key=lambda item: (-int(sizes[item]), item))
    selected_ids = ordered[:maximum]
    selected = np.isin(labels, selected_ids)
    records = [
        {"rank_by_volume": rank, "source_component_id": component_id, "voxels": int(sizes[component_id])}
        for rank, component_id in enumerate(selected_ids, 1)
    ]
    return selected, records


def build_selected_enhancement_localizer(
    *,
    proposal_root: Path,
    input_manifest_path: Path,
    input_root: Path,
    selection_manifest_path: Path,
    venous_fallback_localizer_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Publish a compatible automatic localizer run without reading labels."""

    proposal_root = Path(proposal_root).resolve()
    source_summary = _load(proposal_root / "summary.json")
    case_ids, modes = _selection(selection_manifest_path)
    inputs = _input_index(input_manifest_path, input_root)
    if (
        source_summary.get("schema") != SOURCE_COHORT_SCHEMA
        or source_summary.get("algorithm_version") != SOURCE_ALGORITHM
        or source_summary.get("status") != "complete_blind_proposals_with_declared_fallbacks"
        or source_summary.get("case_ids") != case_ids
        or source_summary.get("labels_read") is not False
        or source_summary.get("ground_truth_lesion_masks_read") != 0
    ):
        raise PipelineError("Bundle fonte de propostas v22 invalido.")
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino da selecao de propostas v22 ja existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22proposal_select_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    manifests: list[dict[str, Any]] = []
    try:
        for sequence, case_id in enumerate(case_ids, 1):
            case_dir = staging / case_id
            case_dir.mkdir()
            source = inputs[case_id]
            liver_path = source["paths"]["liver_mask_venous"]
            selection_records: list[dict[str, int]] = []
            if modes[case_id] == "registered_to_venous":
                source_manifest_path = proposal_root / case_id / "manifest.json"
                if _sha256(source_manifest_path) != source_summary["case_manifest_hashes"].get(case_id):
                    raise PipelineError("Manifesto fonte de proposta v22 adulterado.")
                source_manifest = _load(source_manifest_path)
                if (
                    source_manifest.get("schema") != SOURCE_CASE_SCHEMA
                    or source_manifest.get("status") != "complete_blind_proposals"
                    or source_manifest.get("ground_truth_read") is not False
                ):
                    raise PipelineError("Caso fonte de proposta v22 invalido.")
                items = [
                    item for item in source_manifest["proposals"]
                    if item.get("threshold_key") == THRESHOLD_KEY
                ]
                if len(items) != 1:
                    raise PipelineError("Limiar t3 ausente nas propostas v22.")
                item = items[0]
                source_path = proposal_root / case_id / item["filename"]
                if _sha256(source_path) != item["sha256"]:
                    raise PipelineError("Mascara fonte de proposta v22 adulterada.")
                source_image = nib.load(str(source_path))
                selected, selection_records = select_top_components(
                    np.asarray(source_image.dataobj) > 0
                )
                raw_path = case_dir / "selected_proposals_raw.nii.gz"
                _save_mask_atomic(selected, source_image, raw_path)
                source_kind = "deterministic_enhancement_t3_top5"
                source_hash = _sha256(source_path)
            else:
                reference = sitk.ReadImage(str(source["paths"]["t1_venous"]))
                _, _, fallback_path, _, components, _ = _validate_localizer(
                    case_id, Path(venous_fallback_localizer_root) / case_id, reference
                )
                fallback_image = nib.load(str(fallback_path))
                raw_path = case_dir / "selected_proposals_raw.nii.gz"
                _save_mask_atomic(np.asarray(fallback_image.dataobj) > 0, fallback_image, raw_path)
                selection_records = [
                    {"rank_by_volume": int(item["rank_by_volume"]), "source_component_id": int(item["component_id"]), "voxels": int(item["voxels"])}
                    for item in components[:MAX_COMPONENTS]
                ]
                source_kind = "unregistered_venous_fallback"
                source_hash = _sha256(fallback_path)
            filtered_path = case_dir / "liver_lesion_candidates_in_liver.nii.gz"
            features = candidate_features(raw_path, liver_path, filtered_path)
            manifest: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "candidate_scores_only_no_decision",
                "sequence": sequence,
                "task": "deterministic_enhancement_proposals",
                "algorithm_version": ALGORITHM_VERSION,
                "model_version": "none_deterministic",
                "input_role": "registered_multiphase_t1",
                "input_sha256": source["hashes"]["t1_venous"],
                "liver_mask_role": "liver_mask_venous",
                "liver_mask_sha256": source["hashes"]["liver_mask_venous"],
                "raw_candidate_mask_sha256": _sha256(raw_path),
                "filtered_candidate_mask_sha256": _sha256(filtered_path),
                "source_kind": source_kind,
                "source_mask_sha256": source_hash,
                "selection_records": selection_records,
                "features": features,
                "elapsed_seconds": 0.0,
                "within_90_seconds": True,
                "candidate_mask_is_model_derived": False,
                "candidate_mask_is_deterministic_enhancement": True,
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
        summary: dict[str, Any] = {
            "schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(manifests),
            "case_ids": case_ids,
            "task": "deterministic_enhancement_proposals",
            "model_version": "none_deterministic",
            "input_role": "registered_multiphase_t1",
            "liver_mask_role": "liver_mask_venous",
            "candidate_positive_count": sum(item["features"]["candidate_present"] for item in manifests),
            "candidate_negative_count": sum(not item["features"]["candidate_present"] for item in manifests),
            "source_proposal_summary_sha256": _sha256(proposal_root / "summary.json"),
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


__all__ = ["ALGORITHM_VERSION", "build_selected_enhancement_localizer", "select_top_components"]
