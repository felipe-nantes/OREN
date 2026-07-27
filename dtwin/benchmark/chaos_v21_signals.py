"""Review-gated, label-blind v21 signals for the CHAOS specificity stress arm."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.chaos_v21_panels import (
    COHORT_SCHEMA,
    _case_files,
    _load,
    _safe_relative,
    _validate_config,
)
from dtwin.benchmark.chaos_v21_preparation import verify_chaos_v21_blind_inputs
from dtwin.benchmark.chaos_v21_review import verify_chaos_v21_review
from dtwin.benchmark.liverhccseg_v21_signals import (
    LOCALIZER_INPUT_SCHEMA,
    assemble_v21_raw_signals,
    run_v21_medgemma_scores,
    run_v21_medsiglip_scores,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError
from dtwin.medsiglip_zero_shot import load_medsiglip_config


MEDGEMMA_CASE_SCHEMA = "argos-chaos-v21-medgemma-choice-score-v1"
MEDGEMMA_RUN_SCHEMA = "argos-chaos-v21-medgemma-choice-batch-v1"
MEDSIGLIP_CASE_SCHEMA = "argos-chaos-v21-medsiglip-score-v1"
MEDSIGLIP_RUN_SCHEMA = "argos-chaos-v21-medsiglip-batch-v1"
RAW_SIGNAL_SUMMARY_SCHEMA = "argos-chaos-v21-raw-signal-batch-v1"
LOCALIZER_IMAGE_ROLE = "t2_spir"
LOCALIZER_MASK_ROLE = "liver_mask"


def verify_chaos_v21_signal_context(
    *, panel_root: Path, gallery_root: Path, review_path: Path, prepared_root: Path,
    medgemma_config_path: Path, medsiglip_config_path: Path, expected_case_count: int = 20,
) -> dict[str, Any]:
    """Run every non-model gate before constructing a model object."""

    panel_root = Path(panel_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    review = verify_chaos_v21_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
    )
    cohort = _load(panel_root / "cohort_manifest.json")
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("case_count") != expected_case_count
        or cohort.get("case_ids") != review.get("approved_case_ids")
        or cohort.get("config_sha256") != _sha256(Path(medgemma_config_path).resolve())
        or cohort.get("ground_truth_read") is not False
        or cohort.get("holdout_opened") is not False
        or cohort.get("combined_primary_metric_allowed") is not False
    ):
        raise PipelineError("Coorte CHAOS v21 divergiu da revisao ou da config do leitor.")
    config = _validate_config(Path(medgemma_config_path).resolve())
    med = config["medgemma"]
    if med.get("model_id") != "google/medgemma-1.5-4b-it" or med.get("model_parameter_scale") != "4B":
        raise PipelineError("Executor CHAOS v21 exige exatamente MedGemma 1.5 4B.")
    medsig = load_medsiglip_config(Path(medsiglip_config_path).resolve())
    if medsig.model_id != "google/medsiglip-448" or medsig.decision_enabled is not False:
        raise PipelineError("Executor CHAOS v21 exige MedSigLIP 448 sem decisao autonoma.")
    prepared = verify_chaos_v21_blind_inputs(
        prepared_root=prepared_root, expected_case_count=expected_case_count,
        expected_cohort_signature=str(cohort["prepared_cohort_signature"]),
    )
    for record in cohort["cases"]:
        panel = _safe_relative(panel_root, str(record.get("panel", "")))
        if not panel.is_file() or _sha256(panel) != record.get("panel_sha256"):
            raise PipelineError("Painel CHAOS v21 ausente ou adulterado antes dos scores.")
    return {
        "cohort": cohort, "review": review, "prepared": prepared,
        "medgemma_config": config, "medsiglip_config": medsig,
        "case_ids": list(cohort["case_ids"]),
        "review_signature": review["review_signature"],
        "evaluation_scope": "secondary_negative_domain_shift_stress_only",
        "combined_primary_metric_allowed": False,
        "medgemma_case_schema": MEDGEMMA_CASE_SCHEMA,
        "medgemma_run_schema": MEDGEMMA_RUN_SCHEMA,
        "medsiglip_case_schema": MEDSIGLIP_CASE_SCHEMA,
        "medsiglip_run_schema": MEDSIGLIP_RUN_SCHEMA,
        "raw_signal_summary_schema": RAW_SIGNAL_SUMMARY_SCHEMA,
    }


def build_chaos_v21_localizer_input_manifest(
    *, panel_root: Path, gallery_root: Path, review_path: Path, prepared_root: Path,
    medgemma_config_path: Path, medsiglip_config_path: Path, output_path: Path,
    expected_case_count: int = 20,
) -> dict[str, Any]:
    """Create a neutral localizer input using T2-SPIR, only after review."""

    context = verify_chaos_v21_signal_context(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
        prepared_root=prepared_root, medgemma_config_path=medgemma_config_path,
        medsiglip_config_path=medsiglip_config_path, expected_case_count=expected_case_count,
    )
    prepared_root = Path(prepared_root).resolve()
    prepared_cohort = _load(prepared_root / "cohort_manifest.json")
    prepared_by_id = {str(item["case_id"]): item for item in prepared_cohort["cases"]}
    rows = []
    for case_id in context["case_ids"]:
        _manifest, files = _case_files(prepared_root, prepared_by_id[case_id])
        records = []
        for role in (LOCALIZER_IMAGE_ROLE, LOCALIZER_MASK_ROLE):
            path = files[role]
            records.append({
                "role": role, "relative_path": path.relative_to(prepared_root).as_posix(),
                "bytes": path.stat().st_size, "sha256": _sha256(path),
            })
        rows.append({
            "schema": LOCALIZER_INPUT_SCHEMA, "case_id": case_id, "files": records,
            "localizer_input_semantics": "T2-SPIR secondary domain-shift stress; not T1 venous",
            "review_signature": context["review_signature"],
            "lesion_mask_available": False, "ground_truth_read": False,
            "holdout_opened": False, "combined_primary_metric_allowed": False,
            "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        })
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Manifesto localizador CHAOS v21 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(output)
    return {
        "status": "ready_for_label_blind_localizer",
        "case_count": len(rows), "manifest_sha256": _sha256(output),
        "review_signature": context["review_signature"],
        "input_role": LOCALIZER_IMAGE_ROLE, "liver_mask_role": LOCALIZER_MASK_ROLE,
        "ground_truth_read": False, "holdout_opened": False,
        "combined_primary_metric_allowed": False,
    }


__all__ = [
    "assemble_v21_raw_signals",
    "build_chaos_v21_localizer_input_manifest",
    "run_v21_medgemma_scores",
    "run_v21_medsiglip_scores",
    "verify_chaos_v21_signal_context",
]
