import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_fallback import render_venous_fallback_candidate
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config

CONFIG = Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml")
PROFILE = Path("profiles/figado.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inputs(tmp_path: Path, *, include_truth: bool = False) -> tuple[Path, str]:
    root = tmp_path / "prepared"
    case_id = "anon-fallback-test"
    case = root / "inputs" / case_id
    case.mkdir(parents=True)
    volume = np.linspace(0, 1, 24 * 24 * 24, dtype=np.float32).reshape(24, 24, 24)
    mask = np.zeros_like(volume, dtype=np.uint8)
    mask[5:19, 5:19, 5:19] = 1
    volume_path = case / "venous.nii.gz"
    mask_path = case / "liver.nii.gz"
    sitk.WriteImage(sitk.GetImageFromArray(volume), str(volume_path))
    sitk.WriteImage(sitk.GetImageFromArray(mask), str(mask_path))
    record = {
        "case_id": case_id,
        "files": [
            {
                "role": "t1_venous",
                "relative_path": f"{case_id}/venous.nii.gz",
                "sha256": _sha(volume_path),
            },
            {
                "role": "liver_mask_venous",
                "relative_path": f"{case_id}/liver.nii.gz",
                "sha256": _sha(mask_path),
            },
        ],
    }
    if include_truth:
        record["label"] = "POSITIVE"
    manifests = root / "manifests"
    manifests.mkdir()
    (manifests / "development_inputs.jsonl").write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )
    return root, case_id


def test_fallback_config_is_single_panel_low_latency_pathology_target():
    config = load_screening_config(CONFIG)
    assert config["panel"]["mode"] == "single_grayscale"
    assert config["panel"]["strategy"] == "uniform_9"
    assert config["panel"]["axial_slices"] == 9
    assert config["panel"]["overlay_mode"] == "none"
    assert config["medgemma"]["timeout_seconds"] == 120
    assert config["medgemma"]["max_retries"] == 0
    assert config["rag"]["enabled"] is False


def test_fallback_renders_without_alignment_or_truth(tmp_path):
    inputs, case_id = _inputs(tmp_path)
    output = tmp_path / "panels"
    result = render_venous_fallback_candidate(
        case_id=case_id,
        input_root=inputs,
        output_root=output,
        config_path=CONFIG,
        profile_path=PROFILE,
    )
    assert result["candidate_kind"] == "venous_single_phase_fallback"
    assert result["fallback_reason"] == "multiphase_alignment_gate_failure"
    assert result["ground_truth_read"] is False
    assert result["eligible_for_inference"] is False
    panel = output / case_id / result["panel_filename"]
    assert panel.is_file() and _sha(panel) == result["panel_sha256"]
    reused = render_venous_fallback_candidate(
        case_id=case_id,
        input_root=inputs,
        output_root=output,
        config_path=CONFIG,
        profile_path=PROFILE,
    )
    assert reused["cache_reused"] is True


def test_fallback_rejects_ground_truth_in_neutral_manifest(tmp_path):
    inputs, case_id = _inputs(tmp_path, include_truth=True)
    with pytest.raises(PipelineError, match="ground truth"):
        render_venous_fallback_candidate(
            case_id=case_id,
            input_root=inputs,
            output_root=tmp_path / "panels",
            config_path=CONFIG,
            profile_path=PROFILE,
        )
