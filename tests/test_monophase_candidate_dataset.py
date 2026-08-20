from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import (
    build_candidate_dataset,
    verify_candidate_dataset,
)
from dtwin.learning.monophase_candidate_dataset import (
    derive_monophase_candidate_dataset,
)
from dtwin.learning.protocol import atomic_write_json, canonical_sha256, sha256_file
from dtwin.learning.schemas import PROTOCOL_SCHEMA, ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits


def _fixture(tmp_path: Path):
    cases = [
        ProtectedTrainingCase(
            case_id=f"case-{index:02d}",
            patient_group_id=f"patient-{index:02d}",
            dataset_id="dataset",
            label="POSITIVE" if index % 2 else "NEGATIVE",
        )
        for index in range(10)
    ]
    splits = build_nested_splits(cases, outer_folds=5, inner_folds=2, seed=7)
    splits_path = tmp_path / "configs/training/splits.json"
    atomic_write_json(splits_path, splits)
    protocol_body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_supervised_feature_extraction",
        "splits_sha256": sha256_file(splits_path),
        "labels_excluded_from_feature_artifacts": True,
    }
    protocol_path = tmp_path / "configs/training/protocol.json"
    atomic_write_json(
        protocol_path,
        {**protocol_body, "protocol_signature": canonical_sha256(protocol_body)},
    )
    source_root = tmp_path / "casos/qualification/source"
    for case in cases[:-1]:
        case_root = source_root / case.case_id
        case_root.mkdir(parents=True)
        (case_root / "case_manifest.json").write_text(
            json.dumps({"case_id": case.case_id}), encoding="utf-8"
        )
        panel_rows = []
        for number in (1, 2, 3):
            image_path = case_root / f"panel_{number}.png"
            Image.new("RGB", (8, 8), (10 + number, 80 + number, 180 + number)).save(image_path)
            panel_rows.append(
                {
                    "panel_number": number,
                    "panel_total": 3,
                    "image": image_path.name,
                    "sha256": sha256_file(image_path),
                    "axial_indices_zyx_absolute": [number],
                }
            )
        (case_root / "medgemma_liver_screening_manifest.json").write_text(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "organ": "liver",
                    "regulatory_mode": "RESEARCH",
                    "fusion_channel_map": {"red": "art", "green": "pv", "blue": "del"},
                    "lesion_mask_used": False,
                    "ground_truth_used": False,
                    "contour_rendered": False,
                    "phi_metadata_removed": True,
                    "requires_human_review": True,
                    "panels": panel_rows,
                }
            ),
            encoding="utf-8",
        )
    (source_root / "cohort_manifest.json").write_text(
        json.dumps({"case_ids": [case.case_id for case in cases[:-1]]}), encoding="utf-8"
    )
    source_config = tmp_path / "configs/training/source.yaml"
    source_config.write_text(
        yaml.safe_dump(
            {"sources": [{"dataset_id": "dataset", "root": source_root.relative_to(tmp_path).as_posix()}]}
        ),
        encoding="utf-8",
    )
    source_candidates = tmp_path / "source_candidates"
    build_candidate_dataset(
        config_path=source_config,
        protocol_path=protocol_path,
        splits_path=splits_path,
        workspace_root=tmp_path,
        output_root=source_candidates,
    )
    mono_config = tmp_path / "configs/training/mono.yaml"
    mono_config.write_text(
        yaml.safe_dump(
            {
                "schema": "oren-medsiglip-monophase-representation-config-v1",
                "source_rgb_channel": "green",
                "expected_source_phase_key": "pv",
                "output_phase_name": "single_phase_portal_venous_grayscale",
                "replicate_source_across_rgb": True,
                "dynamic_enhancement_information_present": False,
                "ground_truth_allowed_during_derivation": False,
            }
        ),
        encoding="utf-8",
    )
    return mono_config, source_candidates, protocol_path, splits_path


