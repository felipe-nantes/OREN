"""Volumetria física, versionada e auditável das máscaras do OREN.

O volume autoritativo é contado na máscara binária e multiplicado pelo volume
físico do voxel. A malha 3-D nunca é a fonte da medida. Este módulo também não
afirma acurácia anatômica: sem uma referência humana, ele mede exatamente a
máscara automática recebida e explicita seus gates técnicos.
"""
from __future__ import annotations

import csv
import io
import itertools
import json
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from .core import PipelineError, array_from, now_utc, read_image, sha256_of

VOLUMETRY_SCHEMA = "oren-volumetry-manifest-v1"
VOLUMETRY_CONTRACT = "oren-hepatic-volumetry-contract-v1"
VOLUMETRY_JSON_NAME = "volumetry_manifest.json"
VOLUMETRY_CSV_NAME = "volumetry_summary.csv"

LIVER_ROLE = "orgao"
COUINAUD_PREFIX = "couinaud_"
VESSEL_ROLES = {"portal_vein", "inferior_vena_cava", "hepatic_vein"}


@dataclass(frozen=True)
class VolumetryStructure:
    """Estrutura autorizada pelo pipeline, nunca por caminho vindo do navegador."""

    role: str
    label: str
    mask_path: Path
    material: str = "anatomy"


def measurement_class(role: str, material: str) -> str:
    if role == LIVER_ROLE:
        return "whole_liver"
    if role == "lesao":
        return "manual_or_provided_lesion"
    if role == "candidato":
        return "automatic_unconfirmed_candidate"
    if role.startswith(COUINAUD_PREFIX):
        return "couinaud_segment"
    if material == "vessel" or role in VESSEL_ROLES:
        return "vascular_structure"
    if role == "regiao_classificada":
        return "classification_support_region"
    return "anatomical_structure"


def _as_3d(image: sitk.Image, description: str) -> sitk.Image:
    if image.GetDimension() == 3:
        return image
    size = list(image.GetSize())
    if image.GetDimension() < 3 or any(int(value) != 1 for value in size[3:]):
        raise PipelineError(f"{description} precisa ser uma imagem 3-D.")
    return sitk.Extract(
        image,
        size[:3] + [0] * (image.GetDimension() - 3),
        [0] * image.GetDimension(),
    )


def _finite_geometry(image: sitk.Image) -> bool:
    values = [*image.GetSpacing(), *image.GetOrigin(), *image.GetDirection()]
    return all(math.isfinite(float(value)) for value in values) and all(
        float(value) > 0 for value in image.GetSpacing()
    )


def _same_geometry(left: sitk.Image, right: sitk.Image, atol: float = 1e-5) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), atol=atol, rtol=0)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), atol=atol, rtol=0)
        and np.allclose(left.GetDirection(), right.GetDirection(), atol=atol, rtol=0)
    )


def _lps_dimensions_mm(mask: np.ndarray, image: sitk.Image) -> dict[str, float]:
    indexes_zyx = np.argwhere(mask)
    if indexes_zyx.size == 0:
        return {"left_right": 0.0, "anterior_posterior": 0.0, "superior_inferior": 0.0}
    minimum_xyz = indexes_zyx.min(axis=0)[::-1].astype(np.float64) - 0.5
    maximum_xyz = indexes_zyx.max(axis=0)[::-1].astype(np.float64) + 0.5
    origin = np.asarray(image.GetOrigin(), dtype=np.float64)
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    corners = np.asarray(
        list(itertools.product(*zip(minimum_xyz, maximum_xyz))), dtype=np.float64
    )
    points_lps = (direction @ (corners * spacing).T).T + origin
    extents = points_lps.max(axis=0) - points_lps.min(axis=0)
    return {
        "left_right": float(extents[0]),
        "anterior_posterior": float(extents[1]),
        "superior_inferior": float(extents[2]),
    }


