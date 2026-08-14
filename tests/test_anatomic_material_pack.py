import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tools.build_anatomic_material_textures import build


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "viewer" / "assets" / "materials"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_material_builder_is_deterministic_tile_safe_and_geometry_neutral(tmp_path):
    source = tmp_path / "source.png"
    values = np.linspace(25, 220, 300 * 240 * 3, dtype=np.uint8).reshape((240, 300, 3))
    Image.fromarray(values, "RGB").save(source)

    first = build(source, tmp_path / "first", size=256)
    second = build(source, tmp_path / "second", size=256)

    assert first["geometry_displacement"] is False
    assert first["texture_source"] == "illustrative_not_patient_derived"
    assert first["size"] == [256, 256]
    for name in ("albedo", "normal", "roughness"):
        first_path = tmp_path / "first" / first["maps"][name]["filename"]
        second_path = tmp_path / "second" / second["maps"][name]["filename"]
        assert _sha256(first_path) == _sha256(second_path)
        image = np.asarray(Image.open(first_path))
        np.testing.assert_array_equal(image[:, 0], image[:, -1])
        np.testing.assert_array_equal(image[0, :], image[-1, :])


@pytest.mark.parametrize(
    ("manifest_name", "variant", "size"),
    [
        ("liver_realistic_v1_manifest.json", "desktop_1k", 1024),
        ("liver_realistic_v1_quest512_manifest.json", "quest512", 512),
    ],
)
def test_versioned_repository_material_manifest_matches_every_runtime_asset(
    manifest_name, variant, size
):
    manifest_path = ASSET_DIR / manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema"] == "oren-anatomic-material-pack-v1"
    assert manifest["material_id"] == "liver_realistic_v1"
    assert manifest["geometry_displacement"] is False
    assert manifest["texture_source"] == "illustrative_not_patient_derived"
    assert manifest["variant"] == variant
    assert manifest["size"] == [size, size]
    for metadata in manifest["maps"].values():
        path = ASSET_DIR / metadata["filename"]
        assert path.is_file()
        assert path.stat().st_size == metadata["bytes"]
        assert _sha256(path) == metadata["sha256"]


def test_viewer_uses_only_the_local_allowlisted_material_pack():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    assets = source.split("const REALISTIC_MATERIAL_ASSETS", 1)[1].split(
        "const REALISTIC_MATERIAL_PACK_ID", 1
    )[0]

    assert "./assets/materials/liver_realistic_v1_albedo.png" in assets
    assert "./assets/materials/liver_realistic_v1_normal.png" in assets
    assert "./assets/materials/liver_realistic_v1_roughness.png" in assets
    assert "./assets/materials/liver_realistic_v1_quest512_albedo.png" in assets
    assert "./assets/materials/liver_realistic_v1_quest512_normal.png" in assets
    assert "./assets/materials/liver_realistic_v1_quest512_roughness.png" in assets
    assert "http://" not in assets and "https://" not in assets
    assert "TextureLoader" in source
    assert "preferXrAssets ? REALISTIC_MATERIAL_ASSETS.quest" in source
    assert "ensureSphericalTextureCoordinates" in source
    assert "geometry.deleteAttribute(\"color\")" in source
    assert "displacementMap" not in source
    assert "Textura anatômica indisponível; baseline restaurado" in source


def test_portable_docker_context_includes_runtime_maps_but_not_generation_source():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for filename in (
        "liver_realistic_v1_albedo.png",
        "liver_realistic_v1_normal.png",
        "liver_realistic_v1_roughness.png",
        "liver_realistic_v1_quest512_albedo.png",
        "liver_realistic_v1_quest512_normal.png",
        "liver_realistic_v1_quest512_roughness.png",
    ):
        assert f"!viewer/assets/materials/{filename}" in dockerignore
    assert "!viewer/assets/materials/liver_realistic_v1_source.png" not in dockerignore
    assert "viewer/assets/materials/liver_realistic_v1_source.png" in dockerignore
