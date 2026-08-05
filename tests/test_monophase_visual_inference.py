from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.learning.monophase_visual_inference import validate_monophase_contract


class _Bundle:
    manifest = {
        "analysis_scenario": "monophase_medsiglip",
        "panel_image_mode": "single_phase_portal_venous_grayscale_liver_enriched",
        "source_phase_key": "t1_venous",
        "source_phase_contract": "exactly_one_real_series",
        "dynamic_enhancement_information_present": False,
        "expected_panels_per_case": [2, 3],
    }


def _fixture(tmp_path: Path):
    panels = []
    paths = []
    for number in (1, 2):
        path = tmp_path / f"p{number}.png"
        path.write_bytes(f"panel-{number}".encode())
        paths.append(path)
        panels.append(
            {
                "image": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "input_type": "mri_single_phase_replicated_grayscale_full_fov_liver_enriched",
        "single_phase_replicated_across_rgb": True,
        "dynamic_enhancement_information_present": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "fusion_channel_map": {"red": "mono", "green": "mono", "blue": "mono"},
        "panels": panels,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, paths


def test_accepts_exact_single_phase_contract(tmp_path):
    manifest, paths = _fixture(tmp_path)
    result = validate_monophase_contract(_Bundle(), panel_manifest_path=manifest, panel_paths=paths)
    assert result["dynamic_enhancement_information_present"] is False


def test_accepts_hierarchical_single_phase_bundle(tmp_path):
    manifest, paths = _fixture(tmp_path)
    bundle = _Bundle()
    bundle.manifest = {
        **bundle.manifest,
        "analysis_scenario": "monophase_medsiglip_hierarchical",
    }
    result = validate_monophase_contract(
        bundle, panel_manifest_path=manifest, panel_paths=paths
    )
    assert result["ground_truth_used"] is False


def test_rejects_triphasic_bundle(tmp_path):
    manifest, paths = _fixture(tmp_path)
    bundle = _Bundle()
    bundle.manifest = {**bundle.manifest, "panel_image_mode": "multiphase_rgb_fusion"}
    with pytest.raises(PipelineError, match="não pertence"):
        validate_monophase_contract(bundle, panel_manifest_path=manifest, panel_paths=paths)


def test_rejects_panel_hash_tampering(tmp_path):
    manifest, paths = _fixture(tmp_path)
    paths[0].write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="Hash ou ordem"):
        validate_monophase_contract(_Bundle(), panel_manifest_path=manifest, panel_paths=paths)


def test_rejects_runtime_phase_that_does_not_match_bundle(tmp_path):
    manifest, paths = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="Fase monofásica"):
        validate_monophase_contract(
            _Bundle(),
            panel_manifest_path=manifest,
            panel_paths=paths,
            source_phase_key="t1_delayed",
        )