def _border_contact(mask: np.ndarray) -> dict[str, Any]:
    faces = {
        "left": int(np.count_nonzero(mask[:, :, 0])),
        "right": int(np.count_nonzero(mask[:, :, -1])),
        "anterior": int(np.count_nonzero(mask[:, 0, :])),
        "posterior": int(np.count_nonzero(mask[:, -1, :])),
        "inferior": int(np.count_nonzero(mask[0, :, :])),
        "superior": int(np.count_nonzero(mask[-1, :, :])),
    }
    return {
        "touches_image_border": any(value > 0 for value in faces.values()),
        "border_voxels_by_face": faces,
        "contacting_faces": [key for key, value in faces.items() if value > 0],
    }


def _component_metrics(mask_image: sitk.Image, voxel_volume_ml: float) -> dict[str, Any]:
    components = sitk.ConnectedComponent(sitk.Cast(mask_image > 0, sitk.sitkUInt8), True)
    statistics = sitk.LabelShapeStatisticsImageFilter()
    statistics.ComputePerimeterOn()
    statistics.Execute(components)
    labels = list(statistics.GetLabels())
    counts = sorted(
        (int(statistics.GetNumberOfPixels(label)) for label in labels), reverse=True
    )
    total = int(sum(counts))
    largest = counts[0] if counts else 0
    surface_area_mm2 = float(
        sum(float(statistics.GetPerimeter(label)) for label in labels)
    )
    return {
        "component_count": len(counts),
        "largest_component_voxels": largest,
        "largest_component_volume_ml": float(largest * voxel_volume_ml),
        "largest_component_fraction": float(largest / total) if total else 0.0,
        "surface_area_cm2": surface_area_mm2 / 100.0,
    }


def measure_mask(
    structure: VolumetryStructure,
    reference: sitk.Image,
) -> tuple[dict[str, Any], np.ndarray]:
    path = Path(structure.mask_path)
    if not path.is_file():
        raise PipelineError(f"Máscara ausente para volumetria ({structure.role}): {path}")
    image = _as_3d(read_image(path), f"Máscara {structure.role}")
    if not _finite_geometry(image):
        raise PipelineError(f"Máscara {structure.role} possui geometria física inválida.")
    if not _same_geometry(reference, image):
        raise PipelineError(
            f"Máscara {structure.role} não está na mesma geometria do volume de referência."
        )
    mask = array_from(image) > 0
    voxels = int(np.count_nonzero(mask))
    spacing = tuple(float(value) for value in image.GetSpacing())
    voxel_volume_mm3 = float(math.prod(spacing))
    voxel_volume_ml = voxel_volume_mm3 / 1000.0
    volume_ml = float(voxels * voxel_volume_ml)
    classification = measurement_class(structure.role, structure.material)
    warnings: list[str] = []
    border = _border_contact(mask)
    if border["touches_image_border"]:
        warnings.append("mask_touches_image_border")
    components = _component_metrics(image, voxel_volume_ml) if voxels else {
        "component_count": 0,
        "largest_component_voxels": 0,
        "largest_component_volume_ml": 0.0,
        "largest_component_fraction": 0.0,
        "surface_area_cm2": 0.0,
    }
    if components["component_count"] > 1:
        warnings.append("multiple_connected_components")
    if voxels == 0:
        warnings.append("empty_mask")
    record = {
        "role": structure.role,
        "label": structure.label,
        "material": structure.material,
        "measurement_class": classification,
        "interpretation": (
            "automatic_unconfirmed_region_not_a_confirmed_lesion"
            if classification == "automatic_unconfirmed_candidate"
            else "segmented_structure_volume"
        ),
        "authoritative_measurement_source": "binary_mask_in_physical_space",
        "mask_sha256": sha256_of(path),
        "voxel_count": voxels,
        "voxel_spacing_mm_xyz": list(spacing),
        "voxel_volume_mm3": voxel_volume_mm3,
        "volume_ml": volume_ml,
        "dimensions_lps_mm": _lps_dimensions_mm(mask, image),
        **components,
        **border,
        "technical_quality": {
            "usable": voxels > 0,
            "warnings": warnings,
        },
    }
    return record, mask


