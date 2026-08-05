"""Label-blind dynamic features fused with localized MedSigLIP embeddings."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_enhancement_maps import _compute_enhancement_state
from dtwin.core import PipelineError
from dtwin.learning.localized_candidate_supervision import _same_geometry, _verified_geometry
from dtwin.learning.medsiglip_embeddings import (
    EMBEDDING_MANIFEST_SCHEMA,
    EMBEDDING_RECORD_SCHEMA,
    verify_embeddings,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file


FEATURE_VERSION = "localized-dynamic-statistics-v1"
QUANTILES = (10, 25, 50, 75, 90, 95, 99)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON de features localizadas invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON de features localizadas deve ser objeto.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL de features localizadas invalido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Registro de feature localizada invalido.")
    return rows


def localized_dynamic_features(
    state: dict[str, Any], bounds: list[list[int]], *, proposal_voxels: int,
    component_rank: int, center_zyx: list[int]
) -> tuple[np.ndarray, list[str]]:
    (z0, z1), (y0, y1), (x0, x1) = bounds
    analysis = np.asarray(state["analysis_mask"], dtype=bool)
    region_mask = analysis[z0:z1, y0:y1, x0:x1]
    if int(region_mask.sum()) < 8:
        raise PipelineError("Caixa localizada sem voxels hepaticos suficientes.")
    maps = {
        "arterial": np.asarray(state["arterial_relative"]),
        "venous": np.asarray(state["arterial_relative"] - state["arterial_over_venous"]),
        "delayed": np.asarray(state["arterial_relative"] - state["arterial_over_delayed"]),
        "arterial_over_venous": np.asarray(state["arterial_over_venous"]),
        "arterial_over_delayed": np.asarray(state["arterial_over_delayed"]),
        "venous_over_delayed": np.asarray(state["venous_over_delayed"]),
        "joint": np.asarray(state["joint_enhancement"]),
    }
    values: list[float] = []
    names: list[str] = []
    for name, array in maps.items():
        sample = np.asarray(array[z0:z1, y0:y1, x0:x1][region_mask], dtype=np.float64)
        stats = [*np.percentile(sample, QUANTILES), np.mean(sample), np.std(sample), np.min(sample), np.max(sample)]
        suffixes = [*(f"q{value}" for value in QUANTILES), "mean", "std", "minimum", "maximum"]
        values.extend(float(value) for value in stats)
        names.extend(f"{name}_{suffix}" for suffix in suffixes)
    joint = maps["joint"][z0:z1, y0:y1, x0:x1][region_mask]
    for threshold in (1.0, 2.0, 3.0, 4.0):
        values.append(float(np.mean(joint >= threshold)))
        names.append(f"joint_fraction_ge_{int(threshold)}")
    box_voxels = int((z1 - z0) * (y1 - y0) * (x1 - x0))
    shape = np.asarray(analysis.shape, dtype=np.float64)
    center = np.asarray(center_zyx, dtype=np.float64)
    extras = [
        proposal_voxels / max(box_voxels, 1),
        float(component_rank),
        *(center / np.maximum(shape - 1.0, 1.0)).tolist(),
        region_mask.sum() / max(box_voxels, 1),
    ]
    values.extend(float(value) for value in extras)
    names.extend(["proposal_density", "component_rank", "center_z_relative", "center_y_relative", "center_x_relative", "liver_fraction"])
    vector = np.asarray(values, dtype=np.float32)
    if vector.shape != (87,) or not np.isfinite(vector).all() or len(names) != 87:
        raise PipelineError("Vetor dinamico localizado incompleto ou nao finito.")
    return vector, names


def build_fused_localized_embeddings(
    *, geometry_root: Path, image_dataset_root: Path, medsiglip_root: Path,
    inputs_root: Path, alignment_root: Path, output_root: Path,
    include_visual_embedding: bool = True,
) -> dict[str, Any]:
    geometry_root = Path(geometry_root).resolve()
    image_dataset_root = Path(image_dataset_root).resolve()
    medsiglip_root = Path(medsiglip_root).resolve()
    inputs_root = Path(inputs_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Embeddings localizados fundidos ja existem.")
    geometry_manifest, geometry_rows = _verified_geometry(geometry_root)
    geometry = {(str(row["case_id"]), str(row["candidate_id"])): row for row in geometry_rows}
    source_manifest = verify_embeddings(candidate_root=image_dataset_root, output_root=medsiglip_root)
    source_rows = _jsonl(medsiglip_root / "embedding_records.jsonl")
    image_manifest = _json(image_dataset_root / "dataset_manifest.json")
    staging = output_root.with_name(f".{output_root.name}.{uuid.uuid4().hex[:8]}.tmp")
    staging.mkdir(parents=True)
    output_rows: list[dict[str, Any]] = []
    feature_names: list[str] | None = None
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in source_rows:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    try:
        for case_id, rows in sorted(by_case.items()):
            paths = {
                "arterial": alignment_root / case_id / "art_registered_to_venous.nii.gz",
                "venous": inputs_root / case_id / "dyn" / "t1_venous.nii.gz",
                "delayed": alignment_root / case_id / "del_registered_to_venous.nii.gz",
                "liver": inputs_root / case_id / "masks" / "liver_mask_venous.nii.gz",
            }
            images = {name: sitk.ReadImage(str(path)) for name, path in paths.items()}
            if not all(_same_geometry(images["venous"], image) for image in images.values()):
                raise PipelineError(f"Geometria divergente nas features localizadas: {case_id}.")
            state = _compute_enhancement_state(
                arterial=images["arterial"], venous=images["venous"],
                delayed=images["delayed"], liver_mask=images["liver"]
            )
            for source in rows:
                key = (case_id, str(source["candidate_id"]))
                candidate = geometry.get(key)
                if candidate is None:
                    raise PipelineError(f"Embedding sem geometria localizada: {key}.")
                dynamic, names = localized_dynamic_features(
                    state, candidate["bounds_zyx_exclusive"],
                    proposal_voxels=int(candidate["automatic_proposal_voxels_in_box"]),
                    component_rank=int(candidate["source_component_rank"]),
                    center_zyx=[int(value) for value in candidate["center_zyx"]],
                )
                if feature_names is None:
                    feature_names = names
                elif feature_names != names:
                    raise PipelineError("Ordem de features localizadas variou entre candidatos.")
                visual = np.load(medsiglip_root / str(source["embedding_path"]), allow_pickle=False).astype(np.float32)
                fused = (
                    np.concatenate([visual, dynamic]).astype(np.float32)
                    if include_visual_embedding
                    else dynamic.astype(np.float32)
                )
                relative = Path("embeddings") / case_id / f"{key[1]}.npy"
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as stream:
                    np.save(stream, fused, allow_pickle=False)
                output_rows.append(
                    {
                        "schema": EMBEDDING_RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": str(source["patient_group_id"]),
                        "dataset_id": str(source["dataset_id"]),
                        "candidate_id": key[1],
                        "candidate_kind": (
                            "localized_medsiglip_plus_dynamic_statistics"
                            if include_visual_embedding
                            else "localized_dynamic_statistics_only"
                        ),
                        "panel_number": int(source["panel_number"]),
                        "image_sha256": str(source["image_sha256"]),
                        "embedding_path": relative.as_posix(),
                        "embedding_sha256": sha256_file(destination),
                        "embedding_dimension": int(fused.size),
                        "embedding_dtype": "float32",
                        "embedding_l2_norm": float(np.linalg.norm(fused)),
                        "label_attached": False,
                        "ground_truth_read": False,
                        "lesion_mask_read": False,
                        "research_only": True,
                    }
                )
        output_rows.sort(key=lambda row: (row["case_id"], row["candidate_id"]))
        records_path = staging / "embedding_records.jsonl"
        records_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in output_rows), encoding="utf-8")
        names_path = staging / "dynamic_feature_names.json"
        names_path.write_text(json.dumps(feature_names, indent=2) + "\n", encoding="utf-8")
        body = {
            "schema": EMBEDDING_MANIFEST_SCHEMA,
            "status": "complete_label_blind_localized_fused_features",
            "config_sha256": canonical_sha256(
                {
                    "feature_version": FEATURE_VERSION,
                    "include_visual_embedding": include_visual_embedding,
                }
            ),
            "candidate_dataset_signature": image_manifest["dataset_signature"],
            "candidate_records_sha256": image_manifest["candidate_records_sha256"],
            "expected_embedding_count": len(source_rows),
            "embedding_count": len(output_rows),
            "embedding_records_sha256": sha256_file(records_path),
            "backend": {
                "model_id": source_manifest["backend"]["model_id"],
                "revision": source_manifest["backend"]["revision"],
                "visual_dimension": (
                    source_manifest["backend"]["embedding_dimension"]
                    if include_visual_embedding
                    else 0
                ),
                "dynamic_feature_dimension": len(feature_names or []),
                "embedding_dimension": int(output_rows[0]["embedding_dimension"]),
                "feature_version": FEATURE_VERSION,
                "feature_names_sha256": sha256_file(names_path),
            },
            "source_embedding_signature": source_manifest["embedding_signature"],
            "include_visual_embedding": include_visual_embedding,
            "source_geometry_signature": geometry_manifest["geometry_signature"],
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        result = {**body, "embedding_signature": canonical_sha256(body)}
        (staging / "embedding_manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging, output_root)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["build_fused_localized_embeddings", "localized_dynamic_features"]
