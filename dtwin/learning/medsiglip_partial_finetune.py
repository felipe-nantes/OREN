"""Leakage-safe partial MedSigLIP fine-tuning for Phase 13.

The frozen Phase-5 artifacts are inputs only and are never overwritten.  Each
outer-fold model is trained using one pre-existing inner split for training,
early stopping and threshold selection.  The outer test fold is opened only
for label-blind prediction.
"""
from __future__ import annotations

import gc
import json
import math
import os
import random
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_classifier import _best_threshold
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.splits import validate_nested_splits


CONFIG_SCHEMA = "argos-hybrid-medsiglip-partial-finetune-config-v1"
PREDICTION_SCHEMA = "argos-hybrid-medsiglip-partial-oof-prediction-v1"
FREEZE_SCHEMA = "argos-hybrid-medsiglip-partial-oof-freeze-v1"


def _json(path: Path, description: str = "JSON") -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str = "JSONL") -> list[dict[str, Any]]:
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


def load_partial_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de fine-tuning inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema da config de fine-tuning inválido.")
    if value.get("local_files_only") is not True:
        raise PipelineError("Fine-tuning exige snapshot local e fixado.")
    if int(value.get("image_size", 0)) != 448:
        raise PipelineError("Fine-tuning MedSigLIP exige imagens 448x448.")
    if int(value.get("trainable_last_blocks", 0)) < 1:
        raise PipelineError("Ao menos um bloco visual deve ser treinável.")
    if value.get("adapter_mode", "full_last_blocks") not in {
        "full_last_blocks",
        "lora_qv",
    }:
        raise PipelineError("Modo de adaptação visual inválido.")
    if value.get("train_pooling") not in {"mean_logit", "max_logit"}:
        raise PipelineError("Pooling de treino inválido.")
    if value.get("inference_aggregation") not in {"mean", "max", "top2_mean"}:
        raise PipelineError("Agregação de inferência inválida.")
    if value.get("research_only") is not True:
        raise PipelineError("Fine-tuning deve permanecer research_only.")
    if int(value.get("lesion_masks_read", -1)) != 0:
        raise PipelineError("Máscara de lesão não é permitida nesta etapa.")
    return value


