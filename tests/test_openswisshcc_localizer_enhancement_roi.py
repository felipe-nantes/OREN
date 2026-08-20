import json

import nibabel as nib
import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LCASE
from dtwin.benchmark.openswisshcc_lesion_localizer import RUN_SCHEMA as LRUN
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    build_enhancement_roi_pilot,
)
from dtwin.core import PipelineError


def save(path, data):
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.uint16), np.eye(4)), path)


def fixture(tmp_path, candidate=True, zero_roles=()):
    root = tmp_path / "inputs"
    case = "anon-a"
    c = root / case
    c.mkdir(parents=True)
    files = []
    base = np.arange(32 * 32 * 16).reshape(32, 32, 16) % 1000 + 1
    for role in ("t1_native", "t1_venous", "liver_mask_venous"):
        p = c / f"{role}.nii.gz"
        if role == "liver_mask_venous":
            data = np.zeros_like(base)
            data[3:19, 5:25, 2:11] = 1
        else:
            data = np.zeros_like(base) if role in zero_roles else base
        save(p, data)
        files.append({"role": role, "relative_path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": _sha256(p)})
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(json.dumps({"schema": "argos-public-liver-mri-input-v1", "case_id": case, "files": files, "research_only": True, "clinical_use_allowed": False}))
    reg = tmp_path / "reg" / case
    reg.mkdir(parents=True)
    outputs = []
    for phase, role, name in (("art", "t1_arterial_registered", "art_registered_to_venous.nii.gz"), ("del", "t1_delayed_registered", "del_registered_to_venous.nii.gz")):
        p = reg / name
        data = np.arange(32 * 32 * 16).reshape(32, 32, 16) % 700 + 1
        save(p, np.zeros_like(data) if role in zero_roles else data)
        outputs.append({"phase": phase, "filename": name, "bytes": p.stat().st_size, "sha256": _sha256(p)})
    (reg / "alignment_manifest.json").write_text(json.dumps({"schema": "argos-public-liver-mri-alignment-v1", "case_id": case, "reference_phase": "venous", "arterial_input_role": "t1_arterial_ttc_3", "outputs": outputs, "research_only": True, "clinical_use_allowed": False}))
    run = tmp_path / "run"
    d = run / case
    raw = d / "raw_model_output"
    raw.mkdir(parents=True)
    mask = np.zeros((32, 32, 16))
    if candidate:
        mask[14:18, 14:18, 7:9] = 1
    rawmask = raw / "liver_lesions.nii.gz"
    filtered = d / "liver_lesion_candidates_in_liver.nii.gz"
    save(rawmask, mask)
    save(filtered, mask)
    (d / "localizer_manifest.json").write_text(json.dumps({"schema": LCASE, "case_id": case, "status": "candidate_scores_only_no_decision", "filtered_candidate_mask_sha256": _sha256(filtered), "ground_truth_read": False, "ground_truth_lesion_mask_used": False, "final_decision": None}))
    (run / "summary.json").write_text(json.dumps({"schema": LRUN, "status": "complete_scores_only_no_decision", "case_ids": [case], "ground_truth_read": False, "ground_truth_lesion_mask_used": False, "final_decision": None}))
    return root, manifest, tmp_path / "reg", run


def build(tmp_path, **kwargs):
    root, manifest, reg, run = fixture(tmp_path, **kwargs)
    out = tmp_path / "out"
    result = build_enhancement_roi_pilot(localizer_run=run, input_manifest=manifest, input_root=root, registration_root=reg, output_root=out)
    return root, out, result


def test_enhancement_roi_contains_four_dynamic_phases_without_ground_truth(tmp_path):
    _, out, result = build(tmp_path, candidate=True)
    manifest = json.loads((out / "anon-a" / "enhancement_roi_manifest.json").read_text())
    assert result["schema"] == COHORT_SCHEMA
    assert manifest["schema"] == CASE_SCHEMA
    assert [t["role"] for t in manifest["panels"][0]["tiles"]] == ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]
    assert manifest["ground_truth_lesion_mask_used"] is False
    assert manifest["panels"][0]["usable_phase_count"] == 4


def test_enhancement_roi_fallback_uses_liver_mask_centroid(tmp_path):
    root, out, _ = build(tmp_path, candidate=False)
    manifest = json.loads((out / "anon-a" / "enhancement_roi_manifest.json").read_text())
    panel = manifest["panels"][0]
    liver = sitk.ReadImage(str(root / "anon-a" / "liver_mask_venous.nii.gz"))
    center = np.argwhere(sitk.GetArrayFromImage(liver) > 0).mean(axis=0)[::-1]
    expected = liver.TransformContinuousIndexToPhysicalPoint(tuple(float(value) for value in center))
    assert panel["fallback_no_candidate"] is True
    assert panel["fallback_reason"] == "no_model_derived_candidate"
    assert panel["physical_center_lps_xyz"] == pytest.approx(expected)
    assert all(tile["candidate_contour_shown"] is False for tile in panel["tiles"])


def test_zero_registered_phase_is_explicitly_unavailable_not_fabricated(tmp_path):
    _, out, _ = build(tmp_path, candidate=True, zero_roles=("t1_arterial_registered",))
    manifest = json.loads((out / "anon-a" / "enhancement_roi_manifest.json").read_text())
    panel = manifest["panels"][0]
    arterial = next(tile for tile in panel["tiles"] if tile["role"] == "t1_arterial_registered")
    assert arterial["geometry_in_fov"] is True
    assert arterial["available_in_fov"] is False
    assert arterial["unavailable_reason"] == "sem_contraste_no_roi"
    assert arterial["window"] is None
    assert panel["usable_phase_count"] == 3


def test_panel_aborts_atomically_without_minimum_evidence(tmp_path):
    root, manifest, reg, run = fixture(tmp_path, candidate=True, zero_roles=("t1_native", "t1_arterial_registered", "t1_delayed_registered"))
    out = tmp_path / "out"
    with pytest.raises(PipelineError, match="evidencia minima"):
        build_enhancement_roi_pilot(localizer_run=run, input_manifest=manifest, input_root=root, registration_root=reg, output_root=out)
    assert not out.exists()
    assert not list(tmp_path.glob("._v10enhroi_*"))
