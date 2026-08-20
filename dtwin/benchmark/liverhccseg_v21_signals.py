"""Label-blind, review-gated v21 signal generation for LiverHccSeg.

The three readers are intentionally separate. On the 8 GB CUDA workstation the
TotalSegmentator localizer, MedSigLIP and MedGemma must not be resident at the
same time. Component outputs are immutable and are assembled only after all
three complete with matching panel/review hashes.
"""
from __future__ import annotations

import json
import math
import shutil
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

from dtwin.benchmark.liverhccseg_preparation import verify_liverhccseg_blind_inputs
from dtwin.benchmark.liverhccseg_v21_panels import (
    COHORT_SCHEMA,
    _case_files,
    _load,
    _safe_relative,
    _validate_config,
)
from dtwin.benchmark.liverhccseg_v21_review import verify_liverhccseg_v21_review
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA as LOCALIZER_CASE_SCHEMA,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    RUN_SCHEMA as LOCALIZER_RUN_SCHEMA,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    RAW_SIGNAL_SCHEMA,
    _canonical_sha,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic
from dtwin.medsiglip_zero_shot import load_medsiglip_config

MEDGEMMA_CASE_SCHEMA = "argos-liverhccseg-v21-medgemma-choice-score-v1"
MEDGEMMA_RUN_SCHEMA = "argos-liverhccseg-v21-medgemma-choice-batch-v1"
MEDSIGLIP_CASE_SCHEMA = "argos-liverhccseg-v21-medsiglip-score-v1"
MEDSIGLIP_RUN_SCHEMA = "argos-liverhccseg-v21-medsiglip-batch-v1"
RAW_SIGNAL_SUMMARY_SCHEMA = "argos-public-independent-v21-raw-signal-batch-v1"
LOCALIZER_INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
CHOICES = ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")


class MedGemmaChoiceScorer(Protocol):
    model_id: str
    model_version: str

    def score_panel(self, panel_path: Path, prompt: str) -> dict[str, Any]: ...


class MedSigLIPPanelScorer(Protocol):
    def score_panel(self, panel_path: Path) -> dict[str, Any]: ...


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL v21 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"JSONL v21 vazio ou invalido: {path}")
    return rows