def aggregate_probabilities(values: list[float], method: str) -> float:
    if not values:
        raise PipelineError("Caso sem painéis não pode ser agregado.")
    ordered = sorted((float(value) for value in values), reverse=True)
    if method == "mean":
        return float(np.mean(ordered))
    if method == "max":
        return ordered[0]
    if method == "top2_mean":
        return float(np.mean(ordered[:2]))
    raise PipelineError(f"Agregação inválida: {method}")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_torch_save(path: Path, value: Any, torch: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        torch.save(value, temporary)
        with temporary.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _candidate_paths(
    candidate_root: Path, workspace_root: Path
) -> tuple[dict[str, list[Path]], dict[str, int], dict[str, Any]]:
    manifest = _json(candidate_root / "dataset_manifest.json", "Dataset candidato")
    records_path = candidate_root / "candidate_records.jsonl"
    if manifest.get("ground_truth_read") is not False:
        raise PipelineError("Dataset visual deixou de ser label-blind.")
    if int(manifest.get("lesion_masks_read", -1)) != 0:
        raise PipelineError("Dataset visual consumiu máscara de lesão.")
    if manifest.get("candidate_records_sha256") != sha256_file(records_path):
        raise PipelineError("Registros candidatos foram alterados.")
    grouped: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    root = Path(workspace_root).resolve()
    for row in _jsonl(records_path, "Registros candidatos"):
        if row.get("ground_truth_used") is not False:
            raise PipelineError("Candidato contém ground truth.")
        if row.get("lesion_mask_used") is not False:
            raise PipelineError("Candidato contém máscara de lesão.")
        image_path = (root / str(row["image_path"])).resolve()
        try:
            image_path.relative_to(root)
        except ValueError as exc:
            raise PipelineError("Imagem candidata fora do workspace.") from exc
        if sha256_file(image_path) != row.get("image_sha256"):
            raise PipelineError(f"Imagem candidata alterada: {image_path}")
        grouped[str(row["case_id"])].append((int(row["panel_number"]), image_path))
    paths = {
        case_id: [path for _, path in sorted(items)]
        for case_id, items in grouped.items()
    }
    counts = {case_id: len(items) for case_id, items in paths.items()}
    return paths, counts, manifest


def _seed_everything(seed: int, torch: Any) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _load_runtime(
    config: dict[str, Any],
    *,
    initial_head: tuple[np.ndarray, float] | None = None,
) -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoProcessor, SiglipVisionModel
    except ImportError as exc:
        raise PipelineError(f"Dependência de fine-tuning ausente: {exc}") from exc
    if not torch.cuda.is_available():
        raise PipelineError("Fine-tuning parcial requer CUDA.")
    snapshot = snapshot_download(
        str(config["model_id"]),
        revision=str(config["revision"]),
        local_files_only=True,
    )
    processor = AutoProcessor.from_pretrained(snapshot, local_files_only=True)
    vision = SiglipVisionModel.from_pretrained(
        snapshot, local_files_only=True
    ).to("cuda")
    for parameter in vision.parameters():
        parameter.requires_grad = False
    block_count = len(vision.encoder.layers)
    trainable_blocks = int(config["trainable_last_blocks"])
    if trainable_blocks > block_count:
        raise PipelineError("Número de blocos treináveis excede o encoder.")
    if config.get("adapter_mode", "full_last_blocks") == "full_last_blocks":
        for layer in vision.encoder.layers[-trainable_blocks:]:
            for parameter in layer.parameters():
                parameter.requires_grad = True
    else:
        class LoRALinear(torch.nn.Module):
            def __init__(
                self, base: Any, rank: int, alpha: float, dropout: float
            ) -> None:
                super().__init__()
                self.base = base
                for parameter in self.base.parameters():
                    parameter.requires_grad = False
                self.lora_a = torch.nn.Linear(
                    base.in_features, rank, bias=False
                )
                self.lora_b = torch.nn.Linear(
                    rank, base.out_features, bias=False
                )
                torch.nn.init.kaiming_uniform_(
                    self.lora_a.weight, a=math.sqrt(5)
                )
                torch.nn.init.zeros_(self.lora_b.weight)
                self.dropout = torch.nn.Dropout(dropout)
                self.scale = float(alpha) / float(rank)

            def forward(self, values: Any) -> Any:
                return self.base(values) + (
                    self.lora_b(self.lora_a(self.dropout(values))) * self.scale
                )

        rank = int(config.get("lora_rank", 4))
        alpha = float(config.get("lora_alpha", rank))
        dropout = float(config.get("lora_dropout", 0.0))
        if rank < 1:
            raise PipelineError("Rank LoRA inválido.")
        for layer in vision.encoder.layers[-trainable_blocks:]:
            layer.self_attn.q_proj = LoRALinear(
                layer.self_attn.q_proj, rank, alpha, dropout
            ).to("cuda")
            layer.self_attn.v_proj = LoRALinear(
                layer.self_attn.v_proj, rank, alpha, dropout
            ).to("cuda")
    vision.train()
    head = torch.nn.Linear(int(vision.config.hidden_size), 1).to("cuda")
    if initial_head is not None:
        weight, bias = initial_head
        if weight.shape != (int(vision.config.hidden_size),):
            raise PipelineError("Inicialização da cabeça tem dimensão inválida.")
        with torch.no_grad():
            head.weight.copy_(
                torch.from_numpy(weight.astype(np.float32)).reshape(1, -1).to("cuda")
            )
            head.bias.copy_(
                torch.tensor([float(bias)], dtype=torch.float32, device="cuda")
            )
    return torch, processor, vision, head


def _images(paths: list[Path]) -> list[Image.Image]:
    images: list[Image.Image] = []
    try:
        for path in paths:
            with Image.open(path) as source:
                if source.info:
                    raise PipelineError(f"PNG contém metadados: {path}")
                images.append(source.convert("RGB"))
        return images
    except Exception:
        for image in images:
            image.close()
        raise


def _case_logit(
    *,
    paths: list[Path],
    processor: Any,
    vision: Any,
    head: Any,
    torch: Any,
    amp_dtype: Any,
    pooling: str,
) -> Any:
    images = _images(paths)
    try:
        values = processor(images=images, return_tensors="pt")["pixel_values"]
    finally:
        for image in images:
            image.close()
    values = values.to("cuda", non_blocking=True)
    with torch.autocast(device_type="cuda", dtype=amp_dtype):
        pooled = torch.nn.functional.normalize(
            vision(pixel_values=values).pooler_output.float(), dim=-1
        )
        panel_logits = head(pooled.float()).squeeze(-1)
        if pooling == "max_logit":
            return panel_logits.max()
        return panel_logits.mean()


def _evaluate_loss(
    case_ids: list[str],
    paths: dict[str, list[Path]],
    labels: dict[str, int],
    *,
    processor: Any,
    vision: Any,
    head: Any,
    torch: Any,
    amp_dtype: Any,
    pooling: str,
    positive_weight: float,
) -> float:
    vision.eval()
    head.eval()
    total = 0.0
    count = 0
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([positive_weight], device="cuda")
    )
    with torch.no_grad():
        for case_id in case_ids:
            if case_id not in paths:
                continue
            logit = _case_logit(
                paths=paths[case_id], processor=processor, vision=vision,
                head=head, torch=torch, amp_dtype=amp_dtype, pooling=pooling,
            )
            target = torch.tensor([float(labels[case_id])], device="cuda")
            total += float(loss_fn(logit.reshape(1), target).item())
            count += 1
    vision.train()
    head.train()
    return total / max(1, count)


