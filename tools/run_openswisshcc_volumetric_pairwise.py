"""Run blind natural-language pairwise scoring with the local MedGemma 1.5 4B."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_volumetric_pairwise import (
    PAIRWISE_SCHEMA,
    run_volumetric_pairwise_scores,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config

try:
    from tools.medgemma_server import MedGemmaRuntime
except ModuleNotFoundError:  # Suporta execucao direta: python tools/run_...py
    from medgemma_server import MedGemmaRuntime


class LocalPairwiseScorer:
    def __init__(self, config_path: Path):
        self.config = load_screening_config(config_path)
        self.med = self.config["medgemma"]
        if self.med.get("model_id") != "google/medgemma-1.5-4b-it":
            raise PipelineError("Experimento pairwise exige exatamente MedGemma 1.5 4B.")
        self.runtime = MedGemmaRuntime(self.config)
        self.runtime.load()
        if not self.runtime.loaded:
            raise PipelineError(self.runtime.load_error or "MedGemma 4B nao carregado.")
        self.model_id = str(self.med["model_id"])
        self.model_version = str(self.med["model_version"])

    def close(self) -> None:
        if hasattr(self.runtime, "unload"):
            self.runtime.unload()

    def score_panel(
        self, panel_path: Path, prompt: str, pairs: tuple[dict[str, str], ...]
    ) -> dict[str, Any]:
        panel_path = Path(panel_path).resolve()
        with Image.open(panel_path) as source:
            if source.format != "PNG":
                raise PipelineError("Painel pairwise deve ser PNG.")
            width, height = source.size
            if width * height > int(self.med.get("max_image_pixels", 4_000_000)):
                raise PipelineError("Painel pairwise excede max_image_pixels.")
            source.load()
            image = source.convert("RGB")
        results = []
        for pair in pairs:
            pair_prompt = (
                f"{prompt}\n\n{pair['question']} Complete the answer with exactly one of the "
                "two authorized sentences; do not add explanation."
            )
            choices = [pair["positive"], pair["negative"]]
            selection = self.runtime.choose(image, pair_prompt, choices)
            probabilities = selection.get("choice_probabilities")
            if not isinstance(probabilities, dict) or set(probabilities) != set(choices):
                raise PipelineError("Runtime pairwise retornou probabilidades invalidas.")
            positive = float(probabilities[pair["positive"]])
            results.append({
                "pair_id": pair["pair_id"],
                "positive_statement": pair["positive"],
                "negative_statement": pair["negative"],
                "positive_probability": positive,
                "negative_probability": float(probabilities[pair["negative"]]),
                "selected_statement": selection.get("choice"),
            })
        positives = [float(item["positive_probability"]) for item in results]
        return {
            "schema": PAIRWISE_SCHEMA,
            "scoring_method": "mean_token_log_probability_two_mirrored_pairs_v1",
            "model_id": self.model_id,
            "model_version": self.model_version,
            "panel_sha256": _sha256(panel_path),
            "pairs": results,
            "positive_probability_mean": statistics.fmean(positives),
            "positive_probability_min": min(positives),
            "positive_probability_max": max(positives),
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    scorer = LocalPairwiseScorer(args.multiphase_config)
    try:
        summary = run_volumetric_pairwise_scores(
            panel_root=args.panels,
            review_path=args.review,
            freeze_path=args.freeze,
            config_paths={
                "multiphase": args.multiphase_config,
                "venous": args.venous_config,
                "venous_high_contrast": args.venous_high_contrast_config,
            },
            output_root=args.out,
            scorer=scorer,
            expected_case_count=args.expected_case_count,
            progress=lambda value: print(
                json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True
            ),
        )
    finally:
        scorer.close()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())