def test_derives_exact_grayscale_green_channel_and_verifies(tmp_path):
    config, source, protocol, splits = _fixture(tmp_path)
    output = tmp_path / "mono_candidates"
    manifest = derive_monophase_candidate_dataset(
        config_path=config,
        source_candidate_root=source,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    assert manifest["candidate_record_count"] == 27
    assert manifest["technical_failure_count"] == 1
    assert manifest["ground_truth_read"] is False
    assert manifest["lesion_masks_read"] == 0
    record = json.loads((output / "candidate_records.jsonl").read_text(encoding="utf-8").splitlines()[0])
    with Image.open(tmp_path / record["source_image_path"]) as source_image:
        source_green = source_image.convert("RGB").getchannel("G")
    with Image.open(tmp_path / record["image_path"]) as derived:
        red, green, blue = derived.convert("RGB").split()
    assert red.tobytes() == source_green.tobytes()
    assert red.tobytes() == green.tobytes() == blue.tobytes()
    assert verify_candidate_dataset(
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    ) == manifest


def test_rejects_wrong_declared_source_phase(tmp_path):
    config, source, protocol, splits = _fixture(tmp_path)
    value = yaml.safe_load(config.read_text(encoding="utf-8"))
    value["expected_source_phase_key"] = "art"
    config.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="não representa"):
        derive_monophase_candidate_dataset(
            config_path=config,
            source_candidate_root=source,
            protocol_path=protocol,
            splits_path=splits,
            workspace_root=tmp_path,
            output_root=tmp_path / "mono_candidates",
        )


def test_missing_phase_becomes_case_level_technical_failure_when_configured(tmp_path):
    config, source, protocol, splits = _fixture(tmp_path)
    value = yaml.safe_load(config.read_text(encoding="utf-8"))
    value.update(
        source_rgb_channel="red",
        expected_source_phase_key="art",
        resolve_source_phase_by_manifest=True,
        missing_expected_phase_policy="technical_failure",
    )
    config.write_text(yaml.safe_dump(value), encoding="utf-8")

    source_record = json.loads(
        (source / "candidate_records.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    missing_case = source_record["case_id"]
    case_records = [
        json.loads(line)
        for line in (source / "candidate_records.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["case_id"] == missing_case
    ]
    manifest_path = tmp_path / case_records[0]["source_manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["fusion_channel_map"] = {"red": "pv", "green": "pv", "blue": "pv"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    new_hash = sha256_file(manifest_path)
    all_records = [
        json.loads(line)
        for line in (source / "candidate_records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for record in all_records:
        if record["case_id"] == missing_case:
            record["source_manifest_sha256"] = new_hash
    records_path = source / "candidate_records.jsonl"
    with records_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in all_records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    source_manifest_path = source / "dataset_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest["candidate_records_sha256"] = sha256_file(records_path)
    source_body = {key: val for key, val in source_manifest.items() if key != "dataset_signature"}
    source_manifest = {**source_body, "dataset_signature": canonical_sha256(source_body)}
    source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")

    output = tmp_path / "mono_candidates"
    result = derive_monophase_candidate_dataset(
        config_path=config,
        source_candidate_root=source,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    assert result["missing_expected_phase_case_count"] == 1
    assert result["materialized_case_count"] == 8
    assert result["technical_failure_count"] == 2
    rows = (output / "candidate_records.jsonl").read_text(encoding="utf-8")
    assert missing_case not in rows
    failures = (output / "technical_failures.jsonl").read_text(encoding="utf-8")
    assert f"expected_source_phase_unavailable:art" in failures


def test_output_is_immutable(tmp_path):
    config, source, protocol, splits = _fixture(tmp_path)
    output = tmp_path / "mono_candidates"
    kwargs = dict(
        config_path=config,
        source_candidate_root=source,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    derive_monophase_candidate_dataset(**kwargs)
    with pytest.raises(PipelineError, match="imutável"):
        derive_monophase_candidate_dataset(**kwargs)
