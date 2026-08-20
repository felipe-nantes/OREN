import json

import nibabel as nib
import numpy as np

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LCASE
from dtwin.benchmark.openswisshcc_lesion_localizer import RUN_SCHEMA as LRUN
from dtwin.benchmark.openswisshcc_localizer_roi import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    build_roi_pilot,
)


def save(path, data):
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.uint16), np.eye(4)), path)


def fixture(tmp_path, candidate=True):
    root = tmp_path / "inputs"
    case = "anon-a"
    c = root / case
    c.mkdir(parents=True)
    files = []
    roles = ["t1_venous", "t2_blade", "dwi_trace_run_03", "dwi_adc", "liver_mask_venous"]
    for role in roles:
        data = np.arange(32 * 32 * 16).reshape(32, 32, 16) % 1000 + 1
        if role == "liver_mask_venous":
            data = np.zeros((32, 32, 16))
            data[4:28, 4:28, 2:14] = 1
        p = c / f"{role}.nii.gz"
        save(p, data)
        files.append({"role": role, "relative_path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": _sha256(p)})
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(json.dumps({"schema": "argos-public-liver-mri-input-v1", "case_id": case, "files": files, "research_only": True, "clinical_use_allowed": False}))
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
    lm = {"schema": LCASE, "case_id": case, "status": "candidate_scores_only_no_decision", "filtered_candidate_mask_sha256": _sha256(filtered), "ground_truth_read": False, "ground_truth_lesion_mask_used": False, "final_decision": None}
    (d / "localizer_manifest.json").write_text(json.dumps(lm))
    summary = {"schema": LRUN, "status": "complete_scores_only_no_decision", "case_ids": [case], "ground_truth_read": False, "ground_truth_lesion_mask_used": False, "final_decision": None}
    (run / "summary.json").write_text(json.dumps(summary))
    return root, manifest, run


def test_roi_gallery_uses_model_candidate_without_ground_truth(tmp_path):
    root, manifest, run = fixture(tmp_path, True)
    out = tmp_path / "roi"
    result = build_roi_pilot(localizer_run=run, input_manifest=manifest, input_root=root, output_root=out)
    case_manifest = json.loads((out / "anon-a" / "roi_manifest.json").read_text())
    assert result["schema"] == COHORT_SCHEMA
    assert case_manifest["schema"] == CASE_SCHEMA
    assert case_manifest["ground_truth_lesion_mask_used"] is False
    assert case_manifest["panels"][0]["tiles"][0]["candidate_contour_shown"] is True
    assert (out / "index.html").is_file()


def test_no_candidate_generates_explicit_fallback_panel(tmp_path):
    root, manifest, run = fixture(tmp_path, False)
    out = tmp_path / "roi"
    build_roi_pilot(localizer_run=run, input_manifest=manifest, input_root=root, output_root=out)
    case_manifest = json.loads((out / "anon-a" / "roi_manifest.json").read_text())
    panel = case_manifest["panels"][0]
    assert case_manifest["panel_count"] == 1
    assert panel["fallback_no_candidate"] is True
    assert panel["fallback_reason"] == "no_model_derived_candidate"
    assert all(tile["candidate_contour_shown"] is False for tile in panel["tiles"])
