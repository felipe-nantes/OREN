"""Freeze the label-blind LLD-MMRI v23 partial-FOV handling contract."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_segmentation_pilot import (
    verify_lld_mmri_v23_segmentation_pilot,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import load_screening_config
from dtwin.medgemma_screening import _write_json_atomic


AMENDMENT_SCHEMA = "argos-lld-mmri-v23-label-blind-technical-amendment-v1"
DYNAMIC_ROLES = ("t1_native", "t1_arterial", "t1_venous", "t1_delayed")
SUPPORT_CUTS = (1.0, 0.99, 0.95, 0.80, 0.50)
VALID_SEGMENTATION_STATUS = "valid_liver_mask"
TECHNICAL_FAILURE_STATUS = "technical_failure_no_valid_liver_mask"


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Casos da auditoria LLD-MMRI ausentes ou invalidos.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Auditoria LLD-MMRI vazia.")
    return rows


def _audit_supports(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, list[float]], list[str]]:
    """Validate valid masks and bind explicit technical failures separately."""

    supports: dict[str, list[float]] = {role: [] for role in DYNAMIC_ROLES}
    technical_failure_case_ids: list[str] = []
    for row in rows:
        case_id = row.get("case_id")
        status = row.get("segmentation_status", VALID_SEGMENTATION_STATUS)
        if not isinstance(case_id, str) or not case_id:
            raise PipelineError("Caso invalido no adendo LLD-MMRI.")
        if status == TECHNICAL_FAILURE_STATUS:
            if (
                row.get("dynamic_liver_support_fraction") is not None
                or row.get("minimum_dynamic_liver_support_fraction") is not None
                or row.get("mask_sha256") is not None
                or row.get("segmentation_selected_attempt") is not None
                or row.get("technical_failure_counts_as_error") is not True
                or row.get("liver_voxels") != 0
            ):
                raise PipelineError(
                    "Falha tecnica LLD-MMRI possui evidencia de mascara invalida."
                )
            technical_failure_case_ids.append(case_id)
            continue
        if status != VALID_SEGMENTATION_STATUS:
            raise PipelineError("Status de segmentacao invalido no adendo LLD-MMRI.")
        values = row.get("dynamic_liver_support_fraction")
        if (
            not isinstance(values, dict)
            or set(values) != set(DYNAMIC_ROLES)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
                for value in values.values()
            )
        ):
            raise PipelineError("Cobertura por fase invalida no adendo LLD-MMRI.")
        for role in DYNAMIC_ROLES:
            supports[role].append(float(values[role]))
    if not supports["t1_venous"]:
        raise PipelineError("Adendo LLD-MMRI nao possui mascara hepatica valida.")
    return supports, technical_failure_case_ids


def _support_distribution(
    supports: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    return {
        role: {
            "evaluated_valid_mask_count": len(values),
            "minimum": min(values),
            "complete_count": sum(value == 1.0 for value in values),
            "counts_below": {
                str(cut): sum(value < cut for value in values) for cut in SUPPORT_CUTS
            },
        }
        for role, values in supports.items()
    }


def freeze_lld_mmri_v23_technical_amendment(
    *,
    protocol_root: Path,
    download_root: Path,
    failed_audit_root: Path,
    harmonization_root: Path,
    segmentation_audit_root: Path,
    config_path: Path,
    profile_path: Path,
    output_root: Path,
    expected_segmentation_audit_signature: str | None = None,
) -> dict[str, Any]:
    """Bind the partial-FOV policy to the complete blind segmentation audit."""

    segmentation_audit_root = Path(segmentation_audit_root).resolve()
    audit = verify_lld_mmri_v23_segmentation_pilot(
        protocol_root=protocol_root,
        download_root=download_root,
        failed_audit_root=failed_audit_root,
        harmonization_root=harmonization_root,
        pilot_root=segmentation_audit_root,
        expected_pilot_signature=expected_segmentation_audit_signature,
    )
    rows = _rows(segmentation_audit_root / "cases.jsonl")
    if (
        audit.get("case_count") != len(rows)
        or audit.get("case_ids") != [row.get("case_id") for row in rows]
        or audit.get("selection") != "first_n_frozen_protocol_order_no_labels"
    ):
        raise PipelineError("Adendo LLD-MMRI exige auditoria integral na ordem congelada.")
    supports, technical_failure_case_ids = _audit_supports(rows)
    if audit.get("segmentation_technical_failure_case_count") != len(
        technical_failure_case_ids
    ):
        raise PipelineError("Contagem de falhas tecnicas divergiu da auditoria LLD-MMRI.")
    if any(value != 1.0 for value in supports["t1_venous"]):
        raise PipelineError("Adendo LLD-MMRI exige referencia venosa com cobertura integral.")

    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    config = load_screening_config(config_path)
    load_profile(profile_path)
    fusion = config.get("panel", {}).get("fusion", {})
    if (
        config.get("panel", {}).get("strategy") != "uniform_9"
        or config.get("panel", {}).get("short_liver_policy") != "blank_tiles"
        or fusion.get("partial_fov_policy") != "venous_grayscale"
        or fusion.get("partial_fov_fallback_phase") != "pv"
    ):
        raise PipelineError("Config LLD-MMRI nao implementa o fallback parcial congelado.")
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Adendo tecnico LLD-MMRI existente; sobrescrita recusada.")
    repo_root = Path(__file__).resolve().parents[2]
    code_paths = {
        "segmentation_audit": repo_root / "dtwin/benchmark/lld_mmri_v23_segmentation_pilot.py",
        "preparation": repo_root / "dtwin/benchmark/lld_mmri_v23_preparation.py",
        "panels": repo_root / "dtwin/benchmark/lld_mmri_v23_panels.py",
        "shape": repo_root / "dtwin/benchmark/lld_mmri_v23_shape.py",
        "multiphase_renderer": repo_root / "dtwin/medgemma_panel_multiphase.py",
    }
    if any(not path.is_file() for path in code_paths.values()):
        raise PipelineError("Codigo-fonte do adendo LLD-MMRI ausente.")
    distribution = _support_distribution(supports)
    base = {
        "schema": AMENDMENT_SCHEMA,
        "status": "frozen_before_external_predictions_no_labels",
        "protocol_signature": audit["protocol_signature"],
        "segmentation_audit_signature": audit["pilot_signature"],
        "case_count": len(rows),
        "case_ids": [str(row["case_id"]) for row in rows],
        "valid_segmentation_case_count": len(rows) - len(technical_failure_case_ids),
        "technical_failures": {
            "case_count": len(technical_failure_case_ids),
            "case_ids": technical_failure_case_ids,
            "excluded_from_inference": True,
            "count_as_primary_metric_errors": True,
            "mask_fabrication_allowed": False,
        },
        "support_distribution": distribution,
        "policy": {
            "reference_phase": "t1_venous",
            "reference_phase_requires_full_liver_coverage": True,
            "missing_dynamic_pixels_imputed": False,
            "panel_partial_fov_policy": "venous_grayscale",
            "panel_short_liver_policy": "blank_tiles_no_slice_duplication",
            "shape_partial_fov_policy": "intersection_of_available_dynamic_voxels",
            "minimum_shape_analysis_voxels": 300,
            "partial_fov_cases_excluded_from_primary_metrics": False,
            "technical_failures_count_as_errors": True,
        },
        "config_sha256": _sha256(config_path),
        "profile_sha256": _sha256(profile_path),
        "code_sha256": {name: _sha256(path) for name, path in code_paths.items()},
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "predictions_present": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    amendment = dict(base)
    amendment["amendment_signature"] = _canonical_sha(base)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23amendment_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "amendment.json", amendment)
        _publish_directory(staging, output_root)
        return amendment
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_lld_mmri_v23_technical_amendment(
    *,
    protocol_root: Path,
    download_root: Path,
    failed_audit_root: Path,
    harmonization_root: Path,
    segmentation_audit_root: Path,
    config_path: Path,
    profile_path: Path,
    amendment_root: Path,
    expected_amendment_signature: str | None = None,
) -> dict[str, Any]:
    """Recompute the sources and integrity of a frozen partial-FOV amendment."""

    amendment_root = Path(amendment_root).resolve()
    try:
        amendment = json.loads(
            (amendment_root / "amendment.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Adendo tecnico LLD-MMRI ausente ou invalido.") from exc
    unsigned = dict(amendment) if isinstance(amendment, dict) else {}
    signature = unsigned.pop("amendment_signature", None)
    if (
        amendment.get("schema") != AMENDMENT_SCHEMA
        or signature != _canonical_sha(unsigned)
        or (
            expected_amendment_signature is not None
            and signature != expected_amendment_signature
        )
    ):
        raise PipelineError("Assinatura do adendo tecnico LLD-MMRI invalida.")
    audit = verify_lld_mmri_v23_segmentation_pilot(
        protocol_root=protocol_root,
        download_root=download_root,
        failed_audit_root=failed_audit_root,
        harmonization_root=harmonization_root,
        pilot_root=segmentation_audit_root,
        expected_pilot_signature=amendment.get("segmentation_audit_signature"),
    )
    rows = _rows(Path(segmentation_audit_root).resolve() / "cases.jsonl")
    supports, technical_failure_case_ids = _audit_supports(rows)
    expected_distribution = _support_distribution(supports)
    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    config = load_screening_config(config_path)
    load_profile(profile_path)
    fusion = config.get("panel", {}).get("fusion", {})
    repo_root = Path(__file__).resolve().parents[2]
    code_paths = {
        "segmentation_audit": repo_root / "dtwin/benchmark/lld_mmri_v23_segmentation_pilot.py",
        "preparation": repo_root / "dtwin/benchmark/lld_mmri_v23_preparation.py",
        "panels": repo_root / "dtwin/benchmark/lld_mmri_v23_panels.py",
        "shape": repo_root / "dtwin/benchmark/lld_mmri_v23_shape.py",
        "multiphase_renderer": repo_root / "dtwin/medgemma_panel_multiphase.py",
    }
    expected_policy = {
        "reference_phase": "t1_venous",
        "reference_phase_requires_full_liver_coverage": True,
        "missing_dynamic_pixels_imputed": False,
        "panel_partial_fov_policy": "venous_grayscale",
        "panel_short_liver_policy": "blank_tiles_no_slice_duplication",
        "shape_partial_fov_policy": "intersection_of_available_dynamic_voxels",
        "minimum_shape_analysis_voxels": 300,
        "partial_fov_cases_excluded_from_primary_metrics": False,
        "technical_failures_count_as_errors": True,
    }
    if (
        amendment.get("status") != "frozen_before_external_predictions_no_labels"
        or amendment.get("protocol_signature") != audit["protocol_signature"]
        or amendment.get("case_count") != len(rows)
        or amendment.get("case_ids") != [str(row["case_id"]) for row in rows]
        or amendment.get("valid_segmentation_case_count")
        != len(rows) - len(technical_failure_case_ids)
        or amendment.get("technical_failures")
        != {
            "case_count": len(technical_failure_case_ids),
            "case_ids": technical_failure_case_ids,
            "excluded_from_inference": True,
            "count_as_primary_metric_errors": True,
            "mask_fabrication_allowed": False,
        }
        or audit.get("segmentation_technical_failure_case_count")
        != len(technical_failure_case_ids)
        or amendment.get("support_distribution") != expected_distribution
        or amendment.get("policy") != expected_policy
        or amendment.get("config_sha256") != _sha256(config_path)
        or amendment.get("profile_sha256") != _sha256(profile_path)
        or amendment.get("code_sha256")
        != {name: _sha256(path) for name, path in code_paths.items()}
        or config.get("panel", {}).get("strategy") != "uniform_9"
        or config.get("panel", {}).get("short_liver_policy") != "blank_tiles"
        or fusion.get("partial_fov_policy") != "venous_grayscale"
        or fusion.get("partial_fov_fallback_phase") != "pv"
        or amendment.get("ground_truth_read") is not False
        or amendment.get("lesion_masks_read") != 0
        or amendment.get("predictions_present") is not False
        or amendment.get("metrics_calculated") is not False
    ):
        raise PipelineError("Adendo tecnico LLD-MMRI divergiu das fontes congeladas.")
    return amendment


__all__ = [
    "AMENDMENT_SCHEMA",
    "freeze_lld_mmri_v23_technical_amendment",
    "verify_lld_mmri_v23_technical_amendment",
]
