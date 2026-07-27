"""Fail-closed verification of the frozen OpenSwissHCC v23 baseline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_v23_shape_fusion import (
    PRIMARY_SHAPE_FEATURE,
    SHAPE_WEIGHT,
    V11_WEIGHT,
    _validated_calibrator,
)
from dtwin.core import PipelineError


LOCK_SCHEMA = "argos-openswisshcc-v23-baseline-lock-v1"


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser um objeto JSON.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato v23 ausente: {path}.") from exc
    return digest.hexdigest()


def _resolve_locked_path(workspace: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise PipelineError("Lock v23 contém caminho inseguro.")
    root = workspace.resolve()
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Lock v23 aponta para fora do workspace.") from exc
    return resolved


def verify_v23_baseline_lock(*, lock_path: Path, workspace_root: Path) -> dict[str, Any]:
    """Verify code, inputs, outputs, metrics and safety flags of frozen v23."""

    lock = _load_json(Path(lock_path).resolve(), "Lock do baseline v23")
    if (
        lock.get("schema") != LOCK_SCHEMA
        or lock.get("status") != "frozen_reproducible_development_baseline"
        or lock.get("development_only") is not True
        or lock.get("qualified") is not False
        or lock.get("independent_balanced_validation_required") is not True
        or lock.get("holdout_v21_reuse_forbidden") is not True
    ):
        raise PipelineError("Contrato metodológico do lock v23 é inválido.")

    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        raise PipelineError("Lock v23 não contém inventário de arquivos.")
    verified_paths: dict[str, Path] = {}
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, dict):
            raise PipelineError("Inventário do lock v23 é inválido.")
        path = _resolve_locked_path(Path(workspace_root), relative)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PipelineError(f"Artefato v23 ausente: {relative}.") from exc
        if (
            size != expected.get("bytes")
            or _sha256(path) != expected.get("sha256")
        ):
            raise PipelineError(f"Artefato v23 ausente, alterado ou truncado: {relative}.")
        verified_paths[relative] = path

    roles = lock.get("artifact_roles")
    if not isinstance(roles, dict):
        raise PipelineError("Papéis dos artefatos v23 estão ausentes.")
    required_roles = {"evaluation", "calibrator", "timing"}
    if not required_roles.issubset(roles) or any(
        value not in verified_paths for value in roles.values()
    ):
        raise PipelineError("Papéis dos artefatos v23 não correspondem ao inventário.")

    evaluation = _load_json(verified_paths[roles["evaluation"]], "Avaliação v23")
    metrics = evaluation.get("primary_loocv_metrics")
    expected_metrics = lock.get("expected_primary_loocv_metrics")
    if (
        not isinstance(metrics, dict)
        or not isinstance(expected_metrics, dict)
        or any(metrics.get(name) != expected for name, expected in expected_metrics.items())
        or evaluation.get("weights")
        != {"v11": V11_WEIGHT, PRIMARY_SHAPE_FEATURE: SHAPE_WEIGHT}
        or evaluation.get("development_point_gate_passed") is not True
        or evaluation.get("development_robustness_gate_passed") is not False
        or evaluation.get("final_system_qualification_claimed") is not False
        or evaluation.get("lesion_masks_read") is not False
        or evaluation.get("holdout_opened") is not False
        or evaluation.get("qualified") is not False
    ):
        raise PipelineError("Avaliação v23 diverge do baseline metodológico congelado.")

    repeated = evaluation.get("repeated_stratified_5fold")
    expected_repeated = lock.get("expected_repeated_stratified_5fold")
    if (
        not isinstance(repeated, dict)
        or not isinstance(expected_repeated, dict)
        or any(repeated.get(name) != expected for name, expected in expected_repeated.items())
    ):
        raise PipelineError("Estabilidade repetida v23 diverge do baseline congelado.")

    calibrator = _validated_calibrator(
        _load_json(verified_paths[roles["calibrator"]], "Calibrador v23")
    )
    expected_calibrator = lock.get("expected_calibrator")
    if (
        not isinstance(expected_calibrator, dict)
        or calibrator.get("calibrator_signature")
        != expected_calibrator.get("calibrator_signature")
        or calibrator.get("decision_threshold")
        != expected_calibrator.get("decision_threshold")
    ):
        raise PipelineError("Calibrador v23 diverge do baseline congelado.")

    timing = _load_json(verified_paths[roles["timing"]], "Timing v23")
    expected_timing = lock.get("expected_timing")
    conservative = timing.get("conservative_precomputed_pipeline_seconds")
    if (
        not isinstance(expected_timing, dict)
        or not isinstance(conservative, dict)
        or timing.get("case_count") != expected_timing.get("case_count")
        or timing.get("features_recomputed_exactly") is not True
        or timing.get("labels_read") is not False
        or timing.get("lesion_masks_read") is not False
        or timing.get("raw_dicom_end_to_end_180_seconds_proven") is not False
        or conservative.get("sum") != expected_timing.get("prepared_upper_bound_seconds")
        or conservative.get("passed_180_seconds") is not True
    ):
        raise PipelineError("Timing ou escopo temporal v23 diverge do baseline congelado.")

    return {
        "schema": LOCK_SCHEMA,
        "status": "verified_frozen_reproducible_development_baseline",
        "verified_file_count": len(verified_paths),
        "case_count": evaluation["case_count"],
        "primary_loocv_metrics": {
            name: metrics[name] for name in expected_metrics
        },
        "repeated_stratified_5fold": {
            name: repeated[name] for name in expected_repeated
        },
        "calibrator_signature": calibrator["calibrator_signature"],
        "decision_threshold": calibrator["decision_threshold"],
        "prepared_upper_bound_seconds": conservative["sum"],
        "raw_dicom_end_to_end_180_seconds_proven": False,
        "development_only": True,
        "qualified": False,
        "independent_balanced_validation_required": True,
    }


__all__ = ["LOCK_SCHEMA", "verify_v23_baseline_lock"]
