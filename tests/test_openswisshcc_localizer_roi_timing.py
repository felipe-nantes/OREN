import json

import pytest

from dtwin.benchmark.openswisshcc_localizer_roi_timing import (
    _assert_regeneration_matches,
    compose_case_timing,
)
from dtwin.core import PipelineError


def test_composite_sums_every_prepared_benchmark_stage():
    result = compose_case_timing(
        registration_seconds=13,
        localizer_seconds=30,
        morphology_render_seconds=2,
        enhancement_render_seconds=3,
        medgemma_scoring_seconds=31,
    )
    assert result["prepared_benchmark_composite_seconds"] == 79
    assert result["within_prepared_benchmark_180_seconds"] is True
    assert set(result["stages_seconds"]) == {
        "phase_registration",
        "lesion_localizer",
        "morphology_roi_rendering",
        "enhancement_roi_rendering",
        "medgemma_4b_scoring",
    }


def test_composite_rejects_invalid_or_over_budget_stage():
    with pytest.raises(PipelineError, match="lesion_localizer"):
        compose_case_timing(
            registration_seconds=1,
            localizer_seconds=float("nan"),
            morphology_render_seconds=1,
            enhancement_render_seconds=1,
            medgemma_scoring_seconds=1,
        )


def test_regeneration_requires_byte_identical_approved_png(tmp_path):
    approved = tmp_path / "approved"
    generated = tmp_path / "generated"
    approved.mkdir()
    generated.mkdir()
    (approved / "panel.png").write_bytes(b"same")
    (generated / "panel.png").write_bytes(b"same")
    import hashlib

    digest = hashlib.sha256(b"same").hexdigest()
    manifest = {"panels": [{"image": "panel.png", "sha256": digest}]}
    manifest_path = approved / "roi_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert len(_assert_regeneration_matches(
        generated_manifest=manifest,
        approved_manifest_path=manifest_path,
        generated_dir=generated,
        approved_dir=approved,
    )) == 64
    (generated / "panel.png").write_bytes(b"different")
    with pytest.raises(PipelineError, match="byte-identico"):
        _assert_regeneration_matches(
            generated_manifest=manifest,
            approved_manifest_path=manifest_path,
            generated_dir=generated,
            approved_dir=approved,
        )
