"""Label-blind deterministic liver MRI radiomics and multiphase features."""
from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
import yaml
from scipy import ndimage, stats

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file


FEATURE_SCHEMA = "argos-hybrid-liver-radiomics-case-v1"
MANIFEST_SCHEMA = "argos-hybrid-liver-radiomics-manifest-v1"
PHASES = ("arterial", "venous", "delayed")


def _json(path: Path, description: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def load_radiomics_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config radiômica inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config radiômica deve ser objeto YAML.")
    if value.get("schema") != "argos-hybrid-radiomics-config-v1":
        raise PipelineError("Schema radiômico inválido.")
    if tuple(value.get("phases") or ()) != PHASES:
        raise PipelineError("Fase 6 v1 exige arterial, venous e delayed.")
    if value.get("mask_scope") != "automatic_liver_mask_only":
        raise PipelineError("Somente máscara hepática automática é permitida.")
    if value.get("lesion_masks_allowed") is not False:
        raise PipelineError("Máscaras de lesão devem permanecer proibidas.")
    if value.get("research_only") is not True:
        raise PipelineError("Radiômica deve permanecer research_only.")
    return value


def _geometry(image: sitk.Image) -> dict[str, tuple[float, ...] | tuple[int, ...]]:
    return {
        "size": tuple(int(value) for value in image.GetSize()),
        "spacing": tuple(float(value) for value in image.GetSpacing()),
        "origin": tuple(float(value) for value in image.GetOrigin()),
        "direction": tuple(float(value) for value in image.GetDirection()),
    }


def _same_geometry(left: sitk.Image, right: sitk.Image, tolerance: float = 1e-4) -> bool:
    a, b = _geometry(left), _geometry(right)
    if a["size"] != b["size"]:
        return False
    return all(
        np.allclose(a[key], b[key], rtol=0.0, atol=tolerance)
        for key in ("spacing", "origin", "direction")
    )


def _robust_center_scale(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = 1.4826 * mad
    if not math.isfinite(scale) or scale <= 1e-8:
        q25, q75 = np.quantile(values, [0.25, 0.75])
        scale = float((q75 - q25) / 1.349)
    if not math.isfinite(scale) or scale <= 1e-8:
        scale = float(np.std(values))
    if not math.isfinite(scale) or scale <= 1e-8:
        raise PipelineError("Fase sem variação de intensidade utilizável.")
    return median, scale


def _entropy(values: np.ndarray) -> float:
    clipped = np.clip(values, -5.0, 5.0)
    counts, _ = np.histogram(clipped, bins=32, range=(-5.0, 5.0))
    probabilities = counts[counts > 0].astype(np.float64)
    probabilities /= probabilities.sum()
    return float(-(probabilities * np.log2(probabilities)).sum())


def _distribution_features(prefix: str, values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    quantiles = np.quantile(values, [0.01, 0.05, 0.10, 0.90, 0.95, 0.99])
    skew = float(stats.skew(values, bias=False))
    kurtosis = float(stats.kurtosis(values, fisher=True, bias=False))
    result = {
        f"{prefix}_mean": float(np.mean(values)),
        f"{prefix}_std": float(np.std(values)),
        f"{prefix}_skew": skew if math.isfinite(skew) else 0.0,
        f"{prefix}_kurtosis": kurtosis if math.isfinite(kurtosis) else 0.0,
        f"{prefix}_q01": float(quantiles[0]),
        f"{prefix}_q05": float(quantiles[1]),
        f"{prefix}_q10": float(quantiles[2]),
        f"{prefix}_q90": float(quantiles[3]),
        f"{prefix}_q95": float(quantiles[4]),
        f"{prefix}_q99": float(quantiles[5]),
        f"{prefix}_fraction_gt_2": float(np.mean(values > 2.0)),
        f"{prefix}_fraction_gt_3": float(np.mean(values > 3.0)),
        f"{prefix}_fraction_lt_minus2": float(np.mean(values < -2.0)),
        f"{prefix}_fraction_lt_minus3": float(np.mean(values < -3.0)),
        f"{prefix}_entropy_32bin": _entropy(values),
    }
    return result


def _positive_tail_features(prefix: str, values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    absolute = np.abs(values)
    q90, q95, q99 = np.quantile(absolute, [0.90, 0.95, 0.99])
    top_count = max(1, int(math.ceil(absolute.size * 0.01)))
    top = np.partition(absolute, absolute.size - top_count)[-top_count:]
    return {
        f"{prefix}_abs_q90": float(q90),
        f"{prefix}_abs_q95": float(q95),
        f"{prefix}_abs_q99": float(q99),
        f"{prefix}_abs_top1pct_mean": float(np.mean(top)),
    }


def extract_case_features_from_images(
    *,
    phase_images: dict[str, sitk.Image],
    liver_mask_image: sitk.Image,
    erosion_mm: float,
    local_sigma_mm: float,
    minimum_mask_voxels: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    if set(phase_images) != set(PHASES):
        raise PipelineError("Conjunto de fases incompleto.")
    reference = phase_images["venous"]
    if not _same_geometry(reference, liver_mask_image):
        raise PipelineError("Máscara hepática não coincide com a grade venosa.")
    if any(not _same_geometry(reference, image) for image in phase_images.values()):
        raise PipelineError("Fases dinâmicas não compartilham geometria.")
    mask = sitk.GetArrayFromImage(liver_mask_image) > 0
    if int(mask.sum()) < minimum_mask_voxels:
        raise PipelineError("Máscara hepática abaixo do mínimo de voxels.")
    spacing_xyz = np.asarray(reference.GetSpacing(), dtype=np.float64)
    spacing_zyx = spacing_xyz[::-1]
    distance = ndimage.distance_transform_edt(mask, sampling=spacing_zyx)
    analysis_mask = distance >= float(erosion_mm)
    erosion_used = True
    if int(analysis_mask.sum()) < max(100, minimum_mask_voxels // 4):
        analysis_mask = mask
        erosion_used = False
    coordinates = np.where(mask)
    lower = [max(0, int(axis.min()) - 2) for axis in coordinates]
    upper = [
        min(mask.shape[index], int(axis.max()) + 3)
        for index, axis in enumerate(coordinates)
    ]
    slices = tuple(slice(start, stop) for start, stop in zip(lower, upper))
    cropped_mask = mask[slices]
    cropped_analysis = analysis_mask[slices]
    voxel_volume_mm3 = float(np.prod(spacing_xyz))
    extents_mm = [
        (upper[index] - lower[index]) * spacing_zyx[index]
        for index in range(3)
    ]
    features: dict[str, float] = {
        "liver_volume_ml": float(mask.sum() * voxel_volume_mm3 / 1000.0),
        "liver_analysis_volume_ml": float(
            analysis_mask.sum() * voxel_volume_mm3 / 1000.0
        ),
        "liver_bbox_extent_z_mm": float(extents_mm[0]),
        "liver_bbox_extent_y_mm": float(extents_mm[1]),
        "liver_bbox_extent_x_mm": float(extents_mm[2]),
        "liver_bbox_occupancy": float(
            mask.sum() / np.prod([stop - start for start, stop in zip(lower, upper)])
        ),
        "liver_axial_coverage_fraction": float(
            np.count_nonzero(mask.reshape(mask.shape[0], -1).any(axis=1))
            / mask.shape[0]
        ),
    }
    normalized: dict[str, np.ndarray] = {}
    raw_medians: dict[str, float] = {}
    raw_scales: dict[str, float] = {}
    sigma_zyx = tuple(
        max(0.5, float(local_sigma_mm) / float(spacing))
        for spacing in spacing_zyx
    )
    for phase in PHASES:
        array = sitk.GetArrayFromImage(phase_images[phase]).astype(
            np.float32, copy=False
        )[slices]
        values = array[cropped_analysis]
        if not np.isfinite(values).all():
            raise PipelineError(f"Fase {phase} contém NaN/Inf no fígado.")
        median, scale = _robust_center_scale(values)
        z_volume = (array.astype(np.float32) - median) / scale
        z_values = z_volume[cropped_analysis].astype(np.float64)
        normalized[phase] = z_values
        raw_medians[phase] = median
        raw_scales[phase] = scale
        features.update(_distribution_features(f"{phase}_robust_z", z_values))
        features[f"{phase}_scale_over_abs_median"] = float(
            scale / max(abs(median), scale * 1e-3)
        )
        smoothed = ndimage.gaussian_filter(
            array, sigma=sigma_zyx, mode="nearest"
        )
        residual = ((array - smoothed) / scale)[cropped_analysis]
        features.update(
            _positive_tail_features(f"{phase}_local_residual", residual)
        )
        gradient = ndimage.gaussian_gradient_magnitude(
            array, sigma=1.0, mode="nearest"
        )
        gradient_values = (gradient / scale)[cropped_analysis]
        features.update(
            _positive_tail_features(f"{phase}_gradient", gradient_values)
        )

    for left, right, name in (
        ("arterial", "venous", "arterial_minus_venous"),
        ("arterial", "delayed", "arterial_minus_delayed"),
        ("venous", "delayed", "venous_minus_delayed"),
    ):
        difference = normalized[left] - normalized[right]
        features.update(_distribution_features(name, difference))

    joint = np.minimum(
        normalized["arterial"] - normalized["venous"],
        normalized["arterial"] - normalized["delayed"],
    )
    features.update(_distribution_features("joint_arterial_dominance", joint))
    for left, right in (
        ("arterial", "venous"),
        ("arterial", "delayed"),
        ("venous", "delayed"),
    ):
        features[f"log_abs_median_ratio_{left}_over_{right}"] = float(
            math.log(
                (abs(raw_medians[left]) + raw_scales[left] * 1e-3)
                / (abs(raw_medians[right]) + raw_scales[right] * 1e-3)
            )
        )
        features[f"log_scale_ratio_{left}_over_{right}"] = float(
            math.log(raw_scales[left] / raw_scales[right])
        )
    if not all(math.isfinite(value) for value in features.values()):
        raise PipelineError("Feature radiômica não finita.")
    audit = {
        "mask_voxels": int(mask.sum()),
        "analysis_mask_voxels": int(analysis_mask.sum()),
        "erosion_used": erosion_used,
        "spacing_xyz": spacing_xyz.tolist(),
        "geometry": _geometry(reference),
        "feature_count": len(features),
    }
    return dict(sorted(features.items())), audit


def _resolve_case_files(
    *, case_id: str, dataset_id: str, config: dict[str, Any], root: Path
) -> dict[str, Path] | None:
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise PipelineError("Config radiômica exige sources.")
    for source in sources:
        if not isinstance(source, dict) or source.get("dataset_id") != dataset_id:
            continue
        source_kind = str(source.get("kind"))
        if source_kind == "lld_inputs_v2":
            case_root = root / str(source["inputs_root"]) / case_id
            if not case_root.is_dir():
                continue
            return {
                "arterial": case_root / "t1_arterial.nii.gz",
                "venous": case_root / "t1_venous.nii.gz",
                "delayed": case_root / "t1_delayed.nii.gz",
                "mask": case_root / "liver_mask_venous.nii.gz",
            }
        if source_kind == "openswiss_aligned":
            input_root = root / str(source["inputs_root"]) / case_id
            alignment_root = root / str(source["alignment_root"]) / case_id
            if not input_root.is_dir() or not alignment_root.is_dir():
                continue
            return {
                "arterial": alignment_root / "art_registered_to_venous.nii.gz",
                "venous": input_root / "dyn" / "t1_venous.nii.gz",
                "delayed": alignment_root / "del_registered_to_venous.nii.gz",
                "mask": input_root / "masks" / "liver_mask_venous.nii.gz",
            }
        raise PipelineError(f"kind radiômico desconhecido: {source_kind}")
    return None


def _append_fsync(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_radiomics_features(
    *,
    config_path: Path,
    candidate_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    staging = destination.with_name(f".{destination.name}.incomplete")
    if destination.exists():
        raise PipelineError("Features radiômicas já publicadas.")
    staging.mkdir(parents=True, exist_ok=True)
    config = load_radiomics_config(config_path)
    candidate_manifest = _json(
        Path(candidate_root) / "dataset_manifest.json", "Dataset candidato"
    )
    if candidate_manifest.get("ground_truth_read") is not False:
        raise PipelineError("Dataset candidato não é label-blind.")
    candidate_rows = _jsonl(
        Path(candidate_root) / "candidate_records.jsonl", "Candidatos"
    )
    case_dataset: dict[str, str] = {}
    for row in candidate_rows:
        case_id, dataset_id = str(row["case_id"]), str(row["dataset_id"])
        previous = case_dataset.setdefault(case_id, dataset_id)
        if previous != dataset_id:
            raise PipelineError("Dataset divergente para o mesmo caso.")
    upstream_failures = _jsonl(
        Path(candidate_root) / "technical_failures.jsonl", "Falhas anteriores"
    )
    checkpoint = staging / "checkpoint_features.jsonl"
    completed_rows = _jsonl(checkpoint, "Checkpoint") if checkpoint.exists() else []
    completed = {str(row["case_id"]) for row in completed_rows}
    failure_path = staging / "checkpoint_failures.jsonl"
    new_failures = _jsonl(failure_path, "Checkpoint de falhas") if failure_path.exists() else []
    completed.update(str(row["case_id"]) for row in new_failures)
    parameters = config.get("parameters") or {}
    for case_id in sorted(case_dataset):
        if case_id in completed:
            continue
        files = _resolve_case_files(
            case_id=case_id,
            dataset_id=case_dataset[case_id],
            config=config,
            root=root,
        )
        if files is None or any(not path.is_file() for path in files.values()):
            failure = {
                "case_id": case_id,
                "failure_reason": "missing_common_multiphase_source",
                "counts_as_error": True,
                "ground_truth_read": False,
                "lesion_mask_read": False,
            }
            _append_fsync(failure_path, failure)
            new_failures.append(failure)
            continue
        try:
            images = {
                phase: sitk.ReadImage(str(files[phase])) for phase in PHASES
            }
            mask = sitk.ReadImage(str(files["mask"]))
            features, audit = extract_case_features_from_images(
                phase_images=images,
                liver_mask_image=mask,
                erosion_mm=float(parameters.get("erosion_mm", 3.0)),
                local_sigma_mm=float(parameters.get("local_sigma_mm", 3.0)),
                minimum_mask_voxels=int(
                    parameters.get("minimum_mask_voxels", 1000)
                ),
            )
            row = {
                "schema": FEATURE_SCHEMA,
                "case_id": case_id,
                "patient_group_id": case_id,
                "dataset_id": case_dataset[case_id],
                "features": features,
                "audit": audit,
                "source_hashes": {
                    role: sha256_file(path) for role, path in files.items()
                },
                "source_paths": {
                    role: path.resolve().relative_to(root).as_posix()
                    for role, path in files.items()
                },
                "automatic_liver_mask_used": True,
                "ground_truth_read": False,
                "lesion_mask_read": False,
                "research_only": True,
                "clinical_use_allowed": False,
            }
            _append_fsync(checkpoint, row)
            completed_rows.append(row)
        except Exception as exc:
            failure = {
                "case_id": case_id,
                "failure_reason": f"radiomics_extraction_failed:{type(exc).__name__}:{exc}",
                "counts_as_error": True,
                "ground_truth_read": False,
                "lesion_mask_read": False,
            }
            _append_fsync(failure_path, failure)
            new_failures.append(failure)

    completed_rows.sort(key=lambda row: row["case_id"])
    all_failures = [
        {
            **row,
            "failure_origin": "upstream_candidate_dataset",
            "ground_truth_read": False,
            "lesion_mask_read": False,
        }
        for row in upstream_failures
    ] + [
        {**row, "failure_origin": "radiomics_extraction"} for row in new_failures
    ]
    all_failures.sort(key=lambda row: row["case_id"])
    features_path = staging / "features.jsonl"
    failures_path = staging / "technical_failures.jsonl"
    features_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in completed_rows
        ),
        encoding="utf-8",
    )
    failures_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in all_failures
        ),
        encoding="utf-8",
    )
    feature_names = (
        sorted(completed_rows[0]["features"]) if completed_rows else []
    )
    if any(sorted(row["features"]) != feature_names for row in completed_rows):
        raise PipelineError("Casos radiômicos possuem schemas diferentes.")
    body = {
        "schema": MANIFEST_SCHEMA,
        "status": "complete_label_blind_pending_independent_verification",
        "config_sha256": sha256_file(config_path),
        "candidate_dataset_signature": candidate_manifest["dataset_signature"],
        "expected_case_count": int(candidate_manifest["expected_case_count"]),
        "feature_case_count": len(completed_rows),
        "technical_failure_count": len(all_failures),
        "upstream_technical_failure_count": len(upstream_failures),
        "new_technical_failure_count": len(new_failures),
        "feature_count": len(feature_names),
        "feature_names": feature_names,
        "features_sha256": sha256_file(features_path),
        "technical_failures_sha256": sha256_file(failures_path),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "automatic_liver_masks_only": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    manifest = {**body, "radiomics_signature": canonical_sha256(body)}
    (staging / "radiomics_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checkpoint.unlink(missing_ok=True)
    failure_path.unlink(missing_ok=True)
    os.replace(staging, destination)
    return manifest


def verify_radiomics_features(
    *, candidate_root: Path, workspace_root: Path, output_root: Path
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    output = Path(output_root).resolve()
    candidate_manifest = _json(
        Path(candidate_root) / "dataset_manifest.json", "Dataset candidato"
    )
    manifest = _json(output / "radiomics_manifest.json", "Radiômica")
    unsigned = dict(manifest)
    signature = unsigned.pop("radiomics_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura radiômica diverge.")
    if manifest.get("candidate_dataset_signature") != candidate_manifest.get(
        "dataset_signature"
    ):
        raise PipelineError("Radiômica pertence a outro dataset.")
    features_path = output / "features.jsonl"
    failures_path = output / "technical_failures.jsonl"
    if manifest.get("features_sha256") != sha256_file(features_path):
        raise PipelineError("Features radiômicas foram alteradas.")
    if manifest.get("technical_failures_sha256") != sha256_file(failures_path):
        raise PipelineError("Falhas radiômicas foram alteradas.")
    rows = _jsonl(features_path, "Features radiômicas")
    failures = _jsonl(failures_path, "Falhas radiômicas")
    feature_names = list(manifest.get("feature_names") or [])
    cases = {str(row["case_id"]) for row in rows}
    failed = {str(row["case_id"]) for row in failures}
    if cases & failed:
        raise PipelineError("Caso com feature e falha simultâneas.")
    if len(cases) + len(failed) != int(manifest["expected_case_count"]):
        raise PipelineError("Cobertura radiômica incompleta.")
    for row in rows:
        if sorted(row.get("features") or {}) != feature_names:
            raise PipelineError("Schema de features divergente.")
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in row["features"].values()
        ):
            raise PipelineError("Feature não finita.")
        if row.get("ground_truth_read") is not False:
            raise PipelineError("Ground truth lido.")
        if row.get("lesion_mask_read") is not False:
            raise PipelineError("Máscara de lesão lida.")
        for role, relative in row["source_paths"].items():
            path = root / relative
            if sha256_file(path) != row["source_hashes"][role]:
                raise PipelineError(f"Fonte radiômica alterada: {path}")
    return manifest
