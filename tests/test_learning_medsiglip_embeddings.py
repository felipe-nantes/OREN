from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_embeddings import (
    extract_embeddings,
    verify_embeddings,
)
from dtwin.learning.protocol import sha256_file


class FakeBackend:
    model_id = "fake/medsiglip"
    revision = "a" * 40
    embedding_dimension = 4
    device = "cpu"

    def embed(self, images):
        values = []
        for image in images:
            seed = float(np.asarray(image).mean()) + 1.0
            vector = np.asarray([seed, 2.0, 3.0, 4.0], dtype=np.float32)
            values.append(vector / np.linalg.norm(vector))
        return np.stack(values)

    def metadata(self):
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "embedding_dimension": self.embedding_dimension,
            "device": self.device,
        }

    def close(self):
        pass


def _fixture(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema": "argos-medsiglip-frozen-embedding-config-v1",
                "model_id": "fake/medsiglip",
                "revision": "a" * 40,
                "image_size": 448,
                "device": "cpu",
                "dtype": "float32",
                "batch_size": 2,
                "l2_normalize": True,
                "local_files_only": True,
                "research_only": True,
            }
        ),
        encoding="utf-8",
    )
    candidate_root = tmp_path / "candidates"
    candidate_root.mkdir()
    rows = []
    for index in range(3):
        image = tmp_path / f"image-{index}.png"
        Image.new("RGB", (448, 448), (index, index, index)).save(image)
        rows.append(
            {
                "case_id": f"case-{index}",
                "patient_group_id": f"case-{index}",
                "dataset_id": "dataset",
                "candidate_id": "global-panel-001",
                "candidate_kind": "global_liver_panel",
                "panel_number": 1,
                "image_path": image.relative_to(tmp_path).as_posix(),
                "image_sha256": sha256_file(image),
            }
        )
    records_path = candidate_root / "candidate_records.jsonl"
    records_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    body = {
        "dataset_signature": "dataset-signature",
        "candidate_records_sha256": sha256_file(records_path),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    (candidate_root / "dataset_manifest.json").write_text(
        json.dumps(body), encoding="utf-8"
    )
    return config, candidate_root, tmp_path / "embeddings"


def test_extract_and_verify_embeddings(tmp_path):
    config, candidates, output = _fixture(tmp_path)
    manifest = extract_embeddings(
        config_path=config,
        candidate_root=candidates,
        workspace_root=tmp_path,
        output_root=output,
        backend=FakeBackend(),
    )
    assert manifest["embedding_count"] == 3
    assert manifest["ground_truth_read"] is False
    assert manifest["lesion_masks_read"] == 0
    assert verify_embeddings(
        candidate_root=candidates, output_root=output
    ) == manifest


def test_verifier_detects_embedding_tampering(tmp_path):
    config, candidates, output = _fixture(tmp_path)
    extract_embeddings(
        config_path=config,
        candidate_root=candidates,
        workspace_root=tmp_path,
        output_root=output,
        backend=FakeBackend(),
    )
    record = json.loads(
        (output / "embedding_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    (output / record["embedding_path"]).write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="Embedding alterado"):
        verify_embeddings(candidate_root=candidates, output_root=output)


def test_config_requires_pinned_revision_and_local_files(tmp_path):
    config, candidates, output = _fixture(tmp_path)
    value = yaml.safe_load(config.read_text(encoding="utf-8"))
    value["local_files_only"] = False
    config.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="local_files_only"):
        extract_embeddings(
            config_path=config,
            candidate_root=candidates,
            workspace_root=tmp_path,
            output_root=output,
            backend=FakeBackend(),
        )
