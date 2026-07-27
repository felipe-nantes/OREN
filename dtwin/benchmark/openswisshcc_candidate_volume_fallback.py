"""Build the signed v16 technical gallery for cases without accepted registration."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    COHORT_SCHEMA,
    CONTRACT,
    GROUPS,
    MAX_CANDIDATES,
    MIN_BASE_CANDIDATES,
    OUTPUT_SIDE,
    ROI_MM,
    TARGET_CANDIDATE_COVERAGE,
    _canonical,
    _gallery_page,
    _input_index,
    _load,
    _original_dynamic_inputs,
    _registered_or_none,
    _valid_localizer_run_schema,
    build_candidate_volume_case,
    preview_frame_indices,
)
from dtwin.benchmark.openswisshcc_candidate_volume_timing import PLAN_SCHEMA
from dtwin.benchmark.openswisshcc_highdimensional_inference import _canonical_hash
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


FALLBACK_REASON = "alignment_manifest_missing_after_blind_dice_gate"


def _validate_timing_plan(path: Path) -> dict[str, Any]:
    plan = _load(path)
    signature = plan.pop("plan_signature", None)
    if signature != _canonical_hash(plan):
        raise PipelineError("Assinatura do plano temporal v16 diverge.")
    plan["plan_signature"] = signature
    unavailable = plan.get("alignment_unavailable_cases")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != "frozen_blind_before_v16_scores"
        or plan.get("selection_used_labels") is not False
        or plan.get("ground_truth_read") is not False
        or plan.get("ground_truth_read_by_selection_process") is not False
        or plan.get("development_labels_previously_visible_to_orchestrator") is not True
        or plan.get("development_results_classification") != "exploratory_only"
        or plan.get("holdout_opened") is not False
        or plan.get("research_only") is not True
        or plan.get("clinical_use_allowed") is not False
        or not isinstance(unavailable, list)
        or not unavailable
        or len(unavailable) != plan.get("alignment_unavailable_case_count")
    ):
        raise PipelineError("Plano temporal v16 invalido para fallback original.")
    case_ids = [str(item.get("case_id", "")) for item in unavailable]
    if (
        len(case_ids) != len(set(case_ids))
        or any(not case_id.startswith("anon-") for case_id in case_ids)
        or any(item.get("reason") != FALLBACK_REASON for item in unavailable)
    ):
        raise PipelineError("Casos/razoes de fallback v16 invalidos.")
    return plan


def _gallery_candidates(case_id: str, case_dir: Path, case_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    gallery = []
    for stack in case_manifest["candidate_stacks"]:
        candidate_dir = case_dir / stack["relative_directory"]
        candidate_manifest = _load(candidate_dir / "manifest.json")
        preview = []
        for group in candidate_manifest["groups"]:
            positions = preview_frame_indices(len(group["frames"]))
            labels = {positions[0]: "inicio", positions[-1]: "fim"}
            labels[positions[len(positions) // 2]] = "centro"
            for position in positions:
                frame = group["frames"][position]
                preview.append(
                    {
                        "relative_path": f'{case_id}/{stack["relative_directory"]}/{frame["filename"]}',
                        "caption": (
                            f'{group["role"]} — {labels[position]} — z={frame["source_index_z"]} — '
                            f'alinhamento={group["alignment_mode"]}'
                        ),
                    }
                )
        gallery.append(
            {
                "candidate_number": stack["candidate_number"],
                "description": (
                    "fallback no centro hepatico"
                    if stack["fallback_no_candidate"]
                    else f'rank {stack["component_rank"]}, {stack["component_voxels"]} voxels'
                ),
                "preview_frames": preview,
            }
        )
    return gallery


def build_candidate_volume_fallback_gallery(
    *,
    timing_plan_path: Path,
    localizer_run: Path,
    input_manifest: Path,
    input_root: Path,
    registration_root: Path,
    output_root: Path,
    expected_source_case_count: int = 88,
    roi_mm: float = ROI_MM,
    output_side: int = OUTPUT_SIDE,
    max_input_bytes: int = 8_000_000,
) -> dict[str, Any]:
    """Render only signed alignment-unavailable cases; never run inference."""

    plan_path = Path(timing_plan_path).resolve()
    plan = _validate_timing_plan(plan_path)
    case_ids = sorted(item["case_id"] for item in plan["alignment_unavailable_cases"])
    localizer_run = Path(localizer_run).resolve()
    localizer_summary = _load(localizer_run / "summary.json")
    if (
        not _valid_localizer_run_schema(localizer_summary)
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("ground_truth_read") is not False
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("final_decision") is not None
        or any(case_id not in localizer_summary.get("case_ids", []) for case_id in case_ids)
    ):
        raise PipelineError("Run cego do localizador invalido para fallback v16.")
    morphology = _input_index(input_manifest, input_root)
    dynamic = _original_dynamic_inputs(input_manifest, input_root)
    if len(morphology) != expected_source_case_count or set(morphology) != set(dynamic):
        raise PipelineError("Coorte fonte do fallback v16 inesperada ou inconsistente.")

    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Destino fallback v16 ja existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v16fallback_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    try:
        for case_id in case_ids:
            if _registered_or_none(case_id, registration_root) is not None:
                raise PipelineError("Plano marcou caso sem alinhamento, mas registro publicado foi encontrado.")
            case_dir = staging / case_id
            case_manifest = build_candidate_volume_case(
                case_id=case_id,
                morphology_source=morphology[case_id],
                dynamic_source=dynamic[case_id],
                registered_source=None,
                localizer_dir=localizer_run / case_id,
                destination=case_dir,
                roi_mm=roi_mm,
                output_side=output_side,
                max_input_bytes=max_input_bytes,
            )
            if case_manifest.get("dynamic_alignment_mode") != "original_unregistered_physical_center":
                raise PipelineError("Caso fallback v16 nao registrou o modo dinamico original.")
            records.append(
                {
                    "case_id": case_id,
                    "candidate_stack_count": case_manifest["candidate_stack_count"],
                    "case_manifest_sha256": _sha256(case_dir / "case_manifest.json"),
                    "dynamic_alignment_mode": case_manifest["dynamic_alignment_mode"],
                    "gallery_candidates": _gallery_candidates(case_id, case_dir, case_manifest),
                }
            )
        page = _gallery_page(records).replace(
            "As imagens enviadas ao modelo",
            "Fases arterial/tardia estao explicitamente NAO REGISTRADAS e usam o mesmo centro fisico; "
            "avaliar correspondencia anatomica antes de aprovar. As imagens enviadas ao modelo",
            1,
        )
        (staging / "index.html").write_text(page, encoding="utf-8")
        cohort = {
            "schema": COHORT_SCHEMA,
            "contract": CONTRACT,
            "case_count": len(records),
            "candidate_stack_count": sum(item["candidate_stack_count"] for item in records),
            "cases": records,
            "source_timing_plan_sha256": _sha256(plan_path),
            "source_timing_plan_signature": plan["plan_signature"],
            "source_localizer_summary_sha256": _sha256(localizer_run / "summary.json"),
            "input_manifest_sha256": _sha256(Path(input_manifest).resolve()),
            "protocol": {
                "roi_mm": roi_mm,
                "output_side": output_side,
                "group_slots": [
                    {"slot": role, "category": category, "frame_count": count}
                    for role, category, count in GROUPS
                ],
                "dynamic_alignment_mode": "original_unregistered_physical_center",
                "candidate_target_fraction": TARGET_CANDIDATE_COVERAGE,
                "minimum_base_candidates": MIN_BASE_CANDIDATES,
                "maximum_candidates": MAX_CANDIDATES,
            },
            "gallery_signature": _canonical(records),
            "technical_review_status": "pending",
            "development_results_classification": "exploratory_only",
            "inference_executed": False,
            "ground_truth_read": False,
            "dataset_lesion_mask_used": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, destination)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
