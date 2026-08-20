"""Review-gated v11 signal generation for the LLD-MMRI v23 cohort."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.liverhccseg_v21_panels import _validate_config
from dtwin.benchmark.liverhccseg_v21_signals import (
    assemble_v21_raw_signals,
    run_v21_medgemma_scores,
    run_v21_medsiglip_scores,
)
from dtwin.benchmark.lld_mmri_v23_panels import COHORT_SCHEMA, _load, _safe
from dtwin.benchmark.lld_mmri_v23_preparation import (
    MASK_ROLE,
    verify_lld_mmri_v23_blind_inputs,
)
from dtwin.benchmark.lld_mmri_v23_review import verify_lld_mmri_v23_review
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import INPUT_SCHEMA
from dtwin.core import PipelineError
from dtwin.medsiglip_zero_shot import load_medsiglip_config

MEDGEMMA_CASE_SCHEMA = "argos-lld-mmri-v23-medgemma-choice-score-v1"
MEDGEMMA_RUN_SCHEMA = "argos-lld-mmri-v23-medgemma-choice-batch-v1"
MEDSIGLIP_CASE_SCHEMA = "argos-lld-mmri-v23-medsiglip-score-v1"
MEDSIGLIP_RUN_SCHEMA = "argos-lld-mmri-v23-medsiglip-batch-v1"
RAW_SIGNAL_SUMMARY_SCHEMA = "argos-lld-mmri-v23-raw-signal-batch-v1"


def _prepared_rows(prepared_root: Path) -> dict[str, dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in (prepared_root / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Inputs LLD-MMRI ausentes para os sinais v23.") from exc
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if row.get("schema") != INPUT_SCHEMA or case_id in indexed:
            raise PipelineError("Input LLD-MMRI invalido ou duplicado.")
        indexed[case_id] = row
    return indexed


def verify_lld_mmri_v23_signal_context(
    *,
    protocol_root: Path,
    panel_root: Path,
    gallery_root: Path,
    review_path: Path,
    prepared_root: Path,
    medgemma_config_path: Path,
    medsiglip_config_path: Path,
    expected_case_count: int = 335,
) -> dict[str, Any]:
    """Run every non-model gate before any GPU model may be constructed."""

    panel_root = Path(panel_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    medgemma_config_path = Path(medgemma_config_path).resolve()
    medsiglip_config_path = Path(medsiglip_config_path).resolve()
    review = verify_lld_mmri_v23_review(
        panel_root=panel_root,
        gallery_root=gallery_root,
        review_path=review_path,
    )
    cohort_path = panel_root / "cohort_manifest.json"
    cohort = _load(cohort_path)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("protocol_case_count") != expected_case_count
        or cohort.get("case_count", 0) + cohort.get("technical_failure_case_count", 0)
        != expected_case_count
        or cohort.get("technical_failure_case_count")
        != len(cohort.get("technical_failure_case_ids", []))
        or cohort.get("technical_failures_excluded_from_inference") is not True
        or cohort.get("technical_failures_count_as_primary_metric_errors") is not True
        or cohort.get("case_ids") != review.get("approved_case_ids")
        or cohort.get("config_sha256") != _sha256(medgemma_config_path)
        or cohort.get("ground_truth_read") is not False
        or cohort.get("lesion_masks_used") is not False
    ):
        raise PipelineError("Coorte LLD-MMRI divergiu da revisao ou do leitor v11/v4.")
    config = _validate_config(medgemma_config_path)
    med = config["medgemma"]
    if (
        med.get("model_id") != "google/medgemma-1.5-4b-it"
        or med.get("model_parameter_scale") != "4B"
    ):
        raise PipelineError("Executor LLD-MMRI exige exatamente MedGemma 1.5 4B.")
    medsiglip = load_medsiglip_config(medsiglip_config_path)
    if medsiglip.model_id != "google/medsiglip-448" or medsiglip.decision_enabled is not False:
        raise PipelineError("Executor LLD-MMRI exige MedSigLIP 448 sem decisao autonoma.")
    prepared = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol_root,
        prepared_root=prepared_root,
        expected_preparation_signature=str(cohort["preparation_signature"]),
    )
    if (
        prepared["protocol_case_count"] != expected_case_count
        or prepared["case_count"] != cohort["case_count"]
        or prepared["technical_failure_case_count"]
        != cohort["technical_failure_case_count"]
        or prepared["technical_failure_case_ids"]
        != cohort["technical_failure_case_ids"]
    ):
        raise PipelineError("Preparacao LLD-MMRI divergiu do contrato 335/321/14.")
    for record in cohort["cases"]:
        panel = _safe(panel_root, str(record.get("panel", "")))
        if not panel.is_file() or _sha256(panel) != record.get("panel_sha256"):
            raise PipelineError("Painel LLD-MMRI mudou depois da revisao.")
    return {
        "cohort": cohort,
        "review": review,
        "prepared": prepared,
        "medgemma_config": config,
        "medsiglip_config": medsiglip,
        "case_ids": list(cohort["case_ids"]),
        "protocol_case_count": cohort["protocol_case_count"],
        "case_count": cohort["case_count"],
        "technical_failure_case_count": cohort["technical_failure_case_count"],
        "technical_failure_case_ids": list(cohort["technical_failure_case_ids"]),
        "technical_failures_count_as_primary_metric_errors": True,
        "review_signature": review["review_signature"],
        "medgemma_config_sha256": _sha256(medgemma_config_path),
        "medsiglip_config_sha256": _sha256(medsiglip_config_path),
        "medgemma_case_schema": MEDGEMMA_CASE_SCHEMA,
        "medgemma_run_schema": MEDGEMMA_RUN_SCHEMA,
        "medsiglip_case_schema": MEDSIGLIP_CASE_SCHEMA,
        "medsiglip_run_schema": MEDSIGLIP_RUN_SCHEMA,
        "raw_signal_summary_schema": RAW_SIGNAL_SUMMARY_SCHEMA,
    }


def build_lld_mmri_v23_localizer_input_manifest(
    *, context: dict[str, Any], prepared_root: Path, output_path: Path
) -> dict[str, Any]:
    """Publish only venous MRI and automatic liver mask after human approval."""

    prepared_root = Path(prepared_root).resolve()
    indexed = _prepared_rows(prepared_root)
    rows: list[dict[str, Any]] = []
    for case_id in context["case_ids"]:
        source = indexed.get(case_id)
        if source is None:
            raise PipelineError("Caso aprovado ausente nos inputs LLD-MMRI.")
        by_role = {str(item.get("role", "")): item for item in source.get("files", [])}
        if "t1_venous" not in by_role or MASK_ROLE not in by_role:
            raise PipelineError("Imagem venosa ou mascara hepatica LLD-MMRI ausente.")
        files = []
        for role in ("t1_venous", MASK_ROLE):
            item = by_role[role]
            path = _safe(prepared_root / "inputs", str(item.get("relative_path", "")))
            if (
                not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or _sha256(path) != item.get("sha256")
            ):
                raise PipelineError("Input do localizador LLD-MMRI adulterado.")
            files.append(
                {
                    "role": role,
                    "relative_path": str(item["relative_path"]),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        rows.append(
            {
                "schema": INPUT_SCHEMA,
                "case_id": case_id,
                "files": files,
                "review_signature": context["review_signature"],
                "lesion_mask_available": False,
                "ground_truth_read": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
        )
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Manifesto localizador LLD-MMRI existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return {
        "status": "ready_for_label_blind_localizer",
        "protocol_case_count": context["protocol_case_count"],
        "case_count": len(rows),
        "technical_failure_case_count": context["technical_failure_case_count"],
        "technical_failure_case_ids": context["technical_failure_case_ids"],
        "technical_failures_count_as_primary_metric_errors": True,
        "manifest_sha256": _sha256(output_path),
        "review_signature": context["review_signature"],
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }


def assemble_lld_mmri_v23_raw_signals(
    *,
    context: dict[str, Any],
    medgemma_root: Path,
    medsiglip_root: Path,
    localizer_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Assemble the exact three raw v11 signals without labels or decisions."""

    return assemble_v21_raw_signals(
        context=context,
        medgemma_root=medgemma_root,
        medsiglip_root=medsiglip_root,
        localizer_root=localizer_root,
        output_dir=output_dir,
    )


__all__ = [
    "MEDGEMMA_CASE_SCHEMA",
    "MEDGEMMA_RUN_SCHEMA",
    "MEDSIGLIP_CASE_SCHEMA",
    "MEDSIGLIP_RUN_SCHEMA",
    "RAW_SIGNAL_SUMMARY_SCHEMA",
    "assemble_lld_mmri_v23_raw_signals",
    "build_lld_mmri_v23_localizer_input_manifest",
    "run_v21_medgemma_scores",
    "run_v21_medsiglip_scores",
    "verify_lld_mmri_v23_signal_context",
]
