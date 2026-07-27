"""Score signed volumetric axial tiles one-by-one with local MedGemma 1.5 4B."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from dtwin.benchmark.openswisshcc_slice_pairwise import (
    SLICE_PAIR,
    SLICE_SCHEMA,
    run_slice_pairwise_scores,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config
from tools.medgemma_server import MedGemmaRuntime


class LocalSliceScorer:
    def __init__(self, config_path: Path):
        config = load_screening_config(config_path)
        self.med = config["medgemma"]
        if self.med.get("model_id") != "google/medgemma-1.5-4b-it":
            raise PipelineError("Scorer por corte exige exatamente MedGemma 1.5 4B.")
        self.runtime = MedGemmaRuntime(config)
        self.runtime.load()
        if not self.runtime.loaded:
            raise PipelineError(self.runtime.load_error or "MedGemma 4B nao carregado.")
        self.model_id = str(self.med["model_id"])
        self.model_version = str(self.med["model_version"])

    def close(self) -> None:
        if hasattr(self.runtime, "unload"):
            self.runtime.unload()

    def score_slice(self, image: Image.Image, prompt: str) -> dict[str, Any]:
        choices = [SLICE_PAIR["positive"], SLICE_PAIR["negative"]]
        result = self.runtime.choose(image, prompt, choices)
        probabilities = result.get("choice_probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != set(choices):
            raise PipelineError("Runtime retornou probabilidades axiais invalidas.")
        return {
            "schema": SLICE_SCHEMA,
            "pair_id": SLICE_PAIR["pair_id"],
            "positive_probability": float(probabilities[SLICE_PAIR["positive"]]),
            "negative_probability": float(probabilities[SLICE_PAIR["negative"]]),
            "selected_statement": result.get("choice"),
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
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--max-case-seconds", type=float, default=180.0)
    args = parser.parse_args()
    scorer = LocalSliceScorer(args.multiphase_config)
    try:
        summary = run_slice_pairwise_scores(
            panel_root=args.panels, review_path=args.review, freeze_path=args.freeze,
            config_paths={
                "multiphase": args.multiphase_config,
                "venous": args.venous_config,
                "venous_high_contrast": args.venous_high_contrast_config,
            },
            output_root=args.out, scorer=scorer,
            expected_case_count=args.expected_case_count,
            selected_case_ids=args.case_id, max_case_seconds=args.max_case_seconds,
            progress=lambda value: print(json.dumps(value, sort_keys=True), flush=True),
        )
    finally:
        scorer.close()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
