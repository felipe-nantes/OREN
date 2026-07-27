"""Review-gated, label-blind v21 execution for the OpenSwissHCC holdout."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from dtwin.benchmark.liverhccseg_v21_signals import (
    assemble_v21_raw_signals,
    run_v21_medsiglip_scores,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_holdout import (
    HOLDOUT_AUDIT_SCHEMA,
    HOLDOUT_INPUT_SCHEMA,
    audit_prepared_holdout_label_blind,
)
from dtwin.benchmark.openswisshcc_holdout_panels import (
    COHORT_SCHEMA,
    _validate_config,
)
from dtwin.benchmark.openswisshcc_holdout_review import (
    EXPECTED_CASE_COUNT,
    FALLBACK_KIND,
    verify_holdout_uniform9_review,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    _canonical_sha,
    _load_calibrator,
    score_external_signals,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic
from dtwin.medsiglip_zero_shot import load_medsiglip_config


LOCALIZER_INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
MEDGEMMA_CASE_SCHEMA = "argos-openswisshcc-holdout-v21-medgemma-choice-score-v1"
MEDGEMMA_RUN_SCHEMA = "argos-openswisshcc-holdout-v21-medgemma-choice-batch-v1"
MEDSIGLIP_CASE_SCHEMA = "argos-openswisshcc-holdout-v21-medsiglip-score-v1"
MEDSIGLIP_RUN_SCHEMA = "argos-openswisshcc-holdout-v21-medsiglip-batch-v1"
RAW_SIGNAL_SUMMARY_SCHEMA = "argos-openswisshcc-holdout-v21-raw-signal-batch-v1"
PREDICTION_FREEZE_SCHEMA = "argos-openswisshcc-holdout-v21-prediction-freeze-v1"
CHOICES = ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")

EXPECTED_CALIBRATOR_SHA256 = "1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971"
EXPECTED_CALIBRATOR_SIGNATURE = "cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181"


class MedGemmaChoiceScorer(Protocol):
    model_id: str
    model_version: str

    def score_panel(self, panel_path: Path, prompt: str) -> dict[str, Any]: ...


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON do executor holdout invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Artefato do executor holdout deve ser objeto JSON.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL do executor holdout invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("JSONL do executor holdout vazio ou invalido.")
    return rows


def _safe(root: Path, relative: str) -> Path:
    root = Path(root).resolve()
    part = PurePosixPath(str(relative))
    if part.is_absolute() or ".." in part.parts:
        raise PipelineError("Caminho inseguro no executor holdout.")
    path = (root / Path(*part.parts)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise PipelineError("Arquivo do executor holdout ausente ou fora da raiz.")
    return path


def _input_rows(prepared_root: Path) -> list[dict[str, Any]]:
    rows = _jsonl(prepared_root / "manifests" / "holdout_inputs.jsonl")
    if len(rows) != EXPECTED_CASE_COUNT:
        raise PipelineError("Executor holdout exige exatamente 44 registros de input.")
    seen: set[str] = set()
    for row in rows:
        case_id = str(row.get("case_id", ""))
        serialized = json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
        if (
            row.get("schema") != HOLDOUT_INPUT_SCHEMA
            or row.get("split") != "holdout_blind"
            or not case_id.startswith("anon-openswiss-")
            or case_id in seen
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or any(term in serialized for term in ("sub-", "hcc", "label", "truth", "lesion", "diagnosis"))
        ):
            raise PipelineError("Registro de input holdout invalido ou perdeu o cegamento.")
        seen.add(case_id)
    return rows


def verify_holdout_v21_signal_context(
    *,
    panel_root: Path,
    gallery_root: Path,
    review_path: Path,
    prepared_root: Path,
    prepared_audit_path: Path,
    multiphase_config_path: Path,
    fallback_config_path: Path,
    medsiglip_config_path: Path,
    calibrator_path: Path,
    expected_case_count: int = EXPECTED_CASE_COUNT,
) -> dict[str, Any]:
    """Validate all non-model gates before any model object may be constructed."""

    if expected_case_count != EXPECTED_CASE_COUNT:
        raise PipelineError("Protocolo holdout v21 exige exatamente 44 casos.")
    panel_root = Path(panel_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    review = verify_holdout_uniform9_review(
        panel_root=panel_root,
        gallery_root=gallery_root,
        review_path=review_path,
    )
    cohort = _load(panel_root / "cohort_manifest.json")
    case_ids = [str(item.get("case_id", "")) for item in cohort.get("cases", [])]
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("case_count") != EXPECTED_CASE_COUNT
        or case_ids != review.get("approved_case_ids")
        or cohort.get("holdout_ground_truth_opened") is not False
        or cohort.get("pathology_labels_used") is not False
        or cohort.get("lesion_masks_used") is not False
    ):
        raise PipelineError("Coorte holdout divergiu da revisao assinada.")

    audit_path = Path(prepared_audit_path).resolve()
    persisted_audit = _load(audit_path)
    fresh_audit = audit_prepared_holdout_label_blind(prepared_root)
    if (
        persisted_audit != fresh_audit
        or persisted_audit.get("schema") != HOLDOUT_AUDIT_SCHEMA
        or persisted_audit.get("status") != "label_blind_holdout_preparation_verified"
        or persisted_audit.get("labels_read") is not False
        or persisted_audit.get("lesion_masks_read") != 0
        or cohort.get("prepared_audit_sha256") != _sha256(audit_path)
    ):
        raise PipelineError("Auditoria label-blind do holdout divergiu do freeze dos paineis.")
    rows = _input_rows(prepared_root)
    if [str(row["case_id"]) for row in rows] != case_ids:
        raise PipelineError("Ordem dos inputs holdout divergiu dos paineis aprovados.")

    multiphase_path = Path(multiphase_config_path).resolve()
    fallback_path = Path(fallback_config_path).resolve()
    multiphase_config = _validate_config(multiphase_path, mode="multiphase_fusion")
    fallback_config = _validate_config(fallback_path, mode="single_grayscale")
    if (
        cohort.get("multiphase_config_sha256") != _sha256(multiphase_path)
        or cohort.get("fallback_config_sha256") != _sha256(fallback_path)
    ):
        raise PipelineError("Configs MedGemma divergem das usadas para renderizar o holdout.")
    for config in (multiphase_config, fallback_config):
        med = config.get("medgemma", {})
        if (
            med.get("model_id") != "google/medgemma-1.5-4b-it"
            or med.get("model_parameter_scale") != "4B"
            or med.get("response_mode") != "choice_classification"
            or int(med.get("max_retries", 1)) != 0
            or int(med.get("timeout_seconds", 0)) > 120
        ):
            raise PipelineError("Executor holdout exige o leitor MedGemma 1.5 4B v21 congelado.")
    medsiglip = load_medsiglip_config(Path(medsiglip_config_path).resolve())
    if medsiglip.model_id != "google/medsiglip-448" or medsiglip.decision_enabled is not False:
        raise PipelineError("Executor holdout exige MedSigLIP 448 sem decisao autonoma.")

    calibrator_path = Path(calibrator_path).resolve()
    calibrator = _load_calibrator(calibrator_path)
    if (
        _sha256(calibrator_path) != EXPECTED_CALIBRATOR_SHA256
        or calibrator.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
    ):
        raise PipelineError("Calibrador holdout diverge do protocolo externo v21 congelado.")

    for record in cohort["cases"]:
        panel = _safe(panel_root, str(record.get("panel", "")))
        if _sha256(panel) != record.get("panel_sha256"):
            raise PipelineError("Painel holdout ausente ou adulterado antes dos scores.")
    return {
        "cohort": cohort,
        "review": review,
        "prepared_audit": persisted_audit,
        "input_rows": rows,
        "multiphase_config": multiphase_config,
        "fallback_config": fallback_config,
        "medsiglip_config": medsiglip,
        "calibrator": calibrator,
        "calibrator_path": calibrator_path,
        "case_ids": case_ids,
        "review_signature": review["review_signature"],
        "medgemma_case_schema": MEDGEMMA_CASE_SCHEMA,
        "medgemma_run_schema": MEDGEMMA_RUN_SCHEMA,
        "medsiglip_case_schema": MEDSIGLIP_CASE_SCHEMA,
        "medsiglip_run_schema": MEDSIGLIP_RUN_SCHEMA,
        "raw_signal_summary_schema": RAW_SIGNAL_SUMMARY_SCHEMA,
    }


def context_preflight_summary(context: dict[str, Any]) -> dict[str, Any]:
    """Return a serializable receipt without exposing inputs or protected data."""

    cohort = context["cohort"]
    return {
        "status": "ready_for_review_gated_label_blind_execution",
        "case_count": len(context["case_ids"]),
        "multiphase_case_count": cohort["multiphase_case_count"],
        "venous_fallback_case_count": cohort["venous_fallback_case_count"],
        "review_signature": context["review_signature"],
        "calibrator_signature": context["calibrator"]["calibrator_signature"],
        "labels_read": False,
        "lesion_masks_read": 0,
        "holdout_ground_truth_opened": False,
        "models_loaded": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def build_holdout_v21_localizer_input_manifest(
    *, context: dict[str, Any], prepared_root: Path, output_path: Path
) -> dict[str, Any]:
    """Publish only venous image and automatic liver mask after approval."""

    prepared_root = Path(prepared_root).resolve()
    by_id = {str(row["case_id"]): row for row in context["input_rows"]}
    rows = []
    for case_id in context["case_ids"]:
        source = by_id[case_id]
        files = {str(item.get("role")): item for item in source.get("files", [])}
        if "t1_venous" not in files or "liver_mask_venous" not in files:
            raise PipelineError("Caso holdout sem imagem ou mascara hepatica venosa.")
        selected = []
        for role in ("t1_venous", "liver_mask_venous"):
            item = files[role]
            path = _safe(prepared_root / "inputs", str(item.get("relative_path", "")))
            if path.stat().st_size != item.get("bytes") or _sha256(path) != item.get("sha256"):
                raise PipelineError("Input venoso holdout adulterado antes do localizador.")
            selected.append(
                {
                    "role": role,
                    "relative_path": path.relative_to(prepared_root / "inputs").as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        rows.append(
            {
                "schema": LOCALIZER_INPUT_SCHEMA,
                "case_id": case_id,
                "files": selected,
                "review_signature": context["review_signature"],
                "lesion_mask_available": False,
                "ground_truth_read": False,
                "holdout_opened": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
        )
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Manifesto do localizador holdout ja existe.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return {
        "status": "ready_for_label_blind_localizer",
        "case_count": len(rows),
        "manifest_sha256": _sha256(output_path),
        "review_signature": context["review_signature"],
        "labels_read": False,
        "lesion_masks_read": 0,
        "holdout_ground_truth_opened": False,
    }


def _probabilities(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(CHOICES):
        raise PipelineError("Probabilidades MedGemma holdout incompletas.")
    result: dict[str, float] = {}
    for choice in CHOICES:
        raw = value[choice]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise PipelineError("Probabilidade MedGemma holdout nao numerica.")
        result[choice] = float(raw)
        if not 0.0 <= result[choice] <= 1.0:
            raise PipelineError("Probabilidade MedGemma holdout fora de [0,1].")
    if abs(sum(result.values()) - 1.0) > 2e-5:
        raise PipelineError("Probabilidades MedGemma holdout nao somam 1.")
    return result


def run_holdout_v21_medgemma_scores(
    *,
    context: dict[str, Any],
    panel_root: Path,
    output_root: Path,
    multiphase_scorer: MedGemmaChoiceScorer,
    fallback_scorer: MedGemmaChoiceScorer,
) -> dict[str, Any]:
    """Score every reviewed panel once using its predeclared representation."""

    for scorer in (multiphase_scorer, fallback_scorer):
        if scorer.model_id != "google/medgemma-1.5-4b-it":
            raise PipelineError("Scorer holdout nao confirmou o MedGemma 1.5 4B.")
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Scores MedGemma do holdout ja existem.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._holdout_mg_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    prompts = {
        "multiphase_rgb": str(context["multiphase_config"].get("prompt", {}).get("template", "")),
        FALLBACK_KIND: str(context["fallback_config"].get("prompt", {}).get("template", "")),
    }
    if any(not prompt for prompt in prompts.values()):
        raise PipelineError("Prompt MedGemma holdout vazio.")
    scorers = {"multiphase_rgb": multiphase_scorer, FALLBACK_KIND: fallback_scorer}
    rows = []
    started_all = time.monotonic()
    try:
        for record in context["cohort"]["cases"]:
            case_id = str(record["case_id"])
            kind = str(record["candidate_kind"])
            if kind not in scorers:
                raise PipelineError("Tipo de painel holdout nao possui scorer congelado.")
            panel = _safe(panel_root, str(record["panel"]))
            started = time.monotonic()
            score = scorers[kind].score_panel(panel, prompts[kind])
            elapsed = time.monotonic() - started
            probabilities = _probabilities(score.get("choice_probabilities"))
            rows.append(
                {
                    "schema": MEDGEMMA_CASE_SCHEMA,
                    "case_id": case_id,
                    "candidate_kind": kind,
                    "panel_sha256": record["panel_sha256"],
                    "model_id": scorers[kind].model_id,
                    "model_version": scorers[kind].model_version,
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
            )
        scores_path = staging / "scores.jsonl"
        scores_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
        )
        summary = {
            "schema": MEDGEMMA_RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "case_count": len(rows),
            "case_ids": context["case_ids"],
            "multiphase_case_count": sum(row["candidate_kind"] == "multiphase_rgb" for row in rows),
            "venous_fallback_case_count": sum(row["candidate_kind"] == FALLBACK_KIND for row in rows),
            "scores_sha256": _sha256(scores_path),
            "review_signature": context["review_signature"],
            "mean_case_seconds": statistics.fmean(row["elapsed_seconds"] for row in rows),
            "max_case_seconds": max(row["elapsed_seconds"] for row in rows),
            "total_wall_seconds": time.monotonic() - started_all,
            "final_decision": None,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def run_holdout_v21_medsiglip_scores(**kwargs: Any) -> dict[str, Any]:
    """Use the common v21 scorer with holdout-specific immutable schemas."""

    return run_v21_medsiglip_scores(**kwargs)


def assemble_holdout_v21_raw_signals(**kwargs: Any) -> dict[str, Any]:
    """Assemble the frozen three-signal vector while labels remain closed."""

    return assemble_v21_raw_signals(**kwargs)


def score_holdout_v21_blind(
    *, context: dict[str, Any], signals_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Apply only the already-frozen external calibrator."""

    return score_external_signals(
        calibrator_path=context["calibrator_path"],
        signals_path=signals_path,
        output_dir=output_dir,
        expected_case_count=EXPECTED_CASE_COUNT,
    )


