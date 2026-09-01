"""Post-inference localization of unconfirmed focal liver regions.

The output of this module is deliberately a *candidate region*, never a
diagnosis or a ground-truth lesion mask.  It is run only after the screening
decision has been frozen and its mask is consumed exclusively by the viewer.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .core import (
    Case,
    PipelineError,
    array_from,
    array_to_image,
    now_utc,
    read_image,
    save_image,
    sha256_of,
)

SCHEMA = "argos-candidate-region-v1"
TASK = "liver_lesions_mr"  # default RM — comportamento byte-idêntico
# CT-03 (2026-08-28, plano aprovado): a task pode vir da solicitação — o
# webapp conhece a modalidade/perfil e escreve o request. Allowlist
# fail-closed: nunca uma task arbitrária. "liver_lesions" = Dataset591
# (TC, 842 sujeitos, sem licença comercial); a máscara de saída tem o
# mesmo nome (liver_lesions.nii.gz) nas duas tasks.
ALLOWED_TASKS = frozenset({"liver_lesions_mr", "liver_lesions", "kidney_cysts"})
# Nome(s) do(s) arquivo(s) que cada task grava em staging/. Tasks de órgão
# par produzem um arquivo POR LADO (kidney_cysts: TS 2.15.0/Dataset789) —
# a união dos dois vira a máscara candidata bruta antes da validação.
TASK_OUTPUT_FILES: dict[str, tuple[str, ...]] = {
    "liver_lesions_mr": ("liver_lesions.nii.gz",),
    "liver_lesions": ("liver_lesions.nii.gz",),
    "kidney_cysts": ("kidney_cyst_left.nii.gz", "kidney_cyst_right.nii.gz"),
}


def _same_geometry(a, b) -> bool:
    return (
        a.GetSize() == b.GetSize()
        and np.allclose(a.GetSpacing(), b.GetSpacing(), atol=1e-6)
        and np.allclose(a.GetOrigin(), b.GetOrigin(), atol=1e-5)
        and np.allclose(a.GetDirection(), b.GetDirection(), atol=1e-6)
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def validate_and_store_candidate(
    case: Case,
    raw_mask_path: Path,
    *,
    request: dict[str, Any],
    model_version: str,
    elapsed_seconds: float,
    task: str = TASK,
) -> dict[str, Any]:
    """Validate geometry/binarity, clip to liver and publish an auditable mask."""
    raw_image = read_image(Path(raw_mask_path))
    liver_image = read_image(case.mask_organ)
    if not _same_geometry(raw_image, liver_image):
        raise PipelineError("A região candidata diverge da geometria da máscara hepática.")

    raw_data = array_from(raw_image)
    if not np.isfinite(raw_data).all() or not np.isin(np.unique(raw_data), [0, 1]).all():
        raise PipelineError("A região candidata não é uma máscara binária válida.")
    raw = raw_data > 0
    liver = array_from(liver_image) > 0
    filtered = raw & liver

    labels, component_count = ndimage.label(
        filtered, structure=ndimage.generate_binary_structure(3, 3)
    )
    voxel_volume_mm3 = float(np.prod(liver_image.GetSpacing()))
    components: list[dict[str, Any]] = []
    for component_id in range(1, int(component_count) + 1):
        indexes = np.argwhere(labels == component_id)
        voxels = int(indexes.shape[0])
        volume_mm3 = voxels * voxel_volume_mm3
        centroid_zyx = indexes.mean(axis=0)
        centroid_xyz = tuple(float(value) for value in centroid_zyx[::-1])
        centroid_lps = liver_image.TransformContinuousIndexToPhysicalPoint(centroid_xyz)
        components.append({
            "component_id": component_id,
            "voxels": voxels,
            "volume_mm3": round(volume_mm3, 4),
            "equivalent_diameter_mm": round(
                float((6.0 * volume_mm3 / math.pi) ** (1.0 / 3.0)), 4
            ),
            "centroid_index_xyz": [round(value, 4) for value in centroid_xyz],
            "centroid_lps_mm": [round(float(value), 4) for value in centroid_lps],
            "bbox_min_index_xyz": indexes.min(axis=0)[::-1].astype(int).tolist(),
            "bbox_max_index_xyz": indexes.max(axis=0)[::-1].astype(int).tolist(),
        })
    components.sort(key=lambda item: (-item["volume_mm3"], item["component_id"]))
    for rank, component in enumerate(components, 1):
        component["rank_by_volume"] = rank

    save_image(array_to_image(filtered, liver_image, np.uint8), case.mask_candidate)
    payload = {
        "schema": SCHEMA,
        "created_at": now_utc(),
        "status": "pending_human_review" if component_count else "no_candidate_detected",
        "source": "automatic_post_inference_localizer",
        "task": task,
        "model_version": model_version,
        "screening_frozen_before_localization": True,
        "used_by_screening_inference": False,
        "ground_truth_lesion_mask_used": False,
        "candidate_is_diagnosis": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "request": request,
        "candidate_present": bool(component_count),
        "component_count": int(component_count),
        "raw_candidate_voxels": int(raw.sum()),
        "candidate_voxels_inside_liver": int(filtered.sum()),
        "outside_liver_voxels_removed": int((raw & ~liver).sum()),
        "voxel_volume_mm3": round(voxel_volume_mm3, 8),
        "total_candidate_volume_mm3": round(float(filtered.sum()) * voxel_volume_mm3, 4),
        "components": components,
        "mask_sha256": sha256_of(case.mask_candidate),
        "liver_mask_sha256": sha256_of(case.mask_organ),
        "elapsed_seconds": round(float(elapsed_seconds), 4),
    }
    _atomic_json(case.candidate_manifest, payload)
    return payload


def generate_candidate_region(
    case_dir: Path,
    *,
    device: str,
    request_path: Path,
) -> dict[str, Any]:
    """Run TotalSegmentator in a staging directory and publish only on success."""
    case = Case(Path(case_dir).resolve())
    if not case.volume.is_file() or not case.mask_organ.is_file():
        raise PipelineError("Volume ou máscara hepática ausente para localizar candidato.")
    request_path = Path(request_path).resolve()
    if request_path.parent != case.root or not request_path.is_file():
        raise PipelineError("Solicitação de localização ausente ou fora do caso.")
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Solicitação de localização inválida.") from exc
    if request.get("schema") != "argos-candidate-request-v1":
        raise PipelineError("Schema da solicitação de localização inválido.")
    task = str(request.get("task") or TASK)
    if task not in ALLOWED_TASKS:
        raise PipelineError(f"Task de localização não autorizada: {task!r}.")

    try:
        import importlib.metadata

        from totalsegmentator.python_api import totalsegmentator
    except (ImportError, ModuleNotFoundError) as exc:
        raise PipelineError("TotalSegmentator indisponível para localizar a região candidata.") from exc

    started = time.monotonic()
    staging = Path(tempfile.mkdtemp(prefix="argos_candidate_"))
    try:
        totalsegmentator(
            input=str(case.volume),
            output=str(staging),
            task=task,
            crop_path=str(case.mask_organ),
            device=device,
            fast=False,
            nr_thr_resamp=1,
            nr_thr_saving=1,
            quiet=True,
        )
        output_files = TASK_OUTPUT_FILES.get(task, ("liver_lesions.nii.gz",))
        produced_paths = [staging / name for name in output_files]
        missing = [str(p.name) for p in produced_paths if not p.is_file()]
        if missing:
            raise PipelineError(
                f"O localizador não produziu a(s) máscara(s) esperada(s): {missing}."
            )
        if len(produced_paths) == 1:
            raw_path = produced_paths[0]  # caminho histórico byte-idêntico
        else:
            # União lógica dos lados (rim par): mesma geometria (recorte na
            # máscara do órgão), então basta OR voxel a voxel.
            union_img = read_image(produced_paths[0])
            union_arr = array_from(union_img) > 0
            for extra_path in produced_paths[1:]:
                extra_img = read_image(extra_path)
                if extra_img.GetSize() != union_img.GetSize():
                    raise PipelineError(
                        f"Saídas de '{task}' com geometrias divergentes."
                    )
                union_arr = union_arr | (array_from(extra_img) > 0)
            raw_path = staging / "_union_candidate.nii.gz"
            save_image(
                array_to_image(union_arr.astype(np.uint8), union_img, np.uint8), raw_path
            )
        version = f"TotalSegmentator {importlib.metadata.version('TotalSegmentator')} / {task}"
        return validate_and_store_candidate(
            case,
            raw_path,
            request=request,
            model_version=version,
            elapsed_seconds=time.monotonic() - started,
            task=task,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

