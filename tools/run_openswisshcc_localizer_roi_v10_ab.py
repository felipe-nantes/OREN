"""Run frozen mirrored-A/B scoring on paired OpenSwissHCC v10 ROI galleries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from dtwin.benchmark.openswisshcc_localizer_roi_inference import run_roi_scores
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config

try:
    from tools.medgemma_server import MedGemmaRuntime
except ModuleNotFoundError:
    from medgemma_server import MedGemmaRuntime


class LocalMirroredABScorer:
    def __init__(self, config_path: Path):
        config = load_screening_config(config_path)
        self.med = config["medgemma"]
        if self.med.get("model_id") != "google/medgemma-1.5-4b-it" or self.med.get("model_parameter_scale") != "4B" or self.med.get("response_mode") != "choice_classification":
            raise PipelineError("Scorer ROI v10 exige exatamente MedGemma 1.5 4B em choice_classification.")
        self.runtime = MedGemmaRuntime(config)
        self.runtime.load()
        if not self.runtime.loaded:
            raise PipelineError(self.runtime.load_error or "MedGemma 1.5 4B nao carregado.")
        self.model_id = str(self.med["model_id"])
        self.model_version = str(self.med["model_version"])

    def close(self):
        if hasattr(self.runtime, "unload"):
            self.runtime.unload()

    def score_choice(self, panel_path: Path, prompt: str) -> dict[str, Any]:
        with Image.open(Path(panel_path).resolve()) as source:
            if source.format != "PNG" or source.width * source.height > int(self.med.get("max_image_pixels", 4_000_000)):
                raise PipelineError("Painel ROI v10 invalido para o runtime.")
            source.load()
            image = source.convert("RGB")
        result = self.runtime.choose(image, prompt, ["A", "B"])
        probabilities = result.get("choice_probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != {"A", "B"}:
            raise PipelineError("Runtime ROI v10 retornou probabilidades invalidas.")
        return {"choice": result.get("choice"), "choice_probabilities": {"A": float(probabilities["A"]), "B": float(probabilities["B"])}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology", type=Path, required=True)
    parser.add_argument("--enhancement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--localizer-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--expected-case-count", type=int, default=10)
    args = parser.parse_args()
    scorer = LocalMirroredABScorer(args.config)
    try:
        summary = run_roi_scores(morphology_root=args.morphology, enhancement_root=args.enhancement, review_path=args.review, freeze_path=args.freeze, config_path=args.config, localizer_run=args.localizer_run, output_root=args.out, scorer=scorer, expected_case_count=args.expected_case_count, case_ids=args.case_id, progress=lambda value: print(json.dumps(value, sort_keys=True), flush=True))
    finally:
        scorer.close()
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
