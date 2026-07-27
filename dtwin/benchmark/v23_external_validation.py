"""Fail-closed preparation for a new independent v23 external validation.

This module freezes the qualification contract without opening a candidate
cohort. A second, explicit preflight can later bind a fresh image manifest and
protected labels to the contract before any inference is executed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.core import PipelineError


CONTRACT_SCHEMA = "argos-v23-independent-external-validation-contract-v1"
IMAGE_CASE_SCHEMA = "argos-v23-external-image-case-v1"
LABEL_SCHEMA = "argos-v23-external-protected-label-v1"
READY_PROTOCOL_SCHEMA = "argos-v23-independent-external-ready-protocol-v1"
CASE_ID_PATTERN = re.compile(r"^anon-[a-z0-9][a-z0-9-]{7,95}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MINIMUM_CASES_PER_CLASS = 40
CONSUMED_DATASET_IDS = (
    "openswisshcc",
    "lld_mmri",
    "liverhccseg",
    "chaos_mri",
    "tcga_lihc",
)


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
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
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos JSONL.")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _workspace_path(workspace: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise PipelineError("Manifesto externo contém caminho inseguro.")
    root = Path(workspace).resolve()
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Manifesto externo aponta para fora do workspace.") from exc
    return resolved


def _implementation_path(workspace: Path) -> Path:
    path = _workspace_path(
        workspace,
        "dtwin/benchmark/v23_external_validation.py",
    )
    if not path.is_file():
        raise PipelineError("Implementação da validação externa está ausente.")
    return path


def freeze_v23_external_validation_contract(
    *,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze success criteria and data rules before selecting a new cohort."""

    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    base = {
        "schema": CONTRACT_SCHEMA,
        "status": "frozen_awaiting_fresh_balanced_external_cohort",
        "algorithm": {
            "name": "argos_v23_frozen_shape_fusion",
            "calibrator_signature": baseline["calibrator_signature"],
            "decision_threshold": baseline["decision_threshold"],
            "weights": {
                "v11": 0.8,
                "candidate_weighted_linearity": 0.2,
            },
            "configuration_changes_after_freeze_allowed": False,
        },
        "target_condition": "focal_liver_lesion_suspicion",
        "cohort_requirements": {
            "minimum_positive_cases": MINIMUM_CASES_PER_CLASS,
            "minimum_negative_cases": MINIMUM_CASES_PER_CLASS,
            "single_patient_single_case": True,
            "expert_or_public_reference_standard_required": True,
            "both_classes_must_exist_in_the_same_source_dataset": True,
            "fresh_dataset_not_used_for_development_or_prior_evaluation": True,
            "consumed_dataset_ids_forbidden": list(CONSUMED_DATASET_IDS),
            "study_fingerprint_overlap_forbidden": True,
            "image_manifest_and_labels_must_match_exactly": True,
        },
        "primary_gate": {
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "maximum_raw_input_end_to_end_seconds_per_case": 180.0,
            "inconclusive_counts_as_error": True,
            "technical_failure_counts_as_error": True,
            "point_estimates_are_primary": True,
            "wilson_95_percent_intervals_required": True,
            "confusion_matrix_required": True,
            "roc_auc_secondary_only": True,
        },
        "execution_policy": {
            "one_shot_after_prediction_freeze": True,
            "predictions_must_be_frozen_before_label_evaluation": True,
            "no_threshold_selection_on_external_cohort": True,
            "no_case_exclusion_after_inference": True,
            "no_lesion_mask_in_inference": True,
            "no_ground_truth_in_inference": True,
            "human_review_required": True,
        },
        "source_hashes": {
            "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
            "implementation": _sha256(_implementation_path(Path(workspace_root))),
        },
        "development_result_context_only": {
            "case_count": baseline["case_count"],
            "sensitivity": baseline["primary_loocv_metrics"]["sensitivity"],
            "specificity": baseline["primary_loocv_metrics"]["specificity"],
            "qualified": False,
        },
        "candidate_images_bound": False,
        "protected_labels_bound": False,
        "ready_for_inference": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    contract = {**base, "contract_signature": _canonical_sha(base)}
    destination = Path(output_path).resolve()
    if destination.exists():
        existing = _json(destination, "Contrato externo existente")
        if existing != contract:
            raise PipelineError("Contrato externo existente diverge; sobrescrita recusada.")
        return existing
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, contract)
    return contract


