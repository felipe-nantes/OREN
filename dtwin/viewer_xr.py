"""Auditable, optional render assets for the OREN WebXR client.

The source STL remains authoritative and is never replaced. WebXR may use a
decimated copy only when it passes the same reconstruction-fidelity gate used
by the desktop viewer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pyvista as pv

from .core import sha256_of
from .viewer_artifacts import compute_mesh_metrics


XR_ASSET_SCHEMA = "oren-xr-render-asset-v1"
_TRIANGLE_BUDGETS = {
    "organ": 60_000,
    "candidate": 25_000,
    "lesion": 25_000,
    "classified_region": 30_000,
    "segment": 18_000,
    "vessel": 25_000,
    "gallbladder": 15_000,
}


def xr_triangle_budget(material: str) -> int:
    return int(_TRIANGLE_BUDGETS.get(str(material), 18_000))


def _source_asset(
    source_stl: Path,
    source_metrics: dict[str, Any],
    target: int,
    *,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    result = {
        "schema": XR_ASSET_SCHEMA,
        "stl": source_stl.name,
        "sha256": sha256_of(source_stl),
        "source_stl": source_stl.name,
        "source_mesh_sha256": sha256_of(source_stl),
        "lod_level": 0,
        "triangles": int(source_metrics.get("triangles", 0)),
        "target_triangles": int(target),
        "decimated": False,
        "fidelity_gate_passed": bool(
            source_metrics.get("reconstruction_quality_gate_passed")
        ),
        "measurement_authority": "binary_mask_in_physical_space",
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result


def build_xr_render_asset(
    *,
    mesh: pv.PolyData,
    source_stl: Path,
    source_metrics: dict[str, Any],
    mask_path: Path,
    output_path: Path,
    material: str,
    max_volume_error_percent: float,
    max_surface_p95_voxels: float,
) -> dict[str, Any]:
    """Create a LOD without allowing it to become measurement authority."""

    source_triangles = int(mesh.n_cells)
    target = xr_triangle_budget(material)
    if source_triangles <= target:
        return _source_asset(source_stl, source_metrics, target)

    reduction = 1.0 - (float(target) / float(source_triangles))
    candidate = mesh.triangulate().clean().decimate(reduction).clean()
    temporary = output_path.with_name(f".{output_path.name}.tmp.stl")
    try:
        candidate.save(str(temporary))
        fidelity = compute_mesh_metrics(
            Path(mask_path),
            candidate,
            temporary,
            max_volume_error_percent=float(max_volume_error_percent),
            max_surface_p95_voxels=float(max_surface_p95_voxels),
        )
        if not fidelity.get("reconstruction_quality_gate_passed"):
            return _source_asset(
                source_stl,
                source_metrics,
                target,
                fallback_reason="decimated_asset_failed_fidelity_gate",
            )
        temporary.replace(output_path)
        return {
            "schema": XR_ASSET_SCHEMA,
            "stl": output_path.name,
            "sha256": sha256_of(output_path),
            "source_stl": source_stl.name,
            "source_mesh_sha256": sha256_of(source_stl),
            "lod_level": 1,
            "triangles": int(candidate.n_cells),
            "target_triangles": target,
            "decimated": True,
            "fidelity_gate_passed": True,
            "fidelity": fidelity,
            "measurement_authority": "binary_mask_in_physical_space",
        }
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["XR_ASSET_SCHEMA", "build_xr_render_asset", "xr_triangle_budget"]
