import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.liverhccseg_preparation import (
    prepare_liverhccseg_blind_inputs,
    verify_liverhccseg_blind_inputs,
)
from dtwin.core import PipelineError


def _image(path: Path, value: int, spacing=(1.0, 1.0, 2.0), origin=(0.0, 0.0, 0.0)):
    image = sitk.GetImageFromArray(np.full((4, 6, 8), value, dtype=np.int16))
    image.SetSpacing(spacing)
    image.SetOrigin(origin)
    sitk.WriteImage(image, str(path))


def _source(tmp_path: Path, *, mismatch=False, no_overlap=False):
    root = tmp_path / "source"
    subject = root / "PUBLIC-A" / "DATE"
    subject.mkdir(parents=True)
    for name in ("art_pre.nii.gz", "art.nii.gz", "art_pv.nii.gz", "art_del.nii.gz"):
        _image(
            subject / name,
            2,
            spacing=(2.0, 1.0, 2.0) if mismatch and name == "art_del.nii.gz" else (1.0, 1.0, 2.0),
            origin=(10000.0, 10000.0, 10000.0) if no_overlap and name == "art_del.nii.gz" else (0.0, 0.0, 0.0),
        )
    _image(subject / "rater1_liver.nii.gz", 1)
    _image(subject / "rater1_tumor1.nii.gz", 1)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({
        "status": "tumor_positive_registry_filtered",
        "included_subject_hashes": [hashlib.sha256(b"PUBLIC-A").hexdigest()],
        "ground_truth_available_to_inference": False,
    }), encoding="utf-8")
    return root, audit


def test_preparation_copies_only_registered_phases_and_liver_mask(tmp_path):
    root, audit = _source(tmp_path)
    out = tmp_path / "prepared"
    cohort = prepare_liverhccseg_blind_inputs(
        source_root=root, protected_selection_audit_path=audit, output_root=out,
        cohort_id="test", expected_case_count=1,
    )
    case = next(path for path in out.iterdir() if path.is_dir())
    names = sorted(path.name for path in case.iterdir())
    assert names == [
        "input_manifest.json", "liver_mask.nii.gz", "t1_arterial.nii.gz",
        "t1_delayed.nii.gz", "t1_native.nii.gz", "t1_venous.nii.gz",
    ]
    assert not any("tumor" in path.name.lower() for path in out.rglob("*"))
    assert cohort["case_count"] == 1
    assert cohort["lesion_masks_copied"] is False
    manifest = json.loads((case / "input_manifest.json").read_text("utf-8"))
    assert manifest["organ_mask_source"] == "public_manual_liver_segmentation_rater1"
    assert manifest["pathology_label_present"] is False


def test_preparation_resamples_geometry_mismatch_to_arterial_grid(tmp_path):
    root, audit = _source(tmp_path, mismatch=True)
    out = tmp_path / "prepared"
    prepare_liverhccseg_blind_inputs(
        source_root=root, protected_selection_audit_path=audit, output_root=out,
        cohort_id="test", expected_case_count=1,
    )
    case = next(path for path in out.iterdir() if path.is_dir())
    manifest = json.loads((case / "input_manifest.json").read_text("utf-8"))
    delayed = next(item for item in manifest["files"] if item["role"] == "t1_delayed")
    assert delayed["resampled_to_arterial_grid"] is True
    arterial = sitk.ReadImage(str(case / "t1_arterial.nii.gz"))
    resampled = sitk.ReadImage(str(case / "t1_delayed.nii.gz"))
    assert arterial.GetSize() == resampled.GetSize()
    assert arterial.GetSpacing() == resampled.GetSpacing()
    assert arterial.GetOrigin() == resampled.GetOrigin()
    assert arterial.GetDirection() == resampled.GetDirection()


def test_preparation_rejects_phase_without_liver_support_atomically(tmp_path):
    root, audit = _source(tmp_path, no_overlap=True)
    out = tmp_path / "prepared"
    with pytest.raises(PipelineError, match="cobre apenas"):
        prepare_liverhccseg_blind_inputs(
            source_root=root, protected_selection_audit_path=audit, output_root=out,
            cohort_id="test", expected_case_count=1,
        )
    assert not out.exists()


def test_preparation_rejects_bad_audit_and_overwrite(tmp_path):
    root, audit = _source(tmp_path)
    payload = json.loads(audit.read_text("utf-8"))
    payload["ground_truth_available_to_inference"] = True
    audit.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="isolamento"):
        prepare_liverhccseg_blind_inputs(
            source_root=root, protected_selection_audit_path=audit,
            output_root=tmp_path / "bad", cohort_id="test", expected_case_count=1,
        )

    payload["ground_truth_available_to_inference"] = False
    audit.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "prepared"
    prepare_liverhccseg_blind_inputs(
        source_root=root, protected_selection_audit_path=audit, output_root=out,
        cohort_id="test", expected_case_count=1,
    )
    with pytest.raises(PipelineError, match="sobrescrever"):
        prepare_liverhccseg_blind_inputs(
            source_root=root, protected_selection_audit_path=audit, output_root=out,
            cohort_id="test", expected_case_count=1,
        )


def test_preflight_verifies_complete_prepared_bundle(tmp_path):
    root, audit = _source(tmp_path, mismatch=True)
    out = tmp_path / "prepared"
    cohort = prepare_liverhccseg_blind_inputs(
        source_root=root, protected_selection_audit_path=audit, output_root=out,
        cohort_id="test", expected_case_count=1,
    )
    result = verify_liverhccseg_blind_inputs(
        prepared_root=out,
        expected_cohort_signature=cohort["cohort_signature"],
        expected_case_count=1,
    )
    assert result["status"] == "ready_for_blind_panel_generation"
    assert result["lesion_masks_present"] is False


def test_preflight_rejects_tampered_phase(tmp_path):
    root, audit = _source(tmp_path)
    out = tmp_path / "prepared"
    prepare_liverhccseg_blind_inputs(
        source_root=root, protected_selection_audit_path=audit, output_root=out,
        cohort_id="test", expected_case_count=1,
    )
    case = next(path for path in out.iterdir() if path.is_dir())
    (case / "t1_venous.nii.gz").write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="ausente ou alterado"):
        verify_liverhccseg_blind_inputs(prepared_root=out, expected_case_count=1)
