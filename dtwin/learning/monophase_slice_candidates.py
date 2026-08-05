"""Label-blind axial liver slice candidates for real single-phase MRI.

The automatic whole-liver mask is used only to crop and prove coverage. Lesion
masks and pathology labels are not accepted. Every axial plane containing liver
is represented exactly once, using one case-level intensity window.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import (
    CANDIDATE_DATASET_SCHEMA,
    CANDIDATE_RECORD_SCHEMA,
    _load_split_universe,
    _verify_label_blind_binding,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file


SLICE_DERIVATION_SCHEMA = "oren-monophase-axial-liver-slices-v1"


def is_proven_label_blind_input(row: dict[str, Any]) -> bool:
    if row.get("ground_truth_read") is False and row.get("lesion_mask_present") is False:
        return True
    if not (
        row.get("schema") == "argos-public-liver-mri-holdout-input-v1"
        and row.get("split") == "holdout_blind"
        and row.get("research_only") is True
        and row.get("clinical_use_allowed") is False
    ):
        return False
    forbidden = ("lesion", "tumor", "ground_truth", "label")
    for item in row.get("files", []):
        text = f"{item.get('role', '')}/{item.get('relative_path', '')}".lower()
        if any(token in text for token in forbidden):
            return False
    return True


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Manifesto de entrada inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Manifesto de entrada contém registro inválido.")
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PipelineError(f"Artefato fora do workspace: {path}") from exc


def publish_immutable_directory(staging: Path, destination: Path) -> None:
    """Publish a completed dataset, with a manifest-last Windows fallback."""
    try:
        os.replace(staging, destination)
        return
    except PermissionError:
        if os.name != "nt" or destination.exists():
            raise
    manifest = staging / "dataset_manifest.json"
    if not manifest.is_file():
        raise PipelineError("Publicação sem manifesto final.")
    try:
        destination.mkdir()
        sources = sorted(
            (path for path in staging.rglob("*") if path.is_file() and path != manifest),
            key=lambda path: path.relative_to(staging).as_posix(),
        )
        for source in sources:
            relative = source.relative_to(staging)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256_file(source) != sha256_file(target):
                raise PipelineError(f"Cópia divergente durante publicação: {relative}")
        temporary_manifest = destination / ".dataset_manifest.json.publishing"
        shutil.copy2(manifest, temporary_manifest)
        if sha256_file(manifest) != sha256_file(temporary_manifest):
            raise PipelineError("Manifesto divergiu durante publicação.")
        os.replace(temporary_manifest, destination / "dataset_manifest.json")
        shutil.rmtree(staging)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise


def _role(row: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in row.get("files", []) if item.get("role") == name]
    if len(matches) != 1:
        raise PipelineError(f"Caso {row.get('case_id')} não possui exatamente um arquivo {name}.")
    return matches[0]


def liver_slice_indices(mask_zyx: np.ndarray) -> list[int]:
    if mask_zyx.ndim != 3:
        raise PipelineError("Máscara hepática deve ser 3D.")
    return np.flatnonzero(np.any(mask_zyx, axis=(1, 2))).astype(int).tolist()


def liver_xy_bbox(mask_zyx: np.ndarray, margin_fraction: float) -> tuple[int, int, int, int]:
    points = np.argwhere(mask_zyx)
    if not len(points):
        raise PipelineError("Máscara hepática vazia.")
    y0, x0 = points[:, 1:].min(axis=0)
    y1, x1 = points[:, 1:].max(axis=0) + 1
    margin = int(round(max(y1 - y0, x1 - x0) * float(margin_fraction)))
    return (
        max(0, int(y0) - margin), min(mask_zyx.shape[1], int(y1) + margin),
        max(0, int(x0) - margin), min(mask_zyx.shape[2], int(x1) + margin),
    )


def case_intensity_window(volume_zyx: np.ndarray, mask_zyx: np.ndarray) -> tuple[float, float]:
    values = np.asarray(volume_zyx[mask_zyx], dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < 2:
        raise PipelineError("Intensidade hepática insuficiente.")
    low, high = np.percentile(values, [1.0, 99.0]).tolist()
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        raise PipelineError("Janela de intensidade hepática degenerada.")
    return float(low), float(high)


def render_axial_candidate(
    plane: np.ndarray,
    bbox: tuple[int, int, int, int],
    window: tuple[float, float],
    image_size: int,
) -> Image.Image:
    y0, y1, x0, x1 = bbox
    crop = np.asarray(plane[y0:y1, x0:x1], dtype=np.float32)
    low, high = window
    normalized = np.clip((crop - low) / (high - low), 0.0, 1.0)
    gray = Image.fromarray(np.rint(normalized * 255.0).astype(np.uint8), mode="L")
    scale = min(image_size / gray.width, image_size / gray.height)
    resized = gray.resize(
        (max(1, round(gray.width * scale)), max(1, round(gray.height * scale))),
        Image.Resampling.BICUBIC,
    )
    canvas = Image.new("L", (image_size, image_size), color=0)
    canvas.paste(resized, ((image_size - resized.width) // 2, (image_size - resized.height) // 2))
    return Image.merge("RGB", (canvas, canvas, canvas))


def build_monophase_slice_candidates(
    *,
    input_manifest_path: Path,
    input_files_root: Path,
    protocol_path: Path,
    splits_path: Path,
    workspace_root: Path,
    output_root: Path,
    dataset_id: str = "lld_mmri",
    phase_role: str = "t1_delayed",
    liver_mask_role: str = "liver_mask_venous",
    image_size: int = 448,
    crop_margin_fraction: float = 0.08,
    limit_cases: int | None = None,
    manifest_only_universe: bool = False,
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Dataset de cortes monofásicos já existe; saída é imutável.")
    if image_size != 448:
        raise PipelineError("Candidatos MedSigLIP devem ter 448x448 pixels.")
    if not (0.0 <= crop_margin_fraction <= 0.5):
        raise PipelineError("Margem de crop inválida.")
    protocol = _verify_label_blind_binding(protocol_path, splits_path)
    _, universe = _load_split_universe(splits_path)
    rows = _read_jsonl(Path(input_manifest_path))
    rows = [row for row in rows if str(row.get("case_id")) in universe]
    rows.sort(key=lambda row: str(row["case_id"]))
    if limit_cases is not None:
        if limit_cases < 1:
            raise PipelineError("limit_cases deve ser positivo.")
        rows = rows[:limit_cases]
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    coverage_cases: list[dict[str, Any]] = []
    observed: set[str] = set()
    try:
        try:
            import SimpleITK as sitk
        except ImportError as exc:
            raise PipelineError("SimpleITK é obrigatório para os candidatos axiais.") from exc
        for row in rows:
            case_id = str(row["case_id"])
            if not is_proven_label_blind_input(row):
                raise PipelineError(f"Entrada de {case_id} não é comprovadamente label-blind.")
            if case_id in observed:
                raise PipelineError(f"Caso duplicado: {case_id}")
            observed.add(case_id)
            try:
                phase = _role(row, phase_role)
                mask = _role(row, liver_mask_role)
                phase_path = Path(input_files_root) / str(phase["relative_path"])
                mask_path = Path(input_files_root) / str(mask["relative_path"])
                if sha256_file(phase_path) != phase.get("sha256") or sha256_file(mask_path) != mask.get("sha256"):
                    raise PipelineError("Hash da fase ou máscara hepática divergiu.")
                volume = sitk.GetArrayFromImage(sitk.ReadImage(str(phase_path))).astype(np.float32)
                liver = sitk.GetArrayFromImage(sitk.ReadImage(str(mask_path))) > 0
                if volume.shape != liver.shape:
                    raise PipelineError("Fase e máscara hepática têm geometrias incompatíveis.")
                indices = liver_slice_indices(liver)
                if not indices:
                    raise PipelineError("Máscara hepática sem cortes axiais.")
                bbox = liver_xy_bbox(liver, crop_margin_fraction)
                window = case_intensity_window(volume, liver)
                total_voxels = int(liver.sum())
                covered_voxels = 0
                panel_total = len(indices)
                for panel_number, axial_index in enumerate(indices, start=1):
                    relative_image = Path("slices") / case_id / f"axial_{axial_index:04d}.png"
                    staged_image = staging / relative_image
                    staged_image.parent.mkdir(parents=True, exist_ok=True)
                    image = render_axial_candidate(volume[axial_index], bbox, window, image_size)
                    image.save(staged_image, format="PNG", optimize=True)
                    slice_voxels = int(liver[axial_index].sum())
                    covered_voxels += slice_voxels
                    records.append({
                        "schema": CANDIDATE_RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": case_id,
                        "dataset_id": dataset_id,
                        "candidate_id": f"axial-{axial_index:04d}",
                        "candidate_kind": "single_phase_axial_liver_crop",
                        "automatic_candidate": True,
                        "phase": phase_role,
                        "panel_number": panel_number,
                        "panel_total": panel_total,
                        "slice_indices": [axial_index],
                        "axial_index": axial_index,
                        "relative_liver_position": (
                            0.0 if indices[-1] == indices[0]
                            else (axial_index - indices[0]) / (indices[-1] - indices[0])
                        ),
                        "liver_voxels_in_slice": slice_voxels,
                        "image_path": _relative(root, destination / relative_image),
                        "image_sha256": sha256_file(staged_image),
                        "source_phase_sha256": str(phase["sha256"]),
                        "source_liver_mask_sha256": str(mask["sha256"]),
                        "intensity_window": [window[0], window[1]],
                        "crop_bbox_yxyx": list(bbox),
                        "single_phase_replicated_across_rgb": True,
                        "dynamic_enhancement_information_present": False,
                        "lesion_mask_used": False,
                        "ground_truth_used": False,
                        "phi_metadata_removed": True,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    })
                missing_indices = sorted(set(indices) - {r["axial_index"] for r in records if r["case_id"] == case_id})
                duplicate_count = len(indices) - len(set(indices))
                gate = covered_voxels == total_voxels and not missing_indices and duplicate_count == 0
                if not gate:
                    raise PipelineError("Gate inteiro de cobertura hepática falhou.")
                coverage_cases.append({
                    "case_id": case_id,
                    "first_axial_index": indices[0],
                    "last_axial_index": indices[-1],
                    "axial_slice_count": len(indices),
                    "total_liver_voxels": total_voxels,
                    "covered_liver_voxels": covered_voxels,
                    "missing_indices": missing_indices,
                    "duplicate_indices": duplicate_count,
                    "exact_coverage_gate": True,
                })
            except Exception as exc:
                records = [record for record in records if record["case_id"] != case_id]
                shutil.rmtree(staging / "slices" / case_id, ignore_errors=True)
                failures.append({
                    "schema": "argos-hybrid-label-blind-technical-failure-v1",
                    "case_id": case_id,
                    "failure_reason": f"monophase_slice_candidate_failure:{type(exc).__name__}:{exc}",
                    "counts_as_error": True,
                    "research_only": True,
                })
        materialized = {record["case_id"] for record in records}
        expected = (
            {str(row["case_id"]) for row in rows}
            if manifest_only_universe or limit_cases is not None
            else set(universe)
        )
        for case_id in sorted(expected - materialized - {row["case_id"] for row in failures}):
            failures.append({
                "schema": "argos-hybrid-label-blind-technical-failure-v1",
                "case_id": case_id,
                "failure_reason": "no_label_blind_single_phase_input",
                "counts_as_error": True,
                "research_only": True,
            })
        records.sort(key=lambda row: (row["case_id"], row["axial_index"]))
        failures.sort(key=lambda row: row["case_id"])
        records_path = staging / "candidate_records.jsonl"
        failures_path = staging / "technical_failures.jsonl"
        coverage_path = staging / "coverage_manifest.json"
        _write_jsonl(records_path, records)
        _write_jsonl(failures_path, failures)
        coverage_path.write_text(json.dumps(coverage_cases, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        body = {
            "schema": CANDIDATE_DATASET_SCHEMA,
            "derivation_schema": SLICE_DERIVATION_SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "protocol_signature": protocol["protocol_signature"],
            "splits_sha256": sha256_file(splits_path),
            "input_manifest_sha256": sha256_file(input_manifest_path),
            "phase_role": phase_role,
            "liver_mask_role": liver_mask_role,
            "representation": "all_axial_liver_slices_individual_crop",
            "image_size": image_size,
            "expected_case_count": len(expected),
            "expected_case_scope": (
                "input_manifest" if manifest_only_universe else "frozen_split_universe"
            ),
            "materialized_case_count": len(materialized),
            "technical_failure_count": len(failures),
            "candidate_record_count": len(records),
            "candidate_records_sha256": sha256_file(records_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "coverage_manifest_sha256": sha256_file(coverage_path),
            "all_materialized_cases_exact_coverage": all(row["exact_coverage_gate"] for row in coverage_cases),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "lesion_contours_rendered": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "dataset_signature": canonical_sha256(body)}
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        publish_immutable_directory(staging, destination)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


__all__ = [
    "SLICE_DERIVATION_SCHEMA",
    "build_monophase_slice_candidates",
    "case_intensity_window",
    "liver_slice_indices",
    "liver_xy_bbox",
    "render_axial_candidate",
]
