"""Blind MR liver-lesion candidate localization for OpenSwissHCC development."""
from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import nibabel as nib
import numpy as np
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-lesion-localizer-case-v1"
RUN_SCHEMA = "argos-openswisshcc-lesion-localizer-run-v1"
INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
TASK = "liver_lesions_mr"
INPUT_ROLE = "t1_venous"
LIVER_MASK_ROLE = "liver_mask_venous"


class Localizer(Protocol):
    task: str
    model_version: str

    def localize(self, image_path: Path, liver_mask_path: Path, output_dir: Path) -> Path: ...


class TotalSegmentatorMRLesionLocalizer:
    task = TASK

    def __init__(self) -> None:
        import importlib.metadata

        self.model_version = f"TotalSegmentator {importlib.metadata.version('TotalSegmentator')} Dataset589 fold0"

    def localize(self, image_path: Path, liver_mask_path: Path, output_dir: Path) -> Path:
        from totalsegmentator.python_api import totalsegmentator

        output_dir.mkdir(parents=True, exist_ok=False)
        totalsegmentator(
            input=image_path,
            output=output_dir,
            task=TASK,
            crop_path=liver_mask_path,
            device="gpu",
            fast=False,
            nr_thr_resamp=1,
            nr_thr_saving=1,
            quiet=True,
        )
        return output_dir / "liver_lesions.nii.gz"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Manifesto de entradas v10 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Manifesto de entradas v10 vazio ou invalido.")
    return rows


