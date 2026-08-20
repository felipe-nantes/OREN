"""Create immutable, hash-bound modality subsets without recomputing embeddings."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError
from dtwin.learning.monophase_slice_candidates import publish_immutable_directory
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL invalido: {path}") from exc


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def filter_candidate_embedding_dataset(
    *,
    candidate_root: Path,
    embedding_root: Path,
    sequence_role: str,
    output_candidate_root: Path,
    output_embedding_root: Path,
) -> dict[str, Any]:
    candidate_root = Path(candidate_root).resolve()
    embedding_root = Path(embedding_root).resolve()
    candidate_out = Path(output_candidate_root).resolve()
    embedding_out = Path(output_embedding_root).resolve()
    if candidate_out.exists() or embedding_out.exists():
        raise PipelineError("Saida imutavel de subset ja existe.")
    candidate_manifest = _json(candidate_root / "dataset_manifest.json")
    embedding_manifest = _json(embedding_root / "embedding_manifest.json")
    unsigned_candidate = dict(candidate_manifest)
    candidate_signature = unsigned_candidate.pop("dataset_signature", None)
    if candidate_signature != canonical_sha256(unsigned_candidate):
        raise PipelineError("Assinatura da origem de candidatos diverge.")
    unsigned_embedding = dict(embedding_manifest)
    signature = unsigned_embedding.pop("embedding_signature", None)
    if signature != canonical_sha256(unsigned_embedding):
        raise PipelineError("Assinatura da origem de embeddings diverge.")
    candidate_path = candidate_root / "candidate_records.jsonl"
    embedding_path = embedding_root / "embedding_records.jsonl"
    if candidate_manifest.get("candidate_records_sha256") != sha256_file(candidate_path):
        raise PipelineError("Registros candidatos de origem alterados.")
    if embedding_manifest.get("embedding_records_sha256") != sha256_file(embedding_path):
        raise PipelineError("Registros de embedding de origem alterados.")
    candidates = [row for row in _jsonl(candidate_path) if row.get("sequence_role") == sequence_role]
    keys = {(str(row["case_id"]), str(row["candidate_id"])) for row in candidates}
    embeddings = [
        row for row in _jsonl(embedding_path)
        if (str(row["case_id"]), str(row["candidate_id"])) in keys
    ]
    if not candidates or len(embeddings) != len(candidates):
        raise PipelineError("Subset vazio ou sem correspondencia exata de embeddings.")
    candidate_out.parent.mkdir(parents=True, exist_ok=True)
    embedding_out.parent.mkdir(parents=True, exist_ok=True)
    candidate_staging = Path(tempfile.mkdtemp(prefix=f".{candidate_out.name}.", dir=candidate_out.parent))
    embedding_staging = Path(tempfile.mkdtemp(prefix=f".{embedding_out.name}.", dir=embedding_out.parent))
    try:
        subset_candidate_path = candidate_staging / "candidate_records.jsonl"
        _write_jsonl(subset_candidate_path, candidates)
        candidate_body = {
            "schema": "oren-monophase-complementary-subset-v1",
            "status": "complete_label_blind_pending_independent_verification",
            "source_dataset_signature": candidate_manifest["dataset_signature"],
            "sequence_role": sequence_role,
            "candidate_record_count": len(candidates),
            "candidate_records_sha256": sha256_file(subset_candidate_path),
            "materialized_case_count": len({row["case_id"] for row in candidates}),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        subset_candidate_manifest = {
            **candidate_body,
            "dataset_signature": canonical_sha256(candidate_body),
        }
        (candidate_staging / "dataset_manifest.json").write_text(
            json.dumps(subset_candidate_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for row in embeddings:
            source = embedding_root / str(row["embedding_path"])
            target = embedding_staging / str(row["embedding_path"])
            if sha256_file(source) != row.get("embedding_sha256"):
                raise PipelineError("Arquivo de embedding de origem alterado.")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        subset_embedding_path = embedding_staging / "embedding_records.jsonl"
        _write_jsonl(subset_embedding_path, embeddings)
        embedding_body = {
            "schema": embedding_manifest["schema"],
            "status": "complete_label_blind_pending_independent_verification",
            "config_sha256": embedding_manifest["config_sha256"],
            "candidate_dataset_signature": subset_candidate_manifest["dataset_signature"],
            "candidate_records_sha256": subset_candidate_manifest["candidate_records_sha256"],
            "expected_embedding_count": len(embeddings),
            "embedding_count": len(embeddings),
            "embedding_records_sha256": sha256_file(subset_embedding_path),
            "backend": embedding_manifest["backend"],
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        subset_embedding_manifest = {
            **embedding_body,
            "embedding_signature": canonical_sha256(embedding_body),
        }
        (embedding_staging / "embedding_manifest.json").write_text(
            json.dumps(subset_embedding_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidate_published = False
        embedding_published = False
        try:
            os.replace(candidate_staging, candidate_out)
            candidate_published = True
            os.replace(embedding_staging, embedding_out)
            embedding_published = True
        except Exception:
            if embedding_published and embedding_out.exists():
                shutil.rmtree(embedding_out)
            if candidate_published and candidate_out.exists():
                shutil.rmtree(candidate_out)
            raise
        return {
            "sequence_role": sequence_role,
            "candidate_dataset_signature": subset_candidate_manifest["dataset_signature"],
            "embedding_signature": subset_embedding_manifest["embedding_signature"],
            "candidate_count": len(candidates),
            "case_count": subset_candidate_manifest["materialized_case_count"],
        }
    finally:
        if candidate_staging.exists():
            shutil.rmtree(candidate_staging, ignore_errors=True)
        if embedding_staging.exists():
            shutil.rmtree(embedding_staging, ignore_errors=True)


def rebind_embedding_dataset(
    *, source_candidate_root: Path, source_embedding_root: Path,
    target_candidate_root: Path, output_embedding_root: Path,
) -> dict[str, Any]:
    """Reuse embeddings only when candidate keys and image hashes are identical."""
    source_candidate_root = Path(source_candidate_root).resolve()
    source_embedding_root = Path(source_embedding_root).resolve()
    target_candidate_root = Path(target_candidate_root).resolve()
    output = Path(output_embedding_root).resolve()
    if output.exists():
        raise PipelineError("Saida imutavel de embeddings rebind ja existe.")
    source_candidate_manifest = _json(source_candidate_root / "dataset_manifest.json")
    target_candidate_manifest = _json(target_candidate_root / "dataset_manifest.json")
    source_embedding_manifest = _json(source_embedding_root / "embedding_manifest.json")
    for manifest, field, description in (
        (source_candidate_manifest, "dataset_signature", "candidatos de origem"),
        (target_candidate_manifest, "dataset_signature", "candidatos de destino"),
        (source_embedding_manifest, "embedding_signature", "embeddings de origem"),
    ):
        unsigned = dict(manifest)
        signature = unsigned.pop(field, None)
        if signature != canonical_sha256(unsigned):
            raise PipelineError(f"Assinatura de {description} diverge.")
    if source_embedding_manifest.get("candidate_dataset_signature") != source_candidate_manifest.get("dataset_signature"):
        raise PipelineError("Embeddings de origem pertencem a outro dataset candidato.")
    source_candidate_path = source_candidate_root / "candidate_records.jsonl"
    target_candidate_path = target_candidate_root / "candidate_records.jsonl"
    source_embedding_path = source_embedding_root / "embedding_records.jsonl"
    if source_candidate_manifest.get("candidate_records_sha256") != sha256_file(source_candidate_path):
        raise PipelineError("Candidatos de origem foram alterados.")
    if target_candidate_manifest.get("candidate_records_sha256") != sha256_file(target_candidate_path):
        raise PipelineError("Candidatos de destino foram alterados.")
    if source_embedding_manifest.get("embedding_records_sha256") != sha256_file(source_embedding_path):
        raise PipelineError("Embeddings de origem foram alterados.")
    source_candidates = {
        (str(row["case_id"]), str(row["candidate_id"])): row
        for row in _jsonl(source_candidate_path)
    }
    target_candidates = {
        (str(row["case_id"]), str(row["candidate_id"])): row
        for row in _jsonl(target_candidate_path)
    }
    if set(source_candidates) != set(target_candidates):
        raise PipelineError("Universos candidatos de origem e destino divergem.")
    for key in source_candidates:
        if source_candidates[key].get("image_sha256") != target_candidates[key].get("image_sha256"):
            raise PipelineError(f"Imagem candidata divergiu no rebind: {key}")
    source_embeddings = _jsonl(source_embedding_path)
    if {(str(row["case_id"]), str(row["candidate_id"])) for row in source_embeddings} != set(target_candidates):
        raise PipelineError("Embeddings nao cobrem exatamente candidatos de destino.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    rebound: list[dict[str, Any]] = []
    try:
        for row in source_embeddings:
            key = (str(row["case_id"]), str(row["candidate_id"]))
            source = source_embedding_root / str(row["embedding_path"])
            if sha256_file(source) != row.get("embedding_sha256"):
                raise PipelineError(f"Embedding de origem alterado: {key}")
            target = staging / str(row["embedding_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
            rebound.append({
                **row,
                "patient_group_id": str(target_candidates[key]["patient_group_id"]),
                "dataset_id": str(target_candidates[key]["dataset_id"]),
                "image_sha256": str(target_candidates[key]["image_sha256"]),
            })
        records_path = staging / "embedding_records.jsonl"
        _write_jsonl(records_path, rebound)
        body = {
            "schema": source_embedding_manifest["schema"],
            "status": "complete_label_blind_pending_independent_verification",
            "config_sha256": source_embedding_manifest["config_sha256"],
            "candidate_dataset_signature": target_candidate_manifest["dataset_signature"],
            "candidate_records_sha256": target_candidate_manifest["candidate_records_sha256"],
            "expected_embedding_count": len(rebound), "embedding_count": len(rebound),
            "embedding_records_sha256": sha256_file(records_path),
            "backend": source_embedding_manifest["backend"],
            "rebound_from_embedding_signature": source_embedding_manifest["embedding_signature"],
            "candidate_key_and_image_hash_identity_verified": True,
            "ground_truth_read": False, "lesion_masks_read": 0,
            "research_only": True, "clinical_use_allowed": False,
        }
        manifest = {**body, "embedding_signature": canonical_sha256(body)}
        (staging / "embedding_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publish_immutable_directory(staging, output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


__all__ = ["filter_candidate_embedding_dataset", "rebind_embedding_dataset"]