def _couinaud_partition(
    liver: np.ndarray | None,
    measured_masks: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    segment_roles = sorted(
        role for role in measured_masks if role.startswith(COUINAUD_PREFIX)
    )
    if not segment_roles:
        return {
            "available": False,
            "gate_passed": False,
            "reason": "couinaud_masks_not_available",
            "segment_roles": [],
        }
    if liver is None:
        return {
            "available": True,
            "gate_passed": False,
            "reason": "whole_liver_mask_not_available",
            "segment_roles": segment_roles,
        }
    stack = np.stack([measured_masks[role] for role in segment_roles], axis=0)
    membership = np.sum(stack, axis=0, dtype=np.uint16)
    union = membership > 0
    overlap = membership > 1
    missing = liver & ~union
    outside = union & ~liver
    liver_voxels = int(np.count_nonzero(liver))
    union_inside = int(np.count_nonzero(union & liver))
    overlap_voxels = int(np.count_nonzero(overlap))
    missing_voxels = int(np.count_nonzero(missing))
    outside_voxels = int(np.count_nonzero(outside))
    exact = (
        len(segment_roles) == 8
        and overlap_voxels == 0
        and missing_voxels == 0
        and outside_voxels == 0
    )
    return {
        "available": True,
        "gate_passed": exact,
        "policy": "eight_disjoint_segments_exactly_partition_whole_liver",
        "segment_roles": segment_roles,
        "expected_segment_count": 8,
        "actual_segment_count": len(segment_roles),
        "whole_liver_voxels": liver_voxels,
        "segment_union_inside_liver_voxels": union_inside,
        "missing_liver_voxels": missing_voxels,
        "overlapping_segment_voxels": overlap_voxels,
        "segment_voxels_outside_liver": outside_voxels,
        "liver_coverage_percent": (
            float(union_inside / liver_voxels * 100.0) if liver_voxels else 0.0
        ),
    }


def _load_segmentation_quality(
    value: Mapping[str, Any] | Path | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _volumetry_quality_assessment(
    liver_record: Mapping[str, Any] | None,
    segmentation_quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Grade technical reliability without pretending to know clinical truth."""

    reasons: list[str] = []
    if not liver_record or not (liver_record.get("technical_quality") or {}).get("usable"):
        return {
            "grade": "D",
            "label": "nao_confiavel",
            "usable": False,
            "reasons": ["whole_liver_mask_unusable"],
            "scope": "technical_consistency_not_anatomical_accuracy",
        }
    if liver_record.get("touches_image_border"):
        reasons.append("whole_liver_touches_image_border")
    if float(liver_record.get("largest_component_fraction", 0.0)) < 0.985:
        reasons.append("whole_liver_fragmented")

    adaptive = (segmentation_quality or {}).get("adaptive")
    grade = "B"
    label = "adequada_com_mascara_unica"
    source_agreement = None
    if isinstance(adaptive, Mapping):
        agreement = adaptive.get("agreement") or (
            (adaptive.get("baseline") or {}).get("agreement_with_primary")
        )
        if isinstance(agreement, Mapping):
            source_agreement = {
                "dice": float(agreement.get("dice", 0.0)),
                "jaccard": float(agreement.get("jaccard", 0.0)),
            }
        if adaptive.get("triggered") and not adaptive.get("secondary"):
            grade, label = "C", "revisao_tecnica_recomendada"
            reasons.append("secondary_confirmation_unavailable")
        elif source_agreement and source_agreement["dice"] >= 0.92:
            grade, label = "A", "alta_consistencia_tecnica"
        elif source_agreement and source_agreement["dice"] < 0.80:
            grade, label = "C", "revisao_tecnica_recomendada"
            reasons.append("low_mask_source_agreement")
        elif source_agreement:
            grade, label = "B", "consistencia_tecnica_moderada"
    else:
        reasons.append("cross_source_agreement_not_available")

    if reasons and grade == "A":
        grade, label = "B", "consistencia_tecnica_moderada"
    if any(reason in reasons for reason in (
        "whole_liver_fragmented", "secondary_confirmation_unavailable",
        "low_mask_source_agreement",
    )):
        grade, label = "C", "revisao_tecnica_recomendada"
    return {
        "grade": grade,
        "label": label,
        "usable": grade != "D",
        "reasons": reasons,
        "source_agreement": source_agreement,
        "scope": "technical_consistency_not_anatomical_accuracy",
    }


def _technical_volume_range(
    liver_volume_ml: float | None,
    segmentation_quality: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if liver_volume_ml is None:
        return None
    candidates = [float(liver_volume_ml)]
    adaptive = (segmentation_quality or {}).get("adaptive")
    if isinstance(adaptive, Mapping):
        for key in ("primary", "secondary", "baseline"):
            item = adaptive.get(key)
            if isinstance(item, Mapping) and float(item.get("volume_ml", 0.0)) > 0:
                candidates.append(float(item["volume_ml"]))
    lower = min(candidates)
    upper = max(candidates)
    spread = upper - lower
    return {
        "lower_ml": lower,
        "upper_ml": upper,
        "spread_ml": spread,
        "spread_percent_of_reported": float(spread / liver_volume_ml * 100.0)
        if liver_volume_ml else 0.0,
        "source_count": len(candidates),
        "interpretation": "technical_mask_variation_not_statistical_confidence_interval",
    }


def build_volumetry_manifest(
    *,
    reference_volume: Path,
    structures: Iterable[VolumetryStructure],
    output_dir: Path,
    case_id: str | None = None,
    segmentation_quality: Mapping[str, Any] | Path | None = None,
) -> dict[str, Any]:
    """Mede e persiste JSON/CSV de forma atômica, sem alterar máscaras."""

    reference_path = Path(reference_volume)
    if not reference_path.is_file():
        raise PipelineError(f"Volume de referência ausente: {reference_path}")
    reference = _as_3d(read_image(reference_path), "Volume de referência")
    if not _finite_geometry(reference):
        raise PipelineError("Volume de referência possui geometria física inválida.")

    ordered = sorted(structures, key=lambda item: (item.role != LIVER_ROLE, item.role))
    records: list[dict[str, Any]] = []
    masks: dict[str, np.ndarray] = {}
    for structure in ordered:
        record, mask = measure_mask(structure, reference)
        records.append(record)
        masks[structure.role] = mask

    liver_record = next((row for row in records if row["role"] == LIVER_ROLE), None)
    liver_volume = float(liver_record["volume_ml"]) if liver_record else None
    for record in records:
        record["percent_of_whole_liver"] = (
            float(record["volume_ml"] / liver_volume * 100.0)
            if liver_volume and record["role"] != LIVER_ROLE
            else (100.0 if liver_volume and record["role"] == LIVER_ROLE else None)
        )

    partition = _couinaud_partition(masks.get(LIVER_ROLE), masks)
    if partition.get("available") and not partition.get("gate_passed"):
        for record in records:
            if record["measurement_class"] == "couinaud_segment":
                record["technical_quality"]["usable"] = False
                record["technical_quality"]["warnings"].append(
                    "couinaud_partition_gate_failed"
                )

    segmentation_receipt = _load_segmentation_quality(segmentation_quality)
    quality_assessment = _volumetry_quality_assessment(
        liver_record, segmentation_receipt
    )
    technical_range = _technical_volume_range(liver_volume, segmentation_receipt)
    # Dict local tipado para o mypy verificar o csv_sha256 adicionado depois da
    # escrita do CSV (REF-02/W-005); é o MESMO objeto referenciado no manifest.
    artifacts: dict[str, str] = {
        "json": VOLUMETRY_JSON_NAME,
        "csv": VOLUMETRY_CSV_NAME,
    }
    manifest = {
        "schema": VOLUMETRY_SCHEMA,
        "schema_version": 1,
        "contract": VOLUMETRY_CONTRACT,
        "created_utc": now_utc(),
        "case_id": case_id,
        "scope": "physical_measurement_of_segmented_masks",
        "research_only": True,
        "human_review_required": True,
        "diagnostic_claim": False,
        "segmentation_accuracy_claim": False,
        "authoritative_volume_source": "binary_mask_voxel_count_times_physical_voxel_volume",
        "mesh_is_authoritative_for_volume": False,
        "reference_volume_sha256": sha256_of(reference_path),
        "reference_geometry": {
            "size_xyz": list(reference.GetSize()),
            "spacing_mm_xyz": list(reference.GetSpacing()),
            "origin_lps_mm": list(reference.GetOrigin()),
            "direction": list(reference.GetDirection()),
        },
        "definitions": {
            "whole_liver": (
                "Inclui parênquima, lesões e vasos intra-hepáticos representados "
                "dentro da máscara hepática; exclui vesícula, veia porta "
                "extra-hepática, veia cava inferior, tecido vizinho e fragmentos "
                "removidos pelo refino. Não é substituída pelo volume da malha."
            ),
            "automatic_unconfirmed_candidate": (
                "Região automática não confirmada; seu volume não equivale a volume tumoral."
            ),
            "mesh_fidelity": (
                "Controle separado de reconstrução; não mede acurácia anatômica da máscara."
            ),
        },
        "whole_liver_summary": {
            "volume_ml": liver_volume,
            "technical_range_ml": technical_range,
            "quality": quality_assessment,
            "segmentation_source": (
                ((segmentation_receipt or {}).get("adaptive") or {}).get(
                    "selected_output", "single_mask"
                )
            ),
        },
        "structures": records,
        "couinaud_partition": partition,
        "artifacts": artifacts,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv_atomic(output / VOLUMETRY_CSV_NAME, records)
    artifacts["csv_sha256"] = sha256_of(output / VOLUMETRY_CSV_NAME)
    # O JSON é o marcador autoritativo de conclusão e por isso é publicado por
    # último: uma interrupção nunca deixa um manifesto novo apontando para CSV
    # ausente ou ainda incompleto.
    _write_json_atomic(output / VOLUMETRY_JSON_NAME, manifest)
    return manifest


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_csv_atomic(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    stream = io.StringIO(newline="")
    fieldnames = [
        "role",
        "label",
        "measurement_class",
        "volume_ml",
        "percent_of_whole_liver",
        "voxel_count",
        "voxel_volume_mm3",
        "left_right_mm",
        "anterior_posterior_mm",
        "superior_inferior_mm",
        "component_count",
        "largest_component_fraction",
        "surface_area_cm2",
        "touches_image_border",
        "technical_quality_usable",
        "technical_warnings",
        "mask_sha256",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in records:
        dimensions = record["dimensions_lps_mm"]
        quality = record["technical_quality"]
        writer.writerow(
            {
                "role": record["role"],
                "label": record["label"],
                "measurement_class": record["measurement_class"],
                "volume_ml": format(float(record["volume_ml"]), ".10f"),
                "percent_of_whole_liver": (
                    "" if record["percent_of_whole_liver"] is None
                    else format(float(record["percent_of_whole_liver"]), ".10f")
                ),
                "voxel_count": record["voxel_count"],
                "voxel_volume_mm3": format(float(record["voxel_volume_mm3"]), ".10f"),
                "left_right_mm": format(float(dimensions["left_right"]), ".6f"),
                "anterior_posterior_mm": format(float(dimensions["anterior_posterior"]), ".6f"),
                "superior_inferior_mm": format(float(dimensions["superior_inferior"]), ".6f"),
                "component_count": record["component_count"],
                "largest_component_fraction": format(
                    float(record["largest_component_fraction"]), ".10f"
                ),
                "surface_area_cm2": format(float(record["surface_area_cm2"]), ".6f"),
                "touches_image_border": str(record["touches_image_border"]).lower(),
                "technical_quality_usable": str(quality["usable"]).lower(),
                "technical_warnings": "|".join(quality["warnings"]),
                "mask_sha256": record["mask_sha256"],
            }
        )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(stream.getvalue(), encoding="utf-8", newline="")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_volumetry_artifacts(output_dir: Path | str) -> dict[str, Any]:
    """Independently verify the persisted pair without reading model meshes."""

    output = Path(output_dir)
    json_path = output / VOLUMETRY_JSON_NAME
    csv_path = output / VOLUMETRY_CSV_NAME
    if not json_path.is_file() or not csv_path.is_file():
        raise PipelineError("Artefatos de volumetria incompletos.")
    try:
        manifest = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Manifesto de volumetria invalido.") from exc
    if manifest.get("schema") != VOLUMETRY_SCHEMA or manifest.get("contract") != VOLUMETRY_CONTRACT:
        raise PipelineError("Schema ou contrato de volumetria incompativel.")
    if (manifest.get("artifacts") or {}).get("csv_sha256") != sha256_of(csv_path):
        raise PipelineError("Hash do CSV de volumetria inconsistente.")
    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    records = manifest.get("structures") or []
    if len(rows) != len(records):
        raise PipelineError("CSV e JSON possuem quantidades de estruturas diferentes.")
    by_role = {str(row.get("role")): row for row in records}
    if len(by_role) != len(records):
        raise PipelineError("Manifesto possui papeis de estrutura duplicados.")
    for row in rows:
        record = by_role.get(str(row.get("role")))
        if record is None:
            raise PipelineError("CSV contem estrutura ausente no JSON.")
        expected = float(record["voxel_count"]) * float(record["voxel_volume_mm3"]) / 1000.0
        if not math.isclose(float(record["volume_ml"]), expected, rel_tol=0, abs_tol=1e-9):
            raise PipelineError("Volume JSON nao corresponde a contagem fisica de voxels.")
        if not math.isclose(float(row["volume_ml"]), expected, rel_tol=0, abs_tol=1e-8):
            raise PipelineError("Volume CSV nao corresponde a contagem fisica de voxels.")
    partition = manifest.get("couinaud_partition") or {}
    if partition.get("gate_passed") and not (
        partition.get("actual_segment_count") == 8
        and partition.get("missing_liver_voxels") == 0
        and partition.get("overlapping_segment_voxels") == 0
        and partition.get("segment_voxels_outside_liver") == 0
    ):
        raise PipelineError("Gate Couinaud aprovado sem particao exata.")
    return {
        "status": "verified",
        "schema": "oren-volumetry-verification-v1",
        "manifest_sha256": sha256_of(json_path),
        "csv_sha256": sha256_of(csv_path),
        "structure_count": len(records),
        "whole_liver_volume_ml": (
            (manifest.get("whole_liver_summary") or {}).get("volume_ml")
        ),
        "quality_grade": (
            ((manifest.get("whole_liver_summary") or {}).get("quality") or {}).get("grade")
        ),
        "couinaud_gate_passed": bool(partition.get("gate_passed")),
    }


__all__ = [
    "VOLUMETRY_SCHEMA", "VOLUMETRY_CONTRACT", "VOLUMETRY_JSON_NAME",
    "VOLUMETRY_CSV_NAME", "VolumetryStructure", "measurement_class",
    "measure_mask", "build_volumetry_manifest", "verify_volumetry_artifacts",
]
