from __future__ import annotations

import json

import numpy as np
import SimpleITK as sitk

from dtwin.learning import raw_phase_review as review


def _image(offset: float = 0.0) -> sitk.Image:
    array = np.arange(12 * 24 * 24, dtype=np.float32).reshape(12, 24, 24) + offset
    result = sitk.GetImageFromArray(array)
    result.SetSpacing((1.2, 1.2, 2.5))
    return result


def test_render_panel_is_deterministic_and_uses_common_window(tmp_path):
    images = {review.ARTERIAL: _image(0), review.VENOUS: _image(10), review.DELAYED: _image(20)}
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    metadata = review._render_panel(images, first)
    review._render_panel(images, second)
    assert review._sha256(first) == review._sha256(second)
    assert metadata["axial_indices_on_reference"] == [4, 6, 7]
    assert set(metadata["resampled_coverage"]) == set(review.PHASES)


def test_gallery_is_label_blind_and_records_exclusion(tmp_path, monkeypatch):
    source = tmp_path / "source" / "available"
    source.mkdir(parents=True)

    class Resolution:
        method = "ordered_axial_t1_postcontrast_series"
        confidence = 0.8
        phase_dirs = {phase: source for phase in review.PHASES}
        manifest_path = tmp_path / "resolution.json"

    Resolution.manifest_path.write_text(json.dumps({"selected": {
        phase: {"series_number": index, "series_hash": f"hash-{index}"}
        for index, phase in enumerate(review.PHASES, 1)
    }}), encoding="utf-8")
    monkeypatch.setattr(review, "resolve_raw_dicom_phases", lambda *_: Resolution())
    monkeypatch.setattr(review, "read_phase_series", lambda *_: _image())

    out = tmp_path / "gallery"
    manifest = review.build_raw_phase_review_gallery(
        cases=[{"case_id": "anon-1", "source_name": "available"}, {"case_id": "anon-2", "source_name": "missing"}],
        source_roots=[tmp_path / "source"], output_dir=out,
    )
    serialized = (out / "review_gallery_manifest.json").read_text(encoding="utf-8")
    assert manifest["eligible_cases"] == 1
    assert manifest["excluded_cases"] == 1
    assert manifest["ground_truth_read"] is False
    assert "POSITIVE" not in serialized
    assert "diagnosis" not in serialized.lower()
    assert not (out / "resolved").exists()
    assert (out / "panels" / "anon-1_phases.png").is_file()


def test_existing_gallery_is_not_overwritten(tmp_path):
    output = tmp_path / "gallery"
    output.mkdir()
    try:
        review.build_raw_phase_review_gallery(cases=[], source_roots=[], output_dir=output)
    except Exception as exc:
        assert "não será sobrescrita" in str(exc)
    else:
        raise AssertionError("expected fail-closed overwrite protection")
