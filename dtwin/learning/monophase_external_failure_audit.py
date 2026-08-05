"""Retrospective, development-only audit of monophase external false negatives.

The audit verifies the immutable prediction/evaluation artifacts first. Public
development lesion masks are then used only to measure whether a lesion plane
was present in the already-rendered evidence. Holdout masks are deliberately
unsupported and never opened.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import nibabel as nib
import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.external_bundle_evaluation import _metrics
from dtwin.learning.protocol import canonical_sha256, sha256_file


AUDIT_SCHEMA = "oren-monophase-external-failure-audit-v1"
CASE_SCHEMA = "oren-monophase-external-failure-case-v1"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"Registro JSONL inválido: {path}")
    return rows


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _atomic_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _verify_freezes(prediction_root: Path, evaluation_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    freeze = _json(prediction_root / "prediction_freeze.json")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do freeze monofásico externo divergiu.")
    predictions_path = prediction_root / "predictions.jsonl"
    if freeze.get("predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições monofásicas externas foram alteradas.")
    predictions = _jsonl(predictions_path)
    evaluation = _json(evaluation_path)
    evaluation_unsigned = dict(evaluation)
    evaluation_signature = evaluation_unsigned.pop("evaluation_signature", None)
    if evaluation_signature != canonical_sha256(evaluation_unsigned):
        raise PipelineError("Assinatura da avaliação monofásica externa divergiu.")
    if evaluation.get("prediction_signature") != signature:
        raise PipelineError("Avaliação não pertence ao freeze de predições informado.")
    return predictions, evaluation


def _labels(path: Path, cohort: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in _jsonl(path):
        case_id = str(row.get("case_id") or "")
        label = str(row.get("label") or "").upper()
        if not case_id or label not in {"POSITIVE", "NEGATIVE"}:
            raise PipelineError(f"Label protegido inválido em {path}.")
        result[case_id] = {"label": label, "cohort": cohort}
    return result


def _candidate_indices(candidate_records_path: Path) -> dict[str, list[int]]:
    by_case: dict[str, set[int]] = {}
    for row in _jsonl(candidate_records_path):
        if row.get("dataset_id") != "openswisshcc":
            continue
        case_id = str(row["case_id"])
        by_case.setdefault(case_id, set()).update(int(value) for value in row.get("slice_indices") or [])
    return {case_id: sorted(values) for case_id, values in by_case.items()}


def _development_localizer(path: Path) -> dict[str, dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        return {str(row["case_id"]): row for row in csv.DictReader(stream)}


def _mask_array(archive: zipfile.ZipFile, member: str) -> np.ndarray:
    try:
        compressed = archive.read(member)
        raw = gzip.decompress(compressed) if member.endswith(".gz") else compressed
        image = nib.Nifti1Image.from_bytes(raw)
    except (KeyError, OSError, ValueError) as exc:
        raise PipelineError(f"Máscara pública de desenvolvimento inválida: {member}") from exc
    array = np.asanyarray(image.dataobj)
    if array.ndim != 3:
        raise PipelineError(f"Máscara pública não é 3D: {member}")
    return array > 0


def _development_visibility(
    *,
    archive: zipfile.ZipFile,
    venous_masks: list[dict[str, Any]],
    represented_indices: list[int],
) -> dict[str, Any]:
    rendered = set(int(value) for value in represented_indices)
    lesions: list[dict[str, Any]] = []
    total_voxels = represented_voxels = 0
    for item in venous_masks:
        member = str(item["archive_member"])
        mask = _mask_array(archive, member)
        z_counts = np.count_nonzero(mask, axis=(0, 1))
        lesion_indices = np.flatnonzero(z_counts).astype(int).tolist()
        voxel_count = int(z_counts.sum())
        visible_voxels = int(sum(int(z_counts[index]) for index in rendered if 0 <= index < len(z_counts)))
        total_voxels += voxel_count
        represented_voxels += visible_voxels
        lesions.append(
            {
                "lesion_id": str(item.get("lesion_id") or "unknown"),
                "axial_indices": lesion_indices,
                "axial_plane_count": len(lesion_indices),
                "voxel_count": voxel_count,
                "represented_axial_indices": sorted(rendered.intersection(lesion_indices)),
                "exact_rendered_plane_hit": visible_voxels > 0,
                "represented_voxel_count": visible_voxels,
                "represented_voxel_fraction": visible_voxels / voxel_count if voxel_count else 0.0,
            }
        )
    hit_count = sum(int(row["exact_rendered_plane_hit"]) for row in lesions)
    return {
        "manual_venous_lesion_count": len(lesions),
        "lesions": lesions,
        "lesion_hit_count": hit_count,
        "all_lesions_hit": bool(lesions) and hit_count == len(lesions),
        "any_lesion_hit": hit_count > 0,
        "total_lesion_voxels": total_voxels,
        "represented_lesion_voxels": represented_voxels,
        "represented_lesion_voxel_fraction": (
            represented_voxels / total_voxels if total_voxels else 0.0
        ),
    }


def build_monophase_external_failure_audit(
    *,
    prediction_root: Path,
    evaluation_path: Path,
    development_labels_path: Path,
    holdout_labels_path: Path,
    candidate_records_path: Path,
    development_audit_protocol_path: Path,
    development_lesion_archive_path: Path,
    development_localizer_csv_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists():
        raise PipelineError("Auditoria monofásica externa já existe; sobrescrita recusada.")
    predictions, evaluation = _verify_freezes(Path(prediction_root), Path(evaluation_path))
    labels = _labels(development_labels_path, "development")
    overlap = set(labels) & set(_labels(holdout_labels_path, "holdout"))
    if overlap:
        raise PipelineError("Casos se sobrepõem entre development e holdout.")
    labels.update(_labels(holdout_labels_path, "holdout"))
    if set(labels) != {str(row["case_id"]) for row in predictions}:
        raise PipelineError("Cobertura dos labels não corresponde às predições congeladas.")
    reproduced = _metrics(predictions, {key: value["label"] for key, value in labels.items()})
    expected = evaluation.get("overall") or {}
    for key in ("tp", "tn", "fp", "fn", "technical_failures", "sensitivity", "specificity"):
        if reproduced.get(key) != expected.get(key):
            raise PipelineError(f"Baseline externo não reproduzido no campo {key}.")

    protocol = _json(development_audit_protocol_path)
    if (protocol.get("safety") or {}).get("holdout_opened") is not False:
        raise PipelineError("Protocolo de máscaras não preserva o holdout fechado.")
    protocol_cases = {str(row["case_id"]): row for row in protocol.get("cases") or []}
    indices = _candidate_indices(candidate_records_path)
    localizer = _development_localizer(development_localizer_csv_path)
    failures: list[dict[str, Any]] = []
    causes: Counter[str] = Counter()
    with zipfile.ZipFile(development_lesion_archive_path) as archive:
        for prediction in predictions:
            case_id = str(prediction["case_id"])
            protected = labels[case_id]
            if protected["label"] != "POSITIVE" or prediction.get("prediction") == "POSITIVE":
                continue
            cohort = protected["cohort"]
            represented = indices.get(case_id, [])
            row: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "cohort": cohort,
                "error_type": "false_negative",
                "prediction": str(prediction.get("prediction")),
                "technical_failure": bool(prediction.get("technical_failure")),
                "score": prediction.get("score"),
                "threshold": prediction.get("threshold"),
                "score_margin": (
                    float(prediction["score"]) - float(prediction["threshold"])
                    if prediction.get("score") is not None and prediction.get("threshold") is not None
                    else None
                ),
                "represented_axial_indices": represented,
                "represented_axial_count": len(represented),
                "lesion_masks_used_for_inference": False,
                "lesion_masks_sent_to_model": False,
                "research_only": True,
                "clinical_use_allowed": False,
            }
            if prediction.get("technical_failure"):
                cause = "technical_failure"
                row["mask_audit_status"] = "not_needed_for_technical_failure"
            elif cohort == "holdout":
                cause = "holdout_mask_closed"
                row["mask_audit_status"] = "not_opened_holdout_mask_closed"
            else:
                protocol_case = protocol_cases.get(case_id)
                if not protocol_case or not protocol_case.get("venous_masks"):
                    cause = "development_manual_venous_mask_unavailable"
                    row["mask_audit_status"] = "no_public_venous_mask"
                else:
                    visibility = _development_visibility(
                        archive=archive,
                        venous_masks=list(protocol_case["venous_masks"]),
                        represented_indices=represented,
                    )
                    row["mask_audit_status"] = "development_public_mask_opened_retrospectively"
                    row["visibility"] = visibility
                    local = localizer.get(case_id) or {}
                    row["prior_localizer_stack_visibility_case_hit"] = (
                        str(local.get("stack_visibility_case_hit", "")).lower() == "true"
                    )
                    if not represented:
                        cause = "panel_collection_missing"
                    elif not visibility["any_lesion_hit"]:
                        cause = "lesion_not_on_rendered_axial_plane"
                    else:
                        cause = "lesion_on_rendered_plane_but_classifier_negative"
            row["primary_failure_cause"] = cause
            causes[cause] += 1
            failures.append(row)

    if len(failures) != int(expected.get("fn", -1)):
        raise PipelineError("Quantidade de falsos negativos auditados divergiu do baseline.")
    output_root.mkdir(parents=True)
    cases_path = output_root / "false_negative_cases.jsonl"
    _atomic_jsonl(cases_path, failures)
    body = {
        "schema": AUDIT_SCHEMA,
        "status": "complete_retrospective_audit_with_holdout_masks_closed",
        "baseline": reproduced,
        "false_negative_count": len(failures),
        "failure_causes": dict(sorted(causes.items())),
        "development_false_negative_count": sum(row["cohort"] == "development" for row in failures),
        "holdout_false_negative_count": sum(row["cohort"] == "holdout" for row in failures),
        "holdout_lesion_masks_opened": False,
        "development_lesion_masks_used_retrospectively_only": True,
        "lesion_masks_used_for_inference": False,
        "cases_sha256": sha256_file(cases_path),
        "source_hashes": {
            "predictions": sha256_file(Path(prediction_root) / "predictions.jsonl"),
            "evaluation": sha256_file(evaluation_path),
            "candidate_records": sha256_file(candidate_records_path),
            "development_audit_protocol": sha256_file(development_audit_protocol_path),
            "development_lesion_archive": sha256_file(development_lesion_archive_path),
        },
        "research_only": True,
        "clinical_use_allowed": False,
    }
    result = {**body, "audit_signature": canonical_sha256(body)}
    _atomic_json(output_root / "summary.json", result)
    return result


__all__ = ["AUDIT_SCHEMA", "CASE_SCHEMA", "build_monophase_external_failure_audit"]
