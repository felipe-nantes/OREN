from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import lld_mmri_v23_technical_amendment as module
from dtwin.core import PipelineError


def _audit(tmp_path: Path, monkeypatch, *, venous: float = 1.0) -> Path:
    root = tmp_path / "audit"
    root.mkdir()
    rows = [
        {
            "case_id": "anon-lld-0000000000000000",
            "segmentation_status": "valid_liver_mask",
            "dynamic_liver_support_fraction": {
                "t1_native": 1.0,
                "t1_arterial": 1.0,
                "t1_venous": venous,
                "t1_delayed": 0.45,
            },
        },
        {
            "case_id": "anon-lld-0000000000000001",
            "segmentation_status": "valid_liver_mask",
            "dynamic_liver_support_fraction": {
                "t1_native": 1.0,
                "t1_arterial": 0.98,
                "t1_venous": 1.0,
                "t1_delayed": 1.0,
            },
        },
    ]
    (root / "cases.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_segmentation_pilot",
        lambda **_: {
            "protocol_signature": "p" * 64,
            "pilot_signature": "s" * 64,
            "case_count": 2,
            "case_ids": [row["case_id"] for row in rows],
            "selection": "first_n_frozen_protocol_order_no_labels",
            "segmentation_technical_failure_case_count": 0,
        },
    )
    return root


def test_freezes_partial_fov_policy_before_predictions(monkeypatch, tmp_path: Path):
    audit = _audit(tmp_path, monkeypatch)
    output = tmp_path / "amendment"
    result = module.freeze_lld_mmri_v23_technical_amendment(
        protocol_root=tmp_path / "protocol",
        download_root=tmp_path / "download",
        failed_audit_root=tmp_path / "failed",
        harmonization_root=tmp_path / "harmonized",
        segmentation_audit_root=audit,
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        output_root=output,
    )
    assert result["schema"] == module.AMENDMENT_SCHEMA
    assert result["support_distribution"]["t1_delayed"]["minimum"] == 0.45
    assert result["support_distribution"]["t1_delayed"]["counts_below"]["0.5"] == 1
    assert result["policy"]["missing_dynamic_pixels_imputed"] is False
    assert result["policy"]["partial_fov_cases_excluded_from_primary_metrics"] is False
    assert result["valid_segmentation_case_count"] == 2
    assert result["technical_failures"]["case_count"] == 0
    assert result["support_distribution"]["t1_venous"]["evaluated_valid_mask_count"] == 2
    assert result["ground_truth_read"] is False
    assert result["predictions_present"] is False
    assert (output / "amendment.json").is_file()
    verified = module.verify_lld_mmri_v23_technical_amendment(
        protocol_root=tmp_path / "protocol",
        download_root=tmp_path / "download",
        failed_audit_root=tmp_path / "failed",
        harmonization_root=tmp_path / "harmonized",
        segmentation_audit_root=audit,
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        amendment_root=output,
        expected_amendment_signature=result["amendment_signature"],
    )
    assert verified == result

    tampered = json.loads((output / "amendment.json").read_text(encoding="utf-8"))
    tampered["policy"]["partial_fov_cases_excluded_from_primary_metrics"] = True
    (output / "amendment.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura"):
        module.verify_lld_mmri_v23_technical_amendment(
            protocol_root=tmp_path / "protocol",
            download_root=tmp_path / "download",
            failed_audit_root=tmp_path / "failed",
            harmonization_root=tmp_path / "harmonized",
            segmentation_audit_root=audit,
            config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
            profile_path=Path("profiles/figado.yaml"),
            amendment_root=output,
        )


def test_amendment_rejects_incomplete_venous_reference(monkeypatch, tmp_path: Path):
    audit = _audit(tmp_path, monkeypatch, venous=0.99)
    with pytest.raises(PipelineError, match="venosa com cobertura integral"):
        module.freeze_lld_mmri_v23_technical_amendment(
            protocol_root=tmp_path / "protocol",
            download_root=tmp_path / "download",
            failed_audit_root=tmp_path / "failed",
            harmonization_root=tmp_path / "harmonized",
            segmentation_audit_root=audit,
            config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
            profile_path=Path("profiles/figado.yaml"),
            output_root=tmp_path / "amendment",
        )


def test_amendment_binds_technical_failures_without_treating_them_as_support(
    monkeypatch, tmp_path: Path
):
    audit = _audit(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()]
    rows[1] = {
        "case_id": rows[1]["case_id"],
        "segmentation_status": "technical_failure_no_valid_liver_mask",
        "dynamic_liver_support_fraction": None,
        "minimum_dynamic_liver_support_fraction": None,
        "mask_sha256": None,
        "segmentation_selected_attempt": None,
        "technical_failure_counts_as_error": True,
        "liver_voxels": 0,
    }
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_segmentation_pilot",
        lambda **_: {
            "protocol_signature": "p" * 64,
            "pilot_signature": "s" * 64,
            "case_count": 2,
            "case_ids": [row["case_id"] for row in rows],
            "selection": "first_n_frozen_protocol_order_no_labels",
            "segmentation_technical_failure_case_count": 1,
        },
    )
    result = module.freeze_lld_mmri_v23_technical_amendment(
        protocol_root=tmp_path / "protocol",
        download_root=tmp_path / "download",
        failed_audit_root=tmp_path / "failed",
        harmonization_root=tmp_path / "harmonized",
        segmentation_audit_root=audit,
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        output_root=tmp_path / "amendment",
    )
    assert result["valid_segmentation_case_count"] == 1
    assert result["technical_failures"] == {
        "case_count": 1,
        "case_ids": ["anon-lld-0000000000000001"],
        "excluded_from_inference": True,
        "count_as_primary_metric_errors": True,
        "mask_fabrication_allowed": False,
    }
    assert result["support_distribution"]["t1_venous"]["evaluated_valid_mask_count"] == 1


def test_amendment_rejects_failure_with_fabricated_mask_evidence(
    monkeypatch, tmp_path: Path
):
    audit = _audit(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()]
    rows[1].update(
        segmentation_status="technical_failure_no_valid_liver_mask",
        dynamic_liver_support_fraction=None,
        minimum_dynamic_liver_support_fraction=None,
        mask_sha256="f" * 64,
        segmentation_selected_attempt=None,
        technical_failure_counts_as_error=True,
        liver_voxels=0,
    )
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="evidencia de mascara"):
        module.freeze_lld_mmri_v23_technical_amendment(
            protocol_root=tmp_path / "protocol",
            download_root=tmp_path / "download",
            failed_audit_root=tmp_path / "failed",
            harmonization_root=tmp_path / "harmonized",
            segmentation_audit_root=audit,
            config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
            profile_path=Path("profiles/figado.yaml"),
            output_root=tmp_path / "amendment",
        )
