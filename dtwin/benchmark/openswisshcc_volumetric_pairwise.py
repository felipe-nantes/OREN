"""Blind pairwise MedGemma scoring over the frozen volumetric cohort."""
from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from dtwin.benchmark.openswisshcc_alignment import _load_json, _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_volumetric_gate import verify_volumetric_freeze
from dtwin.benchmark.openswisshcc_volumetric_inference import _current_case
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


PAIRWISE_SCHEMA = "argos-medgemma-volumetric-pairwise-panel-scores-v1"
CASE_SCHEMA = "argos-openswisshcc-volumetric-pairwise-case-v1"
RUN_SCHEMA = "argos-openswisshcc-volumetric-pairwise-run-v1"

PAIR_BANK: tuple[dict[str, str], ...] = (
    {
        "pair_id": "focal_lesion_evidence",
        "question": "Which statement is better supported by the liver MRI panel?",
        "positive": "Evidence supports a suspicious focal liver lesion.",
        "negative": "Evidence does not support a suspicious focal liver lesion.",
    },
    {
        "pair_id": "focal_mass_presence",
        "question": "Which statement best describes the liver MRI panel?",
        "positive": "This panel shows a focal hepatic mass.",
        "negative": "This panel does not show a focal hepatic mass.",
    },
)


class PairwiseScorer(Protocol):
    model_id: str
    model_version: str

    def score_panel(
        self, panel_path: Path, prompt: str, pairs: tuple[dict[str, str], ...]
    ) -> dict[str, Any]: ...


def _json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _panel_prompt(record: dict[str, Any], candidate_kind: str) -> str:
    interval = record.get("axial_interval")
    phase_note = (
        "This is a multiphase color fusion; colors encode registered MRI phases and are not annotations."
        if candidate_kind == "multiphase_registered"
        else "This is a single venous-phase grayscale representation. Do not assume arterial or delayed enhancement."
    )
    return (
        "Research-only review of a segmented liver MRI panel. The contour marks the liver only; "
        "no lesion, diagnosis, or ground truth is marked. Distinguish a suspicious focal liver "
        "lesion from normal parenchyma, vessels, benign anatomic variants, pseudolesions, partial "
        "volume, and artifacts. A prominent or continuous tubular vessel is not by itself a focal "
        "mass. Base the assessment only on the visible panel and do not recommend clinical action.\n\n"
        f"Partial panel {record['panel_number']}/{record['panel_total']}; axial interval {interval}. "
        f"{phase_note} Score the two authorized sentence pairs independently."
    )


def _axial_indices(source: dict[str, Any]) -> list[int]:
    indices = source.get("axial_indices")
    if not isinstance(indices, list):
        interval = source.get("axial_interval")
        if (
            isinstance(interval, list) and len(interval) == 2
            and all(isinstance(value, int) for value in interval)
            and interval[0] <= interval[1]
        ):
            indices = list(range(interval[0], interval[1] + 1))
    if (
        not isinstance(indices, list) or not 1 <= len(indices) <= 9
        or any(not isinstance(value, int) for value in indices)
        or len(indices) != len(set(indices))
    ):
        raise PipelineError("Painel pairwise nao informa indices axiais validos.")
    return indices


def _verify_score(score: dict[str, Any], panel_sha256: str) -> None:
    if (
        score.get("schema") != PAIRWISE_SCHEMA
        or score.get("panel_sha256") != panel_sha256
        or score.get("final_decision") is not None
        or score.get("ground_truth_read") is not False
    ):
        raise PipelineError("Score pairwise violou schema, hash ou cegamento.")
    pairs = score.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != len(PAIR_BANK):
        raise PipelineError("Score pairwise nao contem todos os pares autorizados.")
    for expected, observed in zip(PAIR_BANK, pairs, strict=True):
        probability = observed.get("positive_probability")
        if (
            observed.get("pair_id") != expected["pair_id"]
            or not isinstance(probability, (int, float))
            or not 0.0 <= float(probability) <= 1.0
        ):
            raise PipelineError("Probabilidade pairwise invalida.")


