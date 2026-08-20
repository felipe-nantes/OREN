import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_volumetric import render_volumetric_candidate
from dtwin.core import PipelineError

MULTI = Path("configs/medgemma_local_4b_multiphase_volumetric_choice_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_volumetric_choice_pathology.yaml")
HIGH = Path("configs/medgemma_local_4b_venous_volumetric_high_contrast_choice_pathology.yaml")
SOURCE_HIGH = Path("configs/medgemma_local_4b_venous_review_fallback_high_contrast_pathology.yaml")
PROFILE = Path("profiles/figado.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, include_truth: bool = False) -> tuple[Path, Path, str]:
    case_id = "anon-volumetric-test"
    prepared = tmp_path / "prepared"
    case = prepared / "inputs" / case_id
    case.mkdir(parents=True)
    volume = np.linspace(0, 1, 24 * 24 * 24, dtype=np.float32).reshape(24, 24, 24)
    mask = np.zeros_like(volume, dtype=np.uint8)
    mask[5:19, 4:20, 4:20] = 1  # 14 liver-bearing axial slices -> two panels.
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
        record["label"] = "NEGATIVE"
    manifests = prepared / "manifests"
    manifests.mkdir()
    (manifests / "development_inputs.jsonl").write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )

    source = tmp_path / "source" / case_id
    source.mkdir(parents=True)
    panel = source / "panel.png"
    panel.write_bytes(b"human-reviewed-source-panel")
    candidate = {
        "schema": "argos-public-liver-mri-candidate-v1",
        "candidate_version": "openswisshcc-venous-review-remediation-v1",
        "candidate_kind": "venous_single_phase_fallback",
        "candidate_signature": "source-signature",
        "fallback_reason": "human_review_alignment_or_framing_failure",
        "case_id": case_id,
        "panel_filename": panel.name,
        "panel_sha256": _sha(panel),
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(
            Path("configs/medgemma_local_4b_venous_review_fallback_pathology.yaml")
        ),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (source / "candidate_manifest.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )
    return prepared, source.parent, case_id


def _render(tmp_path: Path, *, include_truth: bool = False):
    prepared, source, case_id = _fixture(tmp_path, include_truth=include_truth)
    output = tmp_path / "volumetric"
    result = render_volumetric_candidate(
        case_id=case_id,
        input_root=prepared,
        alignment_root=tmp_path / "alignments-not-needed",
        source_panel_root=source,
        output_root=output,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        high_contrast_fallback_config=HIGH,
        source_high_contrast_config=SOURCE_HIGH,
        profile_path=PROFILE,
    )
    return result, output, case_id


def test_volumetric_fallback_hashes_complete_collection_and_exact_coverage(tmp_path):
    result, output, case_id = _render(tmp_path)
    assert result["panel_strategy"] == "volumetric_blocks"
    assert result["panel_image_count"] == 2
    assert len(result["panels"]) == 2
    assert result["ground_truth_read"] is False
    assert result["eligible_for_inference"] is False
    coverage = result["coverage"]
    assert coverage["gate_passed"] is True
    assert coverage["covered_liver_voxels"] == coverage["total_liver_voxels"]
    assert coverage["missing_axial_indices"] == []
    assert coverage["duplicate_axial_indices"] == []
    for item in result["panels"]:
        panel = output / case_id / item["image"]
        assert panel.is_file()
        assert _sha(panel) == item["sha256"]
        assert panel.stat().st_size == item["bytes"]


def test_volumetric_candidate_reuses_only_intact_complete_collection(tmp_path):
    first, output, case_id = _render(tmp_path)
    prepared = tmp_path / "prepared"
    source = tmp_path / "source"
    second = render_volumetric_candidate(
        case_id=case_id,
        input_root=prepared,
        alignment_root=tmp_path / "alignments-not-needed",
        source_panel_root=source,
        output_root=output,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        high_contrast_fallback_config=HIGH,
        source_high_contrast_config=SOURCE_HIGH,
        profile_path=PROFILE,
    )
    assert second["cache_reused"] is True
    assert second["panel_set_sha256"] == first["panel_set_sha256"]

    tampered = output / case_id / first["panels"][1]["image"]
    tampered.write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="ausente ou divergente"):
        render_volumetric_candidate(
            case_id=case_id,
            input_root=prepared,
            alignment_root=tmp_path / "alignments-not-needed",
            source_panel_root=source,
            output_root=output,
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            high_contrast_fallback_config=HIGH,
            source_high_contrast_config=SOURCE_HIGH,
            profile_path=PROFILE,
        )


def test_volumetric_candidate_rejects_truth_in_neutral_input_manifest(tmp_path):
    with pytest.raises(PipelineError, match="ground truth"):
        _render(tmp_path, include_truth=True)

