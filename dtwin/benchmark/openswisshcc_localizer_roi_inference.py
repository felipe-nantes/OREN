"""Blind mirrored-A/B MedGemma scoring for frozen paired v10 localizer ROIs."""
from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LOCALIZER_CASE_SCHEMA
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import verify_roi_freeze
from dtwin.benchmark.openswisshcc_localizer_roi_gate import verify_paired_review
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

SCORE_SCHEMA = "argos-medgemma-localizer-roi-mirrored-ab-score-v1"
CASE_SCHEMA = "argos-openswisshcc-localizer-roi-medgemma-case-v1"
RUN_SCHEMA = "argos-openswisshcc-localizer-roi-medgemma-run-v1"


class ABScorer(Protocol):
    model_id: str
    model_version: str

    def score_choice(self, panel_path: Path, prompt: str) -> dict[str, Any]: ...


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da inferencia ROI v10 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON da inferencia ROI v10 deve ser objeto.")
    return value


def _panel(root: Path, case_id: str, representation: str, number: int) -> tuple[Path, dict[str, Any]]:
    case_dir = (Path(root).resolve() / case_id).resolve()
    if not case_dir.is_relative_to(Path(root).resolve()) or not case_dir.is_dir():
        raise PipelineError("Diretorio de painel ROI v10 inseguro.")
    manifest_name = "roi_manifest.json" if representation == "morphology" else "enhancement_roi_manifest.json"
    manifest = _load(case_dir / manifest_name)
    panels = manifest.get("panels", [])
    if not 1 <= number <= len(panels):
        raise PipelineError("Numero de painel ROI v10 invalido.")
    panel = panels[number - 1]
    path = (case_dir / str(panel.get("image", ""))).resolve()
    if not path.is_relative_to(case_dir) or not path.is_file() or _sha256(path) != panel.get("sha256") or path.stat().st_size != panel.get("bytes"):
        raise PipelineError("Painel ROI v10 mudou antes do scoring.")
    return path, panel


def _base_prompt(representation: str, panel: dict[str, Any]) -> str:
    fallback = panel.get("fallback_no_candidate") is True
    unavailable = [tile.get("role") for tile in panel.get("tiles", []) if tile.get("available_in_fov") is False]
    if representation == "morphology":
        evidence = "T1 venous, native T2, ordered DWI TRACE, and native ADC"
    else:
        evidence = "T1 native, registered arterial, T1 venous, and registered delayed phases"
    candidate = (
        "The yellow outline on T1 venous is a model-derived candidate, never ground truth."
        if not fallback
        else "The localizer produced no candidate; this is an explicitly labeled liver-centered fallback with no yellow outline."
    )
    return (
        "Research-only liver MRI scoring. Use only visible pixels in this panel. "
        f"The panel contains {evidence} at the same physical center. {candidate} "
        "Do not treat a vessel, benign anatomical variant, artifact, perfusion change, partial volume, or unavailable tile as a focal lesion. "
        "Do not emit a diagnosis, recommendation, explanation, or final case decision. "
        f"Panel {panel['panel_number']}/{panel['panel_total']}; unavailable tiles: {unavailable or 'none'}."
    )


def _mapped_prompt(base: str, question: dict[str, Any], mapping: dict[str, str]) -> str:
    semantics = {"positive": question["positive_semantics"], "negative": question["negative_semantics"]}
    return (
        f"{base}\n\nQuestion: {question['question']}\n"
        f"A = {semantics[mapping['A']]}\n"
        f"B = {semantics[mapping['B']]}\n"
        "Return exactly one token: A or B."
    )


