"""Auditoria retrospectiva isolada do atlas axial OpenSwissHCC v17.

Este módulo não participa da inferência e não importa o cliente MedGemma. A
etapa ``freeze`` não lê máscaras de lesão. A etapa ``audit`` só pode ser
executada depois de autorização explícita para as máscaras de desenvolvimento.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_axial_atlas import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
)
from dtwin.benchmark.openswisshcc_axial_atlas import (
    PROTOCOL_SIGNATURE as ATLAS_PROTOCOL_SIGNATURE,
)
from dtwin.core import PipelineError

PROTOCOL_SCHEMA = "argos-openswisshcc-v17-atlas-audit-protocol-v1"
AUDIT_SCHEMA = "argos-openswisshcc-v17-atlas-retrospective-audit-v1"
AUTHORIZED_EXTRACTION_SCHEMA = "argos-openswisshcc-v16-authorized-mask-extraction-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON inválido na auditoria v17: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado na auditoria v17: {path}.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError
            rows.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PipelineError(
            f"JSONL inválido na linha {number if 'number' in locals() else 0}: {path}."
        ) from exc
    return rows


def _write_json_atomic(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise PipelineError("Auditoria v17 recusou CSV vazio.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _refuse_holdout(*paths: Path) -> None:
    for path in paths:
        if any("holdout" in part.lower() for part in Path(path).resolve().parts):
            raise PipelineError("Auditoria v17 recusou caminho de holdout.")


def _manual_mask_index_aligned(mask: sitk.Image, reference: sitk.Image) -> bool:
    return (
        mask.GetSize() == reference.GetSize()
        and np.allclose(mask.GetSpacing(), reference.GetSpacing(), rtol=0, atol=1e-7)
        and np.allclose(mask.GetOrigin(), reference.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(mask.GetDirection(), reference.GetDirection(), rtol=0, atol=1e-6)
    )


def _metric(successes: int, total: int) -> dict[str, Any]:
    if total < 0 or successes < 0 or successes > total:
        raise PipelineError("Contagem inválida na métrica v17.")
    if total == 0:
        return {"successes": successes, "total": total, "fraction": None, "percent": None}
    fraction = successes / total
    z = 1.959963984540054
    denominator = 1 + z * z / total
    center = (fraction + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(
        fraction * (1 - fraction) / total + z * z / (4 * total * total)
    ) / denominator
    return {
        "successes": successes,
        "total": total,
        "fraction": fraction,
        "percent": 100.0 * fraction,
        "wilson_95_fraction": [max(0.0, center - radius), min(1.0, center + radius)],
    }


def _mask_bbox_2d(
    mask_2d: np.ndarray, margin_fraction: float
) -> tuple[int, int, int, int]:
    """Replica o crop determinístico usado pelo gerador fallback aprovado."""
    rows, columns = np.where(np.asarray(mask_2d, dtype=bool))
    if rows.size == 0:
        raise PipelineError("Máscara hepática vazia ao reconstruir crop fallback v17.")
    row_span = int(rows.max() - rows.min() + 1)
    column_span = int(columns.max() - columns.min() + 1)
    row_margin = max(2, int(np.ceil(row_span * margin_fraction)))
    column_margin = max(2, int(np.ceil(column_span * margin_fraction)))
    return (
        max(0, int(rows.min()) - row_margin),
        min(mask_2d.shape[0], int(rows.max()) + row_margin + 1),
        max(0, int(columns.min()) - column_margin),
        min(mask_2d.shape[1], int(columns.max()) + column_margin + 1),
    )


def audit_mask_array(
    mask_zyx: np.ndarray,
    *,
    represented_axial_indices: Sequence[int],
    crop_bounds_zyx: Sequence[Sequence[int]],
    spacing_xyz: Sequence[float],
) -> dict[str, Any]:
    """Calcula visibilidade exata de uma máscara, sem resample ou inferência."""
    mask = np.asarray(mask_zyx, dtype=bool)
    if mask.ndim != 3 or not mask.any():
        raise PipelineError("Máscara manual v17 vazia ou não tridimensional.")
    if len(crop_bounds_zyx) != 3 or any(len(bounds) != 2 for bounds in crop_bounds_zyx):
        raise PipelineError("Crop v17 inválido.")
    bounds = [[int(value) for value in pair] for pair in crop_bounds_zyx]
    if any(start < 0 or stop <= start or stop > mask.shape[axis] for axis, (start, stop) in enumerate(bounds)):
        raise PipelineError("Crop v17 fora dos limites da máscara.")
    represented = [int(index) for index in represented_axial_indices]
    if represented != sorted(set(represented)) or any(
        index < 0 or index >= mask.shape[0] for index in represented
    ):
        raise PipelineError("Índices axiais v17 inválidos ou duplicados.")

    visible = np.zeros(mask.shape, dtype=bool)
    z_start, z_stop = bounds[0]
    y_start, y_stop = bounds[1]
    x_start, x_stop = bounds[2]
    visible_z = [index for index in represented if z_start <= index < z_stop]
    visible[visible_z, y_start:y_stop, x_start:x_stop] = True
    intersection = np.logical_and(mask, visible)
    lesion_indices = np.argwhere(mask)
    lesion_z = sorted(set(int(index) for index in lesion_indices[:, 0]))
    total_voxels = int(mask.sum())
    visible_voxels = int(intersection.sum())
    spacing = [float(value) for value in spacing_xyz]
    if len(spacing) != 3 or any(not math.isfinite(value) or value <= 0 for value in spacing):
        raise PipelineError("Spacing v17 inválido.")
    volume_mm3 = total_voxels * float(np.prod(spacing))
    equivalent_diameter_mm = (6.0 * volume_mm3 / math.pi) ** (1.0 / 3.0)
    if equivalent_diameter_mm < 10.0:
        size_bin = "lt_10_mm"
    elif equivalent_diameter_mm < 20.0:
        size_bin = "10_to_lt_20_mm"
    else:
        size_bin = "ge_20_mm"
    return {
        "lesion_voxels": total_voxels,
        "visible_voxels": visible_voxels,
        "visible_fraction": visible_voxels / total_voxels,
        "any_voxel_visible": visible_voxels > 0,
        "all_voxels_visible": visible_voxels == total_voxels,
        "lesion_axial_indices": lesion_z,
        "visible_lesion_axial_indices": sorted(
            set(int(index) for index in np.argwhere(intersection)[:, 0])
        )
        if visible_voxels
        else [],
        "all_lesion_axial_indices_represented": set(lesion_z).issubset(represented),
        "lesion_volume_mm3": volume_mm3,
        "equivalent_sphere_diameter_mm": equivalent_diameter_mm,
        "size_bin": size_bin,
    }


def _validated_authorized_masks(
    *,
    authorized_mask_root: Path,
    extraction_manifest_path: Path,
    allowed_case_ids: set[str],
) -> dict[str, list[tuple[str, Path, str]]]:
    manifest = _load_json(extraction_manifest_path)
    safety = manifest.get("safety", {})
    masks = manifest.get("masks")
    if (
        manifest.get("schema") != AUTHORIZED_EXTRACTION_SCHEMA
        or not isinstance(masks, list)
        or len(masks) != int(manifest.get("mask_count", -1))
        or safety.get("retrospective_only") is not True
        or safety.get("inference_executed") is not False
        or safety.get("medgemma_called") is not False
        or safety.get("lesion_masks_used_for_inference") is not False
        or safety.get("lesion_masks_sent_to_medgemma") is not False
        or safety.get("holdout_opened") is not False
        or safety.get("development_only") is not True
    ):
        raise PipelineError("Manifesto de máscaras autorizadas inválido para v17.")
    indexed: dict[str, list[tuple[str, Path, str]]] = {}
    expected_paths: set[Path] = set()
    seen_keys: set[tuple[str, str]] = set()
    root = authorized_mask_root.resolve()
    for item in masks:
        case_id = str(item.get("case_id", ""))
        lesion_id = str(item.get("lesion_id", ""))
        relative = Path(str(item.get("relative_path", "")))
        key = (case_id, lesion_id)
        if (
            case_id not in allowed_case_ids
            or not lesion_id.startswith("L")
            or key in seen_keys
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix()
            != f"{case_id}/{lesion_id}_t1_venous_seg.nii.gz"
        ):
            raise PipelineError("Entrada insegura ou duplicada no manifesto autorizado v17.")
        seen_keys.add(key)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise PipelineError("Máscara autorizada escapou da raiz v17.")
        if (
            not path.is_file()
            or path.stat().st_size != int(item.get("bytes", -1))
            or _sha256(path) != item.get("sha256")
        ):
            raise PipelineError(f"Máscara autorizada ausente ou alterada: {relative}.")
        expected_paths.add(path)
        indexed.setdefault(case_id, []).append((lesion_id, path, str(item["sha256"])))
    actual_paths = {
        path.resolve() for path in root.rglob("*_t1_venous_seg.nii.gz") if path.is_file()
    }
    if actual_paths != expected_paths:
        raise PipelineError("Arquivos de máscaras autorizadas extras ou ausentes na raiz v17.")
    for values in indexed.values():
        values.sort(key=lambda item: item[0])
    return indexed


def freeze_protocol(
    *,
    atlas_root: Path,
    source_panel_root: Path,
    input_manifest_path: Path,
    input_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Congela a auditoria sem listar, abrir ou decodificar máscaras de lesão."""
    atlas_root = Path(atlas_root).resolve()
    source_panel_root = Path(source_panel_root).resolve()
    input_manifest_path = Path(input_manifest_path).resolve()
    input_root = Path(input_root).resolve()
    output_path = Path(output_path).resolve()
    _refuse_holdout(
        atlas_root, source_panel_root, input_manifest_path, input_root, output_path
    )
    if output_path.exists():
        raise PipelineError("Protocolo de auditoria v17 já existe; sobrescrita recusada.")
    cohort_path = atlas_root / "cohort_manifest.json"
    cohort = _load_json(cohort_path)
    if (
        cohort.get("schema_version") != COHORT_SCHEMA
        or cohort.get("protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
        or int(cohort.get("case_count", -1)) != 87
        or cohort.get("all_gates_passed") is not True
        or cohort.get("ground_truth_read") is not False
        or cohort.get("lesion_mask_read") is not False
        or cohort.get("holdout_read") is not False
    ):
        raise PipelineError("Coorte cega v17 inválida para auditoria.")
    input_rows = {str(row.get("case_id", "")): row for row in _jsonl(input_manifest_path)}
    cases: list[dict[str, Any]] = []
    for record in cohort.get("cases", []):
        case_id = str(record.get("case_id", ""))
        if not case_id.startswith("anon-openswiss-"):
            raise PipelineError("case_id inválido na coorte v17.")
        atlas_manifest_path = atlas_root / str(record.get("manifest", ""))
        if _sha256(atlas_manifest_path) != record.get("manifest_sha256"):
            raise PipelineError(f"Hash do manifesto do atlas divergiu: {case_id}.")
        atlas_manifest = _load_json(atlas_manifest_path)
        if atlas_manifest.get("schema_version") != CASE_SCHEMA:
            raise PipelineError(f"Schema de caso v17 inválido: {case_id}.")
        atlas_values = atlas_manifest.get("atlas", {})
        represented = atlas_values.get("represented_axial_indices")
        if represented != atlas_values.get("expected_axial_indices"):
            raise PipelineError(f"Cobertura axial v17 deixou de ser exata: {case_id}.")
        source_manifest_path = source_panel_root / case_id / "medgemma_liver_screening_manifest.json"
        if _sha256(source_manifest_path) != atlas_manifest.get("source", {}).get(
            "panel_manifest_sha256"
        ):
            raise PipelineError(f"Manifesto de painel-fonte divergiu: {case_id}.")
        source_manifest = _load_json(source_manifest_path)
        input_record = input_rows.get(case_id)
        if not input_record or input_record.get("split") != "development":
            raise PipelineError(f"Input de desenvolvimento ausente: {case_id}.")
        files = input_record.get("files")
        venous = [item for item in files if item.get("role") == "t1_venous"] if isinstance(files, list) else []
        if len(venous) != 1:
            raise PipelineError(f"Referência venosa ambígua: {case_id}.")
        reference_path = input_root / str(venous[0].get("relative_path", ""))
        if _sha256(reference_path) != venous[0].get("sha256"):
            raise PipelineError(f"Hash da referência venosa divergiu: {case_id}.")
        crop_bounds = source_manifest.get("crop_bounds_zyx")
        crop_source = "source_panel_manifest"
        liver_mask_sha256: str | None = None
        if not isinstance(crop_bounds, list):
            margin = source_manifest.get("crop_margin_fraction")
            liver_masks = (
                [item for item in files if item.get("role") == "liver_mask_venous"]
                if isinstance(files, list)
                else []
            )
            if (
                source_manifest.get("crop_to_liver") is not True
                or not isinstance(margin, (int, float))
                or not 0 <= float(margin) <= 1
                or len(liver_masks) != 1
            ):
                raise PipelineError(f"Crop fallback não pode ser reconstruído: {case_id}.")
            liver_mask_path = input_root / str(liver_masks[0].get("relative_path", ""))
            liver_mask_sha256 = _sha256(liver_mask_path)
            if (
                liver_mask_sha256 != liver_masks[0].get("sha256")
                or liver_mask_sha256 != source_manifest.get("input_liver_mask_sha256")
            ):
                raise PipelineError(f"Hash da máscara hepática fallback divergiu: {case_id}.")
            liver_mask = sitk.GetArrayFromImage(sitk.ReadImage(str(liver_mask_path))) > 0
            y_start, y_stop, x_start, x_stop = _mask_bbox_2d(
                liver_mask.any(axis=0), float(margin)
            )
            crop_bounds = [
                [0, int(liver_mask.shape[0])],
                [y_start, y_stop],
                [x_start, x_stop],
            ]
            crop_source = "reconstructed_from_frozen_liver_mask_and_margin"
        cases.append(
            {
                "case_id": case_id,
                "atlas_manifest_sha256": record["manifest_sha256"],
                "atlas_set_sha256": record["atlas_set_sha256"],
                "source_panel_manifest_sha256": _sha256(source_manifest_path),
                "represented_axial_indices": represented,
                "crop_bounds_zyx": crop_bounds,
                "crop_source": crop_source,
                "liver_mask_sha256_if_reconstructed": liver_mask_sha256,
                "reference_relative_path": str(venous[0]["relative_path"]),
                "reference_sha256": str(venous[0]["sha256"]),
            }
        )
    if len(cases) != 87 or len({case["case_id"] for case in cases}) != 87:
        raise PipelineError("Protocolo v17 exige exatamente 87 casos únicos.")
    protocol = {
        "schema_version": PROTOCOL_SCHEMA,
        "purpose": "retrospective_visibility_audit_of_v17_axial_atlas",
        "atlas_protocol_signature": ATLAS_PROTOCOL_SIGNATURE,
        "case_count": 87,
        "sources": {
            "atlas_cohort_manifest_sha256": _sha256(cohort_path),
            "input_manifest_sha256": _sha256(input_manifest_path),
        },
        "definitions": {
            "any_voxel_visible": "manual_mask_intersects_represented_z_and_source_liver_crop",
            "all_voxels_visible": "every_manual_mask_voxel_inside_represented_z_and_source_liver_crop",
            "lesion_size": "equivalent_sphere_diameter_from_mask_volume_and_spacing",
            "confidence_interval": "wilson_95_percent",
        },
        "safety": {
            "development_only": True,
            "ground_truth_label_read": False,
            "lesion_mask_read_during_freeze": False,
            "liver_mask_read_for_fallback_crop_reconstruction": True,
            "medgemma_called": False,
            "lesion_masks_sent_to_medgemma": False,
            "holdout_opened": False,
        },
        "cases": cases,
    }
    protocol["protocol_signature"] = _canonical_sha(protocol)
    _write_json_atomic(output_path, protocol)
    return protocol


def run_audit(
    *,
    protocol_path: Path,
    authorized_mask_root: Path,
    extraction_manifest_path: Path,
    input_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Lê somente máscaras autorizadas e produz métricas retrospectivas."""
    protocol_path = Path(protocol_path).resolve()
    authorized_mask_root = Path(authorized_mask_root).resolve()
    extraction_manifest_path = Path(extraction_manifest_path).resolve()
    input_root = Path(input_root).resolve()
    output_root = Path(output_root).resolve()
    _refuse_holdout(
        protocol_path,
        authorized_mask_root,
        extraction_manifest_path,
        input_root,
        output_root,
    )
    if output_root.exists():
        raise PipelineError("Saída da auditoria v17 já existe; sobrescrita recusada.")
    protocol = _load_json(protocol_path)
    signature = protocol.pop("protocol_signature", None)
    if protocol.get("schema_version") != PROTOCOL_SCHEMA or signature != _canonical_sha(protocol):
        raise PipelineError("Protocolo de auditoria v17 inválido ou alterado.")
    protocol["protocol_signature"] = signature
    cases = protocol.get("cases", [])
    allowed_case_ids = {str(case.get("case_id", "")) for case in cases}
    authorized_masks = _validated_authorized_masks(
        authorized_mask_root=authorized_mask_root,
        extraction_manifest_path=extraction_manifest_path,
        allowed_case_ids=allowed_case_ids,
    )

    lesion_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case["case_id"])
        masks = authorized_masks.get(case_id, [])
        if not masks:
            continue
        reference_path = input_root / str(case["reference_relative_path"])
        if _sha256(reference_path) != case["reference_sha256"]:
            raise PipelineError(f"Referência venosa alterada durante auditoria: {case_id}.")
        reference = sitk.ReadImage(str(reference_path))
        case_lesions: list[dict[str, Any]] = []
        for lesion_id, mask_path, mask_sha256 in masks:
            mask_image = sitk.ReadImage(str(mask_path))
            if not _manual_mask_index_aligned(mask_image, reference):
                raise PipelineError(f"Máscara manual desalinhada, sem resample permitido: {mask_path}.")
            metrics = audit_mask_array(
                sitk.GetArrayFromImage(mask_image) > 0,
                represented_axial_indices=case["represented_axial_indices"],
                crop_bounds_zyx=case["crop_bounds_zyx"],
                spacing_xyz=reference.GetSpacing(),
            )
            row = {
                "case_id": case_id,
                "lesion_id": lesion_id,
                "mask_sha256": mask_sha256,
                **metrics,
            }
            lesion_rows.append(row)
            case_lesions.append(row)
        case_rows.append(
            {
                "case_id": case_id,
                "lesion_count": len(case_lesions),
                "any_lesion_any_voxel_visible": any(
                    row["any_voxel_visible"] for row in case_lesions
                ),
                "all_lesions_any_voxel_visible": all(
                    row["any_voxel_visible"] for row in case_lesions
                ),
                "all_lesions_all_voxels_visible": all(
                    row["all_voxels_visible"] for row in case_lesions
                ),
            }
        )
    if not lesion_rows:
        raise PipelineError("Nenhuma máscara autorizada encontrada para a auditoria v17.")

    size_metrics = {
        size_bin: _metric(
            sum(row["any_voxel_visible"] for row in lesion_rows if row["size_bin"] == size_bin),
            sum(row["size_bin"] == size_bin for row in lesion_rows),
        )
        for size_bin in ("lt_10_mm", "10_to_lt_20_mm", "ge_20_mm")
    }
    summary = {
        "case_count_with_manual_venous_masks": len(case_rows),
        "lesion_count": len(lesion_rows),
        "case_any_lesion_visibility": _metric(
            sum(row["any_lesion_any_voxel_visible"] for row in case_rows), len(case_rows)
        ),
        "case_all_lesions_visibility": _metric(
            sum(row["all_lesions_any_voxel_visible"] for row in case_rows), len(case_rows)
        ),
        "case_all_lesions_full_voxel_coverage": _metric(
            sum(row["all_lesions_all_voxels_visible"] for row in case_rows), len(case_rows)
        ),
        "lesion_any_voxel_visibility": _metric(
            sum(row["any_voxel_visible"] for row in lesion_rows), len(lesion_rows)
        ),
        "lesion_full_voxel_coverage": _metric(
            sum(row["all_voxels_visible"] for row in lesion_rows), len(lesion_rows)
        ),
        "lesion_visibility_by_size": size_metrics,
        "aggregate_visible_voxel_fraction": sum(
            int(row["visible_voxels"]) for row in lesion_rows
        )
        / sum(int(row["lesion_voxels"]) for row in lesion_rows),
    }
    report = {
        "schema_version": AUDIT_SCHEMA,
        "protocol_signature": signature,
        "authorized_extraction_manifest_sha256": _sha256(extraction_manifest_path),
        "summary": summary,
        "safety": {
            "retrospective_only": True,
            "ground_truth_label_read": False,
            "medgemma_called": False,
            "lesion_masks_sent_to_medgemma": False,
            "holdout_opened": False,
        },
        "case_rows": case_rows,
        "lesion_rows": lesion_rows,
    }
    report["audit_signature"] = _canonical_sha(report)
    output_root.mkdir(parents=True)
    _write_json_atomic(output_root / "audit_report.json", report)
    csv_rows = [
        {
            **row,
            "lesion_axial_indices": json.dumps(row["lesion_axial_indices"]),
            "visible_lesion_axial_indices": json.dumps(
                row["visible_lesion_axial_indices"]
            ),
        }
        for row in lesion_rows
    ]
    _write_csv_atomic(output_root / "lesion_rows.csv", csv_rows)
    _write_csv_atomic(output_root / "case_rows.csv", case_rows)
    return report