def _train_fold(
    *,
    config: dict[str, Any],
    train_ids: list[str],
    validation_ids: list[str],
    paths: dict[str, list[Path]],
    labels: dict[str, int],
    seed: int,
    checkpoint_path: Path,
    embedding_map: dict[str, list[np.ndarray]] | None = None,
) -> dict[str, Any]:
    initial_head = None
    if config.get("head_initialization") == "fold_train_logistic":
        if embedding_map is None:
            raise PipelineError("Embeddings são necessários para inicializar a cabeça.")
        matrix: list[np.ndarray] = []
        targets: list[int] = []
        for case_id in train_ids:
            for vector in embedding_map.get(case_id, []):
                matrix.append(vector)
                targets.append(labels[case_id])
        if not matrix or set(targets) != {0, 1}:
            raise PipelineError("Inicialização logística exige duas classes.")
        scaler = StandardScaler().fit(np.stack(matrix))
        transformed = scaler.transform(np.stack(matrix))
        logistic = LogisticRegression(
            C=float(config.get("head_initialization_c", 0.1)),
            class_weight="balanced",
            dual=True,
            max_iter=2000,
            random_state=seed,
            solver="liblinear",
        ).fit(transformed, np.asarray(targets, dtype=np.int64))
        scaled_weight = logistic.coef_[0] / scaler.scale_
        scaled_bias = float(
            logistic.intercept_[0] - np.dot(scaler.mean_, scaled_weight)
        )
        initial_head = (scaled_weight.astype(np.float32), scaled_bias)
    torch, processor, vision, head = _load_runtime(
        config, initial_head=initial_head
    )
    _seed_everything(seed, torch)
    amp_dtype = torch.bfloat16 if config["amp_dtype"] == "bfloat16" else torch.float16
    encoder_parameters = [
        parameter for parameter in vision.parameters() if parameter.requires_grad
    ]
    optimizer = torch.optim.AdamW(
        [
            {"params": encoder_parameters, "lr": float(config["learning_rate_encoder"])},
            {"params": head.parameters(), "lr": float(config["learning_rate_head"])},
        ],
        weight_decay=float(config["weight_decay"]),
    )
    available_train = [case_id for case_id in train_ids if case_id in paths]
    positives = sum(labels[case_id] for case_id in available_train)
    negatives = len(available_train) - positives
    positive_weight = negatives / max(1, positives)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([positive_weight], device="cuda")
    )
    best_loss = math.inf
    best_epoch = 0
    patience = 0
    history: list[dict[str, float | int]] = []
    accumulation = int(config["gradient_accumulation_cases"])
    optimizer.zero_grad(set_to_none=True)
    try:
        for epoch in range(1, int(config["epochs_max"]) + 1):
            order = list(available_train)
            random.Random(seed + epoch).shuffle(order)
            running = 0.0
            for index, case_id in enumerate(order, start=1):
                logit = _case_logit(
                    paths=paths[case_id], processor=processor, vision=vision,
                    head=head, torch=torch, amp_dtype=amp_dtype,
                    pooling=str(config["train_pooling"]),
                )
                target = torch.tensor([float(labels[case_id])], device="cuda")
                loss = loss_fn(logit.reshape(1), target) / accumulation
                loss.backward()
                running += float(loss.item()) * accumulation
                if index % accumulation == 0 or index == len(order):
                    torch.nn.utils.clip_grad_norm_(
                        encoder_parameters + list(head.parameters()),
                        float(config["gradient_clip_norm"]),
                    )
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
            validation_loss = _evaluate_loss(
                validation_ids, paths, labels, processor=processor, vision=vision,
                head=head, torch=torch, amp_dtype=amp_dtype,
                pooling=str(config["train_pooling"]),
                positive_weight=positive_weight,
            )
            history.append(
                {
                    "epoch": epoch,
                    "training_loss": running / max(1, len(order)),
                    "validation_loss": validation_loss,
                }
            )
            if validation_loss < best_loss - 1e-5:
                best_loss = validation_loss
                best_epoch = epoch
                patience = 0
                trainable_state = {
                    name: tensor.detach().cpu()
                    for name, tensor in vision.state_dict().items()
                    if any(
                        name.startswith(
                            f"encoder.layers.{layer_index}."
                        )
                        for layer_index in range(
                            len(vision.encoder.layers)
                            - int(config["trainable_last_blocks"]),
                            len(vision.encoder.layers),
                        )
                    )
                }
                _atomic_torch_save(
                    checkpoint_path,
                    {
                        "encoder_state": trainable_state,
                        "head_state": {
                            name: tensor.detach().cpu()
                            for name, tensor in head.state_dict().items()
                        },
                        "best_epoch": best_epoch,
                        "validation_loss": best_loss,
                        "config_signature": canonical_sha256(config),
                    },
                    torch,
                )
            else:
                patience += 1
                if patience > int(config["early_stopping_patience"]):
                    break
        state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        vision.load_state_dict(state["encoder_state"], strict=False)
        head.load_state_dict(state["head_state"])
        return {
            "torch": torch,
            "processor": processor,
            "vision": vision,
            "head": head,
            "amp_dtype": amp_dtype,
            "best_epoch": best_epoch,
            "best_validation_loss": best_loss,
            "history": history,
        }
    except Exception:
        del head, vision
        gc.collect()
        torch.cuda.empty_cache()
        raise