def _safe_file(root: Path, relative_path: str, expected_bytes: int, expected_hash: str) -> Path:
    path = (root / str(relative_path)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise PipelineError("Entrada v10 ausente ou fora da raiz autorizada.")
    if path.stat().st_size != int(expected_bytes) or _sha256(path) != str(expected_hash):
        raise PipelineError(f"Hash ou bytes da entrada v10 divergiram: {relative_path}.")
    return path


def index_inputs(
    manifest_path: Path,
    input_root: Path,
    expected_case_count: int = 88,
    *,
    input_role: str = INPUT_ROLE,
    liver_mask_role: str = LIVER_MASK_ROLE,
) -> dict[str, dict[str, Any]]:
    root = Path(input_root).resolve()
    rows = _load_jsonl(manifest_path)
    if len(rows) != expected_case_count:
        raise PipelineError("Manifesto v10 nao contem a coorte fonte esperada.")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if (
            row.get("schema") != INPUT_SCHEMA
            or not case_id.startswith("anon-")
            or case_id in indexed
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Registro de entrada v10 invalido ou inseguro.")
        files = row.get("files")
        if not isinstance(files, list):
            raise PipelineError("Lista de entradas v10 ausente.")
        if any(
            "lesion" in (str(item.get("role", "")) + " " + str(item.get("relative_path", ""))).lower()
            for item in files
        ):
            raise PipelineError("Mascara/arquivo de lesao do dataset e proibido no localizador v10.")
        by_role = {str(item.get("role")): item for item in files}
        if len(by_role) != len(files) or input_role not in by_role or liver_mask_role not in by_role:
            raise PipelineError("Imagem ou mascara hepatica do localizador v10 ausente/duplicada.")
        image_record = by_role[input_role]
        liver_record = by_role[liver_mask_role]
        indexed[case_id] = {
            "image": _safe_file(root, image_record["relative_path"], image_record["bytes"], image_record["sha256"]),
            "image_sha256": image_record["sha256"],
            "liver_mask": _safe_file(root, liver_record["relative_path"], liver_record["bytes"], liver_record["sha256"]),
            "liver_mask_sha256": liver_record["sha256"],
        }
    return indexed


def _save_mask_atomic(mask: np.ndarray, reference: nib.spatialimages.SpatialImage, path: Path) -> None:
    header = reference.header.copy()
    header.set_data_dtype(np.uint8)
    image = nib.Nifti1Image(mask.astype(np.uint8), reference.affine, header)
    # Qualification paths are deep. Keep the temporary basename short enough for
    # Windows' legacy MAX_PATH limit while preserving atomic publication.
    tmp = path.with_name(f"._m_{uuid.uuid4().hex[:8]}.nii.gz")
    try:
        nib.save(image, tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def candidate_features(raw_mask_path: Path, liver_mask_path: Path, output_path: Path) -> dict[str, Any]:
    raw_img = nib.load(str(raw_mask_path))
    liver_img = nib.load(str(liver_mask_path))
    if raw_img.shape != liver_img.shape or not np.allclose(raw_img.affine, liver_img.affine, atol=1e-5):
        raise PipelineError("Mascara candidata v10 diverge da geometria hepatica.")
    raw_data = np.asarray(raw_img.dataobj)
    if not np.isfinite(raw_data).all() or not np.isin(np.unique(raw_data), [0, 1]).all():
        raise PipelineError("Mascara candidata v10 nao e binaria ou possui valores invalidos.")
    raw = raw_data > 0
    liver = np.asarray(liver_img.dataobj) > 0
    filtered = raw & liver
    structure = ndimage.generate_binary_structure(3, 3)
    labels, count = ndimage.label(filtered, structure=structure)
    voxel_volume = float(abs(np.linalg.det(raw_img.affine[:3, :3])))
    components = []
    for component_id in range(1, count + 1):
        indices = np.argwhere(labels == component_id)
        voxels = int(indices.shape[0])
        volume = voxels * voxel_volume
        low = indices.min(axis=0).astype(int).tolist()
        high = indices.max(axis=0).astype(int).tolist()
        components.append(
            {
                "component_id": component_id,
                "voxels": voxels,
                "volume_mm3": volume,
                "equivalent_diameter_mm": float((6.0 * volume / math.pi) ** (1.0 / 3.0)),
                "centroid_index_xyz": [float(v) for v in indices.mean(axis=0)],
                "bbox_min_index_xyz": low,
                "bbox_max_index_xyz": high,
            }
        )
    components.sort(key=lambda item: (-item["volume_mm3"], item["component_id"]))
    for new_id, item in enumerate(components, 1):
        item["rank_by_volume"] = new_id
    _save_mask_atomic(filtered, raw_img, output_path)
    return {
        "raw_candidate_voxels": int(raw.sum()),
        "inside_liver_voxels": int(filtered.sum()),
        "outside_liver_voxels_removed": int((raw & ~liver).sum()),
        "voxel_volume_mm3": voxel_volume,
        "component_count": count,
        "total_candidate_volume_mm3": float(filtered.sum() * voxel_volume),
        "largest_component_volume_mm3": float(components[0]["volume_mm3"] if components else 0.0),
        "candidate_present": bool(count),
        "components": components,
    }


def run_localizer_scores(
    *,
    manifest_path: Path,
    input_root: Path,
    output_root: Path,
    case_ids: list[str],
    localizer: Localizer,
    expected_source_case_count: int = 88,
    max_localizer_seconds: float = 90.0,
    selection_signature: str | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    input_role: str = INPUT_ROLE,
    liver_mask_role: str = LIVER_MASK_ROLE,
    runtime_guard: str | None = None,
) -> dict[str, Any]:
    if not 0 < float(max_localizer_seconds) <= 90:
        raise PipelineError("Orcamento do localizador v10 deve estar em (0,90].")
    selected = list(case_ids)
    if not selected or len(selected) != len(set(selected)) or any(not str(case).startswith("anon-") for case in selected):
        raise PipelineError("Selecao de casos v10 invalida.")
    inputs = index_inputs(
        manifest_path, input_root, expected_source_case_count,
        input_role=input_role, liver_mask_role=liver_mask_role,
    )
    if any(case not in inputs for case in selected):
        raise PipelineError("Selecao v10 contem caso fora do manifesto autorizado.")
    out = Path(output_root).resolve()
    if out.exists():
        raise PipelineError("Destino v10 ja existe; resultados nao serao sobrescritos.")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f"._l10_{uuid.uuid4().hex[:6]}"
    staging.mkdir()
    manifests = []
    run_started = time.monotonic()
    try:
        for sequence, case_id in enumerate(selected, 1):
            started = time.monotonic()
            source = inputs[case_id]
            case_dir = staging / case_id
            case_dir.mkdir()
            raw_dir = case_dir / "raw_model_output"
            raw_path = Path(localizer.localize(source["image"], source["liver_mask"], raw_dir)).resolve()
            if not raw_path.is_relative_to(case_dir) or not raw_path.is_file():
                raise PipelineError("Localizador v10 retornou caminho de mascara inseguro ou ausente.")
            filtered_path = case_dir / "liver_lesion_candidates_in_liver.nii.gz"
            features = candidate_features(raw_path, source["liver_mask"], filtered_path)
            elapsed = time.monotonic() - started
            if elapsed > float(max_localizer_seconds):
                raise PipelineError(f"Localizador v10 excedeu {max_localizer_seconds}s em {case_id}.")
            manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "candidate_scores_only_no_decision",
                "sequence": sequence,
                "task": localizer.task,
                "model_version": localizer.model_version,
                "runtime_guard": runtime_guard,
                "input_role": input_role,
                "input_sha256": source["image_sha256"],
                "liver_mask_role": liver_mask_role,
                "liver_mask_sha256": source["liver_mask_sha256"],
                "raw_candidate_mask_sha256": _sha256(raw_path),
                "filtered_candidate_mask_sha256": _sha256(filtered_path),
                "features": features,
                "elapsed_seconds": round(elapsed, 4),
                "within_90_seconds": True,
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
                        "elapsed_seconds": manifest["elapsed_seconds"],
                        "candidate_present": features["candidate_present"],
                    }
                )
        elapsed = [float(item["elapsed_seconds"]) for item in manifests]
        summary = {
            "schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "case_count": len(manifests),
            "candidate_positive_count": sum(bool(item["features"]["candidate_present"]) for item in manifests),
            "candidate_negative_count": sum(not bool(item["features"]["candidate_present"]) for item in manifests),
            "case_ids": selected,
            "task": localizer.task,
            "model_version": localizer.model_version,
            "input_role": input_role,
            "liver_mask_role": liver_mask_role,
            "runtime_guard": runtime_guard,
            "input_manifest_sha256": _sha256(Path(manifest_path).resolve()),
            "selection_signature": selection_signature,
            "mean_case_seconds": statistics.fmean(elapsed),
            "max_case_seconds": max(elapsed),
            "all_cases_within_90_seconds": all(item["within_90_seconds"] for item in manifests),
            "total_wall_seconds": round(time.monotonic() - run_started, 4),
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, out)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
