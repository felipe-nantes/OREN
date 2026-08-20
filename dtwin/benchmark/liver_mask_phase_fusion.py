"""Label-blind fusion of registered liver masks from multiple MR phases."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.mrsegmentator_chaos_runner import verify_run
from dtwin.core import PipelineError, now_utc, sha256_of
from dtwin.segmentation_contract import same_geometry, validate_visualization_mask

RUN_SCHEMA = "argos-liver-mask-phase-fusion-v1"
CASE_SCHEMA = "argos-liver-mask-phase-fusion-case-v1"
ALLOWED_POLICIES = frozenset(
    {
        "majority_2_of_4",
        "venous_fill_largest",
        "venous_guarded_union_fill_12mm",
    }
)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count <= 1:
        return mask.astype(bool, copy=False)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def fuse_arrays(
    phase_masks: dict[str, np.ndarray],
    *,
    policy: str,
    spacing_xyz: tuple[float, float, float],
) -> np.ndarray:
    """Fuse four binary phase masks without any reference or pathology label."""

    required = ("native", "arterial", "venous", "delayed")
    if tuple(sorted(phase_masks)) != tuple(sorted(required)):
        raise PipelineError("Fusao exige exatamente native, arterial, venous e delayed.")
    if policy not in ALLOWED_POLICIES:
        raise PipelineError(f"Politica de fusao invalida: {policy}")
    arrays = [(np.asarray(phase_masks[name]) > 0) for name in required]
    shape = arrays[0].shape
    if any(array.shape != shape for array in arrays):
        raise PipelineError("Mascaras de fase possuem shapes divergentes.")
    votes = np.sum(np.stack(arrays, axis=0), axis=0)
    if policy == "majority_2_of_4":
        fused = votes >= 2
    elif policy == "venous_fill_largest":
        fused = ndimage.binary_fill_holes(arrays[2])
    else:
        venous = arrays[2]
        # Array order is z,y,x; SimpleITK spacing is x,y,z.
        spacing_zyx = tuple(float(value) for value in spacing_xyz[::-1])
        distance_from_venous = ndimage.distance_transform_edt(
            ~venous, sampling=spacing_zyx
        )
        guarded_union = (votes >= 2) | ((votes >= 1) & (distance_from_venous <= 12.0))
        fused = ndimage.binary_fill_holes(guarded_union)
    fused = _largest_component(fused)
    if not bool(fused.any()):
        raise PipelineError("Fusao de fases produziu mascara vazia.")
    return fused.astype(np.uint8)


def _load_mask_on_reference(mask_path: Path, reference: sitk.Image) -> tuple[np.ndarray, bool]:
    image = sitk.ReadImage(str(mask_path))
    resampled = not same_geometry(image, reference)
    if resampled:
        image = sitk.Resample(
            image,
            reference,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
    return (sitk.GetArrayFromImage(image) > 0).astype(np.uint8), resampled


def run_fusion(
    *,
    cohort_root: Path | str,
    phase_runs: dict[str, Path | str],
    output_root: Path | str,
    policy: str,
) -> dict[str, Any]:
    cohort = Path(cohort_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Saida final de fusao ja existe; sobrescrita recusada.")
    if policy not in ALLOWED_POLICIES:
        raise PipelineError(f"Politica de fusao invalida: {policy}")
    required = ("native", "arterial", "venous", "delayed")
    if tuple(sorted(phase_runs)) != tuple(sorted(required)):
        raise PipelineError("Runs de fase incompletos para fusao.")

    roots = {name: Path(phase_runs[name]).resolve() for name in required}
    summaries = {name: verify_run(root) for name, root in roots.items()}
    case_ids = list(summaries["venous"]["case_ids"])
    if any(list(summary["case_ids"]) != case_ids for summary in summaries.values()):
        raise PipelineError("Runs de fase possuem coortes ou ordem divergentes.")

    staging = output.with_name(f".{output.name}.incomplete")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    try:
        for case_id in case_ids:
            reference_path = cohort / case_id / "t1_venous.nii.gz"
            if not reference_path.is_file():
                raise PipelineError(f"Referencia venosa ausente: {case_id}")
            reference = sitk.ReadImage(str(reference_path))
            phase_arrays: dict[str, np.ndarray] = {}
            input_hashes: dict[str, str] = {}
            resampled: dict[str, bool] = {}
            for phase in required:
                mask_path = roots[phase] / "masks" / f"{case_id}.nii.gz"
                phase_arrays[phase], resampled[phase] = _load_mask_on_reference(
                    mask_path, reference
                )
                input_hashes[phase] = sha256_of(mask_path)
            fused = fuse_arrays(
                phase_arrays,
                policy=policy,
                spacing_xyz=tuple(float(value) for value in reference.GetSpacing()),
            )
            image = sitk.GetImageFromArray(fused)
            image.CopyInformation(reference)
            destination = staging / "masks" / f"{case_id}.nii.gz"
            destination.parent.mkdir(parents=True, exist_ok=True)
            sitk.WriteImage(image, str(destination), useCompression=True)
            quality = validate_visualization_mask(destination, reference_path)
            rows.append(
                {
                    "schema": CASE_SCHEMA,
                    "case_id": case_id,
                    "policy": policy,
                    "input_mask_sha256": input_hashes,
                    "resampled_to_venous_grid": resampled,
                    "mask_sha256": sha256_of(destination),
                    "foreground_voxels": quality["foreground_voxels"],
                    "volume_ml": quality["volume_ml"],
                    "ground_truth_read": False,
                    "lesion_masks_read": 0,
                }
            )
        receipts = staging / "cases.jsonl"
        receipts.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        summary = {
            "schema": RUN_SCHEMA,
            "created_utc": now_utc(),
            "policy": policy,
            "case_ids": case_ids,
            "case_count": len(case_ids),
            "completed_cases": len(rows),
            "phase_run_summary_sha256": {
                phase: sha256_of(root / "run_summary.json") for phase, root in roots.items()
            },
            "receipts_sha256": sha256_of(receipts),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "production_files_written": False,
        }
        _atomic_json(staging / "run_summary.json", summary)
        os.replace(staging, output)
        return summary
    except Exception:
        raise


def verify_fusion(output_root: Path | str) -> dict[str, Any]:
    root = Path(output_root).resolve()
    try:
        summary = json.loads((root / "run_summary.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in (root / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Execucao de fusao ausente ou invalida.") from exc
    if summary.get("schema") != RUN_SCHEMA or summary.get("policy") not in ALLOWED_POLICIES:
        raise PipelineError("Schema ou politica da fusao invalida.")
    if len(rows) != summary.get("completed_cases") or len(rows) != summary.get("case_count"):
        raise PipelineError("Contagem da fusao divergente.")
    if sha256_of(root / "cases.jsonl") != summary.get("receipts_sha256"):
        raise PipelineError("Receipts da fusao adulterados.")
    if [row.get("case_id") for row in rows] != summary.get("case_ids"):
        raise PipelineError("Ordem dos casos da fusao divergente.")
    for row in rows:
        mask = root / "masks" / f"{row['case_id']}.nii.gz"
        if not mask.is_file() or sha256_of(mask) != row.get("mask_sha256"):
            raise PipelineError("Mascara de fusao ausente ou adulterada.")
        if row.get("ground_truth_read") is not False or row.get("lesion_masks_read") != 0:
            raise PipelineError("Contrato label-blind da fusao violado.")
    return summary


__all__ = [
    "RUN_SCHEMA",
    "CASE_SCHEMA",
    "ALLOWED_POLICIES",
    "fuse_arrays",
    "run_fusion",
    "verify_fusion",
]
