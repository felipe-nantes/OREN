"""Deterministic 2x2 native T1/T2/ordered-TRACE/ADC panel generation."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_multisequence_audit import TRACE_RE, _rows
from dtwin.benchmark.openswisshcc_multisequence_geometry import _geometry_matches
from dtwin.core import PipelineError
from dtwin.medgemma_panel import _render_tile
from dtwin.medgemma_screening import _write_json_atomic


SCHEMA = "argos-openswisshcc-multisequence-panel-set-v1"


def _physical_points(mask: sitk.Image) -> np.ndarray:
    zyx = np.argwhere(sitk.GetArrayViewFromImage(mask) > 0)
    if not len(zyx):
        raise PipelineError("Mascara hepatica vazia no painel multissequencia.")
    xyz = zyx[:, ::-1].astype(np.float64)
    direction = np.asarray(mask.GetDirection(), dtype=np.float64).reshape(3, 3)
    return (
        np.asarray(mask.GetOrigin(), dtype=np.float64)
        + (direction @ (xyz * np.asarray(mask.GetSpacing(), dtype=np.float64)).T).T
    )


def _continuous_indices(points: np.ndarray, image: sitk.Image) -> np.ndarray:
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    return (
        (direction.T @ (points - np.asarray(image.GetOrigin(), dtype=np.float64)).T).T
        / np.asarray(image.GetSpacing(), dtype=np.float64)
    )


def _inside(indices: np.ndarray, image: sitk.Image) -> np.ndarray:
    size = np.asarray(image.GetSize(), dtype=np.float64)
    return np.all((indices >= -0.5) & (indices <= size - 0.5), axis=1)


def _bbox(indices: np.ndarray, image: sitk.Image, margin_fraction: float = 0.12) -> tuple[int, int, int, int]:
    valid = indices[_inside(indices, image)]
    if not len(valid):
        raise PipelineError("FÃƒÆ’Ã‚Â­gado projetado fora do campo da sequencia.")
    x0, y0 = np.floor(valid[:, :2].min(axis=0)).astype(int)
    x1, y1 = np.ceil(valid[:, :2].max(axis=0)).astype(int) + 1
    mx = max(2, int(math.ceil((x1 - x0) * margin_fraction)))
    my = max(2, int(math.ceil((y1 - y0) * margin_fraction)))
    sx, sy, _ = image.GetSize()
    return (
        int(max(0, y0 - my)),
        int(min(sy, y1 + my)),
        int(max(0, x0 - mx)),
        int(min(sx, x1 + mx)),
    )


def _window(array: np.ndarray, bbox: tuple[int, int, int, int], z_indices: list[int]) -> tuple[float, float]:
    y0, y1, x0, x1 = bbox
    values = np.concatenate([
        np.asarray(array[z, y0:y1, x0:x1], dtype=np.float32).ravel()
        for z in sorted(set(z_indices))
    ])
    values = values[np.isfinite(values)]
    nonzero = values[values != 0]
    if len(nonzero) >= 100:
        values = nonzero
    if len(values) < 10:
        raise PipelineError("Sequencia sem intensidades suficientes no recorte hepatico.")
    lo, hi = np.percentile(values, [1.0, 99.0]).astype(float)
    if hi - lo < 1e-6:
        raise PipelineError("Janela multissequencia sem contraste.")
    return lo, hi


def _manifest_row(path: Path, case_id: str) -> dict[str, Any]:
    matches = [row for row in _rows(path) if row.get("case_id") == case_id]
    if len(matches) != 1:
        raise PipelineError("Caso nao possui exatamente um manifesto de input.")
    row = matches[0]
    if (
        row.get("schema") != "argos-public-liver-mri-input-v1"
        or row.get("research_only") is not True
        or row.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Manifesto de input multissequencia inseguro.")
    return row


def generate_multisequence_panel_set(
    *, case_id: str, input_root: Path, manifest_path: Path, output_root: Path,
    tile_size: int = 448, minimum_fov_fraction: float = 0.95,
    max_input_bytes: int = 8_000_000, max_image_pixels: int = 4_000_000,
) -> dict[str, Any]:
    if not case_id.startswith("anon-") or tile_size < 256:
        raise PipelineError("Parametros multissequencia invalidos.")
    row = _manifest_row(Path(manifest_path).resolve(), case_id)
    files = {str(item["role"]): item for item in row["files"]}
    trace_roles = sorted(
        (role for role in files if TRACE_RE.fullmatch(role)),
        key=lambda role: int(TRACE_RE.fullmatch(role).group(1)),
    )
    if len(trace_roles) < 3:
        raise PipelineError("Painel multissequencia exige ao menos tres TRACE.")
    trace_role = trace_roles[-1]
    t2_role = "t2_blade" if "t2_blade" in files else "t2_haste" if "t2_haste" in files else None
    roles = ["t1_venous", "liver_mask_venous", "dwi_adc", trace_role, t2_role]
    if t2_role is None or any(role not in files for role in roles):
        raise PipelineError("Sequencia obrigatoria ausente no painel multissequencia.")
    input_root = Path(input_root).resolve()

    def resolve(role: str) -> Path:
        item = files[role]
        path = input_root / str(item["relative_path"])
        if (
            not path.is_file() or path.stat().st_size != int(item["bytes"])
            or _sha256(path) != str(item["sha256"])
        ):
            raise PipelineError(f"Hash/bytes divergentes em {role}.")
        return path

    paths = {role: resolve(role) for role in roles}
    images = {role: sitk.ReadImage(str(paths[role])) for role in roles}
    if not _geometry_matches(images["t1_venous"], images["liver_mask_venous"]):
        raise PipelineError("Mascara venosa nao corresponde ao T1.")
    points = _physical_points(images["liver_mask_venous"])
    mapped = {role: _continuous_indices(points, images[role]) for role in roles if role != "liver_mask_venous"}
    trace_inside = _inside(mapped[trace_role], images[trace_role])
    inside_fraction = float(trace_inside.mean())
    if inside_fraction < float(minimum_fov_fraction):
        raise PipelineError("TRACE nao cobre 95% dos pontos fÃƒÆ’Ã‚Â­sicos hepÃƒÆ’Ã‚Â¡ticos.")
    rounded_trace_z = np.rint(mapped[trace_role][:, 2]).astype(int)
    expected_planes = sorted(set(int(value) for value in rounded_trace_z[trace_inside]))
    if not expected_planes:
        raise PipelineError("Nenhum plano TRACE intercepta o fÃƒÆ’Ã‚Â­gado projetado.")

    render_roles = ["t1_venous", t2_role, trace_role, "dwi_adc"]
    panel_positions = []
    for trace_z in expected_planes:
        members = trace_inside & (rounded_trace_z == trace_z)
        indices = {}
        tile_centers = {}
        for role in render_roles:
            valid_members = members & _inside(mapped[role], images[role])
            if not np.any(valid_members):
                indices[role] = None
                tile_centers[role] = None
                continue
            center = np.median(points[valid_members], axis=0)
            mapped_center = _continuous_indices(center.reshape(1, 3), images[role])[0]
            xyz = np.rint(mapped_center).astype(int)
            size = np.asarray(images[role].GetSize())
            if np.any(xyz < 0) or np.any(xyz >= size):
                raise PipelineError(f"Centro fisico valido saiu do campo em {role}.")
            indices[role] = xyz.tolist()
            tile_centers[role] = center.tolist()
        panel_positions.append({
            "trace_plane_index": trace_z,
            "physical_center_xyz": np.median(points[members], axis=0).tolist(),
            "indices_xyz": indices,
            "tile_physical_centers_xyz": tile_centers,
        })

    bboxes = {role: _bbox(mapped[role], images[role]) for role in ("t1_venous", t2_role, trace_role, "dwi_adc")}
    arrays = {role: sitk.GetArrayFromImage(images[role]) for role in roles}
    z_by_role = {
        role: [
            int(position["indices_xyz"][role][2])
            for position in panel_positions
            if position["indices_xyz"][role] is not None
        ]
        for role in render_roles
    }
    windows = {role: _window(arrays[role], bboxes[role], z_by_role[role]) for role in z_by_role}
    output_root = Path(output_root).resolve()
    final_dir = output_root / case_id
    if final_dir.exists():
        raise PipelineError("Saida multissequencia existente; nao sera sobrescrita.")
    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
    staging.mkdir()
    panels = []
    mask_array = arrays["liver_mask_venous"] > 0
    labels = {
        "t1_venous": "T1 VENOSO | contorno hepÃƒÆ’Ã‚Â¡tico",
        t2_role: f"T2 {t2_role.removeprefix('t2_').upper()} | nativo",
        trace_role: f"DWI TRACE {trace_role.rsplit('_', 1)[-1]} | run ordenado final",
        "dwi_adc": "ADC | nativo",
    }
    try:
        total = len(panel_positions)
        for number, position in enumerate(panel_positions, start=1):
            canvas = Image.new("RGB", (tile_size * 2, tile_size * 2), (10, 14, 20))
            tile_records = []
            for tile_number, role in enumerate(render_roles, start=1):
                coordinates = position["indices_xyz"][role]
                available = coordinates is not None
                if available:
                    x, y, z = coordinates
                    mask_2d = mask_array[z] if role == "t1_venous" else np.zeros_like(arrays[role][z], dtype=bool)
                    tile = _render_tile(
                        arrays[role][z], mask_2d,
                        f"{labels[role]} | plano {number}/{total}", tile_size,
                        *windows[role], images[role].GetSpacing()[1], images[role].GetSpacing()[0],
                        2, (0, 255, 255), crop_bbox=bboxes[role], show_contour=role == "t1_venous",
                    )
                else:
                    tile = Image.new("RGB", (tile_size, tile_size), (10, 14, 20))
                    draw = ImageDraw.Draw(tile)
                    draw.text((16, 16), f"{labels[role]} | plano {number}/{total}", fill=(220, 225, 230))
                    draw.text((16, tile_size // 2), "FORA DO FOV NESTE PLANO TRACE", fill=(255, 190, 80))
                canvas.paste(tile, (((tile_number - 1) % 2) * tile_size, ((tile_number - 1) // 2) * tile_size))
                tile_records.append({
                    "tile_number": tile_number, "role": role, "index_xyz": coordinates,
                    "physical_center_xyz": position["tile_physical_centers_xyz"][role],
                    "available_in_fov": available,
                    "show_liver_contour": available and role == "t1_venous",
                    "window": list(windows[role]), "crop_bbox_yxyx": list(bboxes[role]),
                })
            filename = f"medgemma_liver_multisequence_panel_{number:03d}_of_{total:03d}.png"
            path = staging / filename
            if canvas.width * canvas.height > max_image_pixels:
                raise PipelineError("Painel multissequencia excede pixels permitidos.")
            canvas.save(path, format="PNG", optimize=True)
            if path.stat().st_size > max_input_bytes:
                raise PipelineError("Painel multissequencia excede bytes permitidos.")
            panels.append({
                "panel_number": number, "panel_total": total, "image": filename,
                "bytes": path.stat().st_size, "sha256": _sha256(path),
                "trace_plane_index": position["trace_plane_index"],
                "physical_center_xyz": position["physical_center_xyz"], "tiles": tile_records,
            })
        rendered_planes = [int(panel["trace_plane_index"]) for panel in panels]
        duplicates = sorted({value for value in rendered_planes if rendered_planes.count(value) > 1})
        missing = sorted(set(expected_planes) - set(rendered_planes))
        if rendered_planes != expected_planes or duplicates or missing:
            raise PipelineError("Cobertura de planos TRACE incompleta ou duplicada.")
        manifest = {
            "schema": SCHEMA, "case_id": case_id,
            "representation": "native_t1_venous_t2_ordered_trace_adc_2x2",
            "trace_role": trace_role,
            "trace_semantics": "last_ordered_run_not_claimed_as_high_b",
            "t2_role": t2_role,
            "source_sha256": {role: files[role]["sha256"] for role in roles},
            "panel_count": len(panels), "panels": panels,
            "coverage": {
                "total_liver_physical_points": int(len(points)),
                "points_inside_trace_fov": int(trace_inside.sum()),
                "inside_trace_fov_fraction": inside_fraction,
                "minimum_required_fraction": minimum_fov_fraction,
                "expected_trace_planes": expected_planes,
                "rendered_trace_planes": rendered_planes,
                "missing_trace_planes": missing, "duplicate_trace_planes": duplicates,
                "unavailable_tiles": [
                    {"panel_number": panel["panel_number"], "role": tile["role"]}
                    for panel in panels for tile in panel["tiles"]
                    if tile["available_in_fov"] is False
                ],
                "gate_passed": True,
            },
            "ground_truth_read": False, "lesion_mask_used": False,
            "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "multisequence_manifest.json", manifest)
        _publish_directory(staging, final_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise






