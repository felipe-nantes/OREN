"""Blind, predeclared critical-case selection for the v16 end-to-end timing pilot."""
from __future__ import annotations

import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import select_candidate_components
from dtwin.benchmark.openswisshcc_highdimensional_inference import _atomic_json, _canonical_hash
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LOCALIZER_CASE_SCHEMA
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.core import PipelineError


PLAN_SCHEMA = "argos-openswisshcc-candidate-volume-timing-selection-v16"
ALIGNMENT_SCHEMA = "argos-public-liver-mri-alignment-v1"
SCENARIOS = ("fallback", "one_candidate", "three_candidates", "five_candidates")


def _load(path: Path, description: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _technical_record(case_id: str, localizer_root: Path, alignment_root: Path) -> dict:
    localizer_path = localizer_root / case_id / "localizer_manifest.json"
    localizer = _load(localizer_path, "Manifesto localizador do piloto temporal v16")
    features = localizer.get("features", {})
    if (
        localizer.get("schema") != LOCALIZER_CASE_SCHEMA
        or localizer.get("case_id") != case_id
        or localizer.get("status") != "candidate_scores_only_no_decision"
        or localizer.get("ground_truth_read") is not False
        or localizer.get("ground_truth_lesion_mask_used") is not False
        or localizer.get("final_decision") is not None
        or localizer.get("research_only") is not True
        or localizer.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Manifesto localizador viola salvaguardas do piloto temporal v16.")
    components = features.get("components")
    total = int(features.get("inside_liver_voxels", -1))
    if not isinstance(components, list):
        raise PipelineError("Componentes do localizador ausentes no piloto temporal v16.")
    selected, coverage = select_candidate_components(components, total_candidate_voxels=total)
    stack_count = len(selected) if selected else 1
    fallback = not bool(selected)
    localizer_seconds = float(localizer.get("elapsed_seconds", -1))
    if localizer_seconds < 0:
        raise PipelineError("Tempo do localizador negativo/ausente no piloto temporal v16.")
    scenario = (
        "fallback" if fallback else
        "one_candidate" if stack_count == 1 else
        "three_candidates" if stack_count == 3 else
        "five_candidates" if stack_count == 5 else
        "not_selected_scenario"
    )
    record = {
        "case_id": case_id,
        "scenario": scenario,
        "localizer_component_count": len(components),
        "selected_candidate_count": len(selected),
        "candidate_stack_count": stack_count,
        "fallback_no_candidate": fallback,
        "candidate_volume_coverage_fraction": coverage,
        "localizer_elapsed_seconds": localizer_seconds,
        "localizer_manifest_sha256": _sha256(localizer_path),
    }

    alignment_path = alignment_root / case_id / "alignment_manifest.json"
    if not alignment_path.is_file():
        return {
            **record,
            "alignment_available": False,
            "alignment_unavailable_reason": "alignment_manifest_missing_after_blind_dice_gate",
            "alignment_elapsed_seconds": None,
            "known_preprocessing_seconds": None,
            "alignment_manifest_sha256": None,
        }
    alignment = _load(alignment_path, "Manifesto de alinhamento do piloto temporal v16")
    if (
        alignment.get("schema") != ALIGNMENT_SCHEMA
        or alignment.get("case_id") != case_id
        or alignment.get("reference_phase") != "venous"
        or alignment.get("research_only") is not True
        or alignment.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Alinhamento viola salvaguardas do piloto temporal v16.")
    alignment_seconds = float(alignment.get("elapsed_seconds", -1))
    if alignment_seconds < 0:
        raise PipelineError("Tempo de alinhamento negativo/ausente no piloto temporal v16.")
    return {
        **record,
        "alignment_available": True,
        "alignment_unavailable_reason": None,
        "alignment_elapsed_seconds": alignment_seconds,
        "known_preprocessing_seconds": localizer_seconds + alignment_seconds,
        "alignment_manifest_sha256": _sha256(alignment_path),
    }


def build_timing_selection_plan(*, localizer_root: Path, alignment_root: Path, out_path: Path) -> dict:
    localizer_root = Path(localizer_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    summary_path = localizer_root / "summary.json"
    summary = _load(summary_path, "Resumo mesclado do localizador v16")
    if (
        summary.get("schema") != MERGED_RUN_SCHEMA
        or summary.get("status") != "complete_scores_only_no_decision"
        or summary.get("ground_truth_read") is not False
        or summary.get("ground_truth_lesion_mask_used") is not False
        or summary.get("final_decision") is not None
        or summary.get("case_count") != len(summary.get("case_ids", []))
    ):
        raise PipelineError("Resumo do localizador invalido para selecao temporal v16.")
    records = [_technical_record(case_id, localizer_root, alignment_root) for case_id in summary["case_ids"]]
    available = [record for record in records if record["alignment_available"]]
    unavailable = [record for record in records if not record["alignment_available"]]
    selected = []
    for scenario in SCENARIOS:
        eligible = [record for record in available if record["scenario"] == scenario]
        if not eligible:
            raise PipelineError(f"Cenario temporal v16 sem caso elegivel: {scenario}.")
        # Pior tempo tecnico conhecido; empate por case_id torna a escolha deterministica.
        chosen = sorted(eligible, key=lambda item: (-item["known_preprocessing_seconds"], item["case_id"]))[0]
        selected.append(chosen)
    unavailable_records = [
        {
            "case_id": item["case_id"],
            "scenario": item["scenario"],
            "candidate_stack_count": item["candidate_stack_count"],
            "reason": item["alignment_unavailable_reason"],
            "localizer_elapsed_seconds": item["localizer_elapsed_seconds"],
            "localizer_manifest_sha256": item["localizer_manifest_sha256"],
        }
        for item in sorted(unavailable, key=lambda value: value["case_id"])
    ]
    base = {
        "schema": PLAN_SCHEMA,
        "status": "frozen_blind_before_v16_scores",
        "selection_rule": "maximum_known_localizer_plus_alignment_seconds_per_scenario_then_case_id",
        "scenario_order": list(SCENARIOS),
        "selected_cases": selected,
        "source_case_count": len(records),
        "alignment_available_case_count": len(available),
        "alignment_unavailable_case_count": len(unavailable_records),
        "alignment_unavailable_cases": unavailable_records,
        "source_localizer_summary_sha256": _sha256(summary_path),
        "timing_scope": {
            "known_preprocessing_includes": ["alignment", "localizer"],
            "pilot_must_measure_fresh": ["rendering", "candidate_scoring", "end_to_end_wall"],
            "case_time_gate_seconds": 180.0,
        },
        "selection_used_labels": False,
        "ground_truth_read": False,
        "ground_truth_read_by_selection_process": False,
        "development_labels_previously_visible_to_orchestrator": True,
        "development_results_classification": "exploratory_only",
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    plan = dict(base)
    plan["plan_signature"] = _canonical_hash(base)
    out_path = Path(out_path)
    if out_path.exists():
        existing = _load(out_path, "Plano temporal v16 existente")
        if existing != plan:
            raise PipelineError("Plano temporal v16 existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(out_path, plan)
    return plan