def _finite(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError("Valor de sinal v21 nao numerico.")
    result = float(value)
    if not math.isfinite(result):
        raise PipelineError("Valor de sinal v21 nao finito.")
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise PipelineError("Valor de sinal v21 fora do intervalo permitido.")
    return result


def verify_v21_signal_context(
    *, panel_root: Path, gallery_root: Path, review_path: Path, prepared_root: Path,
    medgemma_config_path: Path, medsiglip_config_path: Path, expected_case_count: int = 14,
) -> dict[str, Any]:
    """Run all non-model gates before a model object is created."""

    panel_root = Path(panel_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    review = verify_liverhccseg_v21_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path
    )
    cohort = _load(panel_root / "cohort_manifest.json")
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("case_count") != expected_case_count
        or cohort.get("case_ids") != review.get("approved_case_ids")
        or cohort.get("config_sha256") != _sha256(Path(medgemma_config_path).resolve())
        or cohort.get("ground_truth_read") is not False
        or cohort.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte v21 divergiu da revisao ou da config do leitor.")
    config = _validate_config(Path(medgemma_config_path).resolve())
    med = config["medgemma"]
    if med.get("model_id") != "google/medgemma-1.5-4b-it" or med.get("model_parameter_scale") != "4B":
        raise PipelineError("Executor v21 exige exatamente MedGemma 1.5 4B.")
    medsig = load_medsiglip_config(Path(medsiglip_config_path).resolve())
    if medsig.model_id != "google/medsiglip-448" or medsig.decision_enabled is not False:
        raise PipelineError("Executor v21 exige MedSigLIP 448 sem decisao autonoma.")
    prepared = verify_liverhccseg_blind_inputs(
        prepared_root=prepared_root,
        expected_case_count=expected_case_count,
        expected_cohort_signature=str(cohort["prepared_cohort_signature"]),
    )
    for record in cohort["cases"]:
        panel = _safe_relative(panel_root, str(record.get("panel", "")))
        if not panel.is_file() or _sha256(panel) != record.get("panel_sha256"):
            raise PipelineError("Painel v21 ausente ou adulterado antes dos scores.")
    return {
        "cohort": cohort,
        "review": review,
        "prepared": prepared,
        "medgemma_config": config,
        "medsiglip_config": medsig,
        "case_ids": list(cohort["case_ids"]),
        "review_signature": review["review_signature"],
    }


def build_v21_localizer_input_manifest(
    *, panel_root: Path, gallery_root: Path, review_path: Path, prepared_root: Path,
    medgemma_config_path: Path, medsiglip_config_path: Path, output_path: Path,
    expected_case_count: int = 14,
) -> dict[str, Any]:
    """Create the neutral v10-compatible input manifest after review approval."""

    context = verify_v21_signal_context(
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
        for role, source_role in (("t1_venous", "t1_venous"), ("liver_mask_venous", "liver_mask")):
            path = files[source_role]
            records.append({
                "role": role,
                "relative_path": path.relative_to(prepared_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
        rows.append({
            "schema": LOCALIZER_INPUT_SCHEMA,
            "case_id": case_id,
            "files": records,
            "review_signature": context["review_signature"],
            "lesion_mask_available": False,
            "ground_truth_read": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        })
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Manifesto localizador v21 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(output)
    return {
        "status": "ready_for_label_blind_localizer",
        "case_count": len(rows),
        "manifest_sha256": _sha256(output),
        "review_signature": context["review_signature"],
        "ground_truth_read": False,
        "holdout_opened": False,
    }


def _validate_probabilities(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(CHOICES):
        raise PipelineError("Probabilidades MedGemma v21 incompletas.")
    result = {name: _finite(value[name], minimum=0.0, maximum=1.0) for name in CHOICES}
    if not math.isclose(sum(result.values()), 1.0, abs_tol=2e-5):
        raise PipelineError("Probabilidades MedGemma v21 nao somam 1.")
    return result


def run_v21_medgemma_scores(
    *, context: dict[str, Any], panel_root: Path, output_root: Path,
    scorer: MedGemmaChoiceScorer,
) -> dict[str, Any]:
    """Score the reviewed panel once per case; no class decision is emitted."""

    if scorer.model_id != "google/medgemma-1.5-4b-it":
        raise PipelineError("Scorer v21 nao confirmou o MedGemma 1.5 4B.")
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Scores MedGemma v21 ja existem.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v21mg_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows = []
    started_all = time.monotonic()
    prompt = str(context["medgemma_config"].get("prompt", {}).get("template", ""))
    if not prompt:
        raise PipelineError("Prompt MedGemma v21 vazio.")
    case_schema = str(context.get("medgemma_case_schema", MEDGEMMA_CASE_SCHEMA))
    run_schema = str(context.get("medgemma_run_schema", MEDGEMMA_RUN_SCHEMA))
    try:
        for record in context["cohort"]["cases"]:
            case_id = str(record["case_id"])
            panel = _safe_relative(panel_root, str(record["panel"]))
            started = time.monotonic()
            score = scorer.score_panel(panel, prompt)
            elapsed = time.monotonic() - started
            probabilities = _validate_probabilities(score.get("choice_probabilities"))
            row = {
                "schema": case_schema,
                "case_id": case_id,
                "panel_sha256": record["panel_sha256"],
                "model_id": scorer.model_id,
                "model_version": scorer.model_version,
                "choice_probabilities": probabilities,
                "raw_signal": probabilities["INCONCLUSIVA"] - probabilities["NEGATIVA"],
                "elapsed_seconds": elapsed,
                "review_signature": context["review_signature"],
                "final_decision": None,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "holdout_opened": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            rows.append(row)
        scores_path = staging / "scores.jsonl"
        scores_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        summary = {
            "schema": run_schema, "status": "complete_scores_only_no_decision",
            "case_count": len(rows), "case_ids": context["case_ids"],
            "scores_sha256": _sha256(scores_path), "review_signature": context["review_signature"],
            "mean_case_seconds": statistics.fmean(row["elapsed_seconds"] for row in rows),
            "max_case_seconds": max(row["elapsed_seconds"] for row in rows),
            "total_wall_seconds": time.monotonic() - started_all,
            "final_decision": None, "ground_truth_read": False, "metrics_calculated": False,
            "holdout_opened": False, "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if "protocol_case_count" in context:
            summary.update(
                {
                    "protocol_case_count": context["protocol_case_count"],
                    "technical_failure_case_count": context[
                        "technical_failure_case_count"
                    ],
                    "technical_failure_case_ids": context[
                        "technical_failure_case_ids"
                    ],
                    "technical_failures_excluded_from_inference": True,
                    "technical_failures_count_as_primary_metric_errors": True,
                }
            )
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def run_v21_medsiglip_scores(
    *, context: dict[str, Any], panel_root: Path, output_root: Path,
    scorer: MedSigLIPPanelScorer,
) -> dict[str, Any]:
    """Persist the inverse sagittal v5 signal without a final decision."""

    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Scores MedSigLIP v21 ja existem.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v21ms_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows = []
    started_all = time.monotonic()
    case_schema = str(context.get("medsiglip_case_schema", MEDSIGLIP_CASE_SCHEMA))
    run_schema = str(context.get("medsiglip_run_schema", MEDSIGLIP_RUN_SCHEMA))
    try:
        for record in context["cohort"]["cases"]:
            case_id = str(record["case_id"])
            panel = _safe_relative(panel_root, str(record["panel"]))
            started = time.monotonic()
            score = scorer.score_panel(panel)
            elapsed = time.monotonic() - started
            scores = score.get("scores") if isinstance(score, dict) else None
            views = score.get("view_order") if isinstance(score, dict) else None
            if (
                score.get("schema") != "argos-medsiglip-scores-v2"
                or score.get("panel_sha256") != record["panel_sha256"]
                or not isinstance(scores, list) or len(scores) != 11
                or not isinstance(views, list) or len(views) != 11 or views[-1] != "sagittal"
                or score.get("final_decision") is not None
                or score.get("research_only") is not True
                or score.get("clinical_use_allowed") is not False
            ):
                raise PipelineError("Score MedSigLIP v21 invalido ou divergente do painel.")
            sagittal = _finite(scores[-1].get("positive_probability"), minimum=0.0, maximum=1.0)
            rows.append({
                "schema": case_schema, "case_id": case_id,
                "panel_sha256": record["panel_sha256"], "score": score,
                "raw_signal": -sagittal, "elapsed_seconds": elapsed,
                "review_signature": context["review_signature"], "final_decision": None,
                "ground_truth_read": False, "metrics_calculated": False, "holdout_opened": False,
                "research_only": True, "clinical_use_allowed": False, "requires_human_review": True,
            })
        scores_path = staging / "scores.jsonl"
        scores_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        summary = {
            "schema": run_schema, "status": "complete_scores_only_no_decision",
            "case_count": len(rows), "case_ids": context["case_ids"],
            "scores_sha256": _sha256(scores_path), "review_signature": context["review_signature"],
            "mean_case_seconds": statistics.fmean(row["elapsed_seconds"] for row in rows),
            "max_case_seconds": max(row["elapsed_seconds"] for row in rows),
            "total_wall_seconds": time.monotonic() - started_all,
            "final_decision": None, "ground_truth_read": False, "metrics_calculated": False,
            "holdout_opened": False, "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _component_rows(root: Path, schema: str, case_schema: str, context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = Path(root).resolve()
    summary = _load(root / "summary.json")
    scores_path = root / "scores.jsonl"
    if (
        summary.get("schema") != schema or summary.get("status") != "complete_scores_only_no_decision"
        or summary.get("case_ids") != context["case_ids"] or summary.get("case_count") != len(context["case_ids"])
        or summary.get("scores_sha256") != _sha256(scores_path)
        or summary.get("review_signature") != context["review_signature"]
        or summary.get("ground_truth_read") is not False or summary.get("holdout_opened") is not False
    ):
        raise PipelineError("Lote de componente v21 incompleto ou adulterado.")
    rows = _jsonl(scores_path)
    if [row.get("case_id") for row in rows] != context["case_ids"] or any(row.get("schema") != case_schema for row in rows):
        raise PipelineError("Registros de componente v21 divergiram da coorte.")
    return {str(row["case_id"]): row for row in rows}


def assemble_v21_raw_signals(
    *, context: dict[str, Any], medgemma_root: Path, medsiglip_root: Path,
    localizer_root: Path, output_dir: Path,
) -> dict[str, Any]:
    """Assemble the exact three v11 raw signals; labels remain unavailable."""

    mg = _component_rows(
        medgemma_root,
        str(context.get("medgemma_run_schema", MEDGEMMA_RUN_SCHEMA)),
        str(context.get("medgemma_case_schema", MEDGEMMA_CASE_SCHEMA)),
        context,
    )
    ms = _component_rows(
        medsiglip_root,
        str(context.get("medsiglip_run_schema", MEDSIGLIP_RUN_SCHEMA)),
        str(context.get("medsiglip_case_schema", MEDSIGLIP_CASE_SCHEMA)),
        context,
    )
    localizer_root = Path(localizer_root).resolve()
    localizer_summary = _load(localizer_root / "summary.json")
    if (
        localizer_summary.get("schema") != LOCALIZER_RUN_SCHEMA
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("case_ids") != context["case_ids"]
        or localizer_summary.get("selection_signature") != context["review_signature"]
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("ground_truth_read") is not False
    ):
        raise PipelineError("Lote localizador v21 incompleto ou divergente da revisao.")
    rows = []
    for case_id in context["case_ids"]:
        lm_path = localizer_root / case_id / "localizer_manifest.json"
        lm = _load(lm_path)
        volume = lm.get("features", {}).get("total_candidate_volume_mm3")
        if (
            lm.get("schema") != LOCALIZER_CASE_SCHEMA or lm.get("case_id") != case_id
            or lm.get("ground_truth_lesion_mask_used") is not False or lm.get("ground_truth_read") is not False
        ):
            raise PipelineError("Manifesto localizador v21 invalido.")
        localizer_signal = math.log1p(_finite(volume, minimum=0.0))
        component_seconds = {
            "medgemma_v4": _finite(mg[case_id]["elapsed_seconds"], minimum=0.0),
            "medsiglip_v5": _finite(ms[case_id]["elapsed_seconds"], minimum=0.0),
            "localizer_v10": _finite(lm["elapsed_seconds"], minimum=0.0),
        }
        rows.append({
            "schema": RAW_SIGNAL_SCHEMA, "case_id": case_id,
            "signals": {
                "medgemma_v4_uncertainty_margin": _finite(mg[case_id]["raw_signal"]),
                "medsiglip_v5_inverse_sagittal": _finite(ms[case_id]["raw_signal"]),
                "localizer_v10_log_volume": localizer_signal,
            },
            "component_elapsed_seconds": component_seconds,
            "component_hashes": {
                "medgemma_record": _canonical_sha(mg[case_id]),
                "medsiglip_record": _canonical_sha(ms[case_id]),
                "localizer_manifest_sha256": _sha256(lm_path),
            },
            "review_signature": context["review_signature"],
            "ground_truth_read": False, "metrics_calculated": False, "final_decision": None,
            "holdout_opened": False, "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        })
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Bundle de sinais crus v21 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v21raw_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        signals_path = staging / "raw_signals.jsonl"
        signals_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        totals = [sum(row["component_elapsed_seconds"].values()) for row in rows]
        summary = {
            "schema": str(context.get("raw_signal_summary_schema", RAW_SIGNAL_SUMMARY_SCHEMA)),
            "status": "complete_raw_signals_no_labels_no_decision",
            "case_count": len(rows), "case_ids": context["case_ids"], "signals_sha256": _sha256(signals_path),
            "review_signature": context["review_signature"], "mean_component_sum_seconds": statistics.fmean(totals),
            "max_component_sum_seconds": max(totals), "all_time_gates_180_seconds_passed": all(value <= 180.0 for value in totals),
            "ground_truth_read": False, "metrics_calculated": False, "final_decision": None,
            "holdout_opened": False, "research_only": True, "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if "protocol_case_count" in context:
            summary.update(
                {
                    "protocol_case_count": context["protocol_case_count"],
                    "technical_failure_case_count": context[
                        "technical_failure_case_count"
                    ],
                    "technical_failure_case_ids": context[
                        "technical_failure_case_ids"
                    ],
                    "technical_failures_excluded_from_inference": True,
                    "technical_failures_count_as_primary_metric_errors": True,
                }
            )
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_dir)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
