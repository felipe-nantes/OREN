"""Label-blind monophase candidates extracted from the frozen axial atlas.

For multiphase RGB source panels the delayed/venous evidence is the blue
channel.  Venous fallback panels are grayscale replicated across RGB, so the
same operation is valid for both source kinds.  Every atlas axial plane is
materialized exactly once; pathology labels and lesion masks are not inputs.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import CANDIDATE_RECORD_SCHEMA
from dtwin.learning.protocol import canonical_sha256, sha256_file

SCHEMA = "oren-openswiss-monophase-atlas-candidates-v1"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado: {path}")
    return value


def _pixel_sha256(image: Image.Image) -> str:
    import hashlib

    normalized = image.convert("RGB")
    digest = hashlib.sha256()
    # Must match the signed v17 atlas contract byte-for-byte.
    digest.update(normalized.mode.encode("ascii"))
    digest.update(str(normalized.size).encode("ascii"))
    digest.update(normalized.tobytes())
    return digest.hexdigest()


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


def _extract_case(
    *, case_dir: Path, staging: Path, destination: Path, workspace_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path = case_dir / "axial_atlas_manifest.json"
    manifest = _json(manifest_path)
    case_id = str(manifest.get("case_id") or "")
    atlas = manifest.get("atlas") or {}
    if (
        not case_id.startswith("anon-openswiss-")
        or manifest.get("ground_truth_read") is not False
        or manifest.get("lesion_mask_read") is not False
        or atlas.get("gate_passed") is not True
        or float(atlas.get("coverage_percent", 0.0)) != 100.0
    ):
        raise PipelineError(f"Atlas label-blind invalido: {case_dir}")
    expected = [int(value) for value in atlas.get("expected_axial_indices") or []]
    represented = [int(value) for value in atlas.get("represented_axial_indices") or []]
    if not expected or represented != expected or len(represented) != len(set(represented)):
        raise PipelineError(f"Cobertura axial invalida em {case_id}.")

    records: list[dict[str, Any]] = []
    seen: list[int] = []
    for frame in manifest.get("frames") or []:
        frame_path = case_dir / str(frame.get("image"))
        if sha256_file(frame_path) != frame.get("sha256"):
            raise PipelineError(f"Hash de frame divergente em {case_id}.")
        with Image.open(frame_path) as opened:
            source = opened.convert("RGB")
            for tile in frame.get("tiles") or []:
                if tile.get("empty") is True:
                    continue
                if tile.get("counts_toward_coverage") is not True:
                    raise PipelineError(f"Tile axial real fora da cobertura em {case_id}.")
                index = int(tile["axial_index"])
                quadrant = int(tile["quadrant"]) - 1
                width, height = source.size
                if width != height or width % 2:
                    raise PipelineError(f"Frame 2x2 invalido em {case_id}.")
                tile_size = width // 2
                left = (quadrant % 2) * tile_size
                top = (quadrant // 2) * tile_size
                crop = source.crop((left, top, left + tile_size, top + tile_size))
                if _pixel_sha256(crop) != tile.get("tile_pixel_sha256"):
                    raise PipelineError(f"Hash de pixels divergente em {case_id}/{index}.")
                # Blue is delayed in multiphase RGB. Fallback venous is RGB-replicated.
                delayed = crop.getchannel("B").resize((448, 448), Image.Resampling.BICUBIC)
                output = Image.merge("RGB", (delayed, delayed, delayed))
                relative = Path("slices") / case_id / f"axial_{index:04d}.png"
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                output.save(target, format="PNG", optimize=True)
                records.append(
                    {
                        "schema": CANDIDATE_RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": case_id,
                        "dataset_id": "openswisshcc_development",
                        "candidate_id": f"axial-{index:04d}",
                        "candidate_kind": "delayed_axial_atlas_tile",
                        "automatic_candidate": True,
                        "phase": "t1_delayed_or_venous",
                        "panel_number": len(seen) + 1,
                        "panel_total": len(expected),
                        "slice_indices": [index],
                        "axial_index": index,
                        "image_path": _relative(workspace_root, destination / relative),
                        "image_sha256": sha256_file(target),
                        "source_frame_sha256": str(frame["sha256"]),
                        "source_tile_pixel_sha256": str(tile["tile_pixel_sha256"]),
                        "source_candidate_kind": manifest.get("source", {}).get("candidate_kind"),
                        "single_phase_replicated_across_rgb": True,
                        "dynamic_enhancement_information_present": False,
                        "ground_truth_used": False,
                        "lesion_mask_used": False,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    }
                )
                seen.append(index)
    if seen != expected:
        raise PipelineError(f"Gate axial exato falhou em {case_id}.")
    return records, {
        "case_id": case_id,
        "expected_axial_indices": expected,
        "represented_axial_indices": seen,
        "missing_axial_indices": [],
        "duplicate_axial_indices": [],
        "exact_coverage_gate": True,
        "source_manifest_sha256": sha256_file(manifest_path),
    }


def build_openswiss_monophase_atlas_candidates(
    *, atlas_root: Path, workspace_root: Path, output_root: Path
) -> dict[str, Any]:
    atlas_root = Path(atlas_root).resolve()
    workspace_root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Saida imutavel de candidatos ja existe.")
    cohort_path = atlas_root / "cohort_manifest.json"
    cohort = _json(cohort_path)
    if cohort.get("all_gates_passed") is not True:
        raise PipelineError("Coorte de atlas nao passou os gates.")
    cases = cohort.get("cases") or []
    if not cases:
        raise PipelineError("Coorte de atlas vazia.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    records: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    try:
        for item in cases:
            case_id = str(item["case_id"])
            case_records, case_coverage = _extract_case(
                case_dir=atlas_root / case_id,
                staging=staging,
                destination=destination,
                workspace_root=workspace_root,
            )
            records.extend(case_records)
            coverage.append(case_coverage)
        records.sort(key=lambda row: (row["case_id"], row["axial_index"]))
        coverage.sort(key=lambda row: row["case_id"])
        records_path = staging / "candidate_records.jsonl"
        coverage_path = staging / "coverage_manifest.json"
        _write_jsonl(records_path, records)
        coverage_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        body = {
            "schema": SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "atlas_cohort_sha256": sha256_file(cohort_path),
            "case_count": len(coverage),
            "candidate_record_count": len(records),
            "candidate_records_sha256": sha256_file(records_path),
            "coverage_manifest_sha256": sha256_file(coverage_path),
            "all_cases_exact_coverage": all(row["exact_coverage_gate"] for row in coverage),
            "representation": "individual_delayed_axial_tiles_from_frozen_atlas",
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
        os.replace(staging, destination)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


__all__ = ["SCHEMA", "build_openswiss_monophase_atlas_candidates"]