def _verify_choice(result: dict[str, Any]) -> tuple[float, float, str]:
    probabilities = result.get("choice_probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != {"A", "B"}:
        raise PipelineError("Scorer ROI v10 nao retornou probabilidades A/B exatas.")
    a, b = probabilities["A"], probabilities["B"]
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not 0 <= float(a) <= 1 or not 0 <= float(b) <= 1 or abs(float(a) + float(b) - 1.0) > 1e-5:
        raise PipelineError("Probabilidades A/B ROI v10 invalidas.")
    selected = result.get("choice")
    if selected not in {"A", "B"}:
        raise PipelineError("Escolha A/B ROI v10 invalida.")
    return float(a), float(b), str(selected)


def _score_question(*, scorer: ABScorer, panel_path: Path, base_prompt: str, question: dict[str, Any], mappings: list[dict[str, str]], case_started: float, max_scoring_seconds: float) -> dict[str, Any]:
    mapped = []
    semantic_positive = []
    for mapping in mappings:
        if time.monotonic() - case_started >= max_scoring_seconds:
            raise PipelineError("Scoring ROI v10 excedeu o limite antes da chamada.")
        prompt = _mapped_prompt(base_prompt, question, mapping)
        started = time.monotonic()
        result = scorer.score_choice(panel_path, prompt)
        a, b, selected = _verify_choice(result)
        elapsed = time.monotonic() - started
        if time.monotonic() - case_started > max_scoring_seconds:
            raise PipelineError("Scoring ROI v10 excedeu o limite apos a chamada.")
        positive_token = "A" if mapping["A"] == "positive" else "B"
        semantic_positive.append(a if positive_token == "A" else b)
        mapped.append({"mapping_id": mapping["mapping_id"], "A_semantics": mapping["A"], "B_semantics": mapping["B"], "A_probability": a, "B_probability": b, "selected_token": selected, "positive_token": positive_token, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "elapsed_seconds": round(elapsed, 4)})
    return {"schema": SCORE_SCHEMA, "question_id": question["question_id"], "representation": question["representation"], "semantic_positive_probability": statistics.fmean(semantic_positive), "mappings": mapped, "final_decision": None, "ground_truth_read": False}


def run_roi_scores(*, morphology_root: Path, enhancement_root: Path, review_path: Path, freeze_path: Path, config_path: Path, localizer_run: Path, output_root: Path, scorer: ABScorer, expected_case_count: int = 10, case_ids: list[str] | None = None, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    freeze = verify_roi_freeze(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, config_path=config_path, freeze_path=freeze_path, expected_case_count=expected_case_count)
    review = verify_paired_review(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, expected_case_count=expected_case_count)
    available = [case["case_id"] for case in review["cases"]]
    selected = available if case_ids is None else list(case_ids)
    if not selected or len(selected) != len(set(selected)) or any(case_id not in available for case_id in selected):
        raise PipelineError("Selecao de casos ROI v10 invalida.")
    localizer_root = Path(localizer_run).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Destino de scoring ROI v10 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_run = output.parent / f"._v10ab_{uuid.uuid4().hex[:8]}"
    staging_run.mkdir()
    run_started = time.monotonic()
    manifests = []
    try:
        for sequence, case_id in enumerate(selected, 1):
            case_started = time.monotonic()
            localizer_manifest_path = localizer_root / case_id / "localizer_manifest.json"
            localizer = _load(localizer_manifest_path)
            if localizer.get("schema") != LOCALIZER_CASE_SCHEMA or localizer.get("case_id") != case_id or localizer.get("status") != "candidate_scores_only_no_decision" or localizer.get("ground_truth_read") is not False or localizer.get("ground_truth_lesion_mask_used") is not False or localizer.get("final_decision") is not None:
                raise PipelineError("Manifesto localizador ROI v10 invalido para scoring.")
            upstream_seconds = float(localizer.get("elapsed_seconds", -1))
            if not 0 <= upstream_seconds <= float(freeze["max_upstream_seconds"]):
                raise PipelineError("Tempo upstream ROI v10 ausente ou acima do freeze.")
            case_review = next(case for case in review["cases"] if case["case_id"] == case_id)
            case_staging = staging_run / case_id
            case_staging.mkdir()
            rows = []
            for panel_number in range(1, int(case_review["panel_count"]) + 1):
                panel_rows = []
                for representation, root in (("morphology", morphology_root), ("enhancement", enhancement_root)):
                    panel_path, panel = _panel(Path(root), case_id, representation, panel_number)
                    base_prompt = _base_prompt(representation, panel)
                    for question in freeze["question_bank"]:
                        if question["representation"] != representation:
                            continue
                        score = _score_question(scorer=scorer, panel_path=panel_path, base_prompt=base_prompt, question=question, mappings=freeze["scoring_protocol"]["mappings"], case_started=case_started, max_scoring_seconds=float(freeze["max_scoring_seconds"]))
                        panel_rows.append({"panel_sha256": panel["sha256"], "score": score})
                rows.append({"panel_number": panel_number, "panel_total": case_review["panel_count"], "fallback_no_candidate": case_review["fallback_no_candidate"], "questions": panel_rows})
                _write_json_atomic(case_staging / "mirrored_ab_scores.json", rows)
            scores_path = case_staging / "mirrored_ab_scores.json"
            scoring_seconds = time.monotonic() - case_started
            observed_seconds = upstream_seconds + scoring_seconds
            case_manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "scores_only_no_decision",
                "panel_pairs": len(rows),
                "question_count": sum(len(row["questions"]) for row in rows),
                "mapping_call_count": sum(len(question["score"]["mappings"]) for row in rows for question in row["questions"]),
                "scores_sha256": _sha256(scores_path),
                "experiment_signature": freeze["experiment_signature"],
                "review_signature": review["review_signature"],
                "localizer_manifest_sha256": _sha256(localizer_manifest_path),
                "model_id": scorer.model_id,
                "model_version": scorer.model_version,
                "upstream_localizer_seconds": round(upstream_seconds, 4),
                "scoring_seconds": round(scoring_seconds, 4),
                "observed_localizer_plus_scoring_seconds": round(observed_seconds, 4),
                "within_scoring_budget": scoring_seconds <= float(freeze["max_scoring_seconds"]),
                "within_observed_180_seconds": observed_seconds <= float(freeze["max_end_to_end_seconds"]),
                "end_to_end_measurement_complete": False,
                "unmeasured_stages": ["phase_registration", "roi_rendering"],
                "final_decision": None,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            _write_json_atomic(case_staging / "mirrored_ab_manifest.json", case_manifest)
            manifests.append(case_manifest)
            if progress:
                progress({"sequence": sequence, "case_count": len(selected), "case_id": case_id, "scoring_seconds": case_manifest["scoring_seconds"], "observed_seconds": case_manifest["observed_localizer_plus_scoring_seconds"]})
        scoring_times = [manifest["scoring_seconds"] for manifest in manifests]
        observed_times = [manifest["observed_localizer_plus_scoring_seconds"] for manifest in manifests]
        summary = {
            "schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "case_count": len(manifests),
            "panel_pairs": sum(manifest["panel_pairs"] for manifest in manifests),
            "mapping_call_count": sum(manifest["mapping_call_count"] for manifest in manifests),
            "experiment_signature": freeze["experiment_signature"],
            "review_signature": review["review_signature"],
            "model_id": scorer.model_id,
            "model_version": scorer.model_version,
            "mean_scoring_seconds": statistics.fmean(scoring_times),
            "max_scoring_seconds": max(scoring_times),
            "mean_observed_localizer_plus_scoring_seconds": statistics.fmean(observed_times),
            "max_observed_localizer_plus_scoring_seconds": max(observed_times),
            "all_cases_within_scoring_budget": all(manifest["within_scoring_budget"] for manifest in manifests),
            "all_cases_within_observed_180_seconds": all(manifest["within_observed_180_seconds"] for manifest in manifests),
            "end_to_end_time_gate_evaluable": False,
            "unmeasured_stages": ["phase_registration", "roi_rendering"],
            "total_wall_seconds": round(time.monotonic() - run_started, 4),
            "final_decision": None,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        _write_json_atomic(staging_run / "summary.json", summary)
        _publish_directory(staging_run, output)
        return summary
    except Exception:
        shutil.rmtree(staging_run, ignore_errors=True)
        raise
