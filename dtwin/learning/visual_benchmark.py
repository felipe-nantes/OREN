"""Benchmark runner for the Etapa C visual classifier (production bundle).

Runs the full per-case flow — liver-enriched multiphase panels -> MedSigLIP
embeddings -> production bundle -> binary decision — over a set of cases, and
computes metrics with the in-sample guard as a first-class citizen: cases the
bundle was trained on are reported SEPARATELY and never mixed into a clean
number.

Panel rendering and embedding are injected (``panel_fn``/``embed_fn``) so the
orchestration is unit-testable without a GPU or image IO; the defaults wire the
real `exam_to_panels` / `visual_inference` pipeline.

Input contract per case (honest, since automatic DICOM phase identification is
out of scope): ``phase_paths`` are the already-identified phase volumes and
``coarse_liver_mask_path`` is the liver mask (e.g. the webapp's
``mask_organ.nii.gz``). ``label`` is POSITIVE/NEGATIVE, bound only at metric
time.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.exam_to_panels import build_exam_panels
from dtwin.learning.visual_inference import (
    IN_SAMPLE_NO,
    IN_SAMPLE_UNKNOWN,
    IN_SAMPLE_YES,
    ProductionBundle,
    classify_embeddings,
    embed_panels,
    in_sample_status,
    load_production_bundle,
)

PanelFn = Callable[[str, dict[str, Path], Path, Path], list[Path]]
EmbedFn = Callable[[Sequence[Path]], np.ndarray]


def _default_panel_fn(panel_config_path: Path | str):
    def panel_fn(case_id: str, phase_paths: dict[str, Path], mask_path: Path, out_dir: Path) -> list[Path]:
        result = build_exam_panels(
            case_id=case_id,
            phase_paths=phase_paths,
            coarse_liver_mask_path=mask_path,
            output_dir=out_dir,
            panel_config_path=panel_config_path,
        )
        return result.panel_paths

    return panel_fn


def _default_embed_fn(embedding_config_path: Path | str):
    def embed_fn(panel_paths: Sequence[Path]) -> np.ndarray:
        return embed_panels(embedding_config_path, panel_paths)

    return embed_fn


def _wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: {label: POSITIVE|NEGATIVE, prediction: POSITIVE|NEGATIVE|TECHNICAL_FAILURE, technical_failure}"""
    tp = tn = fp = fn = failures = 0
    for row in rows:
        positive = row["label"] == "POSITIVE"
        if row.get("technical_failure") or row.get("prediction") == "TECHNICAL_FAILURE":
            failures += 1
            fn += 1 if positive else 0
            fp += 0 if positive else 1
            continue
        predicted = row["prediction"] == "POSITIVE"
        if positive and predicted:
            tp += 1
        elif not positive and not predicted:
            tn += 1
        elif positive:
            fn += 1
        else:
            fp += 1
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "case_count": len(rows),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "technical_failures": failures,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2.0,
        "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
        "specificity_ci95_wilson": _wilson(tn, tn + fp),
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def classify_one_case(
    *,
    bundle: ProductionBundle,
    case: dict[str, Any],
    work_dir: Path,
    panel_fn: PanelFn,
    embed_fn: EmbedFn,
) -> dict[str, Any]:
    """Render+embed+classify a single case; any failure becomes a technical
    failure (counted as an error), never a fabricated decision."""
    case_id = str(case["case_id"])
    record: dict[str, Any] = {
        "case_id": case_id,
        "patient_group_id": str(case.get("patient_group_id") or case_id),
        "prediction": "TECHNICAL_FAILURE",
        "technical_failure": True,
        "score": None,
    }
    try:
        phase_paths = {str(k): Path(v) for k, v in case["phase_paths"].items()}
        mask_path = Path(case["coarse_liver_mask_path"])
        panels = panel_fn(case_id, phase_paths, mask_path, Path(work_dir) / case_id)
        embeddings = embed_fn(panels)
        decision = classify_embeddings(bundle, embeddings)
        record.update(
            prediction=decision["prediction"],
            technical_failure=False,
            score=decision["score"],
            threshold=decision["threshold"],
            panel_count=decision["panel_count"],
        )
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def run_visual_benchmark(
    *,
    bundle_root: Path,
    cases: list[dict[str, Any]],
    work_dir: Path,
    panel_config_path: Path | str,
    embedding_config_path: Path | str,
    panel_fn: PanelFn | None = None,
    embed_fn: EmbedFn | None = None,
    provenance: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the visual benchmark over ``cases`` and return a report that keeps
    in-sample, out-of-sample and unknown-provenance metrics strictly separate.

    ``provenance`` maps benchmark identifiers onto the original cohort ids, so a
    collection that renames its cases (e.g. a blind benchmark) can still be
    checked against the training set instead of landing in ``unknown``.
    """
    if not cases:
        raise PipelineError("Benchmark visual exige ao menos um caso.")
    bundle = load_production_bundle(bundle_root)
    panel_fn = panel_fn or _default_panel_fn(panel_config_path)
    embed_fn = embed_fn or _default_embed_fn(embedding_config_path)

    per_case: list[dict[str, Any]] = []
    for case in cases:
        record = classify_one_case(
            bundle=bundle, case=case, work_dir=Path(work_dir),
            panel_fn=panel_fn, embed_fn=embed_fn,
        )
        status = in_sample_status(
            bundle,
            case_id=record["case_id"],
            patient_group_id=record["patient_group_id"],
            provenance=provenance,
        )
        record["in_sample"] = status["in_sample"]
        record["in_sample_verdict"] = status["verdict"]
        record["label"] = str(case["label"]).upper()
        per_case.append(record)

    # `unknown` NUNCA entra no headline: um identificador que não pode ser
    # comparado ao conjunto de treino pode perfeitamente ser in-sample, e
    # tratá-lo como out-of-sample certifica número inflado como limpo.
    out_rows = [r for r in per_case if r["in_sample_verdict"] == IN_SAMPLE_NO]
    in_rows = [r for r in per_case if r["in_sample_verdict"] == IN_SAMPLE_YES]
    unknown_rows = [r for r in per_case if r["in_sample_verdict"] == IN_SAMPLE_UNKNOWN]

    report = {
        "schema": "argos-hybrid-visual-benchmark-report-v1",
        "candidate_id": bundle.manifest.get("candidate_id"),
        "bundle_signature": bundle.manifest.get("bundle_signature"),
        "case_count": len(per_case),
        "in_sample_count": len(in_rows),
        "out_of_sample_count": len(out_rows),
        "unknown_provenance_count": len(unknown_rows),
        # The headline number is ONLY the provably out-of-sample metric.
        # In-sample and unknown are reported apart and explicitly flagged.
        "out_of_sample_metrics": _metrics(out_rows) if out_rows else None,
        "in_sample_metrics_inflated_do_not_report_as_generalization": (
            _metrics(in_rows) if in_rows else None
        ),
        "unknown_provenance_metrics_not_a_generalization_estimate": (
            _metrics(unknown_rows) if unknown_rows else None
        ),
        "warning": " ".join(filter(None, [
            (
                "Contém casos in-sample (vistos no treino do bundle): as métricas "
                "in-sample são infladas e estão separadas."
                if in_rows else ""
            ),
            (
                f"Contém {len(unknown_rows)} caso(s) cuja procedência NÃO pôde ser "
                "comparada ao conjunto de treino (namespace de identificador "
                "distinto). Esses casos podem ser in-sample; não são estimativa "
                "de generalização e ficam fora do headline. Forneça um mapa de "
                "proveniência para decidir."
                if unknown_rows else ""
            ),
            "Só o out-of-sample comprovado é estimativa de generalização."
            if (in_rows or unknown_rows) else "",
        ])) or None,
        "generalization_estimate_reference_oof": "Etapa C nested-OOF 75,91%/76,11% (docs/121)",
        "research_only": True,
        "clinical_use_allowed": False,
        "gate_75_75_stable_by_dataset": False,
        "cases": per_case,
    }
    return report
