from __future__ import annotations

import csv
import gzip
import json
import zipfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning.external_bundle_evaluation import _metrics
from dtwin.learning.monophase_external_failure_audit import (
    build_monophase_external_failure_audit,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Path]:
    prediction_root = tmp_path / "predictions"
    predictions = [
        {"case_id": "dev-pos", "prediction": "NEGATIVE", "technical_failure": False, "score": 0.2, "threshold": 0.5},
        {"case_id": "dev-neg", "prediction": "NEGATIVE", "technical_failure": False, "score": 0.1, "threshold": 0.5},
        {"case_id": "hold-pos", "prediction": "NEGATIVE", "technical_failure": False, "score": 0.3, "threshold": 0.5},
        {"case_id": "hold-neg", "prediction": "POSITIVE", "technical_failure": False, "score": 0.8, "threshold": 0.5},
    ]
    _jsonl(prediction_root / "predictions.jsonl", predictions)
    freeze_body = {
        "predictions_sha256": sha256_file(prediction_root / "predictions.jsonl"),
        "case_count": 4,
    }
    _json(
        prediction_root / "prediction_freeze.json",
        {**freeze_body, "prediction_signature": canonical_sha256(freeze_body)},
    )
    labels = {"dev-pos": "POSITIVE", "dev-neg": "NEGATIVE", "hold-pos": "POSITIVE", "hold-neg": "NEGATIVE"}
    evaluation_body = {
        "prediction_signature": canonical_sha256(freeze_body),
        "overall": _metrics(predictions, labels),
    }
    evaluation = tmp_path / "evaluation.json"
    _json(evaluation, {**evaluation_body, "evaluation_signature": canonical_sha256(evaluation_body)})
    dev_labels = tmp_path / "dev_labels.jsonl"
    hold_labels = tmp_path / "hold_labels.jsonl"
    _jsonl(dev_labels, [{"case_id": "dev-pos", "label": "POSITIVE"}, {"case_id": "dev-neg", "label": "NEGATIVE"}])
    _jsonl(hold_labels, [{"case_id": "hold-pos", "label": "POSITIVE"}, {"case_id": "hold-neg", "label": "NEGATIVE"}])
    candidates = tmp_path / "candidate_records.jsonl"
    _jsonl(candidates, [{"case_id": "dev-pos", "dataset_id": "openswisshcc", "slice_indices": [2]}])
    protocol = tmp_path / "audit_protocol.json"
    member = "derivatives/manual_lesion_annotations/dev-pos/venous-L1_seg.nii.gz"
    _json(protocol, {"safety": {"holdout_opened": False}, "cases": [{"case_id": "dev-pos", "venous_masks": [{"lesion_id": "L1", "archive_member": member}]}]})
    archive = tmp_path / "derivatives.zip"
    mask = np.zeros((4, 4, 5), dtype=np.uint8)
    mask[1:3, 1:3, 2] = 1
    payload = gzip.compress(nib.Nifti1Image(mask, np.eye(4)).to_bytes())
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(member, payload)
    localizer = tmp_path / "case_localization.csv"
    with localizer.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "stack_visibility_case_hit"])
        writer.writeheader()
        writer.writerow({"case_id": "dev-pos", "stack_visibility_case_hit": "True"})
    return {
        "prediction_root": prediction_root,
        "evaluation_path": evaluation,
        "development_labels_path": dev_labels,
        "holdout_labels_path": hold_labels,
        "candidate_records_path": candidates,
        "development_audit_protocol_path": protocol,
        "development_lesion_archive_path": archive,
        "development_localizer_csv_path": localizer,
        "output_root": tmp_path / "output",
    }


def test_audit_reproduces_baseline_and_keeps_holdout_masks_closed(tmp_path):
    args = _fixture(tmp_path)
    result = build_monophase_external_failure_audit(**args)

    assert result["baseline"]["fn"] == 2
    assert result["failure_causes"] == {
        "holdout_mask_closed": 1,
        "lesion_on_rendered_plane_but_classifier_negative": 1,
    }
    assert result["holdout_lesion_masks_opened"] is False
    rows = [json.loads(line) for line in (args["output_root"] / "false_negative_cases.jsonl").read_text().splitlines()]
    development = next(row for row in rows if row["case_id"] == "dev-pos")
    holdout = next(row for row in rows if row["case_id"] == "hold-pos")
    assert development["visibility"]["represented_lesion_voxel_fraction"] == 1.0
    assert holdout["mask_audit_status"] == "not_opened_holdout_mask_closed"


def test_audit_refuses_modified_prediction_freeze(tmp_path):
    args = _fixture(tmp_path)
    freeze_path = args["prediction_root"] / "prediction_freeze.json"
    freeze = json.loads(freeze_path.read_text())
    freeze["case_count"] = 99
    _json(freeze_path, freeze)

    with pytest.raises(PipelineError, match="Assinatura"):
        build_monophase_external_failure_audit(**args)

