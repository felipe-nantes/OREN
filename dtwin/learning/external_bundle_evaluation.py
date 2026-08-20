"""Leakage-safe external evaluation of a frozen visual production bundle."""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import verify_candidate_dataset
from dtwin.learning.medsiglip_embeddings import verify_embeddings
from dtwin.learning.monophase_slice_candidates import is_proven_label_blind_input
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
)
from dtwin.learning.visual_inference import classify_embeddings, load_production_bundle

PREDICTION_SCHEMA = "oren-medsiglip-external-prediction-v1"
FREEZE_SCHEMA = "oren-medsiglip-external-prediction-freeze-v1"
EVALUATION_SCHEMA = "oren-medsiglip-external-evaluation-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


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


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _verify_signed_candidate_artifact(
    candidate_root: Path, workspace_root: Path
) -> dict[str, Any]:
    """Verify hash-bound canonical or derived candidate artifacts."""
    root = Path(candidate_root).resolve()
    manifest = _json(root / "dataset_manifest.json", "Dataset candidato")
    unsigned = dict(manifest)
    signature = unsigned.pop("dataset_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do dataset candidato diverge.")
    records_path = root / "candidate_records.jsonl"
    if manifest.get("candidate_records_sha256") != sha256_file(records_path):
        raise PipelineError("Registros candidatos foram alterados.")
    records = _jsonl(records_path, "Candidatos")
    if len(records) != int(manifest.get("candidate_record_count", -1)):
        raise PipelineError("Contagem de candidatos diverge.")
    for row in records:
        image_path = Path(str(row.get("image_path") or ""))
        if not image_path.is_absolute():
            image_path = Path(workspace_root).resolve() / image_path
        if sha256_file(image_path) != row.get("image_sha256"):
            raise PipelineError(f"Imagem candidata alterada: {row.get('candidate_id')}")
        if row.get("ground_truth_used") is not False:
            raise PipelineError("Ground truth detectado em candidato externo.")
        if row.get("lesion_mask_used") is not False:
            raise PipelineError("Mascara de lesao detectada em candidato externo.")
    if manifest.get("ground_truth_read") is not False or manifest.get("lesion_masks_read") != 0:
        raise PipelineError("Dataset candidato externo nao e comprovadamente label-blind.")
    failures_path = root / "technical_failures.jsonl"
    if "technical_failures_sha256" in manifest:
        if manifest.get("technical_failures_sha256") != sha256_file(failures_path):
            raise PipelineError("Falhas tecnicas candidatas foram alteradas.")
    return manifest


