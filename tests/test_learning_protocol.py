from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.protocol import freeze_protocol, verify_protocol


def _write_labels(path: Path, *, prefix: str, count: int = 20) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(
            json.dumps(
                {
                    "case_id": f"{prefix}-{index:03d}",
                    "label": "POSITIVE" if index % 2 else "NEGATIVE",
                }
            )
            + "\n"
            for index in range(count)
        ),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path):
    labels = (
        tmp_path
        / "casos"
        / "qualification"
        / "dataset"
        / "protected_ground_truth"
        / "labels.jsonl"
    )
    _write_labels(labels, prefix="case")
    config = tmp_path / "configs" / "training" / "hybrid.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        yaml.safe_dump(
            {
                "candidate_id": "test",
                "target_condition": "focal_liver_lesion_suspicion",
                "protected_label_sources": [
                    {
                        "dataset_id": "dataset",
                        "path": labels.relative_to(tmp_path).as_posix(),
                    }
                ],
                "validation": {
                    "outer_folds": 5,
                    "inner_folds": 4,
                    "seed": 7,
                },
                "acceptance": {
                    "sensitivity_minimum": 0.75,
                    "specificity_minimum": 0.75,
                },
                "failure_policy": {
                    "technical_failure_counts_as_error": True
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return (
        labels,
        config,
        tmp_path / "configs/training/protocol.json",
        tmp_path / "configs/training/splits.json",
    )


def test_freeze_and_verify_protocol(tmp_path):
    _, config, protocol, splits = _fixture(tmp_path)
    frozen = freeze_protocol(
        config_path=config,
        workspace_root=tmp_path,
        protocol_path=protocol,
        splits_path=splits,
    )
    verified = verify_protocol(
        config_path=config,
        workspace_root=tmp_path,
        protocol_path=protocol,
        splits_path=splits,
    )
    assert verified == frozen
    assert frozen["aggregate_case_count"] == 20
    assert frozen["aggregate_label_counts"] == {
        "NEGATIVE": 10,
        "POSITIVE": 10,
    }
    assert frozen["lesion_masks_read_during_freeze"] == 0
    assert "case-000" not in protocol.read_text(encoding="utf-8")


def test_freeze_is_immutable(tmp_path):
    _, config, protocol, splits = _fixture(tmp_path)
    freeze_protocol(
        config_path=config,
        workspace_root=tmp_path,
        protocol_path=protocol,
        splits_path=splits,
    )
    with pytest.raises(PipelineError, match="imutável"):
        freeze_protocol(
            config_path=config,
            workspace_root=tmp_path,
            protocol_path=protocol,
            splits_path=splits,
        )


def test_verifier_detects_label_source_change(tmp_path):
    labels, config, protocol, splits = _fixture(tmp_path)
    freeze_protocol(
        config_path=config,
        workspace_root=tmp_path,
        protocol_path=protocol,
        splits_path=splits,
    )
    labels.write_text(
        labels.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="Fonte protegida"):
        verify_protocol(
            config_path=config,
            workspace_root=tmp_path,
            protocol_path=protocol,
            splits_path=splits,
        )


def test_source_outside_workspace_is_rejected(tmp_path):
    _, config, protocol, splits = _fixture(tmp_path)
    config_value = yaml.safe_load(config.read_text(encoding="utf-8"))
    config_value["protected_label_sources"][0]["path"] = str(
        tmp_path.parent / "outside.jsonl"
    )
    config.write_text(yaml.safe_dump(config_value), encoding="utf-8")
    with pytest.raises(PipelineError, match="workspace"):
        freeze_protocol(
            config_path=config,
            workspace_root=tmp_path,
            protocol_path=protocol,
            splits_path=splits,
        )
