from __future__ import annotations

import json

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning.filter_embedding_dataset import (
    filter_candidate_embedding_dataset,
    rebind_embedding_dataset,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path):
    candidates = tmp_path / "candidates"
    embeddings = tmp_path / "embeddings"
    candidates.mkdir()
    embeddings.mkdir()
    rows = [
        {"case_id": "a", "candidate_id": "a-t2", "sequence_role": "t2_haste"},
        {"case_id": "a", "candidate_id": "a-adc", "sequence_role": "dwi_adc"},
        {"case_id": "b", "candidate_id": "b-t2", "sequence_role": "t2_haste"},
    ]
    candidate_records = candidates / "candidate_records.jsonl"
    candidate_records.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    candidate_body = {
        "schema": "source-v1",
        "candidate_records_sha256": sha256_file(candidate_records),
        "ground_truth_read": False,
    }
    _json(
        candidates / "dataset_manifest.json",
        {**candidate_body, "dataset_signature": canonical_sha256(candidate_body)},
    )
    embedding_rows = []
    for index, row in enumerate(rows):
        relative = f"vectors/{index}.npy"
        target = embeddings / relative
        target.parent.mkdir(exist_ok=True)
        np.save(target, np.asarray([index, index + 1], dtype=np.float32))
        embedding_rows.append(
            {
                **row,
                "embedding_path": relative,
                "embedding_sha256": sha256_file(target),
                "label_attached": False,
            }
        )
    embedding_records = embeddings / "embedding_records.jsonl"
    embedding_records.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in embedding_rows),
        encoding="utf-8",
    )
    embedding_body = {
        "schema": "embedding-v1",
        "config_sha256": "a" * 64,
        "candidate_dataset_signature": canonical_sha256(candidate_body),
        "embedding_records_sha256": sha256_file(embedding_records),
        "backend": "test",
    }
    _json(
        embeddings / "embedding_manifest.json",
        {**embedding_body, "embedding_signature": canonical_sha256(embedding_body)},
    )
    return candidates, embeddings


def test_filter_materializes_exact_hash_bound_subset(tmp_path):
    candidates, embeddings = _fixture(tmp_path)
    out_candidates = tmp_path / "out-candidates"
    out_embeddings = tmp_path / "out-embeddings"
    result = filter_candidate_embedding_dataset(
        candidate_root=candidates,
        embedding_root=embeddings,
        sequence_role="t2_haste",
        output_candidate_root=out_candidates,
        output_embedding_root=out_embeddings,
    )
    assert result["candidate_count"] == 2
    assert result["case_count"] == 2
    candidate_rows = [
        json.loads(line)
        for line in (out_candidates / "candidate_records.jsonl").read_text().splitlines()
    ]
    assert {row["sequence_role"] for row in candidate_rows} == {"t2_haste"}
    assert len(list((out_embeddings / "vectors").glob("*.npy"))) == 2


def test_filter_rejects_tampered_candidate_manifest(tmp_path):
    candidates, embeddings = _fixture(tmp_path)
    manifest = json.loads((candidates / "dataset_manifest.json").read_text())
    manifest["ground_truth_read"] = True
    _json(candidates / "dataset_manifest.json", manifest)
    with pytest.raises(PipelineError, match="Assinatura da origem de candidatos"):
        filter_candidate_embedding_dataset(
            candidate_root=candidates,
            embedding_root=embeddings,
            sequence_role="t2_haste",
            output_candidate_root=tmp_path / "out-candidates",
            output_embedding_root=tmp_path / "out-embeddings",
        )


def test_filter_rejects_tampered_embedding_file_without_partial_publish(tmp_path):
    candidates, embeddings = _fixture(tmp_path)
    np.save(embeddings / "vectors/0.npy", np.asarray([99], dtype=np.float32))
    out_candidates = tmp_path / "out-candidates"
    out_embeddings = tmp_path / "out-embeddings"
    with pytest.raises(PipelineError, match="Arquivo de embedding"):
        filter_candidate_embedding_dataset(
            candidate_root=candidates,
            embedding_root=embeddings,
            sequence_role="t2_haste",
            output_candidate_root=out_candidates,
            output_embedding_root=out_embeddings,
        )
    assert not out_candidates.exists()
    assert not out_embeddings.exists()


def test_rebind_reuses_only_identical_candidate_images(tmp_path):
    candidates, embeddings = _fixture(tmp_path)
    source_rows = [json.loads(line) for line in (candidates / "candidate_records.jsonl").read_text().splitlines()]
    target = tmp_path / "target-candidates"
    target.mkdir()
    target_rows = []
    for row in source_rows:
        target_rows.append({
            **row, "patient_group_id": row["case_id"], "dataset_id": "holdout",
            "image_sha256": row.get("image_sha256"),
        })
    (target / "candidate_records.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in target_rows), encoding="utf-8"
    )
    target_body = {
        "schema": "target-v1",
        "candidate_records_sha256": sha256_file(target / "candidate_records.jsonl"),
        "ground_truth_read": False,
    }
    _json(target / "dataset_manifest.json", {**target_body, "dataset_signature": canonical_sha256(target_body)})
    result = rebind_embedding_dataset(
        source_candidate_root=candidates, source_embedding_root=embeddings,
        target_candidate_root=target, output_embedding_root=tmp_path / "rebound",
    )
    assert result["candidate_key_and_image_hash_identity_verified"] is True
    rows = [json.loads(line) for line in (tmp_path / "rebound" / "embedding_records.jsonl").read_text().splitlines()]
    assert {row["dataset_id"] for row in rows} == {"holdout"}


def test_rebind_rejects_changed_image_hash(tmp_path):
    candidates, embeddings = _fixture(tmp_path)
    target = tmp_path / "target-candidates"
    target.mkdir()
    rows = [json.loads(line) for line in (candidates / "candidate_records.jsonl").read_text().splitlines()]
    for row in rows:
        row.update(patient_group_id=row["case_id"], dataset_id="holdout", image_sha256="new")
    (target / "candidate_records.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    body = {"schema": "target-v1", "candidate_records_sha256": sha256_file(target / "candidate_records.jsonl")}
    _json(target / "dataset_manifest.json", {**body, "dataset_signature": canonical_sha256(body)})
    with pytest.raises(PipelineError, match="Imagem candidata divergiu"):
        rebind_embedding_dataset(
            source_candidate_root=candidates, source_embedding_root=embeddings,
            target_candidate_root=target, output_embedding_root=tmp_path / "rebound",
        )
