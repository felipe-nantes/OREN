"""Leakage-safe localized supervision for automatic liver MRI candidates.

Candidate geometry is built without labels or public lesion masks.  A separate
protected stage may subsequently attach training-only targets by measuring
whether an authorized lesion mask is visible inside each renderable 3-D box.
The protected targets are never model inputs and are not required at inference.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw
from scipy import ndimage

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file


GEOMETRY_SCHEMA = "argos-hybrid-localized-candidate-geometry-v1"
GEOMETRY_RECORD_SCHEMA = "argos-hybrid-localized-candidate-record-v1"
TARGET_MANIFEST_SCHEMA = "argos-hybrid-localized-candidate-targets-v1"
TARGET_RECORD_SCHEMA = "argos-hybrid-localized-candidate-target-v1"
IMAGE_DATASET_SCHEMA = "argos-hybrid-localized-candidate-image-dataset-v1"
IMAGE_RECORD_SCHEMA = "argos-hybrid-localized-candidate-image-record-v1"
EXPECTED_PROPOSAL_SCHEMA = "argos-openswisshcc-enhancement-localizer-cohort-v22"
EXPECTED_EXTRACTION_SCHEMA = "argos-openswisshcc-v16-authorized-mask-extraction-v1"
EXPECTED_AUDIT_PROTOCOL_SCHEMA = "argos-openswisshcc-v16-localizer-audit-protocol-v1"


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contem registro invalido.")
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _same_geometry(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def _top_components(mask: np.ndarray, maximum: int) -> list[np.ndarray]:
    if maximum < 1:
        raise PipelineError("top_k deve ser positivo.")
    labels, count = ndimage.label(
        np.asarray(mask, dtype=bool),
        structure=ndimage.generate_binary_structure(3, 2),
    )
    sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
    ordered = sorted(
        range(1, int(count) + 1), key=lambda item: (-int(sizes[item]), item)
    )
    return [labels == component_id for component_id in ordered[:maximum]]


def _box_shape_zyx(
    spacing_xyz: tuple[float, float, float], *, crop_mm: float, visible_slices: int
) -> tuple[int, int, int]:
    if (
        len(spacing_xyz) != 3
        or any(not np.isfinite(value) or value <= 0 for value in spacing_xyz)
        or not np.isfinite(crop_mm)
        or crop_mm <= 0
        or visible_slices < 1
        or visible_slices % 2 == 0
    ):
        raise PipelineError("Geometria de caixa localizada invalida.")
    width_x = max(1, int(np.ceil(crop_mm / spacing_xyz[0])))
    width_y = max(1, int(np.ceil(crop_mm / spacing_xyz[1])))
    return visible_slices, width_y, width_x


def _axis_bounds(anchor: int, width: int, size: int) -> tuple[int, int, int]:
    """Place a fixed-width box starting at/behind an uncovered anchor."""

    if size < 1 or width < 1 or not 0 <= anchor < size:
        raise PipelineError("Limites de eixo invalidos.")
    actual = min(width, size)
    start = min(max(0, anchor), size - actual)
    end = start + actual
    center = start + (actual - 1) // 2
    return start, end, center


def cover_component_with_boxes(
    component: np.ndarray,
    spacing_xyz: tuple[float, float, float],
    *,
    crop_mm: float = 64.0,
    visible_slices: int = 7,
) -> list[dict[str, Any]]:
    """Deterministically cover every proposal voxel with renderable boxes.

    The algorithm only sees the automatic binary proposal.  It never consumes
    lesion geometry.  The first uncovered voxel in z/y/x order anchors the next
    box, which makes the result reproducible and guarantees exact coverage.
    """

    source = np.asarray(component, dtype=bool)
    if source.ndim != 3 or not source.any():
        raise PipelineError("Componente automatico deve ser uma mascara 3-D nao vazia.")
    box_shape = _box_shape_zyx(
        spacing_xyz, crop_mm=crop_mm, visible_slices=visible_slices
    )
    boxes: list[dict[str, Any]] = []
    # Spatial binning visits the proposal coordinates once.  The previous
    # repeated full-volume argwhere was exact but quadratic in the number of
    # boxes for extensive enhancement components.
    coordinates = np.argwhere(source)
    cell_ids = coordinates // np.asarray(box_shape, dtype=np.int64)
    occupied_cells = np.unique(cell_ids, axis=0)
    for cell_z, cell_y, cell_x in occupied_cells:
        anchor_z = min(int(cell_z * box_shape[0]), source.shape[0] - 1)
        anchor_y = min(int(cell_y * box_shape[1]), source.shape[1] - 1)
        anchor_x = min(int(cell_x * box_shape[2]), source.shape[2] - 1)
        z0, z1, cz = _axis_bounds(anchor_z, box_shape[0], source.shape[0])
        y0, y1, cy = _axis_bounds(anchor_y, box_shape[1], source.shape[1])
        x0, x1, cx = _axis_bounds(anchor_x, box_shape[2], source.shape[2])
        covered = int(source[z0:z1, y0:y1, x0:x1].sum())
        if covered < 1:
            raise PipelineError("Celula espacial localizada vazia.")
        boxes.append(
            {
                "center_zyx": [cz, cy, cx],
                "bounds_zyx_exclusive": [[z0, z1], [y0, y1], [x0, x1]],
                "automatic_proposal_voxels_in_box": covered,
            }
        )
    union = np.zeros_like(source, dtype=bool)
    for box in boxes:
        (z0, z1), (y0, y1), (x0, x1) = box["bounds_zyx_exclusive"]
        union[z0:z1, y0:y1, x0:x1] = True
    if np.any(source & ~union):
        raise PipelineError("Cobertura localizada perdeu voxel candidato.")
    return boxes


def lesion_visibility_in_box(
    lesion_mask: np.ndarray, bounds_zyx_exclusive: list[list[int]]
) -> tuple[int, float]:
    lesion = np.asarray(lesion_mask, dtype=bool)
    if lesion.ndim != 3 or len(bounds_zyx_exclusive) != 3:
        raise PipelineError("Mascara ou caixa invalida para supervisao.")
    try:
        (z0, z1), (y0, y1), (x0, x1) = [
            (int(item[0]), int(item[1])) for item in bounds_zyx_exclusive
        ]
    except (TypeError, ValueError, IndexError) as exc:
        raise PipelineError("Limites da caixa de supervisao invalidos.") from exc
    if not (0 <= z0 < z1 <= lesion.shape[0] and 0 <= y0 < y1 <= lesion.shape[1] and 0 <= x0 < x1 <= lesion.shape[2]):
        raise PipelineError("Caixa de supervisao fora do volume.")
    total = int(lesion.sum())
    visible = int(lesion[z0:z1, y0:y1, x0:x1].sum())
    return visible, (visible / total if total else 0.0)


def _verified_geometry(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _load_json(root / "geometry_manifest.json", "Geometria localizada")
    unsigned = dict(manifest)
    signature = unsigned.pop("geometry_signature", None)
    records_path = root / "candidate_geometry.jsonl"
    if (
        signature != canonical_sha256(unsigned)
        or manifest.get("candidate_geometry_sha256") != sha256_file(records_path)
        or manifest.get("ground_truth_read") is not False
        or manifest.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Geometria localizada invalida, alterada ou nao cega.")
    records = _load_jsonl(records_path, "Registros de geometria")
    if any(
        row.get("ground_truth_read") is not False
        or row.get("lesion_mask_used") is not False
        for row in records
    ):
        raise PipelineError("Registro localizado perdeu o contrato label-blind.")
    return manifest, records


def select_label_blind_candidates(
    *, source_root: Path, output_root: Path, maximum_per_case: int = 8
) -> dict[str, Any]:
    """Rank only by automatic proposal burden and publish a time-bounded set."""

    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists() or maximum_per_case < 1:
        raise PipelineError("Selecao localizada invalida ou destino ja existente.")
    source_manifest, records = _verified_geometry(source_root)
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    selected: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        ranked = sorted(
            by_case[case_id],
            key=lambda row: (
                -int(row["automatic_proposal_voxels_in_box"]),
                int(row["source_component_rank"]),
                str(row["candidate_id"]),
            ),
        )[:maximum_per_case]
        for rank, row in enumerate(ranked, 1):
            selected.append({**row, "automatic_selection_rank": rank})
    selected.sort(key=lambda row: (row["case_id"], row["automatic_selection_rank"]))
    output_root.mkdir(parents=True)
    records_path = output_root / "candidate_geometry.jsonl"
    failures_source = source_root / "technical_failures.jsonl"
    failures_path = output_root / "technical_failures.jsonl"
    _write_jsonl(records_path, selected)
    shutil.copyfile(failures_source, failures_path)
    body = {
        "schema": GEOMETRY_SCHEMA,
        "status": "complete_label_blind_time_bounded_localized_geometry",
        "case_count": source_manifest["case_count"],
        "available_case_count": source_manifest["available_case_count"],
        "technical_failure_count": source_manifest["technical_failure_count"],
        "candidate_count": len(selected),
        "candidate_count_min": min((len(value) for value in by_case.values()), default=0, )
        if maximum_per_case > max((len(value) for value in by_case.values()), default=0)
        else maximum_per_case,
        "candidate_count_max": maximum_per_case,
        "candidate_count_mean": len(selected) / len(by_case) if by_case else 0.0,
        "maximum_per_case": maximum_per_case,
        "selection_rule": "automatic_proposal_voxels_desc_then_component_rank_then_candidate_id",
        "threshold_key": source_manifest["threshold_key"],
        "top_k_components": source_manifest["top_k_components"],
        "crop_mm": source_manifest["crop_mm"],
        "visible_slices": source_manifest["visible_slices"],
        "source_geometry_signature": source_manifest["geometry_signature"],
        "candidate_geometry_sha256": sha256_file(records_path),
        "technical_failures_sha256": sha256_file(failures_path),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    result = {**body, "geometry_signature": canonical_sha256(body)}
    (output_root / "geometry_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _normalized(array: np.ndarray, median: float, scale: float) -> np.ndarray:
    if not np.isfinite(scale) or scale <= 0:
        raise PipelineError("Escala de intensidade localizada invalida.")
    clipped = np.clip((np.asarray(array, dtype=np.float32) - median) / scale, -3.0, 3.0)
    return np.asarray(np.rint((clipped + 3.0) * 255.0 / 6.0), dtype=np.uint8)


def _render_localized_patch(
    phases: dict[str, np.ndarray], bounds: list[list[int]], *, image_size: int = 448
) -> Image.Image:
    if image_size != 448:
        raise PipelineError("Representacao localizada v1 exige 448 pixels.")
    (z0, z1), (y0, y1), (x0, x1) = bounds
    if z1 - z0 < 1 or y1 - y0 < 1 or x1 - x0 < 1:
        raise PipelineError("Caixa localizada vazia para renderizacao.")
    canvas = Image.new("RGB", (image_size, image_size), (0, 0, 0))
    tile = image_size // 4
    for index, z in enumerate(range(z0, z1)):
        rgb = np.stack(
            [
                phases["arterial"][z, y0:y1, x0:x1],
                phases["venous"][z, y0:y1, x0:x1],
                phases["delayed"][z, y0:y1, x0:x1],
            ],
            axis=-1,
        )
        frame = Image.fromarray(rgb, mode="RGB").resize(
            (tile, image_size // 2), Image.Resampling.BILINEAR
        )
        canvas.paste(frame, ((index % 4) * tile, (index // 4) * (image_size // 2)))
        frame.close()
    draw = ImageDraw.Draw(canvas)
    draw.text((3 * tile + 8, image_size // 2 + 8), "RESEARCH ONLY", fill=(190, 190, 190))
    return canvas


def build_localized_image_dataset(
    *,
    geometry_root: Path,
    proposal_root: Path,
    inputs_root: Path,
    alignment_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Render the selected geometry without opening protected targets."""

    root = Path(workspace_root).resolve()
    geometry_root = Path(geometry_root).resolve()
    proposal_root = Path(proposal_root).resolve()
    inputs_root = Path(inputs_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Dataset visual localizado ja existe.")
    geometry, records = _verified_geometry(geometry_root)
    staging = output_root.with_name(f".{output_root.name}.{uuid.uuid4().hex[:8]}.tmp")
    staging.mkdir(parents=True)
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    image_records: list[dict[str, Any]] = []
    try:
        for case_id, candidates in sorted(by_case.items()):
            proposal_manifest = _load_json(
                proposal_root / case_id / "manifest.json", "Manifesto de proposta"
            )
            normalization = proposal_manifest.get("normalization") or {}
            paths = {
                "arterial": alignment_root / case_id / "art_registered_to_venous.nii.gz",
                "venous": inputs_root / case_id / "dyn" / "t1_venous.nii.gz",
                "delayed": alignment_root / case_id / "del_registered_to_venous.nii.gz",
            }
            images = {name: sitk.ReadImage(str(path)) for name, path in paths.items()}
            if not all(_same_geometry(images["venous"], image) for image in images.values()):
                raise PipelineError(f"Fases localizadas fora da geometria venosa: {case_id}.")
            phases = {
                name: _normalized(
                    sitk.GetArrayFromImage(image),
                    float(normalization[name]["median"]),
                    float(normalization[name]["scale"]),
                )
                for name, image in images.items()
            }
            for panel_number, candidate in enumerate(
                sorted(candidates, key=lambda row: int(row.get("automatic_selection_rank", 0))), 1
            ):
                candidate_id = str(candidate["candidate_id"])
                relative = Path("images") / case_id / f"{candidate_id}.png"
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                rendered = _render_localized_patch(phases, candidate["bounds_zyx_exclusive"])
                rendered.save(destination, format="PNG", optimize=False)
                rendered.close()
                image_records.append(
                    {
                        "schema": IMAGE_RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": case_id,
                        "dataset_id": "openswisshcc_development",
                        "candidate_id": candidate_id,
                        "candidate_kind": "automatic_localized_multiphase_2_5d",
                        "panel_number": panel_number,
                        "image_path": (output_root / relative).relative_to(root).as_posix(),
                        "image_sha256": sha256_file(destination),
                        "source_geometry_signature": geometry["geometry_signature"],
                        "label_attached": False,
                        "ground_truth_read": False,
                        "lesion_mask_used": False,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    }
                )
        image_records.sort(key=lambda row: (row["case_id"], row["panel_number"]))
        records_path = staging / "candidate_records.jsonl"
        _write_jsonl(records_path, image_records)
        body = {
            "schema": IMAGE_DATASET_SCHEMA,
            "status": "complete_label_blind_localized_images",
            "dataset_signature_source": geometry["geometry_signature"],
            "case_count": len(by_case),
            "candidate_count": len(image_records),
            "candidate_records_sha256": sha256_file(records_path),
            "representation": "seven_axial_slices_arterial_venous_delayed_as_rgb",
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        result = {**body, "dataset_signature": canonical_sha256(body)}
        (staging / "dataset_manifest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_root)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_localized_candidate_geometry(
    *,
    proposal_root: Path,
    output_root: Path,
    threshold_key: str = "t3",
    top_k_components: int = 10,
    crop_mm: float = 64.0,
    visible_slices: int = 7,
) -> dict[str, Any]:
    """Create immutable, label-blind localized geometry from v22 proposals."""

    proposal_root = Path(proposal_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Geometria localizada ja existe; sobrescrita recusada.")
    summary_path = proposal_root / "summary.json"
    summary = _load_json(summary_path, "Resumo de propostas")
    case_ids = [str(value) for value in summary.get("case_ids") or []]
    unavailable = {str(value) for value in summary.get("unavailable_case_ids") or []}
    if (
        summary.get("schema") != EXPECTED_PROPOSAL_SCHEMA
        or len(case_ids) != 87
        or summary.get("labels_read") is not False
        or summary.get("ground_truth_lesion_masks_read") != 0
    ):
        raise PipelineError("Fonte de propostas nao preserva o cegamento exigido.")

    staging = output_root.with_name(f".{output_root.name}.{uuid.uuid4().hex[:8]}.tmp")
    staging.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for case_id in case_ids:
            if case_id in unavailable:
                failures.append({"case_id": case_id, "reason": "automatic_proposals_unavailable"})
                continue
            case_root = proposal_root / case_id
            manifest_path = case_root / "manifest.json"
            manifest = _load_json(manifest_path, "Manifesto de proposta")
            proposal = next(
                (item for item in manifest.get("proposals") or [] if item.get("threshold_key") == threshold_key),
                None,
            )
            if not isinstance(proposal, dict):
                raise PipelineError(f"Proposta {threshold_key} ausente em {case_id}.")
            mask_path = case_root / str(proposal.get("filename") or "")
            if not mask_path.is_file() or sha256_file(mask_path) != proposal.get("sha256"):
                raise PipelineError(f"Mascara automatica alterada em {case_id}.")
            image = sitk.ReadImage(str(mask_path))
            mask = sitk.GetArrayFromImage(image) > 0
            components = _top_components(mask, top_k_components)
            case_sequence = 0
            for component_rank, component in enumerate(components, 1):
                boxes = cover_component_with_boxes(
                    component,
                    tuple(float(value) for value in image.GetSpacing()),
                    crop_mm=crop_mm,
                    visible_slices=visible_slices,
                )
                for component_box_number, box in enumerate(boxes, 1):
                    case_sequence += 1
                    records.append(
                        {
                            "schema": GEOMETRY_RECORD_SCHEMA,
                            "case_id": case_id,
                            "patient_group_id": case_id,
                            "candidate_id": f"localized-{case_sequence:03d}",
                            "source_component_rank": component_rank,
                            "source_component_box_number": component_box_number,
                            **box,
                            "source_proposal_sha256": proposal["sha256"],
                            "source_manifest_sha256": sha256_file(manifest_path),
                            "ground_truth_read": False,
                            "lesion_mask_used": False,
                            "research_only": True,
                            "clinical_use_allowed": False,
                        }
                    )
        records.sort(key=lambda row: (row["case_id"], row["candidate_id"]))
        records_path = staging / "candidate_geometry.jsonl"
        failures_path = staging / "technical_failures.jsonl"
        _write_jsonl(records_path, records)
        _write_jsonl(failures_path, failures)
        per_case: dict[str, int] = {}
        for row in records:
            per_case[row["case_id"]] = per_case.get(row["case_id"], 0) + 1
        body = {
            "schema": GEOMETRY_SCHEMA,
            "status": "complete_label_blind_localized_geometry",
            "case_count": len(case_ids),
            "available_case_count": len(case_ids) - len(failures),
            "technical_failure_count": len(failures),
            "candidate_count": len(records),
            "candidate_count_min": min(per_case.values()) if per_case else 0,
            "candidate_count_max": max(per_case.values()) if per_case else 0,
            "candidate_count_mean": float(np.mean(list(per_case.values()))) if per_case else 0.0,
            "threshold_key": threshold_key,
            "top_k_components": top_k_components,
            "crop_mm": float(crop_mm),
            "visible_slices": visible_slices,
            "coverage_gate": "all_selected_automatic_proposal_voxels_inside_at_least_one_box",
            "proposal_summary_sha256": sha256_file(summary_path),
            "candidate_geometry_sha256": sha256_file(records_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        result = {**body, "geometry_signature": canonical_sha256(body)}
        (staging / "geometry_manifest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_root)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_protected_localized_targets(
    *,
    candidate_root: Path,
    authorized_mask_root: Path,
    audit_protocol_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Attach development-only lesion visibility targets after geometry freeze."""

    candidate_root = Path(candidate_root).resolve()
    authorized_mask_root = Path(authorized_mask_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Targets localizados ja existem; sobrescrita recusada.")
    geometry = _load_json(candidate_root / "geometry_manifest.json", "Geometria localizada")
    unsigned_geometry = dict(geometry)
    signature = unsigned_geometry.pop("geometry_signature", None)
    if signature != canonical_sha256(unsigned_geometry):
        raise PipelineError("Assinatura da geometria localizada diverge.")
    records_path = candidate_root / "candidate_geometry.jsonl"
    if sha256_file(records_path) != geometry.get("candidate_geometry_sha256"):
        raise PipelineError("Registros de geometria localizada foram alterados.")
    records = _load_jsonl(records_path, "Registros de geometria")
    if any(row.get("ground_truth_read") is not False or row.get("lesion_mask_used") is not False for row in records):
        raise PipelineError("Geometria localizada perdeu o contrato label-blind.")

    protocol = _load_json(audit_protocol_path, "Protocolo autorizado")
    if (
        protocol.get("schema") != EXPECTED_AUDIT_PROTOCOL_SCHEMA
        or protocol.get("safety", {}).get("development_only") is not True
        or protocol.get("safety", {}).get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo de mascaras nao e de desenvolvimento protegido.")
    labels = {str(item["case_id"]): str(item["label_post_inference"]) for item in protocol.get("cases") or []}
    extraction_path = authorized_mask_root / "extraction_manifest.json"
    extraction = _load_json(extraction_path, "Extracao autorizada")
    if extraction.get("schema") != EXPECTED_EXTRACTION_SCHEMA:
        raise PipelineError("Extracao de mascaras possui schema inesperado.")
    masks_by_case: dict[str, list[Path]] = {}
    for item in extraction.get("masks") or []:
        path = (authorized_mask_root / str(item.get("relative_path") or "")).resolve()
        if not path.is_relative_to(authorized_mask_root) or not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise PipelineError("Mascara autorizada ausente, insegura ou alterada.")
        masks_by_case.setdefault(str(item["case_id"]), []).append(path)

    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    targets: list[dict[str, Any]] = []
    case_hits: dict[str, bool] = {}
    positive_cases_with_masks = 0
    failure_rows = _load_jsonl(
        candidate_root / "technical_failures.jsonl", "Falhas tecnicas localizadas"
    )
    for failure in failure_rows:
        case_id = str(failure.get("case_id", ""))
        label = labels.get(case_id)
        if label not in {"POSITIVE", "NEGATIVE"} or case_id in by_case:
            raise PipelineError("Falha tecnica localizada sem label ou com candidatos.")
        targets.append(
            {
                "schema": TARGET_RECORD_SCHEMA,
                "case_id": case_id,
                "candidate_id": "case-technical-failure",
                "case_label": label,
                "candidate_target": None,
                "candidate_supervision_available": False,
                "visible_lesion_voxels": None,
                "visible_lesion_fraction": None,
                "lesion_mask_used_for_training_label_only": False,
                "lesion_mask_used_for_candidate_generation": False,
                "technical_failure_placeholder": True,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    for case_id, candidates in sorted(by_case.items()):
        label = labels.get(case_id)
        if label not in {"POSITIVE", "NEGATIVE"}:
            raise PipelineError(f"Label protegido ausente em {case_id}.")
        lesion_union: np.ndarray | None = None
        reference: sitk.Image | None = None
        for path in masks_by_case.get(case_id, []):
            image = sitk.ReadImage(str(path))
            if reference is not None and not _same_geometry(reference, image):
                raise PipelineError(f"Mascaras autorizadas com geometrias divergentes: {case_id}.")
            reference = image
            current = sitk.GetArrayFromImage(image) > 0
            lesion_union = current if lesion_union is None else lesion_union | current
        if label == "POSITIVE" and lesion_union is not None:
            positive_cases_with_masks += 1
        supervised = label == "NEGATIVE" or lesion_union is not None
        case_hit = False
        for row in candidates:
            visible = fraction = None
            target = None
            if label == "NEGATIVE":
                visible, fraction, target = 0, 0.0, 0
            elif lesion_union is not None:
                visible, fraction = lesion_visibility_in_box(
                    lesion_union, row["bounds_zyx_exclusive"]
                )
                target = int(visible > 0)
                case_hit = case_hit or bool(target)
            targets.append(
                {
                    "schema": TARGET_RECORD_SCHEMA,
                    "case_id": case_id,
                    "candidate_id": row["candidate_id"],
                    "case_label": label,
                    "candidate_target": target,
                    "candidate_supervision_available": supervised,
                    "visible_lesion_voxels": visible,
                    "visible_lesion_fraction": fraction,
                    "lesion_mask_used_for_training_label_only": label == "POSITIVE" and lesion_union is not None,
                    "lesion_mask_used_for_candidate_generation": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
            )
        if label == "POSITIVE" and lesion_union is not None:
            case_hits[case_id] = case_hit

    output_root.mkdir(parents=True)
    targets_path = output_root / "protected_candidate_targets.jsonl"
    _write_jsonl(targets_path, targets)
    hits = sum(case_hits.values())
    total = len(case_hits)
    body = {
        "schema": TARGET_MANIFEST_SCHEMA,
        "status": "complete_development_only_training_targets",
        "geometry_signature": geometry["geometry_signature"],
        "target_count": len(targets),
        "technical_failure_count": len(failure_rows),
        "supervised_target_count": sum(row["candidate_target"] is not None for row in targets),
        "positive_candidate_count": sum(row["candidate_target"] == 1 for row in targets),
        "hard_negative_candidate_count": sum(row["candidate_target"] == 0 for row in targets),
        "positive_cases_with_authorized_masks": positive_cases_with_masks,
        "localized_case_hits": hits,
        "localized_case_recall": hits / total if total else 0.0,
        "positive_cases_without_authorized_masks": sorted(
            case_id for case_id, label in labels.items() if label == "POSITIVE" and case_id not in masks_by_case
        ),
        "targets_sha256": sha256_file(targets_path),
        "audit_protocol_sha256": sha256_file(audit_protocol_path),
        "authorized_extraction_sha256": sha256_file(extraction_path),
        "masks_used_for_training_supervision_only": True,
        "masks_used_for_candidate_generation_or_inference": False,
        "holdout_used": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    result = {**body, "target_signature": canonical_sha256(body)}
    (output_root / "target_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


__all__ = [
    "build_localized_image_dataset",
    "build_localized_candidate_geometry",
    "build_protected_localized_targets",
    "cover_component_with_boxes",
    "lesion_visibility_in_box",
    "select_label_blind_candidates",
]
