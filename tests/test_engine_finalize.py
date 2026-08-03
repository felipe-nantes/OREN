# tests/test_engine_finalize.py
import json
from pathlib import Path

import numpy as np
from PIL import Image

from dtwin.engine import Engine
from dtwin.core import array_from, array_to_image, read_image, save_image, sha256_of
from .conftest import make_sphere_mask


def test_finalize_produces_stls_and_manifest(synthetic_case):
    engine = Engine(Path("profiles/figado.yaml"))
    case = engine.finalize(str(synthetic_case.root), no_lesion=False)

    organ_stl = case.outputs / "figado_orgao.stl"
    lesion_stl = case.outputs / "figado_lesao.stl"
    manifest = case.outputs / "viewer_manifest.json"
    assert organ_stl.exists() and organ_stl.stat().st_size > 0
    assert lesion_stl.exists() and lesion_stl.stat().st_size > 0
    assert manifest.exists()

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema"] == "argos-viewer-manifest-v2"
    assert data["schema_version"] == 2
    assert data["organ"] == "figado"
    assert data["coordinate_system"] == "LPS"
    roles = {m["role"]: m for m in data["meshes"]}
    assert set(roles) == {"orgao", "lesao"}
    # STL refs are relative filenames only (viewer depends on this)
    for m in data["meshes"]:
        assert "/" not in m["stl"] and "\\" not in m["stl"]
        assert (case.outputs / m["stl"]).exists()
        metrics = m["metrics"]
        assert metrics["not_segmentation_accuracy"] is True
        assert metrics["source_mask_volume_ml"] > 0
        assert metrics["mesh_sha256"] == sha256_of(case.outputs / m["stl"])
        assert metrics["vertices"] > 0 and metrics["triangles"] > 0

    references = data["reference_images"]
    assert references["contains_phi_metadata"] is False
    axial = references["views"]["axial"]
    mask = array_from(read_image(case.mask_organ_clean)) > 0
    expected_indices = np.flatnonzero(mask.any(axis=(1, 2))).tolist()
    assert [frame["index"] for frame in axial["frames"]] == expected_indices
    assert axial["coverage"] == "all_liver_bearing_planes"
    for view in references["views"].values():
        for frame in view["frames"]:
            image_path = case.outputs / frame["file"]
            assert image_path.is_file()
            assert frame["sha256"] == sha256_of(image_path)
            with Image.open(image_path) as image:
                assert image.size == (512, 512)
                assert not image.getexif()


def test_finalize_no_lesion_flag(synthetic_case):
    # remove the lesion mask, finalize with --no-lesion
    synthetic_case.mask_lesion.unlink()
    engine = Engine(Path("profiles/figado.yaml"))
    case = engine.finalize(str(synthetic_case.root), no_lesion=True)
    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {m["role"] for m in data["meshes"]}
    assert "orgao" in roles
    assert "lesao" not in roles


def test_refinalize_no_lesion_drops_prior_lesion(synthetic_case):
    """Re-running finalize with --no-lesion after a lesion run must not keep the
    stale lesion mesh/STL. Finalize has to be idempotent against prior artifacts."""
    engine = Engine(Path("profiles/figado.yaml"))
    # first pass: real lesion present
    case = engine.finalize(str(synthetic_case.root), no_lesion=False)
    assert (case.outputs / "figado_lesao.stl").exists()

    # operator decides there is no lesion: drop the mask, re-finalize
    synthetic_case.mask_lesion.unlink()
    case = engine.finalize(str(synthetic_case.root), no_lesion=True)

    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {m["role"] for m in data["meshes"]}
    assert "lesao" not in roles, "stale lesion survived a --no-lesion re-finalize"
    assert not (case.outputs / "figado_lesao.stl").exists()
    assert not case.mesh_lesion.exists()


def test_finalize_exports_internal_anatomy_when_available(synthetic_case):
    """Anatomia interna é publicada com metadados para o viewer, sem atlas externo."""
    ref = read_image(synthetic_case.mask_organ)
    shape = tuple(reversed(ref.GetSize()))
    for role, center in (("couinaud_i", (20, 16, 20)), ("vesicula_biliar", (25, 23, 20))):
        mask = make_sphere_mask(shape, center, 4)
        save_image(array_to_image(mask, ref), synthetic_case.anatomy_mask(role))

    case = Engine(Path("profiles/figado.yaml")).finalize(str(synthetic_case.root), no_lesion=False)
    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {item["role"]: item for item in data["meshes"]}

    assert {"orgao", "lesao", "couinaud_i", "vesicula_biliar"} <= set(roles)
    assert roles["couinaud_i"]["label"] == "Segmento Couinaud I"
    assert roles["couinaud_i"]["material"] == "segment"
    assert roles["orgao"]["default_visible"] is False
    assert (case.outputs / roles["couinaud_i"]["stl"]).is_file()
