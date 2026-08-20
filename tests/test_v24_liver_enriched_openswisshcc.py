from __future__ import annotations

import json

import pytest

import dtwin.benchmark.v24_liver_enriched_openswisshcc as subject
from dtwin.core import PipelineError


def test_pilot_selection_includes_all_fallbacks_and_is_deterministic():
    modes = {
        **{f"anon-aligned-{index:03d}": "registered_multiphase_rgb" for index in range(20)},
        **{f"anon-fallback-{index:03d}": "venous_replicated_grayscale" for index in range(3)},
    }
    first = subject._pilot_ids(modes)
    second = subject._pilot_ids(modes)
    assert first == second
    assert len(first) == 10
    assert set(first[:3]) == {
        "anon-fallback-000",
        "anon-fallback-001",
        "anon-fallback-002",
    }


def test_pilot_selection_rejects_too_many_fallbacks():
    modes = {
        f"anon-fallback-{index:03d}": "venous_replicated_grayscale"
        for index in range(11)
    }
    with pytest.raises(PipelineError, match="piloto v24"):
        subject._pilot_ids(modes)


def test_fallback_config_replicates_only_real_venous_phase():
    original = {
        "panel": {
            "fusion": {
                "channel_map": {"red": "art", "green": "pv", "blue": "del"},
                "partial_fov_fallback_phase": "pv",
            }
        }
    }
    result = subject._fallback_config(original)
    assert result["panel"]["fusion"]["channel_map"] == {
        "red": "pv",
        "green": "pv",
        "blue": "pv",
    }
    assert original["panel"]["fusion"]["channel_map"]["red"] == "art"


