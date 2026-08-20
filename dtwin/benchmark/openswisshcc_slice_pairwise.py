"""High-resolution axial-tile pairwise scoring from signed volumetric panels."""
from __future__ import annotations

import hashlib
import io
import shutil
import statistics
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_volumetric_gate import verify_volumetric_freeze
from dtwin.benchmark.openswisshcc_volumetric_inference import _current_case
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

SLICE_SCHEMA = "argos-medgemma-axial-slice-pairwise-score-v1"
CASE_SCHEMA = "argos-openswisshcc-axial-slice-pairwise-case-v1"
RUN_SCHEMA = "argos-openswisshcc-axial-slice-pairwise-run-v1"
SLICE_PAIR = {
    "pair_id": "focal_lesion_evidence",
    "positive": "Evidence supports a suspicious focal liver lesion.",
    "negative": "Evidence does not support a suspicious focal liver lesion.",
}


class SliceScorer(Protocol):
    model_id: str
    model_version: str

    def score_slice(self, image: Image.Image, prompt: str) -> dict[str, Any]: ...


def _png_sha256(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def crop_axial_tiles(panel_path: Path, axial_indices: Sequence[int]) -> list[tuple[int, Image.Image]]:
    if not 1 <= len(axial_indices) <= 9 or len(set(axial_indices)) != len(axial_indices):
        raise PipelineError("Indices axiais invalidos para recorte.")
    with Image.open(panel_path) as source:
        if source.format != "PNG":
            raise PipelineError("Painel volumetrico deve ser PNG.")
        source.load()
        rgb = source.convert("RGB")
    width, height = rgb.size
    if width % 4 or height % 3 or width // 4 != height // 3:
        raise PipelineError("Painel nao possui grade 4x3 quadrada.")
    tile = width // 4
    return [
        (
            int(axial_index),
            rgb.crop(((position % 3) * tile, (position // 3) * tile,
                      (position % 3 + 1) * tile, (position // 3 + 1) * tile)),
        )
        for position, axial_index in enumerate(axial_indices)
    ]


def _slice_prompt(*, panel_number: int, panel_total: int, axial_index: int, candidate_kind: str) -> str:
    phase = (
        "Colors encode registered MRI phases; they are not annotations."
        if candidate_kind == "multiphase_rgb"
        else "This is venous-phase grayscale; do not assume arterial or delayed enhancement."
    )
    return (
        "Research-only assessment of one high-resolution axial liver MRI tile. The contour marks "
        "the liver only; no lesion or ground truth is marked. Distinguish a suspicious focal "
        "liver lesion from vessels, benign anatomy, pseudolesions, partial volume, and artifacts. "
        "A continuous tubular vessel is not a focal mass. Base the answer only on this tile. "
        f"Source panel {panel_number}/{panel_total}; axial index {axial_index}. {phase} "
        "Complete with exactly one authorized sentence and no explanation."
    )


def run_slice_pairwise_scores(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    config_paths: Mapping[str, Path], output_root: Path, scorer: SliceScorer,
    expected_case_count: int = 88, selected_case_ids: Sequence[str] | None = None,
    max_case_seconds: float = 180.0,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    paths = {str(key): Path(value).resolve() for key, value in config_paths.items()}
    freeze = verify_volumetric_freeze(
        freeze_path=freeze_path, panel_root=panel_root, review_path=review_path,
        config_paths=paths, expected_case_count=expected_case_count,
    )
    frozen_by_id = {str(item["case_id"]): item for item in freeze["candidates"]}
    selected = list(selected_case_ids) if selected_case_ids else sorted(frozen_by_id)
    if not selected or len(selected) != len(set(selected)) or any(case_id not in frozen_by_id for case_id in selected):
        raise PipelineError("Selecao de casos do scorer por corte e invalida.")
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    if summary_path.exists():
        return _load_json(summary_path)
    manifests = []
    run_started = time.monotonic()
    for sequence, case_id in enumerate(selected, start=1):
        frozen = frozen_by_id[case_id]
        final_dir = output_root / case_id
        if final_dir.exists():
            raise PipelineError(f"Saida de corte existente sem resumo: {case_id}.")
        case_dir, _candidate, panel_manifest, _ = _current_case(
            panel_root=panel_root, freeze=freeze, case_id=case_id
        )
        source_panels = panel_manifest.get("panels")
        if not isinstance(source_panels, list) or len(source_panels) != len(frozen["panels"]):
            raise PipelineError("Manifesto de paineis incompleto no scorer por corte.")
        staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
        staging.mkdir()
        started = time.monotonic()
        scores = []
        seen: list[int] = []
        try:
            for record, source in zip(frozen["panels"], source_panels, strict=True):
                indices = source.get("axial_indices")
                if not isinstance(indices, list):
                    raise PipelineError("Manifesto real nao contem axial_indices.")
                panel_path = case_dir / str(record["image"])
                if _sha256(panel_path) != record["sha256"]:
                    raise PipelineError("Hash do painel mudou antes do recorte axial.")
                for axial_index, crop in crop_axial_tiles(panel_path, indices):
                    if time.monotonic() - started >= max_case_seconds:
                        raise PipelineError("Scorer axial excedeu 180 segundos por caso.")
                    prompt = _slice_prompt(
                        panel_number=int(record["panel_number"]),
                        panel_total=int(record["panel_total"]),
                        axial_index=axial_index,
                        candidate_kind=str(frozen["candidate_kind"]),
                    )
                    slice_started = time.monotonic()
                    result = scorer.score_slice(crop, prompt)
                    if (
                        result.get("schema") != SLICE_SCHEMA
                        or result.get("final_decision") is not None
                        or result.get("ground_truth_read") is not False
                    ):
                        raise PipelineError("Score axial violou schema ou cegamento.")
                    scores.append({
                        "axial_index": axial_index,
                        "source_panel_number": record["panel_number"],
                        "source_panel_sha256": record["sha256"],
                        "crop_sha256": _png_sha256(crop),
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "elapsed_seconds": round(time.monotonic() - slice_started, 4),
                        "score": result,
                    })
                    seen.append(axial_index)
                    _write_json_atomic(staging / "slice_scores.json", scores)
            expected = list(panel_manifest["coverage"]["expected_axial_indices"])
            if seen != expected or len(seen) != len(set(seen)):
                raise PipelineError("Recortes axiais nao preservaram cobertura exata.")
            elapsed = time.monotonic() - started
            if elapsed > max_case_seconds:
                raise PipelineError("Scorer axial ultrapassou o teto por caso.")
            scores_path = staging / "slice_scores.json"
            manifest = {
                "schema": CASE_SCHEMA, "case_id": case_id,
                "status": "scores_only_no_decision",
                "candidate_signature": frozen["candidate_signature"],
                "panel_set_sha256": frozen["panel_set_sha256"],
                "slice_count": len(scores), "scores_sha256": _sha256(scores_path),
                "experiment_signature": freeze["experiment_signature"],
                "review_signature": freeze["review_signature"],
                "model_id": scorer.model_id, "model_version": scorer.model_version,
                "elapsed_seconds": round(elapsed, 4), "max_case_seconds": max_case_seconds,
                "within_time_limit": True, "final_decision": None,
                "research_only": True, "clinical_use_allowed": False,
                "requires_human_review": True, "ground_truth_read": False,
                "metrics_calculated": False,
            }
            _write_json_atomic(staging / "slice_manifest.json", manifest)
            _publish_directory(staging, final_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        manifests.append(manifest)
        if progress:
            progress({"sequence": sequence, "case_count": len(selected), "case_id": case_id,
                      "slice_count": manifest["slice_count"], "elapsed_seconds": manifest["elapsed_seconds"]})
    times = [float(item["elapsed_seconds"]) for item in manifests]
    summary = {
        "schema": RUN_SCHEMA, "status": "complete", "case_count": len(selected),
        "full_cohort": len(selected) == freeze["case_count"],
        "case_ids": selected, "slice_count": sum(int(item["slice_count"]) for item in manifests),
        "success_count": len(manifests), "failure_count": 0,
        "experiment_signature": freeze["experiment_signature"],
        "review_signature": freeze["review_signature"],
        "model_id": scorer.model_id, "model_version": scorer.model_version,
        "mean_case_seconds": statistics.fmean(times), "max_case_seconds": max(times),
        "total_wall_seconds": round(time.monotonic() - run_started, 4),
        "time_gate_180_seconds_passed": max(times) <= max_case_seconds,
        "final_decision": None, "research_only": True, "clinical_use_allowed": False,
        "requires_human_review": True, "ground_truth_read": False, "metrics_calculated": False,
    }
    _write_json_atomic(summary_path, summary)
    return summary
