"""Complete the exact v23 signal matrix for retrospective OpenSwissHCC.

This phase reproduces the deterministic enhancement t3/top-5 candidate shape
branch on the consumed holdout images.  It does not read labels or public
lesion masks, score cases, choose thresholds, or calculate metrics.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_candidate_shape import (
    ALGORITHM_VERSION as SHAPE_ALGORITHM,
    compute_candidate_shape_features,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    build_enhancement_proposals,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    _compute_enhancement_state,
    _registered_paths,
)
from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import (
    ALGORITHM_VERSION as SELECTION_ALGORITHM,
    MAX_COMPONENTS,
    THRESHOLD_KEY,
    select_top_components,
)
from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS, _canonical_sha
from dtwin.benchmark.v23_retrospective_multicohort_phase2 import (
    _load_jsonl,
    verify_phase2_openswisshcc_inventory,
)
from dtwin.core import PipelineError


SUMMARY_SCHEMA = "argos-v23-retrospective-multicohort-phase3-summary-v1"
SIGNAL_SCHEMA = "argos-v23-retrospective-exact-signal-case-v1"
SHAPE_SCHEMA = "argos-v23-retrospective-holdout-shape-case-v1"
FAILURE_SCHEMA = "argos-v23-retrospective-technical-failure-case-v1"
ALIGNMENT_SUMMARY_SCHEMA = "argos-openswisshcc-holdout-alignment-summary-v1"
HOLDOUT_INPUT_SCHEMA = "argos-public-liver-mri-holdout-input-v1"
QUALITY_REVIEW_SCHEMA = "argos-openswisshcc-multisequence-quality-review-v1"
WEIGHTS = {"v11": 0.80, "candidate_weighted_linearity": 0.20}
EXPECTED_THRESHOLD = 0.5121839080459771
DEVELOPMENT_EXCLUSION_CASE = "anon-openswiss-cb2c5c63fc28b8ee"


def _load(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


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
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.startswith("anon-") or case_id in indexed:
            raise PipelineError(f"{description} contém case_id inválido ou duplicado.")
        indexed[case_id] = row
    return indexed


def _safe_declared_file(root: Path, item: dict[str, Any]) -> Path:
    role = str(item.get("role", ""))
    relative = str(item.get("relative_path", ""))
    if (
        any(token in (role + " " + relative).lower() for token in ("lesion", "tumor"))
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise PipelineError("Entrada proibida no extrator retrospectivo v23.")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PipelineError("Caminho de input v23 saiu da raiz autorizada.") from exc
    if (
        not path.is_file()
        or path.stat().st_size != item.get("bytes")
        or _sha256(path) != item.get("sha256")
    ):
        raise PipelineError(f"Input v23 ausente ou adulterado: {relative}.")
    return path


def _holdout_inputs(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    rows = _load_jsonl(path, "Manifesto de inputs holdout")
    root = path.parent.parent / "inputs"
    indexed: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        case_id = row.get("case_id")
        files = row.get("files")
        if (
            row.get("schema") != HOLDOUT_INPUT_SCHEMA
            or not isinstance(case_id, str)
            or case_id in indexed
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or not isinstance(files, list)
        ):
            raise PipelineError("Manifesto holdout v23 inseguro.")
        by_role = {item.get("role"): item for item in files if isinstance(item, dict)}
        if not {"t1_venous", "liver_mask_venous"} <= set(by_role):
            raise PipelineError(f"Input venoso incompleto: {case_id}.")
        selected = {
            role: _safe_declared_file(root, by_role[role])
            for role in ("t1_venous", "liver_mask_venous")
        }
        indexed[case_id] = {
            "paths": selected,
            "hashes": {role: str(by_role[role]["sha256"]) for role in selected},
        }
        order.append(case_id)
    return order, indexed


def _validated_v11_rows(
    development_path: Path, holdout_path: Path
) -> dict[str, dict[str, float]]:
    rows = _load_jsonl(development_path, "Sinais v11 development") + _load_jsonl(
        holdout_path, "Sinais v11 holdout"
    )
    indexed: dict[str, dict[str, float]] = {}
    allowed = {
        "argos-openswisshcc-v20-blind-fusion-signal-v1",
        "argos-public-independent-v21-raw-signals-v1",
    }
    for row in rows:
        case_id = row.get("case_id")
        signals = row.get("signals")
        if (
            row.get("schema") not in allowed
            or not isinstance(case_id, str)
            or case_id in indexed
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or not isinstance(signals, dict)
        ):
            raise PipelineError("Registro v11 retrospectivo inválido.")
        exact: dict[str, float] = {}
        for name in V11_WEIGHTS:
            value = signals.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise PipelineError(f"Sinal v11 ausente ou não finito: {case_id}/{name}.")
            exact[name] = float(value)
        indexed[case_id] = exact
    return indexed


def _validated_development_shapes(path: Path) -> dict[str, dict[str, Any]]:
    rows = _load_jsonl(path, "Features v23 development")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        value = row.get("features", {}).get("candidate_weighted_linearity")
        if (
            row.get("schema") != "argos-openswisshcc-candidate-shape-case-v23"
            or row.get("status") != "complete_blind_shape_features"
            or not isinstance(case_id, str)
            or case_id in indexed
            or row.get("ground_truth_read") is not False
            or row.get("ground_truth_lesion_mask_used") is not False
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise PipelineError("Feature development v23 inválida.")
        indexed[case_id] = row
    return indexed


def _alignment_contract(
    path: Path, holdout_ids: list[str]
) -> tuple[set[str], dict[str, str], dict[str, str]]:
    summary = _load(path, "Resumo de alinhamento holdout")
    alignments = summary.get("alignments")
    fallbacks = summary.get("technical_fallbacks")
    if (
        summary.get("schema") != ALIGNMENT_SUMMARY_SCHEMA
        or summary.get("status") != "complete_label_blind_alignment_with_declared_fallbacks"
        or summary.get("case_count") != len(holdout_ids)
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") != 0
        or not isinstance(alignments, list)
        or not isinstance(fallbacks, list)
    ):
        raise PipelineError("Contrato de alinhamento holdout inválido.")
    aligned: dict[str, str] = {}
    for item in alignments:
        case_id, digest = item.get("case_id"), item.get("sha256")
        if not isinstance(case_id, str) or case_id in aligned or not isinstance(digest, str):
            raise PipelineError("Alinhamento holdout duplicado ou sem hash.")
        aligned[case_id] = digest
    fallback_reasons: dict[str, str] = {}
    for item in fallbacks:
        case_id = item.get("case_id")
        if (
            not isinstance(case_id, str)
            or case_id in fallback_reasons
            or item.get("fallback") != "venous_single_phase"
            or not isinstance(item.get("reason"), str)
        ):
            raise PipelineError("Fallback holdout inválido.")
        fallback_reasons[case_id] = str(item["reason"])
    if set(aligned) | set(fallback_reasons) != set(holdout_ids) or set(aligned) & set(fallback_reasons):
        raise PipelineError("Alinhamentos e fallbacks não cobrem exatamente o holdout.")
    return set(aligned), aligned, fallback_reasons


def _quality_exclusion(path: Path) -> dict[str, Any]:
    review = _load(path, "Revisão técnica de desenvolvimento")
    cases = review.get("decisions")
    if (
        review.get("schema") != QUALITY_REVIEW_SCHEMA
        or review.get("ground_truth_read") is not False
        or review.get("lesion_mask_used") is not False
        or review.get("quality_review_signature")
        != "f4eb8e03b435820ef8d00656e332de7f9e84438301a0d68201ed59a7f58596d8"
        or not isinstance(cases, list)
    ):
        raise PipelineError("Revisão técnica de desenvolvimento inválida.")
    selected = [item for item in cases if item.get("case_id") == DEVELOPMENT_EXCLUSION_CASE]
    if (
        len(selected) != 1
        or selected[0].get("status") != "technical_quality_exclusion"
        or selected[0].get("reason_code") != "severe_multisequence_quality_degradation"
    ):
        raise PipelineError("Exclusão técnica histórica do caso 72 não foi confirmada.")
    return selected[0]


def _save_mask(mask: np.ndarray, reference: sitk.Image, path: Path) -> None:
    image = sitk.GetImageFromArray(np.asarray(mask, dtype=np.uint8))
    image.CopyInformation(reference)
    sitk.WriteImage(image, str(path), True)


def _holdout_shape(
    *,
    case_id: str,
    source: dict[str, Any],
    alignment_root: Path,
    staging: Path,
    expected_alignment_hash: str,
) -> dict[str, Any]:
    arterial_path, delayed_path, hashes = _registered_paths(case_id, alignment_root)
    if hashes["alignment_manifest"] != expected_alignment_hash:
        raise PipelineError(f"Hash do alinhamento divergiu: {case_id}.")
    venous = sitk.ReadImage(str(source["paths"]["t1_venous"]))
    state = _compute_enhancement_state(
        arterial=sitk.ReadImage(str(arterial_path)),
        venous=venous,
        delayed=sitk.ReadImage(str(delayed_path)),
        liver_mask=sitk.ReadImage(str(source["paths"]["liver_mask_venous"])),
    )
    proposals = build_enhancement_proposals(
        joint_enhancement=state["joint_enhancement"],
        analysis_mask=state["analysis_mask"],
        spacing_xyz=venous.GetSpacing(),
    )
    selected, components = select_top_components(
        proposals[THRESHOLD_KEY]["mask"], maximum=MAX_COMPONENTS
    )
    case_dir = staging / "candidate_masks" / case_id
    case_dir.mkdir(parents=True)
    relative = f"candidate_masks/{case_id}/selected_enhancement_t3_top5.nii.gz"
    mask_path = staging / relative
    _save_mask(selected, venous, mask_path)
    candidate = sitk.ReadImage(str(mask_path))
    shape = compute_candidate_shape_features(candidate)
    return {
        "schema": SHAPE_SCHEMA,
        "case_id": case_id,
        "status": "complete_exact_v23_shape",
        "proposal_algorithm": "whole-liver-joint-enhancement-proposals-v1",
        "selection_algorithm": SELECTION_ALGORITHM,
        "shape_algorithm": SHAPE_ALGORITHM,
        "threshold_key": THRESHOLD_KEY,
        "maximum_components": MAX_COMPONENTS,
        "selected_components": components,
        "candidate_mask": relative,
        "candidate_mask_sha256": _sha256(mask_path),
        "features": shape["features"],
        "source_hashes": {
            **source["hashes"],
            **hashes,
        },
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "predictions_calculated": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def build_phase3_exact_v23_signals(
    *,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    development_v11_signals_path: Path,
    holdout_v11_signals_path: Path,
    development_shape_features_path: Path,
    holdout_manifest_path: Path,
    holdout_alignment_root: Path,
    holdout_alignment_summary_path: Path,
    development_quality_review_path: Path,
    output_dir: Path,
    expected_cases: int = 132,
) -> dict[str, Any]:
    phase2 = verify_phase2_openswisshcc_inventory(
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    inventory_rows = _load_jsonl(
        Path(phase2_root) / "case_inventory.jsonl", "Inventário da Fase 2"
    )
    inventory = _rows_by_case(inventory_rows, "Inventário da Fase 2")
    holdout_ids, holdout_inputs = _holdout_inputs(Path(holdout_manifest_path).resolve())
    if set(holdout_ids) != {
        case_id for case_id, row in inventory.items()
        if row.get("source_split") == "holdout_consumed"
    }:
        raise PipelineError("Holdout da Fase 3 divergiu do inventário congelado.")
    aligned, alignment_hashes, fallback_reasons = _alignment_contract(
        Path(holdout_alignment_summary_path).resolve(), holdout_ids
    )
    _quality_exclusion(Path(development_quality_review_path).resolve())
    v11 = _validated_v11_rows(
        Path(development_v11_signals_path).resolve(),
        Path(holdout_v11_signals_path).resolve(),
    )
    development_shapes = _validated_development_shapes(
        Path(development_shape_features_path).resolve()
    )
    if set(v11) != set(inventory) - {DEVELOPMENT_EXCLUSION_CASE}:
        raise PipelineError(
            "Sinais v11 devem cobrir todos os casos salvo a exclusão técnica predeclarada."
        )

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Fase 3 já existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_multicohort_phase3_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        holdout_shapes = [
            _holdout_shape(
                case_id=case_id,
                source=holdout_inputs[case_id],
                alignment_root=Path(holdout_alignment_root).resolve(),
                staging=staging,
                expected_alignment_hash=alignment_hashes[case_id],
            )
            for case_id in holdout_ids
            if case_id in aligned
        ]
        holdout_by_id = {row["case_id"]: row for row in holdout_shapes}
        signal_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for case_id in sorted(inventory):
            split = inventory[case_id]["source_split"]
            shape_row = development_shapes.get(case_id) or holdout_by_id.get(case_id)
            if shape_row is None:
                if case_id == DEVELOPMENT_EXCLUSION_CASE:
                    reason = "severe_multisequence_quality_degradation"
                    stage = "predeclared_blind_technical_quality_review"
                elif case_id in fallback_reasons:
                    reason = fallback_reasons[case_id]
                    stage = "frozen_multiphase_alignment_gate"
                else:
                    raise PipelineError(f"Feature v23 ausente sem falha predeclarada: {case_id}.")
                failures.append(
                    {
                        "schema": FAILURE_SCHEMA,
                        "case_id": case_id,
                        "source_split": split,
                        "status": "exact_v23_not_computable_count_as_error",
                        "failure_stage": stage,
                        "reason_code": reason,
                        "signals_fabricated": False,
                        "ground_truth_read": False,
                        "ground_truth_lesion_mask_used": False,
                        "predictions_calculated": False,
                        "metrics_calculated": False,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    }
                )
                continue
            weighted = float(shape_row["features"]["candidate_weighted_linearity"])
            signal_rows.append(
                {
                    "schema": SIGNAL_SCHEMA,
                    "case_id": case_id,
                    "source_split": split,
                    "status": "complete_exact_v23_score_inputs",
                    "v11_signals": v11[case_id],
                    "candidate_weighted_linearity": weighted,
                    "fixed_weights": WEIGHTS,
                    "fixed_threshold": EXPECTED_THRESHOLD,
                    "source_shape_kind": (
                        "frozen_development_v23_shape"
                        if case_id in development_shapes
                        else "retrospective_exact_holdout_t3_top5_shape"
                    ),
                    "ground_truth_read": False,
                    "ground_truth_lesion_mask_used": False,
                    "predictions_calculated": False,
                    "metrics_calculated": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
            )
        _write_jsonl(staging / "exact_v23_signals.jsonl", signal_rows)
        _write_jsonl(staging / "holdout_shape_features.jsonl", holdout_shapes)
        _write_jsonl(staging / "technical_failures.jsonl", failures)
        artifacts = {
            "exact_v23_signals": "exact_v23_signals.jsonl",
            "exact_v23_signals_sha256": _sha256(staging / "exact_v23_signals.jsonl"),
            "holdout_shape_features": "holdout_shape_features.jsonl",
            "holdout_shape_features_sha256": _sha256(staging / "holdout_shape_features.jsonl"),
            "technical_failures": "technical_failures.jsonl",
            "technical_failures_sha256": _sha256(staging / "technical_failures.jsonl"),
            "phase2_summary_sha256": _sha256(Path(phase2_root) / "summary.json"),
            "development_v11_signals_sha256": _sha256(Path(development_v11_signals_path)),
            "holdout_v11_signals_sha256": _sha256(Path(holdout_v11_signals_path)),
            "development_shape_features_sha256": _sha256(Path(development_shape_features_path)),
            "holdout_manifest_sha256": _sha256(Path(holdout_manifest_path)),
            "holdout_alignment_summary_sha256": _sha256(Path(holdout_alignment_summary_path)),
            "development_quality_review_sha256": _sha256(Path(development_quality_review_path)),
        }
        summary_body = {
            "schema": SUMMARY_SCHEMA,
            "status": "phase3_exact_v23_signal_matrix_complete_with_explicit_failures",
            "contract_signature": phase2["contract_signature"],
            "phase2_signature": phase2["phase2_signature"],
            "case_count": expected_cases,
            "exact_v23_signal_count": len(signal_rows),
            "technical_failure_count": len(failures),
            "development_shape_reused_count": len(development_shapes),
            "holdout_shape_generated_count": len(holdout_shapes),
            "holdout_alignment_fallback_failure_count": len(fallback_reasons),
            "fixed_v23": {
                "weights": WEIGHTS,
                "decision_threshold": EXPECTED_THRESHOLD,
                "shape_feature": "candidate_weighted_linearity",
                "shape_algorithm": SHAPE_ALGORITHM,
                "selection_algorithm": SELECTION_ALGORITHM,
            },
            "technical_failure_policy": "count_as_error_no_signal_fabrication",
            "artifacts": artifacts,
            "safety": {
                "labels_read": False,
                "lesion_masks_read": 0,
                "predictions_calculated": False,
                "metrics_calculated": False,
                "all_consumed_image_files_rehashed": True,
            },
            "next_gate": {
                "ready_for_patient_level_out_of_fold_scoring": True,
                "ready_for_metrics": False,
                "technical_failures_must_remain_errors": True,
            },
            "research_only": True,
            "clinical_use_allowed": False,
        }
        summary = {**summary_body, "phase3_signature": _canonical_sha(summary_body)}
        _write_json(staging / "summary.json", summary)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return summary


def verify_phase3_exact_v23_signals(
    *,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    expected_cases: int = 132,
) -> dict[str, Any]:
    phase2 = verify_phase2_openswisshcc_inventory(
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    root = Path(phase3_root).resolve()
    summary = _load(root / "summary.json", "Resumo da Fase 3")
    unsigned = dict(summary)
    signature = unsigned.pop("phase3_signature", None)
    artifacts = summary.get("artifacts")
    if (
        summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("status")
        != "phase3_exact_v23_signal_matrix_complete_with_explicit_failures"
        or signature != _canonical_sha(unsigned)
        or summary.get("phase2_signature") != phase2["phase2_signature"]
        or summary.get("case_count") != expected_cases
        or not isinstance(artifacts, dict)
        or summary.get("safety", {}).get("labels_read") is not False
        or summary.get("safety", {}).get("lesion_masks_read") != 0
    ):
        raise PipelineError("Resumo da Fase 3 adulterado ou divergente.")
    for name in ("exact_v23_signals", "holdout_shape_features", "technical_failures"):
        relative = artifacts.get(name)
        digest = artifacts.get(f"{name}_sha256")
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or _sha256(root / relative) != digest
        ):
            raise PipelineError("Artefato da Fase 3 adulterado.")
    signals = _load_jsonl(root / artifacts["exact_v23_signals"], "Sinais da Fase 3")
    shapes = _load_jsonl(root / artifacts["holdout_shape_features"], "Shapes da Fase 3")
    failures = _load_jsonl(root / artifacts["technical_failures"], "Falhas da Fase 3")
    ids = [row.get("case_id") for row in signals + failures]
    if (
        len(ids) != expected_cases
        or len(set(ids)) != expected_cases
        or len(signals) != summary.get("exact_v23_signal_count")
        or len(failures) != summary.get("technical_failure_count")
    ):
        raise PipelineError("Cobertura de casos da Fase 3 inconsistente.")
    for row in signals:
        value = row.get("candidate_weighted_linearity")
        v11 = row.get("v11_signals")
        if (
            row.get("schema") != SIGNAL_SCHEMA
            or row.get("status") != "complete_exact_v23_score_inputs"
            or set(v11 or {}) != set(V11_WEIGHTS)
            or any(not math.isfinite(float(item)) for item in (v11 or {}).values())
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0.0 <= float(value) <= 1.0
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
        ):
            raise PipelineError("Sinal exato v23 inválido.")
    shape_ids: set[str] = set()
    for row in shapes:
        relative = row.get("candidate_mask")
        if (
            row.get("schema") != SHAPE_SCHEMA
            or row.get("status") != "complete_exact_v23_shape"
            or not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or _sha256(root / relative) != row.get("candidate_mask_sha256")
            or row.get("ground_truth_read") is not False
            or row.get("ground_truth_lesion_mask_used") is not False
        ):
            raise PipelineError("Shape holdout da Fase 3 inválido.")
        recomputed = compute_candidate_shape_features(
            sitk.ReadImage(str(root / relative))
        )["features"]
        persisted = row.get("features")
        if (
            not isinstance(persisted, dict)
            or set(recomputed) != set(persisted)
            or any(
                not math.isclose(
                    float(recomputed[name]),
                    float(persisted[name]),
                    rel_tol=1e-6,
                    abs_tol=1e-9,
                )
                for name in recomputed
            )
        ):
            raise PipelineError("Feature shape não reproduz a máscara persistida.")
        shape_ids.add(str(row["case_id"]))
    if len(shape_ids) != summary.get("holdout_shape_generated_count"):
        raise PipelineError("Contagem de shapes holdout divergiu.")
    for row in failures:
        if (
            row.get("schema") != FAILURE_SCHEMA
            or row.get("status") != "exact_v23_not_computable_count_as_error"
            or row.get("signals_fabricated") is not False
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
        ):
            raise PipelineError("Falha técnica da Fase 3 inválida.")
    return summary


__all__ = [
    "FAILURE_SCHEMA",
    "SHAPE_SCHEMA",
    "SIGNAL_SCHEMA",
    "SUMMARY_SCHEMA",
    "build_phase3_exact_v23_signals",
    "verify_phase3_exact_v23_signals",
]
