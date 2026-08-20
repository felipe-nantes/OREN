"""Bind the 132-case OpenSwissHCC inventory for retrospective v23 evaluation.

Phase 2 reads the already-public case labels only to verify patient uniqueness,
class counts and deterministic stratification.  It never reads image pixels or
lesion masks and does not calculate predictions or metrics.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.v23_retrospective_multicohort import (
    verify_retrospective_multicohort_contract,
)
from dtwin.core import PipelineError

SUMMARY_SCHEMA = "argos-v23-retrospective-multicohort-phase2-summary-v1"
CASE_SCHEMA = "argos-v23-retrospective-openswisshcc-case-inventory-v1"
FOLD_SCHEMA = "argos-v23-retrospective-openswisshcc-protected-fold-v1"
SPLIT_SCHEMA = "argos-v23-retrospective-openswisshcc-split-protocol-v1"
REPEATS = 50
FOLDS = 5
SEED = 20260720
REQUIRED_DYNAMIC_ROLES = ("t1_native", "t1_venous", "t1_delayed")


def _load_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _rows_by_case(
    rows: list[dict[str, Any]], description: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in result:
            raise PipelineError(f"{description} contém case_id inválido ou duplicado.")
        result[case_id] = row
    return result


def _validate_input_row(
    row: dict[str, Any], *, split: str, input_root: Path
) -> tuple[list[str], str, int]:
    schemas = {
        "development": "argos-public-liver-mri-input-v1",
        "holdout_consumed": "argos-public-liver-mri-holdout-input-v1",
    }
    files = row.get("files")
    if (
        row.get("schema") != schemas[split]
        or row.get("research_only") is not True
        or row.get("clinical_use_allowed") is not False
        or not isinstance(files, list)
        or not files
    ):
        raise PipelineError(f"Entrada OpenSwissHCC inválida: {row.get('case_id')}.")
    roles: list[str] = []
    fingerprint_rows: list[list[Any]] = []
    total_bytes = 0
    for item in files:
        role = item.get("role")
        relative = item.get("relative_path")
        size = item.get("bytes")
        digest = item.get("sha256")
        if (
            not isinstance(role, str)
            or not role
            or any(token in role.lower() for token in ("lesion", "tumor"))
            or not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise PipelineError(f"Arquivo OpenSwissHCC inválido: {row.get('case_id')}.")
        path = (input_root / relative).resolve()
        try:
            path.relative_to(input_root.resolve())
        except ValueError as exc:
            raise PipelineError("Manifesto OpenSwissHCC contém caminho inseguro.") from exc
        if not path.is_file() or path.stat().st_size != size:
            raise PipelineError(
                f"Arquivo OpenSwissHCC ausente ou com bytes divergentes: {relative}."
            )
        roles.append(role)
        fingerprint_rows.append([role, digest, size])
        total_bytes += size
    fingerprint = _canonical_sha(sorted(fingerprint_rows))
    return sorted(roles), fingerprint, total_bytes


def _has_exact_dynamic_roles(roles: list[str]) -> tuple[bool, list[str]]:
    available = set(roles)
    missing = [role for role in REQUIRED_DYNAMIC_ROLES if role not in available]
    if (
        "t1_arterial" not in available
        and not any(role.startswith("t1_arterial_ttc_") for role in available)
    ):
        missing.append("t1_arterial_any")
    return not missing, missing


def _stratified_repeated_folds(
    labels: dict[str, str],
    *,
    repeats: int = REPEATS,
    folds: int = FOLDS,
    seed: int = SEED,
) -> dict[str, list[int]]:
    if repeats <= 0 or folds < 2:
        raise PipelineError("Configuração de folds inválida.")
    assignments = {case_id: [] for case_id in labels}
    for repeat in range(repeats):
        for label in ("POSITIVE", "NEGATIVE"):
            case_ids = [case_id for case_id, value in labels.items() if value == label]
            ranked = sorted(
                case_ids,
                key=lambda case_id: hashlib.sha256(
                    f"{seed}|{repeat}|{label}|{case_id}".encode("utf-8")
                ).hexdigest(),
            )
            for position, case_id in enumerate(ranked):
                assignments[case_id].append(position % folds)
    return assignments


def _validate_labels(
    rows: list[dict[str, Any]], expected_cases: set[str]
) -> tuple[dict[str, str], dict[str, str]]:
    labels: dict[str, str] = {}
    patients: dict[str, str] = {}
    public_subjects: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        label = row.get("label")
        public_subject = row.get("public_subject_id")
        if (
            row.get("schema") != "argos-openswisshcc-ground-truth-v1"
            or not isinstance(case_id, str)
            or case_id in labels
            or label not in {"POSITIVE", "NEGATIVE"}
            or not isinstance(public_subject, str)
            or not public_subject.startswith("sub-")
            or public_subject in public_subjects
            or row.get("review_status") != "dataset_expert_validated"
        ):
            raise PipelineError("Labels OpenSwissHCC inválidos ou pacientes duplicados.")
        labels[case_id] = label
        patients[case_id] = case_id
        public_subjects.add(public_subject)
    if set(labels) != expected_cases:
        raise PipelineError("Inventário de imagens e labels OpenSwissHCC divergem.")
    return labels, patients


def _signal_ids(path: Path, schemas: set[str], description: str) -> set[str]:
    rows = _load_jsonl(path, description)
    result: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        if (
            row.get("schema") not in schemas
            or not isinstance(case_id, str)
            or case_id in result
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
        ):
            raise PipelineError(f"{description} contém registro inválido.")
        signals = row.get("signals")
        if not isinstance(signals, dict) or not {
            "medgemma_v4_uncertainty_margin",
            "medsiglip_v5_inverse_sagittal",
            "localizer_v10_log_volume",
        }.issubset(signals):
            raise PipelineError(f"{description} não contém os três sinais v11.")
        result.add(case_id)
    return result


def _shape_ids(path: Path) -> set[str]:
    rows = _load_jsonl(path, "Features geométricas v23")
    result: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        features = row.get("features")
        if (
            row.get("schema") != "argos-openswisshcc-candidate-shape-case-v23"
            or not isinstance(case_id, str)
            or case_id in result
            or row.get("ground_truth_read") is not False
            or row.get("ground_truth_lesion_mask_used") is not False
            or not isinstance(features, dict)
            or not isinstance(features.get("candidate_weighted_linearity"), (int, float))
        ):
            raise PipelineError("Features geométricas v23 inválidas.")
        result.add(case_id)
    return result


def build_phase2_openswisshcc_inventory(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    development_manifest_path: Path,
    development_labels_path: Path,
    holdout_manifest_path: Path,
    holdout_labels_path: Path,
    development_v11_signals_path: Path,
    holdout_v11_signals_path: Path,
    development_shape_features_path: Path,
    output_dir: Path,
    expected_cases: int = 132,
    expected_positive: int = 63,
    expected_negative: int = 69,
) -> dict[str, Any]:
    """Bind cases, labels and existing signal availability without scoring."""

    workspace = Path(workspace_root).resolve()
    contract = verify_retrospective_multicohort_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace,
    )
    dev_manifest_path = Path(development_manifest_path).resolve()
    hold_manifest_path = Path(holdout_manifest_path).resolve()
    dev_rows = _load_jsonl(dev_manifest_path, "Manifesto OpenSwissHCC development")
    hold_rows = _load_jsonl(hold_manifest_path, "Manifesto OpenSwissHCC holdout")
    dev = _rows_by_case(dev_rows, "Manifesto development")
    hold = _rows_by_case(hold_rows, "Manifesto holdout")
    if set(dev) & set(hold):
        raise PipelineError("Mesmo caso aparece em development e holdout.")
    all_cases = set(dev) | set(hold)
    if len(all_cases) != expected_cases:
        raise PipelineError(
            f"OpenSwissHCC deveria conter {expected_cases} casos, recebeu {len(all_cases)}."
        )

    label_rows = _load_jsonl(
        Path(development_labels_path).resolve(), "Labels development"
    ) + _load_jsonl(Path(holdout_labels_path).resolve(), "Labels holdout")
    labels, patient_groups = _validate_labels(label_rows, all_cases)
    positives = sum(value == "POSITIVE" for value in labels.values())
    negatives = sum(value == "NEGATIVE" for value in labels.values())
    if positives != expected_positive or negatives != expected_negative:
        raise PipelineError("Contagens de classe OpenSwissHCC divergiram do protocolo.")

    dev_v11 = _signal_ids(
        Path(development_v11_signals_path).resolve(),
        {"argos-openswisshcc-v20-blind-fusion-signal-v1"},
        "Sinais v11 development",
    )
    hold_v11 = _signal_ids(
        Path(holdout_v11_signals_path).resolve(),
        {"argos-public-independent-v21-raw-signals-v1"},
        "Sinais v11 holdout",
    )
    v11_ids = dev_v11 | hold_v11
    shape_ids = _shape_ids(Path(development_shape_features_path).resolve())
    if not dev_v11 <= set(dev) or not hold_v11 <= set(hold) or not shape_ids <= all_cases:
        raise PipelineError("Sinais existentes apontam para caso fora do inventário.")

    inventory: list[dict[str, Any]] = []
    exact_phase_count = 0
    total_declared_bytes = 0
    for case_id in sorted(all_cases):
        source_split = "development" if case_id in dev else "holdout_consumed"
        row = dev.get(case_id) or hold[case_id]
        manifest_path = dev_manifest_path if case_id in dev else hold_manifest_path
        input_root = manifest_path.parent.parent / "inputs"
        roles, study_fingerprint, declared_bytes = _validate_input_row(
            row, split=source_split, input_root=input_root
        )
        exact_phases, missing_phases = _has_exact_dynamic_roles(roles)
        exact_phase_count += int(exact_phases)
        total_declared_bytes += declared_bytes
        v11 = case_id in v11_ids
        shape = case_id in shape_ids
        inventory.append(
            {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "patient_group_id": patient_groups[case_id],
                "source_split": source_split,
                "study_fingerprint_sha256": study_fingerprint,
                "input_manifest_row_sha256": _canonical_sha(row),
                "declared_file_count": len(row["files"]),
                "declared_bytes": declared_bytes,
                "available_roles": roles,
                "required_dynamic_phases_available": exact_phases,
                "missing_required_dynamic_phases": missing_phases,
                "existing_signals": {
                    "v11_complete": v11,
                    "candidate_weighted_linearity": shape,
                    "exact_v23_score_inputs_complete": v11 and shape and exact_phases,
                },
                "label_in_public_inventory": False,
                "lesion_mask_used": False,
                "image_pixels_read": False,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )

    repeated = _stratified_repeated_folds(labels)
    protected_folds = [
        {
            "schema": FOLD_SCHEMA,
            "case_id": case_id,
            "patient_group_id": patient_groups[case_id],
            "label": labels[case_id],
            "loocv_outer_fold_id": case_id,
            "repeated_5fold_outer_assignments": repeated[case_id],
        }
        for case_id in sorted(all_cases)
    ]
    split_body = {
        "schema": SPLIT_SCHEMA,
        "primary_estimator": "patient_level_leave_one_out",
        "primary_case_count": expected_cases,
        "fixed_v23_weights": True,
        "ecdf_fit_on_outer_training_only": True,
        "threshold_fit_on_outer_training_only": True,
        "held_out_case_excluded_from_transform_and_threshold": True,
        "future_candidate_selection_requires_inner_training_only_folds": True,
        "inner_fold_algorithm": "sha256_ranked_stratified_round_robin_v1",
        "robustness_estimator": {
            "repeats": REPEATS,
            "folds": FOLDS,
            "seed": SEED,
            "assignment_algorithm": "sha256_ranked_stratified_round_robin_v1",
        },
        "group_key": "patient_group_id",
        "one_case_per_patient_verified": True,
        "best_fold_cannot_qualify": True,
    }
    split_protocol = {
        **split_body,
        "split_protocol_signature": _canonical_sha(split_body),
    }

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Fase 2 já existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_multicohort_phase2_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_jsonl(staging / "case_inventory.jsonl", inventory)
        _write_jsonl(
            staging / "protected_ground_truth/fold_assignments.jsonl",
            protected_folds,
        )
        _write_json(staging / "split_protocol.json", split_protocol)
        inventory_path = staging / "case_inventory.jsonl"
        folds_path = staging / "protected_ground_truth/fold_assignments.jsonl"
        split_path = staging / "split_protocol.json"
        exact_ready = sum(
            row["existing_signals"]["exact_v23_score_inputs_complete"]
            for row in inventory
        )
        availability_by_split = {}
        for split in ("development", "holdout_consumed"):
            split_rows = [row for row in inventory if row["source_split"] == split]
            availability_by_split[split] = {
                "case_count": len(split_rows),
                "required_dynamic_phases_available_count": sum(
                    row["required_dynamic_phases_available"] for row in split_rows
                ),
                "v11_complete_count": sum(
                    row["existing_signals"]["v11_complete"] for row in split_rows
                ),
                "candidate_weighted_linearity_complete_count": sum(
                    row["existing_signals"]["candidate_weighted_linearity"]
                    for row in split_rows
                ),
                "exact_v23_score_inputs_complete_count": sum(
                    row["existing_signals"]["exact_v23_score_inputs_complete"]
                    for row in split_rows
                ),
            }
        summary_body = {
            "schema": SUMMARY_SCHEMA,
            "status": "phase2_inventory_and_splits_frozen",
            "contract_signature": contract["contract_signature"],
            "case_count": expected_cases,
            "positive_count_protected": positives,
            "negative_count_protected": negatives,
            "development_case_count": len(dev),
            "holdout_consumed_case_count": len(hold),
            "unique_patient_count": len(set(patient_groups.values())),
            "all_required_dynamic_phases_available_count": exact_phase_count,
            "v11_signals_complete_count": len(v11_ids),
            "candidate_weighted_linearity_complete_count": len(shape_ids),
            "exact_v23_score_inputs_complete_count": exact_ready,
            "exact_v23_score_inputs_missing_count": expected_cases - exact_ready,
            "missing_component_counts": {
                "v11": expected_cases - len(v11_ids),
                "candidate_weighted_linearity": expected_cases - len(shape_ids),
            },
            "signal_availability_by_split": availability_by_split,
            "total_declared_input_bytes": total_declared_bytes,
            "artifacts": {
                "case_inventory": "case_inventory.jsonl",
                "case_inventory_sha256": _sha256(inventory_path),
                "protected_fold_assignments":
                    "protected_ground_truth/fold_assignments.jsonl",
                "protected_fold_assignments_sha256": _sha256(folds_path),
                "split_protocol": "split_protocol.json",
                "split_protocol_sha256": _sha256(split_path),
                "development_manifest_sha256": _sha256(dev_manifest_path),
                "holdout_manifest_sha256": _sha256(hold_manifest_path),
                "development_labels_sha256":
                    _sha256(Path(development_labels_path).resolve()),
                "holdout_labels_sha256": _sha256(Path(holdout_labels_path).resolve()),
                "development_v11_signals_sha256":
                    _sha256(Path(development_v11_signals_path).resolve()),
                "holdout_v11_signals_sha256":
                    _sha256(Path(holdout_v11_signals_path).resolve()),
                "development_shape_features_sha256":
                    _sha256(Path(development_shape_features_path).resolve()),
            },
            "safety": {
                "labels_read_for_stratification_and_inventory_only": True,
                "labels_exposed_in_public_case_inventory": False,
                "lesion_masks_read": 0,
                "image_pixels_read": 0,
                "predictions_calculated": False,
                "metrics_calculated": False,
                "file_existence_and_declared_bytes_verified": True,
                "declared_file_sha256_rehashed_from_image_bytes": False,
            },
            "next_gate": {
                "ready_for_missing_signal_generation": True,
                "ready_for_v23_scoring": exact_ready == expected_cases,
                "ready_for_metrics": False,
                "required_missing_signal_cases": expected_cases - exact_ready,
            },
            "research_only": True,
            "clinical_use_allowed": False,
        }
        summary = {**summary_body, "phase2_signature": _canonical_sha(summary_body)}
        _write_json(staging / "summary.json", summary)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return summary


def verify_phase2_openswisshcc_inventory(
    *,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    expected_cases: int = 132,
    expected_positive: int = 63,
    expected_negative: int = 69,
) -> dict[str, Any]:
    root = Path(phase2_root).resolve()
    contract = verify_retrospective_multicohort_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    summary = _load_object(root / "summary.json", "Resumo da Fase 2")
    unsigned = dict(summary)
    signature = unsigned.pop("phase2_signature", None)
    artifacts = summary.get("artifacts")
    if (
        summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("status") != "phase2_inventory_and_splits_frozen"
        or signature != _canonical_sha(unsigned)
        or summary.get("contract_signature") != contract["contract_signature"]
        or summary.get("case_count") != expected_cases
        or summary.get("positive_count_protected") != expected_positive
        or summary.get("negative_count_protected") != expected_negative
        or summary.get("unique_patient_count") != expected_cases
        or not isinstance(artifacts, dict)
    ):
        raise PipelineError("Resumo da Fase 2 adulterado ou divergente.")
    for key, relative_key in (
        ("case_inventory_sha256", "case_inventory"),
        ("protected_fold_assignments_sha256", "protected_fold_assignments"),
        ("split_protocol_sha256", "split_protocol"),
    ):
        relative = artifacts.get(relative_key)
        digest = artifacts.get(key)
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(digest, str)
            or _sha256(root / relative) != digest
        ):
            raise PipelineError("Artefato da Fase 2 adulterado.")
    inventory = _load_jsonl(root / artifacts["case_inventory"], "Inventário da Fase 2")
    folds = _load_jsonl(
        root / artifacts["protected_fold_assignments"],
        "Folds protegidos da Fase 2",
    )
    if (
        len(inventory) != expected_cases
        or len(folds) != expected_cases
        or len({row.get("case_id") for row in inventory}) != expected_cases
        or {row.get("case_id") for row in inventory}
        != {row.get("case_id") for row in folds}
        or any("label" in row for row in inventory)
        or any(row.get("label_in_public_inventory") is not False for row in inventory)
    ):
        raise PipelineError("Inventário/folds da Fase 2 inconsistentes.")
    protected_labels: dict[str, str] = {}
    protected_patients: set[str] = set()
    protected_assignments: dict[str, list[int]] = {}
    for row in folds:
        case_id = row.get("case_id")
        patient = row.get("patient_group_id")
        label = row.get("label")
        assignments = row.get("repeated_5fold_outer_assignments")
        if (
            row.get("schema") != FOLD_SCHEMA
            or not isinstance(case_id, str)
            or not isinstance(patient, str)
            or patient in protected_patients
            or label not in {"POSITIVE", "NEGATIVE"}
            or not isinstance(assignments, list)
            or len(assignments) != REPEATS
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value < FOLDS
                for value in assignments
            )
        ):
            raise PipelineError("Folds protegidos da Fase 2 inválidos.")
        protected_labels[case_id] = label
        protected_patients.add(patient)
        protected_assignments[case_id] = assignments
    if (
        sum(value == "POSITIVE" for value in protected_labels.values())
        != expected_positive
        or sum(value == "NEGATIVE" for value in protected_labels.values())
        != expected_negative
        or protected_assignments != _stratified_repeated_folds(protected_labels)
    ):
        raise PipelineError("Estratificação protegida da Fase 2 divergiu.")
    split = _load_object(root / artifacts["split_protocol"], "Protocolo de splits")
    split_unsigned = dict(split)
    split_signature = split_unsigned.pop("split_protocol_signature", None)
    if (
        split.get("schema") != SPLIT_SCHEMA
        or split_signature != _canonical_sha(split_unsigned)
        or split.get("one_case_per_patient_verified") is not True
        or split.get("ecdf_fit_on_outer_training_only") is not True
        or split.get("threshold_fit_on_outer_training_only") is not True
    ):
        raise PipelineError("Protocolo de splits da Fase 2 inválido.")
    return summary


__all__ = [
    "CASE_SCHEMA",
    "FOLD_SCHEMA",
    "FOLDS",
    "REPEATS",
    "SEED",
    "SPLIT_SCHEMA",
    "SUMMARY_SCHEMA",
    "_stratified_repeated_folds",
    "build_phase2_openswisshcc_inventory",
    "verify_phase2_openswisshcc_inventory",
]
