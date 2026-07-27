from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from dtwin.benchmark import lld_mmri_v23_signals as module


def _context_sources(monkeypatch, tmp_path: Path):
    case_id = "anon-lld-0000000000000000"
    panel_root = tmp_path / "panels"
    panel = panel_root / case_id / "panel.png"
    panel.parent.mkdir(parents=True)
    panel.write_bytes(b"panel")
    med_config = tmp_path / "med.yaml"; med_config.write_text("med", encoding="utf-8")
    ms_config = tmp_path / "ms.yaml"; ms_config.write_text("ms", encoding="utf-8")
    cohort = {
        "schema": module.COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "protocol_case_count": 2,
        "case_count": 1,
        "technical_failure_case_count": 1,
        "technical_failure_case_ids": ["anon-lld-9999999999999999"],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "case_ids": [case_id],
        "cases": [{"case_id": case_id, "panel": f"{case_id}/panel.png", "panel_sha256": module._sha256(panel)}],
        "config_sha256": module._sha256(med_config),
        "preparation_signature": "p" * 64,
        "ground_truth_read": False,
        "lesion_masks_used": False,
    }
    (panel_root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_review",
        lambda **_: {"approved_case_ids": [case_id], "review_signature": "r" * 64},
    )
    monkeypatch.setattr(
        module,
        "_validate_config",
        lambda _: {"medgemma": {"model_id": "google/medgemma-1.5-4b-it", "model_parameter_scale": "4B"}},
    )
    monkeypatch.setattr(
        module,
        "load_medsiglip_config",
        lambda _: SimpleNamespace(model_id="google/medsiglip-448", decision_enabled=False),
    )
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_blind_inputs",
        lambda **_: {
            "protocol_case_count": 2,
            "case_count": 1,
            "technical_failure_case_count": 1,
            "technical_failure_case_ids": ["anon-lld-9999999999999999"],
            "preparation_signature": "p" * 64,
        },
    )
    context = module.verify_lld_mmri_v23_signal_context(
        protocol_root=tmp_path / "protocol",
        panel_root=panel_root,
        gallery_root=tmp_path / "gallery",
        review_path=tmp_path / "review.json",
        prepared_root=tmp_path / "prepared",
        medgemma_config_path=med_config,
        medsiglip_config_path=ms_config,
        expected_case_count=2,
    )
    return context, case_id


def test_signal_context_is_review_gated_and_model_exact(monkeypatch, tmp_path: Path):
    context, case_id = _context_sources(monkeypatch, tmp_path)
    assert context["case_ids"] == [case_id]
    assert context["protocol_case_count"] == 2
    assert context["technical_failure_case_count"] == 1
    assert context["review_signature"] == "r" * 64
    assert context["medgemma_case_schema"] == module.MEDGEMMA_CASE_SCHEMA
    assert context["medsiglip_case_schema"] == module.MEDSIGLIP_CASE_SCHEMA


def test_localizer_manifest_contains_only_venous_and_automatic_liver_mask(monkeypatch, tmp_path: Path):
    context, case_id = _context_sources(monkeypatch, tmp_path)
    prepared = tmp_path / "prepared"
    case = prepared / "inputs" / case_id
    case.mkdir(parents=True)
    files = []
    for role in ("t1_venous", "liver_mask_venous"):
        path = case / f"{role}.nii.gz"
        path.write_bytes(role.encode())
        files.append(
            {
                "role": role,
                "relative_path": f"{case_id}/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": module._sha256(path),
            }
        )
    (prepared / "inputs.jsonl").write_text(
        json.dumps({"schema": module.INPUT_SCHEMA, "case_id": case_id, "files": files}) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "localizer_inputs.jsonl"
    result = module.build_lld_mmri_v23_localizer_input_manifest(
        context=context,
        prepared_root=prepared,
        output_path=output,
    )
    assert result["case_count"] == 1
    assert result["protocol_case_count"] == 2
    assert result["technical_failure_case_count"] == 1
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert {item["role"] for item in row["files"]} == {"t1_venous", "liver_mask_venous"}
    assert row["lesion_mask_available"] is False
    assert "label" not in output.read_text(encoding="utf-8").lower()
