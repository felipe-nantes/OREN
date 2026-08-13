"""Versioned, PHI-safe contract for experimental liver segmentation.

This module deliberately does not participate in the production pipeline yet.
It establishes the disk contract used by shadow experiments while protecting
the files consumed by the classifier and the current 3-D viewer.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from .core import PipelineError, now_utc, sha256_of


INPUT_SCHEMA = "argos-segmentation-native-input-v2"
QUALITY_SCHEMA = "argos-segmentation-visualization-quality-v2"

INPUT_MANIFEST_NAME = "segmentation_input_manifest_v2.json"
VISUALIZATION_MASK_NAME = "mask_organ_visualization_v2.nii.gz"
QUALITY_MANIFEST_NAME = "segmentation_quality_manifest_v2.json"

PROTECTED_ARTIFACT_NAMES = frozenset(
    {
        "volume.nii.gz",
        "volume_zscore.nii.gz",
        "mask_organ.nii.gz",
        "mask_organ_union.nii.gz",
        "mask_organ_clean.nii.gz",
        "medgemma_report.json",
    }
)


@dataclass(frozen=True)
class ExperimentalSegmentationPaths:
    """Only paths an experimental segmenter is allowed to create."""

    input_manifest: Path
    visualization_mask: Path
    quality_manifest: Path


def experimental_paths(case_root: Path | str) -> ExperimentalSegmentationPaths:
    root = Path(case_root).resolve()
    return ExperimentalSegmentationPaths(
        input_manifest=root / INPUT_MANIFEST_NAME,
        visualization_mask=root / VISUALIZATION_MASK_NAME,
        quality_manifest=root / QUALITY_MANIFEST_NAME,
    )


def assert_experimental_output(path: Path | str, case_root: Path | str) -> Path:
    """Reject writes outside the case or over any production artifact."""

    candidate = Path(path).resolve()
    root = Path(case_root).resolve()
    allowed = set(experimental_paths(root).__dict__.values())
    if candidate.name in PROTECTED_ARTIFACT_NAMES:
        raise PipelineError(f"Artefato de producao protegido: {candidate.name}")
    if candidate not in allowed:
        raise PipelineError(
            "Saida experimental fora do contrato de segmentacao visual: "
            f"{candidate}"
        )
    return candidate


def _finite(values: tuple[float, ...]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def image_geometry(image: sitk.Image) -> dict[str, Any]:
    """Return validated physical geometry without patient metadata."""

    if image.GetDimension() != 3:
        raise PipelineError(
            f"Segmentacao experimental exige imagem 3-D; recebido {image.GetDimension()}-D."
        )
    size = tuple(int(value) for value in image.GetSize())
    spacing = tuple(float(value) for value in image.GetSpacing())
    origin = tuple(float(value) for value in image.GetOrigin())
    direction = tuple(float(value) for value in image.GetDirection())
    if any(value <= 0 for value in size):
        raise PipelineError("Geometria com tamanho vazio ou negativo.")
    if any(value <= 0 for value in spacing):
        raise PipelineError("Geometria com spacing vazio ou negativo.")
    if not (_finite(spacing) and _finite(origin) and _finite(direction)):
        raise PipelineError("Geometria contem valor nao finito.")
    matrix = np.asarray(direction, dtype=np.float64).reshape(3, 3)
    if abs(float(np.linalg.det(matrix))) < 1e-6:
        raise PipelineError("Matriz de direcao singular.")
    return {
        "size_xyz": list(size),
        "spacing_xyz_mm": list(spacing),
        "origin_xyz_mm": list(origin),
        "direction": list(direction),
        "pixel_id": int(image.GetPixelID()),
        "pixel_type": str(image.GetPixelIDTypeAsString()),
    }


def same_geometry(first: sitk.Image, second: sitk.Image, *, tolerance: float = 1e-5) -> bool:
    if first.GetDimension() != second.GetDimension():
        return False
    if tuple(first.GetSize()) != tuple(second.GetSize()):
        return False
    pairs = (
        (first.GetSpacing(), second.GetSpacing()),
        (first.GetOrigin(), second.GetOrigin()),
        (first.GetDirection(), second.GetDirection()),
    )
    return all(
        np.allclose(np.asarray(left), np.asarray(right), atol=tolerance, rtol=0.0)
        for left, right in pairs
    )


def build_native_input_manifest(
    *,
    source_volume: Path | str,
    reference_volume: Path | str,
    source_role: str,
) -> dict[str, Any]:
    """Describe a native-intensity segmentation input without leaking its path."""

    source_path = Path(source_volume).resolve()
    reference_path = Path(reference_volume).resolve()
    if not source_path.is_file() or not reference_path.is_file():
        raise PipelineError("Volume fonte ou volume de referencia ausente.")
    if not source_role or not source_role.replace("_", "").isalnum():
        raise PipelineError("Papel da fonte de segmentacao invalido.")
    try:
        source_image = sitk.ReadImage(str(source_path))
        reference_image = sitk.ReadImage(str(reference_path))
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"Falha ao ler entrada de segmentacao: {exc}") from exc
    return {
        "schema": INPUT_SCHEMA,
        "created_utc": now_utc(),
        "purpose": "visualization_only",
        "research_only": True,
        "classification_input_immutable": True,
        "source_role": source_role,
        "source": {
            "sha256": sha256_of(source_path),
            "geometry": image_geometry(source_image),
            "intensity_policy": "native_preserved",
        },
        "reference_grid": {
            "sha256": sha256_of(reference_path),
            "geometry": image_geometry(reference_image),
        },
        "source_already_on_reference_grid": same_geometry(source_image, reference_image),
        "output_mask_interpolation": "nearest_neighbor",
        "privacy": {
            "source_path_stored": False,
            "dicom_metadata_stored": False,
            "patient_identifiers_stored": False,
        },
    }


def validate_visualization_mask(
    mask_path: Path | str, reference_volume: Path | str
) -> dict[str, Any]:
    """Validate the candidate only; never copy it over a production mask."""

    candidate_path = Path(mask_path).resolve()
    reference_path = Path(reference_volume).resolve()
    if not candidate_path.is_file() or not reference_path.is_file():
        raise PipelineError("Mascara visual experimental ou referencia ausente.")
    try:
        mask_image = sitk.ReadImage(str(candidate_path))
        reference_image = sitk.ReadImage(str(reference_path))
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"Falha ao ler mascara visual experimental: {exc}") from exc
    if not same_geometry(mask_image, reference_image):
        raise PipelineError("Mascara visual experimental fora da grade de referencia.")
    values = sitk.GetArrayViewFromImage(mask_image)
    if not np.isfinite(values).all():
        raise PipelineError("Mascara visual experimental contem valor nao finito.")
    foreground = values > 0
    if not bool(foreground.any()):
        raise PipelineError("Mascara visual experimental vazia.")
    unique = np.unique(values)
    if not set(float(value) for value in unique).issubset({0.0, 1.0}):
        raise PipelineError("Mascara visual experimental deve ser binaria (0/1).")
    spacing = np.asarray(mask_image.GetSpacing(), dtype=np.float64)
    voxel_volume_ml = float(np.prod(spacing) / 1000.0)
    return {
        "sha256": sha256_of(candidate_path),
        "geometry": image_geometry(mask_image),
        "foreground_voxels": int(foreground.sum()),
        "volume_ml": float(foreground.sum() * voxel_volume_ml),
        "binary": True,
        "same_reference_grid": True,
    }


def build_quality_manifest(
    *,
    backend_id: str,
    backend_version: str,
    input_manifest: dict[str, Any],
    visualization_mask: Path | str,
    reference_volume: Path | str,
    elapsed_seconds: float,
    fallback_used: bool = False,
) -> dict[str, Any]:
    if input_manifest.get("schema") != INPUT_SCHEMA:
        raise PipelineError("Manifesto de entrada experimental incompativel.")
    if not backend_id or not backend_version:
        raise PipelineError("Backend experimental exige identificador e versao.")
    if not math.isfinite(float(elapsed_seconds)) or float(elapsed_seconds) < 0:
        raise PipelineError("Tempo de segmentacao invalido.")
    return {
        "schema": QUALITY_SCHEMA,
        "created_utc": now_utc(),
        "status": "APPROVED_WITH_WARNING" if fallback_used else "APPROVED",
        "purpose": "visualization_only",
        "classification_input_immutable": True,
        "backend": {"id": backend_id, "version": backend_version},
        "input_sha256": input_manifest["source"]["sha256"],
        "reference_sha256": input_manifest["reference_grid"]["sha256"],
        "mask": validate_visualization_mask(visualization_mask, reference_volume),
        "elapsed_seconds": float(elapsed_seconds),
        "fallback_used": bool(fallback_used),
        "human_review_required": True,
    }


def atomic_write_experimental_json(
    path: Path | str, payload: dict[str, Any], *, case_root: Path | str
) -> Path:
    destination = assert_experimental_output(path, case_root)
    allowed_json = {
        experimental_paths(case_root).input_manifest,
        experimental_paths(case_root).quality_manifest,
    }
    if destination not in allowed_json:
        raise PipelineError("Escritor JSON nao pode ocupar o artefato NIfTI experimental.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def approved_visualization_mask(case_root: Path | str) -> Path | None:
    """Return the shadow mask only when its complete safety receipt is valid.

    Invalid or partial shadow artifacts degrade to the existing viewer source
    instead of failing an otherwise valid exam.
    """

    paths = experimental_paths(case_root)
    if not paths.visualization_mask.is_file() or not paths.quality_manifest.is_file():
        return None
    try:
        quality = json.loads(paths.quality_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if quality.get("schema") != QUALITY_SCHEMA:
        return None
    if quality.get("status") not in {"APPROVED", "APPROVED_WITH_WARNING"}:
        return None
    required = {
        "purpose": "visualization_only",
        "classification_input_immutable": True,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "production_files_written": False,
    }
    if any(quality.get(key) != expected for key, expected in required.items()):
        return None
    recorded_hash = ((quality.get("mask") or {}).get("sha256"))
    if not recorded_hash or sha256_of(paths.visualization_mask) != recorded_hash:
        return None
    return paths.visualization_mask


__all__ = [
    "INPUT_SCHEMA",
    "QUALITY_SCHEMA",
    "INPUT_MANIFEST_NAME",
    "VISUALIZATION_MASK_NAME",
    "QUALITY_MANIFEST_NAME",
    "PROTECTED_ARTIFACT_NAMES",
    "ExperimentalSegmentationPaths",
    "experimental_paths",
    "assert_experimental_output",
    "image_geometry",
    "same_geometry",
    "build_native_input_manifest",
    "validate_visualization_mask",
    "build_quality_manifest",
    "atomic_write_experimental_json",
    "approved_visualization_mask",
]
