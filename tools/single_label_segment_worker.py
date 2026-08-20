#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker isolado (um tiro, killable) que roda TotalSegmentator total_mr
para UM rotulo generico, escolhido via --label. Usado para complementar a
representacao arterial (aorta -- total_mr nao tem rotulo de arteria
hepatica nas suas 50 classes) nos 20 casos ja selecionados como melhores e
piores.

Nao toca em dtwin/benchmark/lld_mmri_v23_preparation.py (congelado); segue o
mesmo padrao de isolamento de tools/lld_mmri_v23_segment_worker.py.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.windows_spawn_guard import (
    block_optional_module_for_spawn,
)


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def segment_single_label(source: Path, output_mask: Path, label: str, *, device: str, fast: bool) -> dict:
    from totalsegmentator.python_api import totalsegmentator

    configured_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    weights_dir = (
        Path(configured_weights).expanduser().resolve()
        if configured_weights
        else (Path.home() / ".totalsegmentator" / "nnunet" / "results").resolve()
    )
    if not weights_dir.is_dir():
        raise RuntimeError("Pesos locais do TotalSegmentator nao encontrados.")

    started = time.perf_counter()
    with (
        tempfile.TemporaryDirectory(prefix="argos-single-label-home-") as home_folder,
        tempfile.TemporaryDirectory(prefix="argos-single-label-out-") as output_folder,
    ):
        runtime_home = Path(home_folder)
        output_dir = Path(output_folder)
        _write_json_atomic(
            runtime_home / "config.json",
            {
                "totalseg_id": "argos_single_label_ephemeral",
                "send_usage_stats": False,
                "prediction_counter": 0,
                "statistics_disclaimer_shown": True,
            },
        )
        previous_home = os.environ.get("TOTALSEG_HOME_DIR")
        previous_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
        os.environ["TOTALSEG_HOME_DIR"] = str(runtime_home)
        os.environ["TOTALSEG_WEIGHTS_PATH"] = str(weights_dir)
        try:
            totalsegmentator(
                input=str(Path(source).resolve()),
                output=str(output_dir),
                task="total_mr",
                roi_subset=[label],
                device=device,
                fast=bool(fast),
                quiet=True,
            )
        finally:
            if previous_home is None:
                os.environ.pop("TOTALSEG_HOME_DIR", None)
            else:
                os.environ["TOTALSEG_HOME_DIR"] = previous_home
            if previous_weights is None:
                os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
            else:
                os.environ["TOTALSEG_WEIGHTS_PATH"] = previous_weights

        produced = output_dir / f"{label}.nii.gz"
        if not produced.is_file():
            raise RuntimeError(f"TotalSegmentator nao produziu {label}.nii.gz.")
        output_mask.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output_mask)

    return {
        "engine": "TotalSegmentator", "task": "total_mr", "roi_subset": [label],
        "device": device, "fast": bool(fast), "elapsed_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()
    with block_optional_module_for_spawn("pyarrow"):
        receipt = segment_single_label(
            args.source, args.output, args.label, device=args.device, fast=args.fast
        )
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
