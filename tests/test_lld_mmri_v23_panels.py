from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from dtwin.benchmark import lld_mmri_v23_panels as module
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _prepared(tmp_path: Path, *, case_count: int = 1) -> tuple[Path, str]:
    root = tmp_path / "prepared"
    rows = []
    for index in range(case_count):
        case_id = f"anon-lld-{index:016d}"
        case = root / "inputs" / case_id
        case.mkdir(parents=True)
        files = []
        for role in ("t1_arterial", "t1_venous", "t1_delayed", "liver_mask_venous"):
            path = case / f"{role}.nii.gz"
            path.write_bytes((role + "\n").encode())
            files.append(
                {
                    "role": role,
                    "relative_path": f"{case_id}/{path.name}",
                    "bytes": path.stat().st_size,
                    "sha256": module._sha256(path),
                }
            )
        base = {
            "schema": module.INPUT_SCHEMA,
            "case_id": case_id,
            "files": files,
            "lesion_mask_present": False,
            "pathology_label_present": False,
            "ground_truth_read": False,
            "dynamic_liver_support_fraction": {
                "t1_arterial": 1.0,
                "t1_venous": 1.0,
                "t1_delayed": 0.75,
            },
        }
        row = dict(base)
        row["case_signature"] = _canonical_sha(base)
        rows.append(row)
    (root / "inputs.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (root / "summary.json").write_text(
        json.dumps({"case_ids": [row["case_id"] for row in rows]}), encoding="utf-8"
    )
    return root, rows[0]["case_id"]


def test_builds_uniform9_panels_pending_human_review(monkeypatch, tmp_path: Path):
    prepared, case_id = _prepared(tmp_path)
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_blind_inputs",
        lambda **_: {
            "protocol_case_count": 2,
            "case_count": 1,
            "technical_failure_case_count": 1,
            "technical_failure_case_ids": ["anon-lld-9999999999999999"],
            "preparation_signature": "p" * 64,
            "inputs_sha256": "i" * 64,
        },
    )
    config = {
        "panel": {"mode": "multiphase_fusion", "strategy": "uniform_9"},
        "medgemma": {"model_id": "google/medgemma-1.5-4b-it"},
    }
    monkeypatch.setattr(module, "_validate_config", lambda _: config)
    monkeypatch.setattr(module, "load_profile", lambda _: {"orgao": "figado"})
    monkeypatch.setattr(module, "model_trace", lambda _: {"model": "4b"})

    def fake_generator(**kwargs):
        assert kwargs["phase_support_fractions"] == {"art": 1.0, "pv": 1.0, "del": 0.75}
        output = kwargs["output_dir"]
        panel = output / "panel.png"
        Image.new("RGB", (96, 64), "black").save(panel)
        manifest = output / "panel_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "lesion_pre_marked": False,
                    "panel_count": 11,
                    "visible_phi_confirmed": False,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            panel_path=panel,
            panel_paths=(panel,),
            manifest_path=manifest,
        )

    monkeypatch.setattr(module, "generate_liver_panel_multiphase", fake_generator)
    config_path = tmp_path / "config.yaml"
    profile_path = tmp_path / "profile.yaml"
    config_path.write_text("config", encoding="utf-8")
    profile_path.write_text("profile", encoding="utf-8")
    output = tmp_path / "panels"
    result = module.build_lld_mmri_v23_uniform9_panels(
        protocol_root=tmp_path / "protocol",
        prepared_root=prepared,
        output_root=output,
        config_path=config_path,
        profile_path=profile_path,
    )
    assert result["schema"] == module.COHORT_SCHEMA
    assert result["case_count"] == 1
    assert result["protocol_case_count"] == 2
    assert result["technical_failure_case_count"] == 1
    assert result["technical_failures_count_as_primary_metric_errors"] is True
    assert result["case_ids"] == [case_id]
    assert result["all_panels_uniform9"] is True
    assert result["all_panels_pending_human_review"] is True
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_used"] is False
    assert result["cases"][0]["elapsed_seconds"] >= 0


