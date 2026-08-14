"""Build deterministic, tile-safe PBR maps for OREN anatomical rendering.

The source image is an original illustrative texture. Generated maps influence
only lighting and color; they never modify patient geometry or measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mirrored_tile(source: Image.Image, size: int) -> Image.Image:
    half = size // 2
    seed = ImageOps.fit(source.convert("RGB"), (half, half), method=Image.Resampling.LANCZOS)
    tile = Image.new("RGB", (size, size))
    tile.paste(seed, (0, 0))
    tile.paste(ImageOps.mirror(seed), (half, 0))
    tile.paste(ImageOps.flip(seed), (0, half))
    tile.paste(ImageOps.flip(ImageOps.mirror(seed)), (half, half))
    return tile


def _normal_map(height: np.ndarray, strength: float = 2.4) -> Image.Image:
    horizontal = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    vertical = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    nx = -horizontal * strength
    ny = vertical * strength
    nz = np.ones_like(height)
    length = np.sqrt((nx * nx) + (ny * ny) + (nz * nz))
    normal = np.stack((nx / length, ny / length, nz / length), axis=-1)
    return Image.fromarray(np.uint8(np.clip((normal * 0.5 + 0.5) * 255, 0, 255)), "RGB")


def _seal_edges(image: Image.Image) -> Image.Image:
    """Make opposite borders byte-identical for repeat-wrapped WebGL sampling."""
    pixels = np.asarray(image).copy()
    pixels[:, -1] = pixels[:, 0]
    pixels[-1, :] = pixels[0, :]
    return Image.fromarray(pixels, image.mode)


def build(source: Path, output_dir: Path, *, size: int = 1024, variant: str = "") -> dict:
    if size < 256 or size > 2048 or size % 2:
        raise ValueError("size must be an even integer between 256 and 2048")
    output_dir.mkdir(parents=True, exist_ok=True)
    original = Image.open(source)
    albedo = _mirrored_tile(original, size)
    albedo = ImageEnhance.Color(albedo).enhance(0.90)
    albedo = ImageEnhance.Brightness(albedo).enhance(1.17)
    albedo = ImageEnhance.Contrast(albedo).enhance(1.08)

    gray = np.asarray(albedo.convert("L"), dtype=np.float32) / 255.0
    low = np.asarray(
        albedo.convert("L").filter(ImageFilter.GaussianBlur(radius=max(size / 128, 4))),
        dtype=np.float32,
    ) / 255.0
    detail = np.clip((gray - low) * 2.1 + 0.5, 0.0, 1.0)
    height = np.asarray(
        Image.fromarray(np.uint8(detail * 255), "L").filter(ImageFilter.GaussianBlur(radius=0.55)),
        dtype=np.float32,
    ) / 255.0
    normal = _normal_map(height)
    roughness = np.uint8(np.clip(118 + ((0.5 - detail) * 78), 72, 176))
    roughness_image = Image.fromarray(roughness, "L")
    albedo = _seal_edges(albedo)
    normal = _seal_edges(normal)
    roughness_image = _seal_edges(roughness_image)

    suffix = f"_{variant}" if variant else ""
    outputs = {
        "albedo": output_dir / f"liver_realistic_v1{suffix}_albedo.png",
        "normal": output_dir / f"liver_realistic_v1{suffix}_normal.png",
        "roughness": output_dir / f"liver_realistic_v1{suffix}_roughness.png",
    }
    albedo.save(outputs["albedo"], optimize=True)
    normal.save(outputs["normal"], optimize=True)
    roughness_image.save(outputs["roughness"], optimize=True)

    manifest = {
        "schema": "oren-anatomic-material-pack-v1",
        "material_id": "liver_realistic_v1",
        "variant": variant or "desktop_1k",
        "texture_source": "illustrative_not_patient_derived",
        "geometry_displacement": False,
        "size": [size, size],
        "maps": {
            name: {"filename": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}
            for name, path in outputs.items()
        },
    }
    manifest_path = output_dir / f"liver_realistic_v1{suffix}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**manifest, "manifest": str(manifest_path), "manifest_sha256": _sha256(manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--variant", default="")
    args = parser.parse_args()
    print(json.dumps(
        build(args.source, args.output_dir, size=args.size, variant=args.variant),
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
