"""Label-blind 2.5D multiphase candidate patches and protected training targets."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
import yaml
from PIL import Image, ImageDraw
from scipy import ndimage

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file


DATASET_SCHEMA = "argos-hybrid-patch25d-dataset-v1"
RECORD_SCHEMA = "argos-hybrid-patch25d-record-v1"
TARGET_SCHEMA = "argos-hybrid-patch25d-protected-target-v1"
TARGET_MANIFEST_SCHEMA = "argos-hybrid-patch25d-protected-target-manifest-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto.")
    return value


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
        raise PipelineError(f"{description} contém linha inválida.")
    return rows


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config 2.5D inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != "argos-hybrid-patch25d-config-v1":
        raise PipelineError("Schema da config 2.5D inválido.")
    if int(value.get("top_k", 0)) != 10 or int(value.get("adjacent_slices", 0)) != 5:
        raise PipelineError("Contrato v1 exige top10 e cinco cortes adjacentes.")
    if value.get("lesion_masks_allowed_during_image_generation") is not False:
        raise PipelineError("Geração visual 2.5D deve ser label-blind.")
    return value


def _same_geometry(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def _top_components(mask: np.ndarray, maximum: int) -> list[np.ndarray]:
    labels, count = ndimage.label(
        np.asarray(mask, dtype=bool), structure=ndimage.generate_binary_structure(3, 2)
    )
    sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
    ordered = sorted(range(1, int(count) + 1), key=lambda item: (-int(sizes[item]), item))
    return [labels == component_id for component_id in ordered[:maximum]]


def _normalize(array: np.ndarray, median: float, scale: float) -> np.ndarray:
    if not np.isfinite(scale) or scale <= 0:
        raise PipelineError("Escala robusta inválida no patch 2.5D.")
    value = np.clip((array.astype(np.float32) - float(median)) / float(scale), -3.0, 3.0)
    return np.asarray(np.rint((value + 3.0) * 255.0 / 6.0), dtype=np.uint8)


def _crop_bounds(
    component: np.ndarray, spacing_xyz: tuple[float, float, float], crop_mm: float
) -> tuple[int, int, int, int, int]:
    points = np.argwhere(component)
    if points.size == 0:
        raise PipelineError("Componente candidato vazio.")
    center_z, center_y, center_x = np.rint(np.mean(points, axis=0)).astype(int)
    half_x = max(16, int(np.ceil(crop_mm / max(spacing_xyz[0], 1e-6) / 2.0)))
    half_y = max(16, int(np.ceil(crop_mm / max(spacing_xyz[1], 1e-6) / 2.0)))
    return center_z, center_y - half_y, center_y + half_y, center_x - half_x, center_x + half_x


def _bounded_crop(array: np.ndarray, z: int, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    z = min(max(z, 0), array.shape[0] - 1)
    height, width = y1 - y0, x1 - x0
    result = np.zeros((height, width), dtype=array.dtype)
    sy0, sy1 = max(0, y0), min(array.shape[1], y1)
    sx0, sx1 = max(0, x0), min(array.shape[2], x1)
    if sy1 > sy0 and sx1 > sx0:
        result[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = array[z, sy0:sy1, sx0:sx1]
    return result


def _render_patch(
    phases: dict[str, np.ndarray],
    component: np.ndarray,
    spacing_xyz: tuple[float, float, float],
    *,
    crop_mm: float,
    image_size: int,
) -> Image.Image:
    center_z, y0, y1, x0, x1 = _crop_bounds(component, spacing_xyz, crop_mm)
    canvas = Image.new("RGB", (image_size, image_size), (0, 0, 0))
    tile_w, tile_h = image_size // 3, image_size // 2
    offsets = (-2, -1, 0, 1, 2)
    for index, offset in enumerate(offsets):
        rgb = np.stack(
            [
                _bounded_crop(phases["arterial"], center_z + offset, y0, y1, x0, x1),
                _bounded_crop(phases["venous"], center_z + offset, y0, y1, x0, x1),
                _bounded_crop(phases["delayed"], center_z + offset, y0, y1, x0, x1),
            ],
            axis=-1,
        )
        tile = Image.fromarray(rgb, mode="RGB").resize((tile_w, tile_h), Image.Resampling.BILINEAR)
        x = (index % 3) * tile_w
        y = (index // 3) * tile_h
        canvas.paste(tile, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((image_size - tile_w + 5, image_size - tile_h + 5), "RESEARCH ONLY", fill=(190, 190, 190))
    return canvas


def build_label_blind_dataset(
    *, config_path: Path, workspace_root: Path, output_root: Path
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Dataset 2.5D já existe.")
    staging = output.with_name(f".{output.name}.incomplete")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    config = load_config(config_path)
    proposal_root = root / str(config["proposal_root"])
    inputs_root = root / str(config["inputs_root"])
    alignment_root = root / str(config["alignment_root"])
    localizer_audit_path = root / str(config["localizer_audit"])
    localizer_audit = _json(localizer_audit_path, "Auditoria do localizador")
    gate_metric = next(
        (
            item
            for item in localizer_audit.get("metrics") or []
            if item.get("threshold_key") == "t3" and item.get("selection") == "top10"
        ),
        None,
    )
    if (
        gate_metric is None
        or float(gate_metric.get("case_recall", 0.0))
        < float(config["localizer_case_recall_gate"])
        or float(gate_metric.get("lesion_recall", 0.0))
        < float(config["localizer_lesion_recall_gate"])
    ):
        raise PipelineError("Localizador t3/top10 não passou o gate de recall 2.5D.")
    proposal_summary = _json(proposal_root / "summary.json", "Resumo das propostas")
    case_ids = [str(value) for value in proposal_summary.get("case_ids") or []]
    unavailable = {str(value) for value in proposal_summary.get("unavailable_case_ids") or []}
    if (
        len(case_ids) != 87
        or proposal_summary.get("labels_read") is not False
        or proposal_summary.get("ground_truth_lesion_masks_read") != 0
    ):
        raise PipelineError("Propostas v22 não satisfazem o contrato label-blind.")
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for case_id in case_ids:
            if case_id in unavailable:
                failures.append({"case_id": case_id, "reason": "multiphase_registration_unavailable"})
                continue
            case_proposal = proposal_root / case_id
            proposal_manifest = _json(case_proposal / "manifest.json", "Manifesto de proposta")
            item = next(
                (value for value in proposal_manifest["proposals"] if value["threshold_key"] == "t3"),
                None,
            )
            if not item:
                raise PipelineError(f"Proposta t3 ausente: {case_id}.")
            proposal_path = case_proposal / str(item["filename"])
            if sha256_file(proposal_path) != item["sha256"]:
                raise PipelineError(f"Proposta t3 alterada: {case_id}.")
            venous_path = inputs_root / case_id / "dyn" / "t1_venous.nii.gz"
            arterial_path = alignment_root / case_id / "art_registered_to_venous.nii.gz"
            delayed_path = alignment_root / case_id / "del_registered_to_venous.nii.gz"
            images = {
                "arterial": sitk.ReadImage(str(arterial_path)),
                "venous": sitk.ReadImage(str(venous_path)),
                "delayed": sitk.ReadImage(str(delayed_path)),
            }
            proposal_image = sitk.ReadImage(str(proposal_path))
            if any(not _same_geometry(images["venous"], image) for image in [images["arterial"], images["delayed"], proposal_image]):
                raise PipelineError(f"Geometria incompatível no patch 2.5D: {case_id}.")
            normalization = proposal_manifest["normalization"]
            phase_arrays = {
                phase: _normalize(
                    sitk.GetArrayFromImage(image),
                    normalization[phase]["median"],
                    normalization[phase]["scale"],
                )
                for phase, image in images.items()
            }
            components = _top_components(
                sitk.GetArrayFromImage(proposal_image) > 0, int(config["top_k"])
            )
            for rank, component in enumerate(components, 1):
                candidate_id = f"candidate-{rank:03d}"
                relative = Path("images") / case_id / f"{candidate_id}.png"
                image = _render_patch(
                    phase_arrays,
                    component,
                    tuple(float(value) for value in images["venous"].GetSpacing()),
                    crop_mm=float(config["crop_mm"]),
                    image_size=int(config["image_size"]),
                )
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target, format="PNG", optimize=False)
                image.close()
                points = np.argwhere(component)
                records.append(
                    {
                        "schema": RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": case_id,
                        "dataset_id": "openswisshcc_development",
                        "candidate_id": candidate_id,
                        "candidate_kind": "automatic_t3_top10_component_2_5d",
                        "panel_number": rank,
                        "component_voxels": int(component.sum()),
                        "center_zyx": [float(value) for value in np.mean(points, axis=0)],
                        "image_path": (output / relative).relative_to(root).as_posix(),
                        "image_sha256": sha256_file(target),
                        "label_attached": False,
                        "ground_truth_read": False,
                        "lesion_mask_used": False,
                        "research_only": True,
                    }
                )
        records.sort(key=lambda row: (row["case_id"], row["candidate_id"]))
        records_path = staging / "candidate_records.jsonl"
        records_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
        )
        failures_path = staging / "technical_failures.jsonl"
        failures_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in failures),
            encoding="utf-8",
        )
        body = {
            "schema": DATASET_SCHEMA,
            "status": "complete_label_blind_candidate_images",
            "config_sha256": sha256_file(config_path),
            "source_proposal_summary_sha256": sha256_file(proposal_root / "summary.json"),
            "localizer_audit_sha256": sha256_file(localizer_audit_path),
            "localizer_case_recall": float(gate_metric["case_recall"]),
            "localizer_lesion_recall": float(gate_metric["lesion_recall"]),
            "case_count": len(case_ids),
            "available_case_count": len(case_ids) - len(failures),
            "technical_failure_count": len(failures),
            "candidate_count": len(records),
            "candidate_records_sha256": sha256_file(records_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "localizer_rule": "joint_enhancement_t3_top10_by_volume",
            "adjacent_slices": 5,
            "phases_as_rgb_channels": ["arterial", "venous", "delayed"],
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "dataset_signature": canonical_sha256(body)}
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_protected_targets(
    *,
    candidate_root: Path,
    proposal_root: Path,
    labels_path: Path,
    lesion_extraction_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    candidate_root = Path(candidate_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Targets protegidos 2.5D já existem.")
    output_root.mkdir(parents=True)
    dataset = _json(candidate_root / "dataset_manifest.json", "Dataset 2.5D")
    records = _jsonl(candidate_root / "candidate_records.jsonl", "Candidatos 2.5D")
    labels = {
        str(row["case_id"]): str(row["label"])
        for row in _jsonl(labels_path, "Labels protegidos")
    }
    extraction = _json(
        Path(lesion_extraction_root) / "extraction_manifest.json",
        "Extração autorizada de máscaras",
    )
    masks_by_case: dict[str, list[Path]] = {}
    for item in extraction.get("masks") or []:
        path = Path(lesion_extraction_root) / str(item["relative_path"])
        if sha256_file(path) != item["sha256"]:
            raise PipelineError("Máscara pública autorizada alterada.")
        masks_by_case.setdefault(str(item["case_id"]), []).append(path)
    records_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        records_by_case.setdefault(str(row["case_id"]), []).append(row)
    targets: list[dict[str, Any]] = []
    proposal_summary = _json(Path(proposal_root) / "summary.json", "Resumo das propostas")
    cohort_case_ids = [str(value) for value in proposal_summary.get("case_ids") or []]
    for case_id in cohort_case_ids:
        if case_id not in records_by_case:
            targets.append(
                {
                    "schema": TARGET_SCHEMA,
                    "case_id": case_id,
                    "candidate_id": "case-technical-failure",
                    "case_label": labels[case_id],
                    "candidate_target": None,
                    "candidate_supervision_available": False,
                    "lesion_mask_used_for_training_label_only": False,
                    "technical_failure_placeholder": True,
                    "research_only": True,
                }
            )
    for case_id, candidates in sorted(records_by_case.items()):
        label = labels[case_id]
        proposal_manifest = _json(Path(proposal_root) / case_id / "manifest.json", "Proposta")
        item = next(value for value in proposal_manifest["proposals"] if value["threshold_key"] == "t3")
        proposal_image = sitk.ReadImage(str(Path(proposal_root) / case_id / item["filename"]))
        components = _top_components(
            sitk.GetArrayFromImage(proposal_image) > 0, 10
        )
        lesion_union: np.ndarray | None = None
        for path in masks_by_case.get(case_id, []):
            lesion_image = sitk.ReadImage(str(path))
            if not _same_geometry(proposal_image, lesion_image):
                raise PipelineError(f"Máscara de lesão fora da geometria: {case_id}.")
            current = sitk.GetArrayFromImage(lesion_image) > 0
            lesion_union = current if lesion_union is None else lesion_union | current
        if label == "NEGATIVE":
            mask_supervision_available = True
        else:
            mask_supervision_available = lesion_union is not None
        for row, component in zip(candidates, components):
            target = (
                0
                if label == "NEGATIVE"
                else (int(bool(np.any(component & lesion_union))) if lesion_union is not None else None)
            )
            targets.append(
                {
                    "schema": TARGET_SCHEMA,
                    "case_id": case_id,
                    "candidate_id": row["candidate_id"],
                    "case_label": label,
                    "candidate_target": target,
                    "candidate_supervision_available": mask_supervision_available,
                    "lesion_mask_used_for_training_label_only": label == "POSITIVE" and lesion_union is not None,
                    "research_only": True,
                }
            )
    targets_path = output_root / "protected_candidate_targets.jsonl"
    targets_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in targets),
        encoding="utf-8",
    )
    body = {
        "schema": TARGET_MANIFEST_SCHEMA,
        "candidate_dataset_signature": dataset["dataset_signature"],
        "target_count": len(targets),
        "supervised_target_count": sum(row["candidate_target"] is not None for row in targets),
        "positive_candidate_count": sum(row["candidate_target"] == 1 for row in targets),
        "negative_candidate_count": sum(row["candidate_target"] == 0 for row in targets),
        "positive_cases_without_venous_mask": sorted(
            {
                row["case_id"]
                for row in targets
                if row["case_label"] == "POSITIVE"
                and row["candidate_supervision_available"] is False
            }
        ),
        "targets_sha256": sha256_file(targets_path),
        "masks_used_for_training_supervision_only": True,
        "masks_used_for_candidate_generation_or_embedding": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    manifest = {**body, "target_signature": canonical_sha256(body)}
    (output_root / "target_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
