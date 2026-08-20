"""Render current versus shadow liver meshes without touching viewer artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyvista as pv
import SimpleITK as sitk
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.core import sha256_of
from dtwin.stages import _isolar_orgao_para_visualizacao, _mesh_from_mask


def _clean(source: Path, destination: Path) -> dict:
    image = sitk.ReadImage(str(source))
    array = sitk.GetArrayFromImage(image) > 0
    cleaned, receipt = _isolar_orgao_para_visualizacao(array)
    output = sitk.GetImageFromArray(cleaned.astype(np.uint8))
    output.CopyInformation(image)
    sitk.WriteImage(output, str(destination), useCompression=True)
    receipt["source_voxels"] = int(array.sum())
    receipt["clean_voxels"] = int(cleaned.sum())
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-mask", type=Path, required=True)
    parser.add_argument("--shadow-mask", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=REPO / "profiles/figado.yaml")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(args.profile.read_text(encoding="utf-8"))
    mesh_config = config["mesh"]
    clean_current = output / "mask_organ_current_visual_clean.nii.gz"
    clean_shadow = output / "mask_organ_shadow_visual_clean.nii.gz"
    clean_receipts = {
        "current": _clean(args.current_mask.resolve(), clean_current),
        "shadow": _clean(args.shadow_mask.resolve(), clean_shadow),
    }
    kwargs = {
        "level": float(mesh_config.get("nivel_marching_cubes", 0.5)),
        "smooth_iter": int(mesh_config.get("suavizacao_iteracoes", 30)),
        "feature_angle": float(mesh_config.get("feature_angle", 60.0)),
        "pass_band": float(mesh_config.get("taubin_pass_band", 0.1)),
        "isotropic_mm": float(mesh_config.get("reamostragem_isotropica_mm", 0.8)),
        "gaussian_sigma_mm": float(mesh_config.get("suavizacao_campo_sigma_mm", 2.0)),
        "max_triangles": int(mesh_config.get("max_triangulos", 160000)),
    }
    current_mesh = _mesh_from_mask(clean_current, **kwargs)
    shadow_mesh = _mesh_from_mask(clean_shadow, **kwargs)
    if current_mesh is None or shadow_mesh is None:
        raise RuntimeError("Uma das mascaras nao produziu malha.")
    current_vtp = output / "mesh_organ_current_shadow_audit.vtp"
    shadow_vtp = output / "mesh_organ_candidate_shadow_audit.vtp"
    current_mesh.save(str(current_vtp))
    shadow_mesh.save(str(shadow_vtp))

    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(1800, 820))
    for index, (mesh, title, color) in enumerate(
        (
            (current_mesh, "ATUAL — total_mr venoso", "#C8A27D"),
            (shadow_mesh, "SHADOW — MRSegmentator arterial", "#E6B566"),
        )
    ):
        plotter.subplot(0, index)
        plotter.set_background("#081019")
        plotter.add_mesh(mesh, color=color, smooth_shading=True, specular=0.25, roughness=0.55)
        plotter.add_text(title, font_size=15, color="white", position="upper_edge")
        plotter.add_axes(line_width=2, color="white")
        plotter.camera_position = "iso"
        plotter.camera.zoom(1.15)
    plotter.link_views()
    screenshot = output / "shadow_mesh_comparison.png"
    plotter.screenshot(str(screenshot))
    plotter.close()

    receipt = {
        "schema": "argos-segmentation-shadow-mesh-comparison-v2",
        "purpose": "visualization_only",
        "not_segmentation_accuracy": True,
        "production_files_written": False,
        "current_mask_sha256": sha256_of(args.current_mask),
        "shadow_mask_sha256": sha256_of(args.shadow_mask),
        "cleaning": clean_receipts,
        "current_mesh": {
            "sha256": sha256_of(current_vtp),
            "triangles": int(current_mesh.n_cells),
            "volume_ml": round(abs(float(current_mesh.volume)) / 1000.0, 4),
        },
        "shadow_mesh": {
            "sha256": sha256_of(shadow_vtp),
            "triangles": int(shadow_mesh.n_cells),
            "volume_ml": round(abs(float(shadow_mesh.volume)) / 1000.0, 4),
        },
        "screenshot_sha256": sha256_of(screenshot),
        "mesh_parameters": kwargs,
    }
    manifest = output / "shadow_mesh_comparison.json"
    manifest.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
