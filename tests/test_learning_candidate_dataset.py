from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import (
    build_candidate_dataset,
    verify_candidate_dataset,
)
from dtwin.learning.protocol import atomic_write_json, canonical_sha256, sha256_file
from dtwin.learning.schemas import PROTOCOL_SCHEMA
from dtwin.learning.splits import build_nested_splits
from dtwin.learning.schemas import ProtectedTrainingCase


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, unsafe: bool = False):
    cases = [
        ProtectedTrainingCase(
            case_id=f"case-{index:02d}",
            patient_group_id=f"patient-{index:02d}",
            dataset_id="dataset",
            label="POSITIVE" if index % 2 else "NEGATIVE",
        )
        for index in range(10)
    ]
    splits = build_nested_splits(
        cases, outer_folds=5, inner_folds=2, seed=1
    )
    splits_path = tmp_path / "configs/training/splits.json"
    atomic_write_json(splits_path, splits)
    protocol_body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_supervised_feature_extraction",
        "splits_sha256": sha256_file(splits_path),
        "labels_excluded_from_feature_artifacts": True,
    }
    protocol = {
        **protocol_body,
        "protocol_signature": canonical_sha256(protocol_body),
    }
    protocol_path = tmp_path / "configs/training/protocol.json"
    atomic_write_json(protocol_path, protocol)

    source_root = tmp_path / "casos/qualification/source"
    case_ids = [case.case_id for case in cases[:-1]]
    for case_id in case_ids:
        case_root = source_root / case_id
        case_root.mkdir(parents=True)
        (case_root / "case_manifest.json").write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    **({"label": "POSITIVE"} if unsafe else {}),
                }
            ),
            encoding="utf-8",
        )
        panels = []
        for number in (1, 2, 3):
            image = case_root / f"panel_{number}.png"
            image.write_bytes(f"{case_id}:{number}".encode())
            panels.append(
                {
                    "panel_number": number,
                    "panel_total": 3,
                    "image": image.name,
                    "sha256": _sha(image),
                    "axial_indices_zyx_absolute": [number],
                }
            )
        (case_root / "medgemma_liver_screening_manifest.json").write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "organ": "liver",
                    "regulatory_mode": "RESEARCH",
                    "lesion_mask_used": False,
                    "ground_truth_used": False,
                    "contour_rendered": False,
                    "phi_metadata_removed": True,
                    "requires_human_review": True,
                    "panels": panels,
                }
            ),
            encoding="utf-8",
        )
    (source_root / "cohort_manifest.json").write_text(
        json.dumps({"case_ids": case_ids}), encoding="utf-8"
    )
    config_path = tmp_path / "configs/training/candidates.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "dataset_id": "dataset",
                        "root": source_root.relative_to(tmp_path).as_posix(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return config_path, protocol_path, splits_path, tmp_path / "output"


def test_build_and_verify_label_blind_candidate_dataset(tmp_path):
    config, protocol, splits, output = _fixture(tmp_path)
    manifest = build_candidate_dataset(
        config_path=config,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    assert manifest["materialized_case_count"] == 9
    assert manifest["technical_failure_count"] == 1
    assert manifest["candidate_record_count"] == 27
    assert manifest["ground_truth_read"] is False
    assert manifest["lesion_masks_read"] == 0
    assert verify_candidate_dataset(
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    ) == manifest


def test_builder_rejects_protected_field_in_case_manifest(tmp_path):
    config, protocol, splits, output = _fixture(tmp_path, unsafe=True)
    with pytest.raises(PipelineError, match="campos protegidos"):
        build_candidate_dataset(
            config_path=config,
            protocol_path=protocol,
            splits_path=splits,
            workspace_root=tmp_path,
            output_root=output,
        )


def test_verifier_detects_image_tampering(tmp_path):
    config, protocol, splits, output = _fixture(tmp_path)
    build_candidate_dataset(
        config_path=config,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    record = json.loads(
        (output / "candidate_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    (tmp_path / record["image_path"]).write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="Imagem alterada"):
        verify_candidate_dataset(
            protocol_path=protocol,
            splits_path=splits,
            workspace_root=tmp_path,
            output_root=output,
        )


def test_output_is_immutable(tmp_path):
    config, protocol, splits, output = _fixture(tmp_path)
    build_candidate_dataset(
        config_path=config,
        protocol_path=protocol,
        splits_path=splits,
        workspace_root=tmp_path,
        output_root=output,
    )
    with pytest.raises(PipelineError, match="imutável"):
        build_candidate_dataset(
            config_path=config,
            protocol_path=protocol,
            splits_path=splits,
            workspace_root=tmp_path,
            output_root=output,
        )