def _existing_case(case_dir: Path, frozen: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    manifest_path = case_dir / "pairwise_manifest.json"
    scores_path = case_dir / "pairwise_panel_scores.json"
    if not manifest_path.is_file() or not scores_path.is_file():
        raise PipelineError(f"Saida pairwise parcial existente: {case_dir.name}.")
    manifest = _load_json(manifest_path)
    if (
        manifest.get("schema") != CASE_SCHEMA
        or manifest.get("status") != "scores_only_no_decision"
        or manifest.get("experiment_signature") != freeze["experiment_signature"]
        or manifest.get("candidate_signature") != frozen["candidate_signature"]
        or manifest.get("panel_set_sha256") != frozen["panel_set_sha256"]
        or manifest.get("pair_bank_sha256") != _json_sha256(PAIR_BANK)
        or manifest.get("scores_sha256") != _sha256(scores_path)
    ):
        raise PipelineError(f"Saida pairwise existente divergiu do freeze: {case_dir.name}.")
    return manifest


def run_volumetric_pairwise_scores(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    config_paths: Mapping[str, Path], output_root: Path, scorer: PairwiseScorer,
    expected_case_count: int = 88,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Score every approved panel without opening labels or emitting a decision."""
    paths = {str(key): Path(value).resolve() for key, value in config_paths.items()}
    freeze = verify_volumetric_freeze(
        freeze_path=freeze_path, panel_root=panel_root, review_path=review_path,
        config_paths=paths, expected_case_count=expected_case_count,
    )
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    if summary_path.exists():
        summary = _load_json(summary_path)
        if summary.get("experiment_signature") != freeze["experiment_signature"]:
            raise PipelineError("Resumo pairwise existente pertence a outro experimento.")
        for frozen in freeze["candidates"]:
            _existing_case(output_root / str(frozen["case_id"]), frozen, freeze)
        return summary

    manifests: list[dict[str, Any]] = []
    started = time.monotonic()
    pair_hash = _json_sha256(PAIR_BANK)
    for sequence, frozen in enumerate(freeze["candidates"], start=1):
        case_id = str(frozen["case_id"])
        final_dir = output_root / case_id
        if final_dir.exists():
            manifest = _existing_case(final_dir, frozen, freeze)
        else:
            case_dir, _candidate, panel_manifest, _ = _current_case(
                panel_root=panel_root, freeze=freeze, case_id=case_id
            )
            source_panels = panel_manifest.get("panels")
            if not isinstance(source_panels, list) or len(source_panels) != frozen["panel_image_count"]:
                raise PipelineError("Manifesto volumetrico incompleto no scorer pairwise.")
            staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
            staging.mkdir()
            case_started = time.monotonic()
            panel_results: list[dict[str, Any]] = []
            try:
                for record, source in zip(frozen["panels"], source_panels, strict=True):
                    panel_started = time.monotonic()
                    prompt = _panel_prompt(record, str(frozen["candidate_kind"]))
                    panel_path = case_dir / str(record["image"])
                    score = scorer.score_panel(panel_path, prompt, PAIR_BANK)
                    _verify_score(score, str(record["sha256"]))
                    indices = _axial_indices(source)
                    panel_results.append({
                        "panel_number": record["panel_number"],
                        "panel_total": record["panel_total"],
                        "image": record["image"],
                        "sha256": record["sha256"],
                        "axial_indices": indices,
                        "real_axial_tile_count": len(indices),
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "elapsed_seconds": round(time.monotonic() - panel_started, 4),
                        "score": score,
                    })
                    _write_json_atomic(staging / "pairwise_panel_scores.json", panel_results)
                scores_path = staging / "pairwise_panel_scores.json"
                manifest = {
                    "schema": CASE_SCHEMA,
                    "case_id": case_id,
                    "status": "scores_only_no_decision",
                    "candidate_signature": frozen["candidate_signature"],
                    "panel_set_sha256": frozen["panel_set_sha256"],
                    "panel_image_count": frozen["panel_image_count"],
                    "scores_sha256": _sha256(scores_path),
                    "experiment_signature": freeze["experiment_signature"],
                    "review_signature": freeze["review_signature"],
                    "pair_bank_sha256": pair_hash,
                    "model_id": scorer.model_id,
                    "model_version": scorer.model_version,
                    "elapsed_seconds": round(time.monotonic() - case_started, 4),
                    "final_decision": None,
                    "research_only": True,
                    "clinical_use_allowed": False,
                    "requires_human_review": True,
                    "ground_truth_read": False,
                    "metrics_calculated": False,
                }
                _write_json_atomic(staging / "pairwise_manifest.json", manifest)
                _publish_directory(staging, final_dir)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        manifests.append(manifest)
        if progress:
            progress({
                "sequence": sequence, "case_count": freeze["case_count"],
                "case_id": case_id, "status": manifest["status"],
                "elapsed_seconds": manifest["elapsed_seconds"],
            })

    elapsed = [float(item["elapsed_seconds"]) for item in manifests]
    summary = {
        "schema": RUN_SCHEMA,
        "status": "complete" if len(manifests) == freeze["case_count"] else "technical_failure",
        "case_count": freeze["case_count"],
        "panel_image_count": freeze["panel_image_count"],
        "success_count": len(manifests),
        "failure_count": freeze["case_count"] - len(manifests),
        "experiment_signature": freeze["experiment_signature"],
        "review_signature": freeze["review_signature"],
        "pair_bank": list(PAIR_BANK),
        "pair_bank_sha256": pair_hash,
        "model_id": scorer.model_id,
        "model_version": scorer.model_version,
        "mean_case_seconds": statistics.fmean(elapsed),
        "max_case_seconds": max(elapsed),
        "total_wall_seconds": round(time.monotonic() - started, 4),
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
    }
    _write_json_atomic(summary_path, summary)
    return summary