def predict_external_bundle(
    *,
    bundle_root: Path,
    candidate_root: Path,
    embedding_root: Path,
    protocol_path: Path,
    splits_path: Path,
    workspace_root: Path,
    dataset_id: str,
    failure_case_prefix: str,
    expected_case_count: int,
    output_root: Path,
    case_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Freeze decisions without opening labels or lesion masks."""

    root = Path(workspace_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Predições externas já existem; saída é imutável.")
    if case_manifest_path is None:
        verify_candidate_dataset(
            protocol_path=protocol_path,
            splits_path=splits_path,
            workspace_root=root,
            output_root=candidate_root,
        )
    else:
        _verify_signed_candidate_artifact(candidate_root, root)
    embedding_manifest = verify_embeddings(
        candidate_root=candidate_root,
        output_root=embedding_root,
    )
    bundle = load_production_bundle(bundle_root)
    candidate_rows = _jsonl(Path(candidate_root) / "candidate_records.jsonl", "Candidatos")
    embedding_rows = _jsonl(Path(embedding_root) / "embedding_records.jsonl", "Embeddings")
    failure_path = Path(candidate_root) / "technical_failures.jsonl"
    failure_rows = _jsonl(failure_path, "Falhas técnicas") if failure_path.exists() else []

    allowed_case_ids: set[str] | None = None
    case_manifest_sha256: str | None = None
    if case_manifest_path is not None:
        case_manifest_rows = _jsonl(Path(case_manifest_path), "Manifesto label-blind de casos")
        if any(not is_proven_label_blind_input(row) for row in case_manifest_rows):
            raise PipelineError("Manifesto externo não é comprovadamente label-blind.")
        allowed_case_ids = {str(row["case_id"]) for row in case_manifest_rows}
        if len(allowed_case_ids) != len(case_manifest_rows):
            raise PipelineError("Caso duplicado no manifesto externo.")
        if len(allowed_case_ids) != int(expected_case_count):
            raise PipelineError("Manifesto externo tem contagem de casos divergente.")
        case_manifest_sha256 = sha256_file(case_manifest_path)

    selected_candidates = [
        row for row in candidate_rows
        if (
            str(row.get("case_id")) in allowed_case_ids
            if allowed_case_ids is not None
            else row.get("dataset_id") == dataset_id
        )
    ]
    materialized_ids = {str(row["case_id"]) for row in selected_candidates}
    failure_ids = {
        str(row["case_id"])
        for row in failure_rows
        if (
            str(row.get("case_id")) in allowed_case_ids
            if allowed_case_ids is not None
            else str(row.get("case_id") or "").startswith(failure_case_prefix)
        )
    }
    case_ids = materialized_ids | failure_ids
    if materialized_ids & failure_ids:
        raise PipelineError("Caso externo aparece como materializado e falha técnica.")
    if len(case_ids) != int(expected_case_count):
        raise PipelineError(
            f"Cobertura externa divergente: {len(case_ids)} != {expected_case_count}."
        )
    training_ids = bundle.training_case_ids | bundle.training_patient_group_ids
    if case_ids & training_ids:
        raise PipelineError("Coorte externa contém caso/paciente visto no treino.")

    selected_keys = {
        (str(row["case_id"]), str(row["candidate_id"])) for row in selected_candidates
    }
    embeddings_by_case: dict[str, list[tuple[int, np.ndarray]]] = defaultdict(list)
    for row in embedding_rows:
        key = (str(row["case_id"]), str(row["candidate_id"]))
        if key not in selected_keys:
            continue
        vector = np.load(Path(embedding_root) / str(row["embedding_path"]), allow_pickle=False)
        embeddings_by_case[key[0]].append((int(row["panel_number"]), vector))

    predictions: list[dict[str, Any]] = []
    for case_id in sorted(case_ids):
        if case_id in failure_ids:
            predictions.append(
                {
                    "schema": PREDICTION_SCHEMA,
                    "case_id": case_id,
                    "dataset_id": dataset_id,
                    "prediction": "TECHNICAL_FAILURE",
                    "technical_failure": True,
                    "score": None,
                    "ground_truth_in_artifact": False,
                    "lesion_mask_read": False,
                    "research_only": True,
                }
            )
            continue
        ordered = sorted(embeddings_by_case.get(case_id, []), key=lambda item: item[0])
        if not ordered:
            raise PipelineError(f"Caso materializado sem embeddings: {case_id}.")
        decision = classify_embeddings(bundle, np.stack([item[1] for item in ordered]))
        predictions.append(
            {
                "schema": PREDICTION_SCHEMA,
                "case_id": case_id,
                "dataset_id": dataset_id,
                "prediction": decision["prediction"],
                "technical_failure": False,
                "score": decision["score"],
                "threshold": decision["threshold"],
                "panel_count": decision["panel_count"],
                "ground_truth_in_artifact": False,
                "lesion_mask_read": False,
                "research_only": True,
            }
        )

    output.mkdir(parents=True)
    predictions_path = output / "predictions.jsonl"
    _write_jsonl(predictions_path, predictions)
    body = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen_before_public_labels_opened",
        "bundle_signature": bundle.manifest["bundle_signature"],
        "candidate_dataset_signature": _json(
            Path(candidate_root) / "dataset_manifest.json", "Dataset candidato"
        )["dataset_signature"],
        "embedding_signature": embedding_manifest["embedding_signature"],
        "dataset_id": dataset_id,
        "case_manifest_sha256": case_manifest_sha256,
        "case_count": len(predictions),
        "materialized_case_count": len(materialized_ids),
        "technical_failure_count": len(failure_ids),
        "predictions_sha256": sha256_file(predictions_path),
        "training_case_overlap": 0,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    _atomic_json(output / "prediction_freeze.json", freeze)
    return freeze


def _wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def _metrics(rows: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    auc_labels: list[int] = []
    auc_scores: list[float] = []
    for row in rows:
        positive = labels[str(row["case_id"])] == "POSITIVE"
        if row.get("technical_failure") is True:
            failures += 1
            fn += int(positive)
            fp += int(not positive)
            continue
        predicted = row["prediction"] == "POSITIVE"
        tp += int(positive and predicted)
        tn += int(not positive and not predicted)
        fn += int(positive and not predicted)
        fp += int(not positive and predicted)
        auc_labels.append(int(positive))
        auc_scores.append(float(row["score"]))
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "case_count": len(rows), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "technical_failures": failures,
        "sensitivity": sensitivity, "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "roc_auc_computable_cases": _auc(auc_labels, auc_scores),
        "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
        "specificity_ci95_wilson": _wilson(tn, tn + fp),
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def evaluate_external_bundle(
    *,
    bundle_root: Path,
    prediction_root: Path,
    training_protocol_config_path: Path,
    workspace_root: Path,
    protected_dataset_ids: set[str],
    output_root: Path,
) -> dict[str, Any]:
    """Open public labels only after verifying the immutable prediction freeze."""

    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Avaliação externa já existe; saída é imutável.")
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze externo")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if freeze.get("schema") != FREEZE_SCHEMA or signature != canonical_sha256(unsigned):
        raise PipelineError("Freeze externo inválido ou com assinatura divergente.")
    predictions_path = Path(prediction_root) / "predictions.jsonl"
    if freeze.get("predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições externas foram alteradas.")
    predictions = _jsonl(predictions_path, "Predições externas")
    if any("label" in row or "ground_truth" in row for row in predictions):
        raise PipelineError("Predições externas contêm ground truth.")
    bundle = load_production_bundle(bundle_root)
    if freeze.get("bundle_signature") != bundle.manifest.get("bundle_signature"):
        raise PipelineError("Freeze pertence a outro bundle.")

    protected = {
        case.case_id: case
        for case in load_protected_cases(training_protocol_config_path, workspace_root)
        if case.dataset_id in protected_dataset_ids
    }
    covered = {str(row["case_id"]) for row in predictions}
    if covered != set(protected):
        raise PipelineError("Cobertura das predições diverge dos labels externos autorizados.")
    labels = {case_id: case.label for case_id, case in protected.items()}
    by_dataset = {
        dataset_id: _metrics(
            [row for row in predictions if protected[str(row["case_id"])].dataset_id == dataset_id],
            labels,
        )
        for dataset_id in sorted(protected_dataset_ids)
    }
    body = {
        "schema": EVALUATION_SCHEMA,
        "prediction_signature": freeze["prediction_signature"],
        "bundle_signature": freeze["bundle_signature"],
        "ground_truth_opened_after_predictions_frozen": True,
        "lesion_masks_read": 0,
        "technical_failures_count_as_errors": True,
        "overall": _metrics(predictions, labels),
        "by_dataset": by_dataset,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    report = {**body, "evaluation_signature": canonical_sha256(body)}
    output.mkdir(parents=True)
    _atomic_json(output / "evaluation.json", report)
    return report


__all__ = [
    "EVALUATION_SCHEMA", "FREEZE_SCHEMA", "PREDICTION_SCHEMA",
    "evaluate_external_bundle", "predict_external_bundle",
]