def test_modes_require_exact_eligible_partition(tmp_path):
    dev = tmp_path / "dev.json"
    hold = tmp_path / "hold.json"
    dev.write_text(
        json.dumps(
            {
                "schema": subject.DEV_MODE_SCHEMA,
                "case_count": 87,
                "cases": [
                    {
                        "case_id": f"anon-dev-{index:03d}",
                        "dynamic_alignment_mode": "registered_to_venous",
                    }
                    for index in range(87)
                ],
            }
        ),
        encoding="utf-8",
    )
    hold.write_text(
        json.dumps(
            {
                "schema": subject.HOLDOUT_ALIGNMENT_SCHEMA,
                "labels_read": False,
                "lesion_masks_read": 0,
                "alignments": [{"case_id": "anon-hold", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    eligible = {f"anon-dev-{index:03d}" for index in range(87)} | {"anon-hold"}
    result = subject._modes(
        development_mode_manifest=dev,
        holdout_alignment_summary=hold,
        eligible_ids=eligible,
    )
    assert len(result) == 88
    assert result["anon-hold"] == "registered_multiphase_rgb"


def test_modes_reject_holdout_label_leak(tmp_path):
    dev = tmp_path / "dev.json"
    hold = tmp_path / "hold.json"
    dev.write_text(
        json.dumps(
            {
                "schema": subject.DEV_MODE_SCHEMA,
                "case_count": 87,
                "cases": [
                    {
                        "case_id": f"anon-dev-{index:03d}",
                        "dynamic_alignment_mode": "registered_to_venous",
                    }
                    for index in range(87)
                ],
            }
        ),
        encoding="utf-8",
    )
    hold.write_text(
        json.dumps(
            {
                "schema": subject.HOLDOUT_ALIGNMENT_SCHEMA,
                "labels_read": True,
                "lesion_masks_read": 0,
                "alignments": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="inválido"):
        subject._modes(
            development_mode_manifest=dev,
            holdout_alignment_summary=hold,
            eligible_ids={f"anon-dev-{index:03d}" for index in range(87)},
        )


def test_verify_protocol_rejects_signature_tampering(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("x", encoding="utf-8")
    body = {
        "schema": subject.PROTOCOL_SCHEMA,
        "status": "frozen_before_v24_liver_enriched_signal_generation",
        "case_count": 132,
        "signal_eligible_case_count": 130,
        "technical_failures_carried_forward": 2,
        "source_hashes": {"config": subject._sha256(config)},
        "labels_read": False,
        "lesion_masks_read": 0,
        "metrics_calculated": False,
    }
    value = {**body, "protocol_signature": subject._canonical_sha(body)}
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(value), encoding="utf-8")
    assert subject.verify_v24_liver_enriched_protocol(
        protocol_path=protocol, config_path=config
    )["case_count"] == 132
    value["case_count"] = 131
    protocol.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="adulterado"):
        subject.verify_v24_liver_enriched_protocol(
            protocol_path=protocol, config_path=config
        )


def test_candidate_fusion_is_predeclared_fixed_80_20():
    assert subject.LIVER_ENRICHED_POLICY.endswith("2or3x9_v1")
    # The exact values are also asserted by the real frozen protocol verifier.
    assert subject.PILOT_CASE_COUNT == 10


def test_approval_is_signed_and_keeps_inference_locked(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("x", encoding="utf-8")
    protocol = {"protocol_signature": "p" * 64}
    monkeypatch.setattr(
        subject,
        "verify_v24_liver_enriched_protocol",
        lambda **_: protocol,
    )
    gallery_root = tmp_path / "gallery"
    gallery_root.mkdir()
    gallery_body = {
        "schema": subject.GALLERY_SCHEMA,
        "status": "pending_human_review",
        "pilot_signature": "q" * 64,
        "case_count": 10,
        "labels_read": False,
        "lesion_masks_read": 0,
        "inference_authorized": False,
    }
    gallery = {
        **gallery_body,
        "gallery_signature": subject._canonical_sha(gallery_body),
    }
    (gallery_root / "gallery_manifest.json").write_text(
        json.dumps(gallery), encoding="utf-8"
    )
    output = tmp_path / "review.json"
    result = subject.approve_v24_liver_enriched_gallery(
        protocol_path=tmp_path / "protocol.json",
        config_path=config,
        gallery_root=gallery_root,
        reviewer="jm",
        output_path=output,
    )
    assert result["status"] == "approved_for_full_label_blind_generation"
    assert result["inference_authorized"] is False
    assert result["labels_read"] is False
    assert result["lesion_masks_read"] == 0
    unsigned = dict(result)
    signature = unsigned.pop("review_signature")
    assert signature == subject._canonical_sha(unsigned)


def test_approval_rejects_blank_reviewer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subject,
        "verify_v24_liver_enriched_protocol",
        lambda **_: {"protocol_signature": "p" * 64},
    )
    gallery_root = tmp_path / "gallery"
    gallery_root.mkdir()
    body = {
        "schema": subject.GALLERY_SCHEMA,
        "status": "pending_human_review",
        "pilot_signature": "q" * 64,
        "case_count": 10,
        "labels_read": False,
        "lesion_masks_read": 0,
        "inference_authorized": False,
    }
    (gallery_root / "gallery_manifest.json").write_text(
        json.dumps({**body, "gallery_signature": subject._canonical_sha(body)}),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="não pode ser aprovada"):
        subject.approve_v24_liver_enriched_gallery(
            protocol_path=tmp_path / "protocol.json",
            config_path=tmp_path / "config.yaml",
            gallery_root=gallery_root,
            reviewer=" ",
            output_path=tmp_path / "review.json",
        )


def test_full_checkpoint_record_rejects_missing_panel(tmp_path):
    case = tmp_path / "anon-case"
    case.mkdir()
    manifest_body = {
        "spatial_policy": subject.LIVER_ENRICHED_POLICY,
        "organ_mask_rendered": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "crop_to_liver": False,
        "contour_rendered": False,
        "panel_image_count": 2,
    }
    manifest = case / "manifest.json"
    manifest.write_text(json.dumps(manifest_body), encoding="utf-8")
    record = {
        "case_id": "anon-case",
        "panel_count": 2,
        "manifest": "anon-case/manifest.json",
        "manifest_sha256": subject._sha256(manifest),
        "panels": [
            {
                "panel_number": 1,
                "relative_path": "anon-case/missing1.png",
                "sha256": "a" * 64,
            },
            {
                "panel_number": 2,
                "relative_path": "anon-case/missing2.png",
                "sha256": "b" * 64,
            },
        ],
    }
    with pytest.raises(PipelineError, match="Painel da coorte"):
        subject._validate_full_record(tmp_path.resolve(), record)
