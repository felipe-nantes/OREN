"""Checkpointed MedSigLIP image-embedding extraction."""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np
import yaml
from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file


EMBEDDING_MANIFEST_SCHEMA = "argos-medsiglip-frozen-embeddings-v1"
EMBEDDING_RECORD_SCHEMA = "argos-medsiglip-frozen-embedding-record-v1"


class ImageEmbeddingBackend(Protocol):
    model_id: str
    revision: str
    embedding_dimension: int
    device: str

    def embed(self, images: Sequence[Image.Image]) -> np.ndarray: ...

    def metadata(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _json(path: Path, description: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def load_embedding_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config MedSigLIP inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config MedSigLIP deve ser objeto YAML.")
    if value.get("schema") != "argos-medsiglip-frozen-embedding-config-v1":
        raise PipelineError("Schema da config MedSigLIP inválido.")
    if not value.get("model_id") or not value.get("revision"):
        raise PipelineError("model_id e revision são obrigatórios.")
    if int(value.get("image_size", 0)) != 448:
        raise PipelineError("MedSigLIP v1 exige image_size=448.")
    if value.get("local_files_only") is not True:
        raise PipelineError("Extração congelada exige local_files_only=true.")
    if value.get("l2_normalize") is not True:
        raise PipelineError("Embedding v1 exige normalização L2.")
    if value.get("research_only") is not True:
        raise PipelineError("Extração deve permanecer research_only.")
    return value


class HuggingFaceMedSigLIPBackend:
    """Vision-only pooled representation from the pinned MedSigLIP snapshot."""

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise PipelineError(f"Dependência MedSigLIP ausente: {exc}") from exc
        self._torch = torch
        self.model_id = str(config["model_id"])
        self.revision = str(config["revision"])
        self.device = str(config.get("device", "cuda"))
        if self.device == "cuda" and not torch.cuda.is_available():
            raise PipelineError("CUDA indisponível para MedSigLIP.")
        self._snapshot = Path(
            snapshot_download(
                self.model_id,
                revision=self.revision,
                local_files_only=True,
            )
        ).resolve()
        dtype_name = str(config.get("dtype", "float16"))
        dtype = torch.float16 if dtype_name == "float16" else torch.float32
        self._processor = AutoProcessor.from_pretrained(
            self._snapshot, local_files_only=True
        )
        self._model = AutoModel.from_pretrained(
            self._snapshot,
            local_files_only=True,
            dtype=dtype,
        ).to(self.device)
        self._model.eval()
        self._dtype = dtype
        self.embedding_dimension = int(
            self._model.config.vision_config.hidden_size
        )

    def embed(self, images: Sequence[Image.Image]) -> np.ndarray:
        torch = self._torch
        inputs = self._processor(
            images=list(images), return_tensors="pt"
        )
        pixel_values = inputs["pixel_values"].to(
            self.device, dtype=self._dtype
        )
        with torch.inference_mode():
            output = self._model.get_image_features(
                pixel_values=pixel_values
            )
            tensor = output.pooler_output
            tensor = torch.nn.functional.normalize(tensor.float(), dim=-1)
        result = tensor.cpu().numpy().astype(np.float32, copy=False)
        if result.ndim != 2 or result.shape[1] != self.embedding_dimension:
            raise PipelineError("Dimensão inesperada do embedding MedSigLIP.")
        if not np.isfinite(result).all():
            raise PipelineError("Embedding MedSigLIP contém NaN/Inf.")
        return result

    def metadata(self) -> dict[str, Any]:
        artifacts: dict[str, str] = {}
        for name in (
            "config.json",
            "preprocessor_config.json",
            "model.safetensors.index.json",
        ):
            path = self._snapshot / name
            if path.is_file():
                artifacts[name] = sha256_file(path)
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "snapshot_name": self._snapshot.name,
            "artifact_hashes": artifacts,
            "device": self.device,
            "embedding_dimension": self.embedding_dimension,
            "pooling": "vision_pooler_output",
            "normalization": "l2",
            "output_dtype": "float32",
        }

    def close(self) -> None:
        torch = self._torch
        self._model.to("cpu")
        del self._model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _safe_name(value: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in value):
        raise PipelineError(f"Identificador inseguro: {value!r}")
    return value


def _atomic_npy(path: Path, vector: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as stream:
            np.save(stream, vector, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_fsync(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )
        stream.flush()
        os.fsync(stream.fileno())


def _checkpoint_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = _jsonl(path, "Checkpoint de embeddings")
    keys = [
        (str(row.get("case_id")), str(row.get("candidate_id"))) for row in rows
    ]
    if len(keys) != len(set(keys)):
        raise PipelineError("Checkpoint contém candidatos duplicados.")
    return rows


def extract_embeddings(
    *,
    config_path: Path,
    candidate_root: Path,
    workspace_root: Path,
    output_root: Path,
    backend: ImageEmbeddingBackend | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    candidate_root = Path(candidate_root).resolve()
    destination = Path(output_root).resolve()
    staging = destination.with_name(f".{destination.name}.incomplete")
    if destination.exists():
        raise PipelineError("Cache de embeddings já publicado.")
    staging.mkdir(parents=True, exist_ok=True)
    config = load_embedding_config(config_path)
    candidate_manifest_path = candidate_root / "dataset_manifest.json"
    candidate_records_path = candidate_root / "candidate_records.jsonl"
    candidate_manifest = _json(candidate_manifest_path, "Dataset candidato")
    if candidate_manifest.get("ground_truth_read") is not False:
        raise PipelineError("Dataset candidato não é label-blind.")
    if candidate_manifest.get("lesion_masks_read") != 0:
        raise PipelineError("Dataset candidato consumiu máscara de lesão.")
    if (
        candidate_manifest.get("candidate_records_sha256")
        != sha256_file(candidate_records_path)
    ):
        raise PipelineError("Manifesto candidato foi alterado.")
    candidates = _jsonl(candidate_records_path, "Candidatos")
    candidates.sort(
        key=lambda row: (row["case_id"], row["candidate_id"])
    )
    if limit is not None:
        if limit < 1:
            raise PipelineError("limit deve ser positivo.")
        candidates = candidates[:limit]
    checkpoint_path = staging / "checkpoint_embeddings.jsonl"
    completed = _checkpoint_rows(checkpoint_path)
    completed_keys = {
        (str(row["case_id"]), str(row["candidate_id"])) for row in completed
    }
    active_backend = backend or HuggingFaceMedSigLIPBackend(config)
    batch_size = int(config.get("batch_size", 4))
    if batch_size < 1:
        raise PipelineError("batch_size deve ser positivo.")
    try:
        pending = [
            row
            for row in candidates
            if (str(row["case_id"]), str(row["candidate_id"]))
            not in completed_keys
        ]
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            images: list[Image.Image] = []
            try:
                for row in batch:
                    image_path = root / str(row["image_path"])
                    if sha256_file(image_path) != row.get("image_sha256"):
                        raise PipelineError(
                            f"Imagem alterada: {row['image_path']}"
                        )
                    with Image.open(image_path) as source:
                        if source.info:
                            raise PipelineError(
                                f"PNG contém metadados: {row['image_path']}"
                            )
                        images.append(source.convert("RGB"))
                vectors = active_backend.embed(images)
            finally:
                for image in images:
                    image.close()
            if vectors.shape != (
                len(batch),
                active_backend.embedding_dimension,
            ):
                raise PipelineError("Backend retornou matriz incompatível.")
            batch_records: list[dict[str, Any]] = []
            for row, vector in zip(batch, vectors):
                if not np.isfinite(vector).all():
                    raise PipelineError("Embedding contém NaN/Inf.")
                norm = float(np.linalg.norm(vector))
                if not math.isclose(norm, 1.0, rel_tol=2e-4, abs_tol=2e-4):
                    raise PipelineError(
                        f"Embedding não normalizado: norma={norm}"
                    )
                case_id = _safe_name(str(row["case_id"]))
                candidate_id = _safe_name(str(row["candidate_id"]))
                relative_embedding = (
                    Path("embeddings")
                    / case_id
                    / f"{candidate_id}.npy"
                )
                embedding_path = staging / relative_embedding
                _atomic_npy(embedding_path, vector.astype(np.float32))
                batch_records.append(
                    {
                        "schema": EMBEDDING_RECORD_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": str(row["patient_group_id"]),
                        "dataset_id": str(row["dataset_id"]),
                        "candidate_id": candidate_id,
                        "candidate_kind": str(row["candidate_kind"]),
                        "panel_number": int(row["panel_number"]),
                        "image_sha256": str(row["image_sha256"]),
                        "embedding_path": relative_embedding.as_posix(),
                        "embedding_sha256": sha256_file(embedding_path),
                        "embedding_dimension": int(vector.shape[0]),
                        "embedding_dtype": "float32",
                        "embedding_l2_norm": norm,
                        "label_attached": False,
                        "ground_truth_read": False,
                        "lesion_mask_read": False,
                        "research_only": True,
                    }
                )
            _append_fsync(checkpoint_path, batch_records)
            completed.extend(batch_records)
        completed.sort(key=lambda row: (row["case_id"], row["candidate_id"]))
        records_path = staging / "embedding_records.jsonl"
        records_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in completed
            ),
            encoding="utf-8",
        )
        body = {
            "schema": EMBEDDING_MANIFEST_SCHEMA,
            "status": (
                "smoke_complete"
                if limit is not None
                else "complete_label_blind_pending_independent_verification"
            ),
            "config_sha256": sha256_file(config_path),
            "candidate_dataset_signature": candidate_manifest[
                "dataset_signature"
            ],
            "candidate_records_sha256": sha256_file(
                candidate_records_path
            ),
            "expected_embedding_count": len(candidates),
            "embedding_count": len(completed),
            "embedding_records_sha256": sha256_file(records_path),
            "backend": active_backend.metadata(),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "embedding_signature": canonical_sha256(body)}
        (staging / "embedding_manifest.json").write_text(
            json.dumps(
                manifest, ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        checkpoint_path.unlink(missing_ok=True)
        os.replace(staging, destination)
        return manifest
    finally:
        active_backend.close()


def verify_embeddings(
    *,
    candidate_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    candidate_root = Path(candidate_root).resolve()
    output_root = Path(output_root).resolve()
    candidate_manifest = _json(
        candidate_root / "dataset_manifest.json", "Dataset candidato"
    )
    manifest = _json(
        output_root / "embedding_manifest.json", "Manifesto de embeddings"
    )
    unsigned = dict(manifest)
    signature = unsigned.pop("embedding_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura dos embeddings diverge.")
    if (
        manifest.get("candidate_dataset_signature")
        != candidate_manifest.get("dataset_signature")
    ):
        raise PipelineError("Embeddings pertencem a outro dataset.")
    records_path = output_root / "embedding_records.jsonl"
    if manifest.get("embedding_records_sha256") != sha256_file(records_path):
        raise PipelineError("Registros de embeddings foram alterados.")
    rows = _jsonl(records_path, "Registros de embeddings")
    if len(rows) != int(manifest.get("embedding_count", -1)):
        raise PipelineError("Contagem de embeddings divergente.")
    keys: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row["case_id"]), str(row["candidate_id"]))
        if key in keys:
            raise PipelineError("Embedding duplicado.")
        keys.add(key)
        embedding_path = output_root / str(row["embedding_path"])
        if sha256_file(embedding_path) != row.get("embedding_sha256"):
            raise PipelineError(f"Embedding alterado: {key}")
        vector = np.load(embedding_path, allow_pickle=False)
        if vector.shape != (int(row["embedding_dimension"]),):
            raise PipelineError(f"Dimensão divergente: {key}")
        if vector.dtype != np.float32 or not np.isfinite(vector).all():
            raise PipelineError(f"Embedding numérico inválido: {key}")
        if row.get("label_attached") is not False:
            raise PipelineError("Label anexado antes da avaliação.")
        if row.get("ground_truth_read") is not False:
            raise PipelineError("Ground truth lido na extração.")
        if row.get("lesion_mask_read") is not False:
            raise PipelineError("Máscara de lesão lida na extração.")
    return manifest