def test_gallery_is_label_blind_and_immutable(monkeypatch, tmp_path: Path):
    prepared, _ = _prepared(tmp_path)
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_blind_inputs",
        lambda **_: {
            "protocol_case_count": 1,
            "case_count": 1,
            "technical_failure_case_count": 0,
            "technical_failure_case_ids": [],
            "preparation_signature": "p" * 64,
            "inputs_sha256": "i" * 64,
        },
    )
    monkeypatch.setattr(module, "_validate_config", lambda _: {"panel": {}})
    monkeypatch.setattr(module, "load_profile", lambda _: {})
    monkeypatch.setattr(module, "model_trace", lambda _: {})

    def fake_generator(**kwargs):
        case_id = kwargs["case_manifest_path"].parent.name
        panel = kwargs["output_dir"] / "panel.png"
        Image.new("RGB", (96, 64), "black").save(panel)
        manifest = kwargs["output_dir"] / "panel_manifest.json"
        manifest.write_text(json.dumps({"case_id": case_id, "lesion_pre_marked": False, "panel_count": 11, "visible_phi_confirmed": False}), encoding="utf-8")
        return SimpleNamespace(panel_path=panel, panel_paths=(panel,), manifest_path=manifest)

    monkeypatch.setattr(module, "generate_liver_panel_multiphase", fake_generator)
    config = tmp_path / "config.yaml"; config.write_text("x", encoding="utf-8")
    profile = tmp_path / "profile.yaml"; profile.write_text("x", encoding="utf-8")
    panels = tmp_path / "panels"
    module.build_lld_mmri_v23_uniform9_panels(
        protocol_root=tmp_path / "protocol", prepared_root=prepared,
        output_root=panels, config_path=config, profile_path=profile,
    )
    gallery = tmp_path / "gallery"
    result = module.build_lld_mmri_v23_uniform9_gallery(
        panel_root=panels, output_dir=gallery
    )
    assert result["schema"] == module.GALLERY_SCHEMA
    assert result["approved"] is False
    assert result["ground_truth_read"] is False
    text = (gallery / "index.html").read_text(encoding="utf-8")
    assert "Não avalie diagnóstico" in text
    assert "POSITIVE" not in text


def test_panel_generation_resumes_from_durable_case_checkpoint(
    monkeypatch, tmp_path: Path
):
    prepared, _ = _prepared(tmp_path, case_count=2)
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_blind_inputs",
        lambda **_: {
            "protocol_case_count": 2,
            "case_count": 2,
            "technical_failure_case_count": 0,
            "technical_failure_case_ids": [],
            "preparation_signature": "p" * 64,
            "inputs_sha256": "i" * 64,
        },
    )
    monkeypatch.setattr(module, "_validate_config", lambda _: {"panel": {}})
    monkeypatch.setattr(module, "load_profile", lambda _: {})
    monkeypatch.setattr(module, "model_trace", lambda _: {})
    config = tmp_path / "config.yaml"; config.write_text("x", encoding="utf-8")
    profile = tmp_path / "profile.yaml"; profile.write_text("x", encoding="utf-8")
    output = tmp_path / "panels"
    first_calls = []

    def render_or_fail(**kwargs):
        case_id = kwargs["case_manifest_path"].parent.name
        first_calls.append(case_id)
        if case_id.endswith("1"):
            raise PipelineError("synthetic interruption")
        panel = kwargs["output_dir"] / "panel.png"
        Image.new("RGB", (96, 64), "black").save(panel)
        manifest = kwargs["output_dir"] / "panel_manifest.json"
        manifest.write_text(
            json.dumps({"case_id": case_id, "lesion_pre_marked": False,
                        "panel_count": 11, "visible_phi_confirmed": False}),
            encoding="utf-8",
        )
        return SimpleNamespace(panel_path=panel, panel_paths=(panel,), manifest_path=manifest)

    monkeypatch.setattr(module, "generate_liver_panel_multiphase", render_or_fail)
    with pytest.raises(PipelineError, match="synthetic interruption"):
        module.build_lld_mmri_v23_uniform9_panels(
            protocol_root=tmp_path / "protocol", prepared_root=prepared,
            output_root=output, config_path=config, profile_path=profile,
        )
    incomplete = tmp_path / ".panels.incomplete"
    assert not output.exists()
    assert len(module._load_jsonl_checkpoint(incomplete / "checkpoint_cases.jsonl")) == 1

    resumed_calls = []

    def render_resumed(**kwargs):
        case_id = kwargs["case_manifest_path"].parent.name
        resumed_calls.append(case_id)
        panel = kwargs["output_dir"] / "panel.png"
        Image.new("RGB", (96, 64), "black").save(panel)
        manifest = kwargs["output_dir"] / "panel_manifest.json"
        manifest.write_text(
            json.dumps({"case_id": case_id, "lesion_pre_marked": False,
                        "panel_count": 11, "visible_phi_confirmed": False}),
            encoding="utf-8",
        )
        return SimpleNamespace(panel_path=panel, panel_paths=(panel,), manifest_path=manifest)

    monkeypatch.setattr(module, "generate_liver_panel_multiphase", render_resumed)
    result = module.build_lld_mmri_v23_uniform9_panels(
        protocol_root=tmp_path / "protocol", prepared_root=prepared,
        output_root=output, config_path=config, profile_path=profile,
    )
    assert result["case_count"] == 2
    assert resumed_calls == ["anon-lld-0000000000000001"]
    assert not incomplete.exists()