def freeze_holdout_v21_predictions(
    *,
    context: dict[str, Any],
    raw_signal_root: Path,
    score_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Sign predictions and protocol before any future label authorization."""

    raw_signal_root = Path(raw_signal_root).resolve()
    score_root = Path(score_root).resolve()
    raw_summary = _load(raw_signal_root / "summary.json")
    score_summary = _load(score_root / "summary.json")
    scores_path = score_root / "scores.jsonl"
    score_rows = _jsonl(scores_path)
    if (
        raw_summary.get("schema") != RAW_SIGNAL_SUMMARY_SCHEMA
        or raw_summary.get("status") != "complete_raw_signals_no_labels_no_decision"
        or raw_summary.get("case_ids") != context["case_ids"]
        or raw_summary.get("review_signature") != context["review_signature"]
        or raw_summary.get("ground_truth_read") is not False
        or score_summary.get("schema") != SCORE_SUMMARY_SCHEMA
        or score_summary.get("status") != "complete_predictions_frozen_labels_still_closed"
        or score_summary.get("case_ids") != context["case_ids"]
        or score_summary.get("case_count") != EXPECTED_CASE_COUNT
        or score_summary.get("scores_sha256") != _sha256(scores_path)
        or score_summary.get("source_signals_sha256") != _sha256(raw_signal_root / "raw_signals.jsonl")
        or score_summary.get("calibrator_sha256") != _sha256(context["calibrator_path"])
        or score_summary.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
        or score_summary.get("ground_truth_read") is not False
        or score_summary.get("metrics_calculated") is not False
        or score_summary.get("holdout_opened") is not False
        or [str(row.get("case_id", "")) for row in score_rows] != context["case_ids"]
        or score_summary.get("positive_prediction_count")
        != sum(row.get("decision") == "POSITIVE" for row in score_rows)
        or score_summary.get("negative_prediction_count")
        != sum(row.get("decision") == "NEGATIVE" for row in score_rows)
        or score_summary.get("all_time_gates_passed")
        != all(row.get("time_gate_180_seconds_passed") is True for row in score_rows)
    ):
        raise PipelineError("Predicoes holdout incompletas ou adulteradas; freeze recusado.")
    for row in score_rows:
        if (
            row.get("schema") != SCORE_SCHEMA
            or row.get("decision") not in {"POSITIVE", "NEGATIVE"}
            or row.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("holdout_opened") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or not isinstance(row.get("total_component_seconds"), (int, float))
            or isinstance(row.get("total_component_seconds"), bool)
            or not math.isfinite(float(row["total_component_seconds"]))
            or float(row["total_component_seconds"]) < 0.0
            or row.get("time_gate_180_seconds_passed")
            is not (float(row["total_component_seconds"]) <= 180.0)
        ):
            raise PipelineError("Predicao individual holdout invalida; freeze recusado.")
    payload: dict[str, Any] = {
        "schema": PREDICTION_FREEZE_SCHEMA,
        "status": "predictions_and_final_protocol_frozen_labels_closed",
        "case_count": EXPECTED_CASE_COUNT,
        "case_ids": context["case_ids"],
        "decision_rule": context["calibrator"]["decision_rule"],
        "threshold": context["calibrator"]["threshold"],
        "time_gate_seconds": 180.0,
        "review_signature": context["review_signature"],
        "calibrator_sha256": _sha256(context["calibrator_path"]),
        "calibrator_signature": EXPECTED_CALIBRATOR_SIGNATURE,
        "raw_signal_summary_sha256": _sha256(raw_signal_root / "summary.json"),
        "raw_signals_sha256": _sha256(raw_signal_root / "raw_signals.jsonl"),
        "score_summary_sha256": _sha256(score_root / "summary.json"),
        "scores_sha256": _sha256(scores_path),
        "positive_prediction_count": score_summary["positive_prediction_count"],
        "negative_prediction_count": score_summary["negative_prediction_count"],
        "all_time_gates_passed": score_summary["all_time_gates_passed"],
        "labels_read": False,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_ground_truth_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["protocol_signature"] = _canonical_sha(payload)
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Freeze final das predicoes holdout ja existe.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, payload)
    return payload


def verify_holdout_v21_prediction_freeze(
    *,
    context: dict[str, Any],
    raw_signal_root: Path,
    score_root: Path,
    freeze_path: Path,
    expected_protocol_signature: str | None = None,
) -> dict[str, Any]:
    """Verify the immutable prediction/protocol freeze without opening labels."""

    raw_signal_root = Path(raw_signal_root).resolve()
    score_root = Path(score_root).resolve()
    freeze = _load(Path(freeze_path).resolve())
    score_summary = _load(score_root / "summary.json")
    unsigned = {key: value for key, value in freeze.items() if key != "protocol_signature"}
    expected = {
        "schema": PREDICTION_FREEZE_SCHEMA,
        "status": "predictions_and_final_protocol_frozen_labels_closed",
        "case_count": EXPECTED_CASE_COUNT,
        "case_ids": context["case_ids"],
        "decision_rule": context["calibrator"]["decision_rule"],
        "threshold": context["calibrator"]["threshold"],
        "time_gate_seconds": 180.0,
        "review_signature": context["review_signature"],
        "calibrator_sha256": _sha256(context["calibrator_path"]),
        "calibrator_signature": EXPECTED_CALIBRATOR_SIGNATURE,
        "raw_signal_summary_sha256": _sha256(raw_signal_root / "summary.json"),
        "raw_signals_sha256": _sha256(raw_signal_root / "raw_signals.jsonl"),
        "score_summary_sha256": _sha256(score_root / "summary.json"),
        "scores_sha256": _sha256(score_root / "scores.jsonl"),
        "positive_prediction_count": freeze.get("positive_prediction_count"),
        "negative_prediction_count": freeze.get("negative_prediction_count"),
        "all_time_gates_passed": freeze.get("all_time_gates_passed"),
        "labels_read": False,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_ground_truth_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    signature = str(freeze.get("protocol_signature", ""))
    if (
        unsigned != expected
        or signature != _canonical_sha(unsigned)
        or freeze.get("case_count") != len(context["case_ids"])
        or freeze.get("positive_prediction_count", -1)
        + freeze.get("negative_prediction_count", -1)
        != EXPECTED_CASE_COUNT
        or freeze.get("positive_prediction_count")
        != score_summary.get("positive_prediction_count")
        or freeze.get("negative_prediction_count")
        != score_summary.get("negative_prediction_count")
        or freeze.get("all_time_gates_passed")
        != score_summary.get("all_time_gates_passed")
        or score_summary.get("status") != "complete_predictions_frozen_labels_still_closed"
        or score_summary.get("case_ids") != context["case_ids"]
        or score_summary.get("scores_sha256") != _sha256(score_root / "scores.jsonl")
        or score_summary.get("calibrator_sha256") != _sha256(context["calibrator_path"])
        or score_summary.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
        or score_summary.get("ground_truth_read") is not False
        or score_summary.get("metrics_calculated") is not False
        or score_summary.get("holdout_opened") is not False
    ):
        raise PipelineError("Freeze final do holdout invalido ou adulterado.")
    if expected_protocol_signature is not None and signature != expected_protocol_signature:
        raise PipelineError("Assinatura autorizada do protocolo holdout diverge do freeze.")
    return freeze
