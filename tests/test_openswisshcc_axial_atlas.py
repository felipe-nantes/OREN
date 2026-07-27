from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import openswisshcc_axial_atlas as atlas
from dtwin.core import PipelineError


def _sha256(path: Path) -> str:
    return atlas._sha256(path)


def _write_source(
    root: Path,
    *,
    case_id: str = "anon-openswiss-test001",
    count: int = 5,
    tile_size: int = 384,
) -> Path:
    case = root / case_id
    case.mkdir(parents=True)
    expected = list(range(10, 10 + count))
    panel_count = (count + 8) // 9
    candidate_panels = []
    manifest_panels = []
    for panel_offset in range(panel_count):
        panel_number = panel_offset + 1
        filename = f"medgemma_liver_screening_panel_{panel_number:03d}_of_{panel_count:03d}.png"
        image = Image.new("RGB", (tile_size * 4, tile_size * 3), "black")
        tiles = []
        indices = expected[panel_offset * 9 : (panel_offset + 1) * 9]
        for tile_offset, index in enumerate(indices):
            color = (index, index + 1, index + 2)
            tile = Image.new("RGB", (tile_size, tile_size), color)
            image.paste(
                tile,
                ((tile_offset % 3) * tile_size, (tile_offset // 3) * tile_size),
            )
            tiles.append(
                {
                    "tile_number": tile_offset + 1,
                    "orientation": "axial",
                    "index": index,
                    "relative_position_percent": 100.0 * (index - expected[0]) / max(1, count - 1),
                    "liver_voxels_in_plane": 100 + index,
                    "liver_volume_percent": 100.0 / count,
                    "counts_toward_coverage": True,
                }
            )
        tiles.extend(
            [
                {
                    "tile_number": 10,
                    "orientation": "coronal",
                    "index": 20,
                    "relative_position_percent": 50.0,
                    "liver_voxels_in_plane": 100,
                    "liver_volume_percent": 1.0,
                    "counts_toward_coverage": False,
                },
                {
                    "tile_number": 11,
                    "orientation": "sagittal",
                    "index": 21,
                    "relative_position_percent": 50.0,
                    "liver_voxels_in_plane": 100,
                    "liver_volume_percent": 1.0,
                    "counts_toward_coverage": False,
                },
            ]
        )
        path = case / filename
        image.save(path)
        digest = _sha256(path)
        candidate_panels.append(
            {
                "panel_number": panel_number,
                "panel_total": panel_count,
                "image": filename,
                "sha256": digest,
                "bytes": path.stat().st_size,
                "axial_interval": [indices[0], indices[-1]],
            }
        )
        manifest_panels.append(
            {
                "panel_number": panel_number,
                "panel_total": panel_count,
                "image": filename,
                "sha256": digest,
                "axial_indices": indices,
                "axial_interval": [indices[0], indices[-1]],
                "tiles": tiles,
            }
        )
    coverage = {
        "coverage_percent": 100.0,
        "covered_liver_voxels": 12345,
        "duplicate_axial_indices": [],
        "expected_axial_indices": expected,
        "first_liver_slice": expected[0],
        "gate_passed": True,
        "gate_rule": "covered_liver_voxels == total_liver_voxels",
        "last_liver_slice": expected[-1],
        "missing_axial_indices": [],
        "total_liver_voxels": 12345,
    }
    candidate = {
        "candidate_version": atlas.SOURCE_CANDIDATE_VERSION,
        "case_id": case_id,
        "candidate_signature": "a" * 64,
        "candidate_kind": "multiphase_rgb",
        "panel_strategy": "volumetric_blocks",
        "ground_truth_read": False,
        "panel_set_sha256": "b" * 64,
        "coverage": coverage,
        "panels": candidate_panels,
    }
    panel_manifest = {
        "schema_version": atlas.SOURCE_PANEL_SCHEMA,
        "case_id": case_id,
        "lesion_pre_marked": False,
        "panel_strategy": "volumetric_blocks",
        "panels": manifest_panels,
    }
    (case / "candidate_manifest.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )
    (case / "medgemma_liver_screening_manifest.json").write_text(
        json.dumps(panel_manifest), encoding="utf-8"
    )
    return case


def test_build_case_repacks_every_axial_tile_exactly_once(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source", count=5)
    manifest = atlas.build_axial_atlas_case(source, tmp_path / "out")

    assert manifest["atlas"]["gate_passed"] is True
    assert manifest["atlas"]["represented_axial_indices"] == [10, 11, 12, 13, 14]
    assert manifest["atlas"]["missing_axial_indices"] == []
    assert manifest["atlas"]["duplicate_axial_indices"] == []
    assert manifest["atlas"]["frame_count"] == 2
    assert manifest["ground_truth_read"] is False
    assert manifest["lesion_mask_read"] is False

    first = Image.open(tmp_path / "out" / source.name / manifest["frames"][0]["image"])
    assert first.size == (768, 768)
    assert first.getpixel((10, 10)) == (10, 11, 12)
    assert first.getpixel((394, 10)) == (11, 12, 13)
    assert first.getpixel((10, 394)) == (12, 13, 14)
    assert first.getpixel((394, 394)) == (13, 14, 15)

    second = Image.open(tmp_path / "out" / source.name / manifest["frames"][1]["image"])
    assert second.getpixel((10, 10)) == (14, 15, 16)
    assert second.getpixel((394, 10)) == (0, 0, 0)
    assert [tile["empty"] for tile in manifest["frames"][1]["tiles"]] == [
        False,
        True,
        True,
        True,
    ]


def test_native_320px_tiles_are_preserved_without_resize(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source", count=5, tile_size=320)
    manifest = atlas.build_axial_atlas_case(source, tmp_path / "out")
    frame_path = tmp_path / "out" / source.name / manifest["frames"][0]["image"]
    with Image.open(frame_path) as image:
        assert image.size == (640, 640)
        assert image.getpixel((330, 10)) == (11, 12, 13)
    assert manifest["atlas"]["tile_size_pixels"] == [320, 320]
    assert manifest["atlas"]["frame_size_pixels"] == [640, 640]


@pytest.mark.parametrize("count,expected_frames", [(1, 1), (4, 1), (5, 2), (9, 3), (10, 3), (37, 10)])
def test_frame_count_is_deterministic(
    tmp_path: Path, count: int, expected_frames: int
) -> None:
    source = _write_source(tmp_path / "source", count=count)
    manifest = atlas.build_axial_atlas_case(source, tmp_path / "out")
    assert manifest["atlas"]["frame_count"] == expected_frames
    assert manifest["atlas"]["tile_count"] == count


def test_source_hash_tampering_aborts_before_output(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source")
    panel = next(source.glob("medgemma_liver_screening_panel_*.png"))
    panel.write_bytes(panel.read_bytes() + b"tamper")
    with pytest.raises(PipelineError, match="Hash inconsistente"):
        atlas.build_axial_atlas_case(source, tmp_path / "out")
    assert not (tmp_path / "out" / source.name).exists()


def test_missing_or_duplicate_axial_index_aborts(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source")
    path = source / "medgemma_liver_screening_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["panels"][0]["tiles"][1]["index"] = 10
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="missing=.*11.*duplicates=.*10"):
        atlas.build_axial_atlas_case(source, tmp_path / "out")


def test_failed_source_coverage_gate_aborts(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source")
    path = source / "candidate_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["coverage"]["covered_liver_voxels"] -= 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="100% exatos"):
        atlas.build_axial_atlas_case(source, tmp_path / "out")


def test_frame_limit_aborts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source", count=5)
    monkeypatch.setattr(atlas, "MAX_FRAMES", 1)
    with pytest.raises(PipelineError, match="limite congelado"):
        atlas.build_axial_atlas_case(source, tmp_path / "out")


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source")
    atlas.build_axial_atlas_case(source, tmp_path / "out")
    with pytest.raises(PipelineError, match="já existe"):
        atlas.build_axial_atlas_case(source, tmp_path / "out")


def test_cohort_and_gallery_are_blind_and_hash_verified(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    first = _write_source(source_root, case_id="anon-openswiss-test001", count=5)
    second = _write_source(source_root, case_id="anon-openswiss-test002", count=10)
    cohort = atlas.build_axial_atlas_cohort(
        source_root, tmp_path / "atlas", [first.name, second.name]
    )
    gallery = atlas.build_axial_atlas_gallery(tmp_path / "atlas", tmp_path / "gallery")

    assert cohort["case_count"] == 2
    assert cohort["tile_count"] == 15
    assert cohort["all_gates_passed"] is True
    assert cohort["ground_truth_read"] is False
    assert cohort["holdout_read"] is False
    assert gallery["case_count"] == 2
    assert gallery["review_status"] == "pending_human_review"
    index = (tmp_path / "gallery" / "index.html").read_text(encoding="utf-8")
    assert "Não há labels" in index
    assert "POSITIVE" not in index


def test_gallery_rejects_changed_case_manifest(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "source")
    atlas.build_axial_atlas_cohort(
        tmp_path / "source", tmp_path / "atlas", [source.name]
    )
    manifest = tmp_path / "atlas" / source.name / "axial_atlas_manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(PipelineError, match="Manifesto v17 alterado"):
        atlas.build_axial_atlas_gallery(tmp_path / "atlas", tmp_path / "gallery")


def test_cohort_failure_is_atomic(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    first = _write_source(source_root, case_id="anon-openswiss-test001")
    second = _write_source(source_root, case_id="anon-openswiss-test002")
    second_panel = next(second.glob("medgemma_liver_screening_panel_*.png"))
    second_panel.write_bytes(second_panel.read_bytes() + b"tamper")
    destination = tmp_path / "atlas"
    with pytest.raises(PipelineError, match="Hash inconsistente"):
        atlas.build_axial_atlas_cohort(
            source_root, destination, [first.name, second.name]
        )
    assert not destination.exists()


def test_directory_publish_retries_transient_windows_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    staging = tmp_path / "staging"
    destination = tmp_path / "published"
    staging.mkdir()
    (staging / "ready.txt").write_text("ok", encoding="utf-8")
    original_replace = atlas.os.replace
    calls = 0

    def flaky_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError("transient lock")
        original_replace(source, target)

    monkeypatch.setattr(atlas.os, "replace", flaky_replace)
    monkeypatch.setattr(atlas.time, "sleep", lambda _seconds: None)
    atlas._publish_directory(staging, destination)
    assert calls == 3
    assert (destination / "ready.txt").read_text(encoding="utf-8") == "ok"


def test_case_list_rejects_holdout_and_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "cohort.json"
    path.write_text(
        json.dumps({"cases": [{"case_id": "anon-openswiss-holdout001"}]}),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="não autorizado"):
        atlas.case_ids_from_cohort_manifest(path)

    with pytest.raises(PipelineError, match="duplicada"):
        atlas.build_axial_atlas_cohort(
            tmp_path, tmp_path / "out", ["anon-openswiss-a", "anon-openswiss-a"]
        )


def _review_gallery(tmp_path: Path) -> Path:
    source = _write_source(tmp_path / "source")
    atlas.build_axial_atlas_cohort(
        tmp_path / "source", tmp_path / "atlas", [source.name]
    )
    atlas.build_axial_atlas_gallery(tmp_path / "atlas", tmp_path / "gallery")
    return tmp_path / "gallery"


def test_signed_human_review_is_bound_to_gallery_hashes(tmp_path: Path) -> None:
    gallery = _review_gallery(tmp_path)
    confirmations = {key: True for key in atlas.REQUIRED_REVIEW_CONFIRMATIONS}
    review = atlas.record_axial_atlas_review(
        gallery_root=gallery,
        out_path=tmp_path / "reviews" / "pilot.json",
        reviewer="jm",
        confirmations=confirmations,
        approved=True,
        notes="Fallback venoso em escala de cinza aprovado.",
        reviewed_at_utc="2026-07-17T12:00:00+00:00",
    )
    assert review["status"] == "approved_for_full87_generation"
    assert review["case_count"] == 1
    assert review["ground_truth_read"] is False
    assert review["holdout_read"] is False
    assert len(review["review_signature"]) == 64


def test_review_requires_every_confirmation(tmp_path: Path) -> None:
    gallery = _review_gallery(tmp_path)
    confirmations = {key: True for key in atlas.REQUIRED_REVIEW_CONFIRMATIONS}
    confirmations["venous_fallback_readable"] = False
    with pytest.raises(PipelineError, match="todas as confirmações"):
        atlas.record_axial_atlas_review(
            gallery_root=gallery,
            out_path=tmp_path / "review.json",
            reviewer="jm",
            confirmations=confirmations,
            approved=True,
        )


def test_review_revalidates_every_gallery_frame(tmp_path: Path) -> None:
    gallery = _review_gallery(tmp_path)
    frame = next(gallery.glob("anon-*/*.png"))
    frame.write_bytes(frame.read_bytes() + b"tamper")
    confirmations = {key: True for key in atlas.REQUIRED_REVIEW_CONFIRMATIONS}
    with pytest.raises(PipelineError, match="Hash alterado"):
        atlas.record_axial_atlas_review(
            gallery_root=gallery,
            out_path=tmp_path / "review.json",
            reviewer="jm",
            confirmations=confirmations,
            approved=True,
        )