def _predict(
    case_ids: list[str],
    paths: dict[str, list[Path]],
    *,
    runtime: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, float]:
    torch = runtime["torch"]
    vision = runtime["vision"]
    head = runtime["head"]
    vision.eval()
    head.eval()
    scores: dict[str, float] = {}
    with torch.no_grad():
        for case_id in case_ids:
            if case_id not in paths:
                continue
            images = _images(paths[case_id])
            try:
                values = runtime["processor"](
                    images=images, return_tensors="pt"
                )["pixel_values"].to("cuda")
            finally:
                for image in images:
                    image.close()
            with torch.autocast(device_type="cuda", dtype=runtime["amp_dtype"]):
                pooled = torch.nn.functional.normalize(
                    vision(pixel_values=values).pooler_output.float(), dim=-1
                )
                logits = head(pooled.float()).squeeze(-1)
                probabilities = torch.sigmoid(logits).float().cpu().tolist()
            scores[case_id] = aggregate_probabilities(
                probabilities, str(config["inference_aggregation"])
            )
    return scores


def _close_runtime(runtime: dict[str, Any]) -> None:
    torch = runtime["torch"]
    runtime["vision"].to("cpu")
    runtime["head"].to("cpu")
    runtime.clear()
    gc.collect()
    torch.cuda.empty_cache()


