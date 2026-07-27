import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_volumetric_batch import COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_volumetric_gallery import (
    build_volumetric_review_gallery,
)
from dtwin.core import PipelineError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def _cohort(tmp_path: Path) -> Path:
    root = tmp_path / "panels"
    cases = []
    for case_id in ("anon-a", "anon-b"):
        case = root / case_id
        case.mkdir(parents=True)
        panels = []
        for number in (1, 2):
            image = case / f"panel-{number}.png"
            image.write_bytes(f"{case_id}-{number}".encode())
            panels.append({
                "panel_number": number,
                "panel_total": 2,
                "image": image.name,
                "sha256": _sha(image),
                "bytes": image.stat().st_size,
                "axial_interval": [number, number],
            })
        candidate = {
            "case_id": case_id,
            "candidate_kind": "multiphase_rgb",
            "candidate_signature": f"signature-{case_id}",
            "panel_set_sha256": _canonical(panels),
            "panel_image_count": 2,
            "panels": panels,
            "coverage": {
                "gate_passed": True,
                "total_liver_voxels": 10,
                "covered_liver_voxels": 10,
            },
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "eligible_for_inference": False,
        }
        (case / "candidate_manifest.json").write_text(json.dumps(candidate), encoding="utf-8")
        cases.append({
            "case_id": case_id,
            "candidate_signature": candidate["candidate_signature"],
        })
    cohort = {
        "schema": COHORT_SCHEMA,
        "case_count": 2,
        "cases": cases,
        "cohort_signature": "cohort-signature",
        "ground_truth_read": False,
        "inference_executed": False,
    }
    (root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    return root


def test_gallery_lists_and_signs_every_panel_without_approval(tmp_path):
    root = _cohort(tmp_path)
    output = tmp_path / "gallery"
    result = build_volumetric_review_gallery(
        panel_root=root, output_dir=output, expected_case_count=2
    )
    assert result["case_count"] == 2
    assert result["panel_image_count"] == 4
    assert result["authoritative_approval"] is False
    assert result["ground_truth_read"] is False
    page = (output / "index.html").read_text(encoding="utf-8")
    for case_id in ("anon-a", "anon-b"):
        assert case_id in page
    assert page.count('loading="lazy"') == 4


def test_gallery_rejects_tampered_nonpreview_panel(tmp_path):
    root = _cohort(tmp_path)
    (root / "anon-a" / "panel-2.png").write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="divergente"):
        build_volumetric_review_gallery(
            panel_root=root,
            output_dir=tmp_path / "gallery",
            expected_case_count=2,
        )