def verify_v23_external_validation_contract(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    contract = _json(Path(contract_path).resolve(), "Contrato externo")
    signature = contract.get("contract_signature")
    unsigned = dict(contract)
    unsigned.pop("contract_signature", None)
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    expected_hashes = {
        "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
        "implementation": _sha256(_implementation_path(Path(workspace_root))),
    }
    if (
        contract.get("schema") != CONTRACT_SCHEMA
        or contract.get("status")
        != "frozen_awaiting_fresh_balanced_external_cohort"
        or signature != _canonical_sha(unsigned)
        or contract.get("source_hashes") != expected_hashes
        or contract.get("algorithm", {}).get("calibrator_signature")
        != baseline["calibrator_signature"]
        or contract.get("algorithm", {}).get("decision_threshold")
        != baseline["decision_threshold"]
        or contract.get("ready_for_inference") is not False
        or contract.get("qualified") is not False
    ):
        raise PipelineError("Contrato externo ausente, adulterado ou divergente.")
    return contract


def _validate_images(
    *,
    rows: list[dict[str, Any]],
    workspace_root: Path,
    forbidden_fingerprints: set[str],
) -> tuple[list[str], str, list[str]]:
    case_ids: list[str] = []
    dataset_ids: set[str] = set()
    fingerprints: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        dataset_id = row.get("source_dataset_id")
        fingerprint = row.get("study_fingerprint_sha256")
        files = row.get("files")
        if (
            row.get("schema") != IMAGE_CASE_SCHEMA
            or not isinstance(case_id, str)
            or CASE_ID_PATTERN.fullmatch(case_id) is None
            or not isinstance(dataset_id, str)
            or not dataset_id.strip()
            or dataset_id.lower() in CONSUMED_DATASET_IDS
            or not isinstance(fingerprint, str)
            or SHA_PATTERN.fullmatch(fingerprint) is None
            or fingerprint in forbidden_fingerprints
            or fingerprint in fingerprints
            or not isinstance(files, list)
            or not files
            or row.get("ground_truth_read") is not False
            or row.get("lesion_masks_used") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError(f"Registro de imagem externa inválido: {case_id}.")
        for item in files:
            role = str(item.get("role", "")).lower()
            relative = item.get("relative_path")
            size = item.get("bytes")
            digest = item.get("sha256")
            if (
                any(token in role for token in ("lesion", "tumor", "ground_truth"))
                or not isinstance(relative, str)
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size <= 0
                or not isinstance(digest, str)
                or SHA_PATTERN.fullmatch(digest) is None
            ):
                raise PipelineError(f"Arquivo externo inválido em {case_id}.")
            path = _workspace_path(workspace_root, relative)
            if (
                not path.is_file()
                or path.stat().st_size != size
                or _sha256(path) != digest
            ):
                raise PipelineError(f"Hash/bytes externos divergiram em {case_id}.")
        case_ids.append(case_id)
        dataset_ids.add(dataset_id.lower())
        fingerprints.add(fingerprint)
    if len(case_ids) != len(set(case_ids)) or len(dataset_ids) != 1:
        raise PipelineError("Coorte externa deve ter IDs únicos e uma única fonte.")
    return case_ids, next(iter(dataset_ids)), sorted(fingerprints)


def _validate_labels(
    rows: list[dict[str, Any]],
    expected_case_ids: list[str],
) -> tuple[int, int]:
    labels: dict[str, str] = {}
    for row in rows:
        case_id = row.get("case_id")
        label = row.get("label")
        if (
            row.get("schema") != LABEL_SCHEMA
            or not isinstance(case_id, str)
            or case_id in labels
            or label not in {"POSITIVE", "NEGATIVE"}
            or row.get("target_condition") != "focal_liver_lesion_suspicion"
            or row.get("reference_standard")
            not in {"public_expert_annotation", "independent_expert_review"}
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Label externo protegido inválido.")
        labels[case_id] = label
    if set(labels) != set(expected_case_ids):
        raise PipelineError("Labels e imagens da coorte externa não correspondem.")
    positives = sum(value == "POSITIVE" for value in labels.values())
    negatives = sum(value == "NEGATIVE" for value in labels.values())
    if positives < MINIMUM_CASES_PER_CLASS or negatives < MINIMUM_CASES_PER_CLASS:
        raise PipelineError(
            "Coorte externa requer ao menos 40 positivos e 40 negativos."
        )
    return positives, negatives


def preflight_v23_external_validation(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    image_manifest_path: Path,
    protected_labels_path: Path,
    workspace_root: Path,
    output_dir: Path,
    forbidden_fingerprints_path: Path | None = None,
    allow_protected_label_inventory: bool = False,
) -> dict[str, Any]:
    """Bind a fresh balanced cohort and publish a ready-to-infer protocol."""

    if allow_protected_label_inventory is not True:
        raise PipelineError("Inventário dos labels externos não foi autorizado.")
    contract = verify_v23_external_validation_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    forbidden: set[str] = set()
    if forbidden_fingerprints_path is not None:
        deny = _jsonl(forbidden_fingerprints_path, "Denylist de estudos consumidos")
        for row in deny:
            digest = row.get("study_fingerprint_sha256")
            if not isinstance(digest, str) or SHA_PATTERN.fullmatch(digest) is None:
                raise PipelineError("Denylist de estudos consumidos inválida.")
            forbidden.add(digest)
    image_path = Path(image_manifest_path).resolve()
    label_path = Path(protected_labels_path).resolve()
    image_rows = _jsonl(image_path, "Manifesto de imagens externas")
    label_rows = _jsonl(label_path, "Labels externos protegidos")
    case_ids, dataset_id, fingerprints = _validate_images(
        rows=image_rows,
        workspace_root=workspace_root,
        forbidden_fingerprints=forbidden,
    )
    positives, negatives = _validate_labels(label_rows, case_ids)
    if len(case_ids) != positives + negatives:
        raise PipelineError("Contagem externa inconsistente.")

    base = {
        "schema": READY_PROTOCOL_SCHEMA,
        "status": "ready_for_single_label_blind_external_inference",
        "contract_signature": contract["contract_signature"],
        "dataset_id": dataset_id,
        "case_count": len(case_ids),
        "positive_count_protected": positives,
        "negative_count_protected": negatives,
        "case_ids": case_ids,
        "study_fingerprints_sha256": hashlib.sha256(
            "\n".join(fingerprints).encode("ascii")
        ).hexdigest(),
        "image_manifest_sha256": _sha256(image_path),
        "protected_labels_sha256": _sha256(label_path),
        "forbidden_fingerprint_count": len(forbidden),
        "algorithm": contract["algorithm"],
        "primary_gate": contract["primary_gate"],
        "execution_policy": contract["execution_policy"],
        "predictions_present": False,
        "ground_truth_available_to_inference": False,
        "lesion_masks_available_to_inference": False,
        "ready_for_inference": True,
        "metrics_calculated": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Preflight externo existente; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_external_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "protocol.json", protocol)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return protocol


__all__ = [
    "CONTRACT_SCHEMA",
    "CONSUMED_DATASET_IDS",
    "IMAGE_CASE_SCHEMA",
    "LABEL_SCHEMA",
    "MINIMUM_CASES_PER_CLASS",
    "READY_PROTOCOL_SCHEMA",
    "freeze_v23_external_validation_contract",
    "preflight_v23_external_validation",
    "verify_v23_external_validation_contract",
]
