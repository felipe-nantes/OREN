from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.monophase_protocol import resolve_monophase_sequence_contract
from dtwin.learning.monophase_subtype_adjudication import (
    aggregate_balanced_choice_reads,
    build_balanced_choice_prompts,
    fuse_subtype_adjudication,
    request_balanced_subtype_reads,
    validated_top2,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/medgemma_local_4b_monophase_rag.yaml"))
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--class-probabilities", help="JSON com as quatro probabilidades")
    parser.add_argument("--hcc", type=float)
    parser.add_argument("--fnh", type=float)
    parser.add_argument("--hemangioma", type=float)
    parser.add_argument("--hepatic-cyst", type=float)
    parser.add_argument("--binary-prediction", choices=("POSITIVE", "NEGATIVE", "INCONCLUSIVE"), default="INCONCLUSIVE")
    parser.add_argument("--source-phase-key", default="t1_delayed")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.class_probabilities:
        probabilities = json.loads(args.class_probabilities)
    else:
        numeric = {
            "hcc": args.hcc,
            "fnh": args.fnh,
            "hemangioma": args.hemangioma,
            "hepatic_cyst": args.hepatic_cyst,
        }
        if any(value is None for value in numeric.values()):
            parser.error("informe --class-probabilities ou as quatro probabilidades numéricas")
        probabilities = numeric
    top2 = validated_top2(probabilities)
    specs = build_balanced_choice_prompts(
        top2=top2, source_phase_key=args.source_phase_key, panel_number=1, panel_total=1
    )
    gateway = request_balanced_subtype_reads(config_path=args.config, image_path=args.image, prompt_specs=specs)
    adjudication = aggregate_balanced_choice_reads(prompt_specs=specs, reads=gateway["reads"])
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    result = {
        "gateway": gateway,
        "result": fuse_subtype_adjudication(
            binary_prediction=args.binary_prediction,
            class_probabilities=probabilities,
            medgemma_adjudication=adjudication,
            sequence_contract=contract,
        ),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