def generate_partial_oof(
    *,
    finetune_config_path: Path,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    candidate_root: Path,
    embedding_root: Path | None,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    config = load_partial_config(finetune_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    paths, panel_counts, candidate_manifest = _candidate_paths(
        Path(candidate_root), Path(workspace_root)
    )
    embedding_map: dict[str, list[np.ndarray]] | None = None
    embedding_signature: str | None = None
    if config.get("head_initialization") == "fold_train_logistic":
        if embedding_root is None:
            raise PipelineError("Config exige o cache congelado de embeddings.")
        from dtwin.learning.medsiglip_classifier import _load_embedding_map
        from dtwin.learning.medsiglip_embeddings import verify_embeddings

        embedding_manifest = verify_embeddings(
            candidate_root=Path(candidate_root),
            output_root=Path(embedding_root),
        )
        embedding_signature = str(embedding_manifest["embedding_signature"])
        embedding_map, _ = _load_embedding_map(Path(embedding_root))
    protected = load_protected_cases(
        training_protocol_config_path, workspace_root
    )
    protected_by_id = {case.case_id: case for case in protected}
    labels = {
        case.case_id: int(case.label == "POSITIVE") for case in protected
    }
    destination = Path(output_root).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    predictions_by_case: dict[str, dict[str, Any]] = {}
    fold_records: list[dict[str, Any]] = []
    for outer in splits["outer_folds"]:
        fold_index = int(outer["outer_fold"])
        fold_result_path = destination / f"outer_fold_{fold_index}_result.json"
        if fold_result_path.exists():
            result = _json(fold_result_path, "Resultado parcial de fold")
            for row in result["predictions"]:
                predictions_by_case[str(row["case_id"])] = row
            fold_records.append(result["selection"])
            continue
        calibration = outer["inner_folds"][0]
        checkpoint_path = destination / f"outer_fold_{fold_index}_trainable.pt"
        runtime = _train_fold(
            config=config,
            train_ids=list(calibration["train_case_ids"]),
            validation_ids=list(calibration["validation_case_ids"]),
            paths=paths,
            labels=labels,
            seed=int(config["seed"]) + fold_index,
            checkpoint_path=checkpoint_path,
            embedding_map=embedding_map,
        )
        try:
            validation_ids = list(calibration["validation_case_ids"])
            validation_scores = _predict(
                validation_ids, paths, runtime=runtime, config=config
            )
            threshold, inner_metrics = _best_threshold(
                validation_ids, validation_scores, labels
            )
            test_ids = list(outer["test_case_ids"])
            test_scores = _predict(
                test_ids, paths, runtime=runtime, config=config
            )
            predictions: list[dict[str, Any]] = []
            for case_id in test_ids:
                score = test_scores.get(case_id)
                predictions.append(
                    {
                        "schema": PREDICTION_SCHEMA,
                        "case_id": case_id,
                        "patient_group_id": case_id,
                        "dataset_id": protected_by_id[case_id].dataset_id,
                        "outer_fold": fold_index,
                        "panel_count": panel_counts.get(case_id, 0),
                        "score": score,
                        "threshold": threshold,
                        "prediction": (
                            "TECHNICAL_FAILURE"
                            if score is None
                            else ("POSITIVE" if score >= threshold else "NEGATIVE")
                        ),
                        "technical_failure": score is None,
                        "aggregation": config["inference_aggregation"],
                        "ground_truth_in_artifact": False,
                        "held_out_label_used": False,
                        "research_only": True,
                    }
                )
            selection = {
                "outer_fold": fold_index,
                "calibration_inner_fold": int(calibration["inner_fold"]),
                "train_case_count": len(calibration["train_case_ids"]),
                "validation_case_count": len(validation_ids),
                "test_case_count": len(test_ids),
                "best_epoch": runtime["best_epoch"],
                "best_validation_loss": runtime["best_validation_loss"],
                "threshold": threshold,
                "inner_metrics": inner_metrics,
                "checkpoint_sha256": sha256_file(checkpoint_path),
                "held_out_labels_used_for_fit_or_threshold": False,
            }
            result = {"selection": selection, "predictions": predictions}
            _atomic_json(fold_result_path, result)
            predictions_by_case.update(
                {str(row["case_id"]): row for row in predictions}
            )
            fold_records.append(selection)
        finally:
            _close_runtime(runtime)
    expected = {
        str(case_id)
        for fold in splits["outer_folds"]
        for case_id in fold["test_case_ids"]
    }
    if set(predictions_by_case) != expected:
        raise PipelineError("Predições parciais não cobrem o universo OOF.")
    predictions = [predictions_by_case[case_id] for case_id in sorted(expected)]
    predictions_path = destination / "oof_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in predictions:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    fold_path = destination / "fold_selection.json"
    _atomic_json(fold_path, sorted(fold_records, key=lambda row: row["outer_fold"]))
    body = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": config["candidate_id"],
        "stage": config["stage"],
        "training_protocol_signature": protocol["protocol_signature"],
        "candidate_dataset_signature": candidate_manifest["dataset_signature"],
        "embedding_signature": embedding_signature,
        "finetune_config_sha256": sha256_file(finetune_config_path),
        "splits_sha256": sha256_file(splits_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(row["technical_failure"] for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(fold_path),
        "individual_ground_truth_persisted": False,
        "held_out_labels_used_for_fit_or_threshold": False,
        "encoder_trainable": True,
        "trainable_last_blocks": int(config["trainable_last_blocks"]),
        "lesion_masks_read": 0,
        "phase5_artifacts_modified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    _atomic_json(destination / "prediction_freeze.json", freeze)
    return freeze
