from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from dtwin.core import PipelineError
from dtwin.learning.openswiss_monophase_atlas_candidates import (
    build_openswiss_monophase_atlas_candidates,
)
from dtwin.learning.protocol import sha256_file


def _pixel(image: Image.Image) -> str:
    normalized = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(normalized.mode.encode("ascii"))
    digest.update(str(normalized.size).encode("ascii"))
    digest.update(normalized.tobytes())
    return digest.hexdigest()


def _fixture(root: Path) -> Path:
    atlas = root / "atlas"
    case_id = "anon-openswiss-test0001"
    case = atlas / case_id
    case.mkdir(parents=True)
    frame = Image.new("RGB", (8, 8))
    tiles = []
    for q, index in enumerate((3, 4, 5)):
        tile = Image.new("RGB", (4, 4), (10 + q, 20 + q, 30 + q))
        frame.paste(tile, ((q % 2) * 4, (q // 2) * 4))
        tiles.append({
            "quadrant": q + 1,
            "empty": False,
            "counts_toward_coverage": True,
            "axial_index": index,
            "tile_pixel_sha256": _pixel(tile),
        })
    tiles.append({"quadrant": 4, "empty": True, "counts_toward_coverage": False})
    frame_path = case / "frame.png"
    frame.save(frame_path)
    manifest = {
        "case_id": case_id,
        "ground_truth_read": False,
        "lesion_mask_read": False,
        "source": {"candidate_kind": "multiphase_rgb"},
        "atlas": {
            "gate_passed": True,
            "coverage_percent": 100.0,
            "expected_axial_indices": [3, 4, 5],
            "represented_axial_indices": [3, 4, 5],
        },
        "frames": [{
            "image": "frame.png",
            "sha256": sha256_file(frame_path),
            "tiles": tiles,
        }],
    }
    manifest_path = case / "axial_atlas_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cohort = {
        "all_gates_passed": True,
        "cases": [{"case_id": case_id}],
    }
    (atlas / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    return atlas


def test_builds_exact_monophase_tiles_without_labels(tmp_path: Path) -> None:
    atlas = _fixture(tmp_path)
    out = tmp_path / "out"
    result = build_openswiss_monophase_atlas_candidates(
        atlas_root=atlas, workspace_root=tmp_path, output_root=out
    )
    assert result["all_cases_exact_coverage"] is True
    assert result["candidate_record_count"] == 3
    rows = [json.loads(line) for line in (out / "candidate_records.jsonl").read_text().splitlines()]
    assert [row["axial_index"] for row in rows] == [3, 4, 5]
    assert all(row["ground_truth_used"] is False for row in rows)
    with Image.open(tmp_path / rows[0]["image_path"]) as image:
        assert image.size == (448, 448)
        assert image.getpixel((100, 100)) == (30, 30, 30)


def test_rejects_tampered_frame(tmp_path: Path) -> None:
    atlas = _fixture(tmp_path)
    Image.new("RGB", (8, 8), "black").save(atlas / "anon-openswiss-test0001" / "frame.png")
    with pytest.raises(PipelineError, match="Hash de frame"):
        build_openswiss_monophase_atlas_candidates(
            atlas_root=atlas, workspace_root=tmp_path, output_root=tmp_path / "out"
        )
