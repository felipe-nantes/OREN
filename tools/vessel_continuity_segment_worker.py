#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker isolado (um tiro, processo killable) que roda TotalSegmentator
total_mr com roi_subset = figado + veia porta/esplenica + veia cava inferior,
na MESMA chamada (custo de inferencia por rotulo extra e marginal -- e' o
mesmo forward pass do modelo, so muda quais canais sao extraidos).

Reaproveita o padrao de isolamento de tools/lld_mmri_v23_segment_worker.py
(subprocess com timeout, --receipt), mas NAO toca em
dtwin/benchmark/lld_mmri_v23_preparation.py (modulo congelado). A funcao de
segmentacao fica aqui, local a esta medicao pontual (mesmo padrao de
tools/measure_four_phase_union_gain.py, que tambem nao modifica codigo de
producao para rodar um experimento).

--output aponta para o arquivo do figado; os dois vasos saem como arquivos
irmaos, trocando o sufixo antes de ".nii.gz":
    caso_liver.nii.gz -> caso_portal_vein_and_splenic_vein.nii.gz
                       -> caso_inferior_vena_cava.nii.gz
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
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn  # noqa: E402

ROI_LABELS = ["liver", "portal_vein_and_splenic_vein", "inferior_vena_cava"]


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def total_mr_liver_vessels_segmenter(
    source_venous: Path, output_liver_mask: Path, *, device: str = "gpu", fast: bool = False
) -> dict[str, Any]:
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
    stem = output_liver_mask.name
    if not stem.endswith("_liver.nii.gz"):
        raise RuntimeError("--output deve terminar em '_liver.nii.gz'.")
    base = stem[: -len("_liver.nii.gz")]
    portal_out = output_liver_mask.parent / f"{base}_portal_vein_and_splenic_vein.nii.gz"
    cava_out = output_liver_mask.parent / f"{base}_inferior_vena_cava.nii.gz"

    with (
        tempfile.TemporaryDirectory(prefix="argos-vessel-totalseg-home-") as home_folder,
        tempfile.TemporaryDirectory(prefix="argos-vessel-totalseg-output-") as output_folder,
    ):
        runtime_home = Path(home_folder)
        output_dir = Path(output_folder)
        _write_json_atomic(
            runtime_home / "config.json",
            {
                "totalseg_id": "argos_vessel_continuity_ephemeral",
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
                input=str(Path(source_venous).resolve()),
                output=str(output_dir),
                task="total_mr",
                roi_subset=ROI_LABELS,
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

        produced_liver = output_dir / "liver.nii.gz"
        if not produced_liver.is_file():
            raise RuntimeError("TotalSegmentator nao produziu liver.nii.gz.")
        output_liver_mask.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced_liver, output_liver_mask)

        found_vessels = {}
        for rotulo, destino in (
            ("portal_vein_and_splenic_vein", portal_out),
            ("inferior_vena_cava", cava_out),
        ):
            produced = output_dir / f"{rotulo}.nii.gz"
            if produced.is_file():
                shutil.copyfile(produced, destino)
                found_vessels[rotulo] = True
            else:
                found_vessels[rotulo] = False

    return {
        "engine": "TotalSegmentator",
        "task": "total_mr",
        "roi_subset": ROI_LABELS,
        "device": device,
        "fast": bool(fast),
        "found_vessels": found_vessels,
        "elapsed_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()
    with block_optional_module_for_spawn("pyarrow"):
        receipt = total_mr_liver_vessels_segmenter(
            args.source, args.output, device=args.device, fast=args.fast
        )
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
