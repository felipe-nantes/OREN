"""Preparação cega de pilhas MRI para a entrada 3D nativa do MedGemma 1.5.

Somente o volume T1 venoso e a máscara hepática anatômica são aceitos. Labels,
máscaras de lesão e metadados clínicos não fazem parte desta interface.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path, PurePosixPath

import numpy as np
import SimpleITK as sitk
from PIL import Image

from dtwin.core import PipelineError, sha256_of


SCHEMA = "argos-medgemma-highdimensional-stack-v1"
CONTRACT = "dtwin-medgemma-volume-v1"
VOLUME_ROLE = "t1_venous"
MASK_ROLE = "liver_mask_venous"
MIN_SLICES = 5
MAX_SLICES = 85
MAX_SIDE = 512
_CASE_ID = re.compile(r"^anon-openswiss-[0-9a-f]{16}$")
_FORBIDDEN_INPUT_TERMS = (
    "lesion",
    "tumor",
    "ground_truth",
    "label",
    "manual_mask",
    "hcc_mask",
)


def _select_slice_indices(
    first: int,
    last: int,
    total: int,
    *,
    minimum: int = MIN_SLICES,
    maximum: int = MAX_SLICES,
) -> list[int]:
    """Expande intervalos curtos e aplica a amostragem oficial quando >85."""

    if total < minimum:
        raise PipelineError(f"Volume tem {total} cortes; são necessários ao menos {minimum}.")
    if not (0 <= first <= last < total):
        raise PipelineError("Intervalo hepático inválido.")
    if minimum < 1 or maximum < minimum:
        raise PipelineError("Limites de amostragem inválidos.")

    start, end = first, last
    missing = max(0, minimum - (end - start + 1))
    start = max(0, start - (missing // 2))
    end = min(total - 1, end + missing - (first - start))
    if end - start + 1 < minimum:
        start = max(0, end - minimum + 1)
    interval = list(range(start, end + 1))
    if len(interval) <= maximum:
        return interval

    # Fórmula do notebook oficial: i/MAX_SLICE, i em 1..MAX_SLICE.
    selected = [
        interval[int(round(i / maximum * (len(interval) - 1)))]
        for i in range(1, maximum + 1)
    ]
    if len(selected) != maximum or len(set(selected)) != maximum:
        raise PipelineError("Amostragem equidistante produziu índices duplicados.")
    return selected


def _safe_source(input_root: Path, relative_path: str) -> Path:
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative_path:
        raise PipelineError("Caminho inseguro no manifesto de desenvolvimento.")
    root = Path(input_root).resolve()
    candidate = (root / Path(*posix.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Arquivo de entrada escapou da raiz autorizada.") from exc
    if not candidate.is_file():
        raise PipelineError(f"Arquivo de entrada ausente para role segura: {posix.name}")
    return candidate


def _load_case_record(manifest_path: Path, case_id: str) -> dict:
    found = []
    with Path(manifest_path).open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("case_id") == case_id:
                found.append(record)
    if len(found) != 1:
        raise PipelineError(f"Esperado um registro para {case_id}; encontrados {len(found)}.")
    record = found[0]
    if (
        record.get("schema") != "argos-public-liver-mri-input-v1"
        or record.get("split") != "development"
        or record.get("research_only") is not True
        or record.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Manifesto de desenvolvimento incompatível ou inseguro.")
    return record


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-5)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-5)
    )


def _orient_pair_lps(volume: sitk.Image, liver_mask: sitk.Image):
    """Orienta o par e harmoniza somente ruído numérico de metadados."""

    if not _geometry_equal(volume, liver_mask):
        raise PipelineError("Geometria do volume e da máscara hepática diverge.")
    volume_lps = sitk.DICOMOrient(volume, "LPS")
    mask_lps = sitk.DICOMOrient(liver_mask, "LPS")
    if volume_lps.GetSize() != mask_lps.GetSize():
        raise PipelineError("Tamanho divergiu após orientação LPS.")
    spacing_delta = float(np.max(np.abs(np.asarray(volume_lps.GetSpacing()) - np.asarray(mask_lps.GetSpacing()))))
    origin_delta = float(np.max(np.abs(np.asarray(volume_lps.GetOrigin()) - np.asarray(mask_lps.GetOrigin()))))
    direction_delta = float(np.max(np.abs(np.asarray(volume_lps.GetDirection()) - np.asarray(mask_lps.GetDirection()))))
    harmonized = not _geometry_equal(volume_lps, mask_lps)
    if harmonized:
        mask_lps.CopyInformation(volume_lps)
    if not _geometry_equal(volume_lps, mask_lps):
        raise PipelineError("Geometria divergiu após orientação LPS.")
    return volume_lps, mask_lps, {
        "input_geometry_tolerance": 1e-5,
        "post_orientation_max_spacing_delta_before_harmonization": spacing_delta,
        "post_orientation_max_origin_delta_before_harmonization": origin_delta,
        "post_orientation_max_direction_delta_before_harmonization": direction_delta,
        "mask_metadata_harmonized_after_orientation": harmonized,
        "voxel_array_alignment_preserved": True,
    }

def _scaled_rgb_slice(array: np.ndarray, lo: float, hi: float) -> Image.Image:
    normalized = np.clip((array.astype(np.float32) - lo) / (hi - lo), 0.0, 1.0)
    image = Image.fromarray(np.rint(normalized * 255.0).astype(np.uint8), mode="L").convert("RGB")
    width, height = image.size
    if max(width, height) > MAX_SIDE:
        scale = MAX_SIDE / max(width, height)
        target = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(target, Image.Resampling.LANCZOS)
    return image


def _publish_staging_directory(staging: Path, destination: Path) -> None:
    """Publica atomicamente, tolerando locks transitórios de antivírus no Windows."""

    for attempt in range(8):
        try:
            staging.rename(destination)
            return
        except PermissionError:
            if destination.exists() or attempt == 7:
                raise
            time.sleep(0.1 * (2**attempt))

def _validate_reusable(destination: Path, *, case_id: str, volume_hash: str, mask_hash: str) -> dict:
    manifest_path = destination / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Pilha existente sem manifesto válido; reuso recusado.") from exc
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("contract") != CONTRACT
        or manifest.get("case_id") != case_id
        or manifest.get("source", {}).get("volume_sha256") != volume_hash
        or manifest.get("source", {}).get("liver_mask_sha256") != mask_hash
        or manifest.get("gate", {}).get("passed") is not True
    ):
        raise PipelineError("Pilha existente não corresponde às entradas atuais.")
    for item in manifest.get("images", []):
        path = destination / item["filename"]
        if not path.is_file() or sha256_of(path) != item.get("sha256"):
            raise PipelineError("Hash inconsistente em pilha reutilizada.")
    if len(manifest.get("images", [])) != manifest.get("slice_count"):
        raise PipelineError("Quantidade inconsistente em pilha reutilizada.")
    return manifest


def build_highdimensional_stack(
    *,
    manifest_path: Path,
    input_root: Path,
    out_root: Path,
    case_id: str,
    maximum_slices: int = MAX_SLICES,
) -> dict:
    """Constrói uma pilha axial cega, determinística e auditável para um caso."""

    if not _CASE_ID.fullmatch(case_id):
        raise PipelineError("case_id não é um identificador OpenSwissHCC anonimizado.")
    if not MIN_SLICES <= maximum_slices <= MAX_SLICES:
        raise PipelineError(
            f"maximum_slices deve estar entre {MIN_SLICES} e {MAX_SLICES}."
        )
    record = _load_case_record(manifest_path, case_id)
    files = record.get("files")
    if not isinstance(files, list):
        raise PipelineError("Lista de arquivos ausente no manifesto.")
    for item in files:
        descriptor = f"{item.get('role', '')} {item.get('relative_path', '')}".lower()
        if any(term in descriptor for term in _FORBIDDEN_INPUT_TERMS):
            raise PipelineError("Manifesto contém entrada proibida de lesão/ground truth.")
    by_role = {str(item.get("role")): item for item in files}
    if len(by_role) != len(files) or not {VOLUME_ROLE, MASK_ROLE}.issubset(by_role):
        raise PipelineError("Roles venoso/máscara hepática ausentes ou duplicados.")

    volume_path = _safe_source(input_root, str(by_role[VOLUME_ROLE]["relative_path"]))
    mask_path = _safe_source(input_root, str(by_role[MASK_ROLE]["relative_path"]))
    volume_hash = sha256_of(volume_path)
    mask_hash = sha256_of(mask_path)
    if volume_hash != by_role[VOLUME_ROLE].get("sha256"):
        raise PipelineError("Hash do volume venoso diverge do manifesto.")
    if mask_hash != by_role[MASK_ROLE].get("sha256"):
        raise PipelineError("Hash da máscara hepática diverge do manifesto.")

    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    destination = (out_root / case_id).resolve()
    try:
        destination.relative_to(out_root)
    except ValueError as exc:
        raise PipelineError("Destino da pilha escapou da raiz autorizada.") from exc
    if destination.exists():
        return _validate_reusable(
            destination,
            case_id=case_id,
            volume_hash=volume_hash,
            mask_hash=mask_hash,
        )

    volume = sitk.ReadImage(str(volume_path), sitk.sitkFloat32)
    liver_mask = sitk.ReadImage(str(mask_path))
    if volume.GetDimension() != 3 or liver_mask.GetDimension() != 3:
        raise PipelineError("A entrada high-dimensional exige volumes 3D.")
    volume, liver_mask, geometry_audit = _orient_pair_lps(volume, liver_mask)

    array = sitk.GetArrayFromImage(volume).astype(np.float32, copy=False)
    mask = sitk.GetArrayFromImage(liver_mask) > 0
    if not np.isfinite(array).all():
        raise PipelineError("Volume contém intensidades não finitas.")
    planes = np.flatnonzero(mask.any(axis=(1, 2)))
    if planes.size == 0:
        raise PipelineError("Máscara hepática vazia.")
    lo, hi = float(array.min()), float(array.max())
    if not hi > lo:
        raise PipelineError("Volume sem faixa dinâmica para normalização min–max.")
    selected = _select_slice_indices(
        int(planes[0]),
        int(planes[-1]),
        int(array.shape[0]),
        maximum=maximum_slices,
    )

    staging = out_root / f".{case_id}.tmp-{uuid.uuid4().hex}"
    staging.mkdir()
    image_records = []
    try:
        for order, source_index in enumerate(selected, start=1):
            filename = f"slice_{order:03d}.png"
            image = _scaled_rgb_slice(array[source_index], lo, hi)
            path = staging / filename
            image.save(path, format="PNG", optimize=False)
            width, height = image.size
            image_records.append(
                {
                    "order": order,
                    "source_index_lps_z": source_index,
                    "filename": filename,
                    "sha256": sha256_of(path),
                    "bytes": path.stat().st_size,
                    "width": width,
                    "height": height,
                    "mode": "RGB",
                    "contains_liver_mask": bool(mask[source_index].any()),
                }
            )

        selected_liver_voxels = int(mask[selected].sum())
        manifest = {
            "schema": SCHEMA,
            "contract": CONTRACT,
            "case_id": case_id,
            "source": {
                "volume_role": VOLUME_ROLE,
                "volume_sha256": volume_hash,
                "liver_mask_role": MASK_ROLE,
                "liver_mask_sha256": mask_hash,
            },
            "orientation": "LPS",
            "geometry_audit": geometry_audit,
            "normalization": {
                "method": "per_volume_min_max",
                "minimum": lo,
                "maximum": hi,
                "finite_values_required": True,
            },
            "sampling": {
                "strategy": "liver_interval_official_equidistant_capped",
                "formula_when_over_limit": (
                    f"index[round(i/{maximum_slices}*(N-1))], "
                    f"i=1..{maximum_slices}"
                ),
                "liver_first_lps_z": int(planes[0]),
                "liver_last_lps_z": int(planes[-1]),
                "liver_plane_count": int(planes.size),
                "liver_interval_plane_count": int(planes[-1] - planes[0] + 1),
                "selected_indices_lps_z": selected,
                "maximum_slices": maximum_slices,
                "minimum_slices": MIN_SLICES,
            },
            "liver_mask_audit": {
                "total_voxels": int(mask.sum()),
                "voxels_on_selected_planes": selected_liver_voxels,
                "coverage_fraction": selected_liver_voxels / int(mask.sum()),
                "used_only_for_axial_interval": True,
            },
            "slice_count": len(image_records),
            "images": image_records,
            "gate": {
                "count_within_configured_limit": (
                    MIN_SLICES <= len(image_records) <= maximum_slices
                ),
                "all_images_at_most_512": all(
                    max(item["width"], item["height"]) <= MAX_SIDE for item in image_records
                ),
                "all_hashes_present": all(len(item["sha256"]) == 64 for item in image_records),
                "ground_truth_used": False,
                "lesion_mask_used": False,
                "phi_metadata_included": False,
                "passed": True,
            },
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if not all(value is True for key, value in manifest["gate"].items() if key.endswith("present") or key.startswith("count_") or key.startswith("all_")):
            raise PipelineError("Gate técnico da pilha high-dimensional falhou.")
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_staging_directory(staging, destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
