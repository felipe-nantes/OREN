#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teste ISOLADO do MRSegmentator (docs/191/193 continuam a busca por um
segmentador de figado melhor que o total_mr generalista).

RODA EXCLUSIVAMENTE NO VENV .venv-mrseg -- nunca toca o .venv-win de producao.
Chama a CLI mrsegmentator via subprocesso. Escreve so' em experiments/.

Pergunta 1 (robustez): o MRSegmentator sobrevive a' preparacao 0-255 do LLD,
onde o liver_segments_mr colapsou (docs/193)? -> volume nao-vazio na venosa.

Pergunta 2 (acuracia): contra a referencia humana do CHAOS, seu Dice bate o
total_mr (0,9082, docs/176) e o liver_segments_mr (0,9256, docs/191)?

Uso (com o python do venv ISOLADO):
    .venv-mrseg/Scripts/python.exe tools/test_mrsegmentator_isolated.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk

REPO = Path(__file__).resolve().parents[1]
MRSEG = REPO / ".venv-mrseg" / "Scripts" / "mrsegmentator.exe"
LLD_INPUTS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
LLD_TMR = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
CHAOS = REPO / "data/prepared/chaos_v21_blind"
OUT = REPO / "experiments/mrsegmentator_lld_test"
LIVER_LABEL = 5

# volumes total_mr ja medidos (docs/193) nos casos LLD venosos
TMR_LLD = {"anon-lld-0164881aa6759a00": 630, "anon-lld-08c7d7e145ac0800": 892,
           "anon-lld-0c4a7eb1d2016bba": 303}
CHAOS_CASOS = sorted(d.name for d in CHAOS.iterdir() if d.is_dir())[:6] if CHAOS.is_dir() else []


def roda_mrseg(src: Path, outdir: Path) -> Path:
    # Diretorio POR CASO: os inputs se chamam todos t1_venous/t1_in, entao uma
    # pasta compartilhada faria os casos sobrescreverem uns aos outros.
    outdir.mkdir(parents=True, exist_ok=True)
    esperado = outdir / f"{src.stem.replace('.nii','')}_seg.nii.gz"
    if not esperado.is_file():
        subprocess.run([str(MRSEG), "-i", str(src), "-o", str(outdir),
                        "--fast", "--cpu_only", "--no_tqdm"],
                       cwd=REPO, check=True, capture_output=True, text=True)
    return esperado


def liver_de(seg_path: Path):
    seg = sitk.ReadImage(str(seg_path))
    arr = sitk.GetArrayFromImage(seg) == LIVER_LABEL
    vol = float(arr.sum()) * math.prod(seg.GetSpacing()) / 1000.0
    return arr, vol


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    resultado = {"robustez_lld_venoso": {}, "acuracia_chaos": {}}

    print("=" * 70)
    print("MRSegmentator -- teste isolado (.venv-mrseg, nao toca producao)")
    print("=" * 70)
    print("\n[1] ROBUSTEZ na preparacao 0-255 do LLD (liver_segments_mr deu 0 mL):")
    for anon, tmr_vol in TMR_LLD.items():
        src = LLD_INPUTS / anon / "t1_venous.nii.gz"
        if not src.is_file():
            continue
        seg = roda_mrseg(src, OUT / "out" / anon)
        _, vol = liver_de(seg)
        resultado["robustez_lld_venoso"][anon] = {"mrsegmentator_ml": round(vol, 0),
                                                   "total_mr_ml": tmr_vol,
                                                   "liver_segments_mr_ml": 0}
        print(f"    {anon[:22]}: MRSeg {vol:4.0f} mL | total_mr {tmr_vol} mL | liver_seg_mr 0 mL")

    print("\n[2] ACURACIA vs referencia humana CHAOS (Dice):")
    for caso in CHAOS_CASOS:
        src = CHAOS / caso / "t1_in.nii.gz"
        ref_p = CHAOS / caso / "liver_mask.nii.gz"
        if not (src.is_file() and ref_p.is_file()):
            continue
        seg = roda_mrseg(src, OUT / "chaos" / caso)
        ref_img = sitk.ReadImage(str(ref_p))
        ref = sitk.GetArrayFromImage(ref_img) > 0
        # MRSegmentator pode devolver a saida numa grade diferente da referencia;
        # reamostra a predicao de figado para a grade da referencia (vizinho mais
        # proximo, mascara binaria) antes do Dice.
        seg_img = sitk.ReadImage(str(seg))
        liver_img = sitk.BinaryThreshold(seg_img, LIVER_LABEL, LIVER_LABEL, 1, 0)
        if (seg_img.GetSize() != ref_img.GetSize()
                or seg_img.GetSpacing() != ref_img.GetSpacing()
                or seg_img.GetOrigin() != ref_img.GetOrigin()):
            liver_img = sitk.Resample(liver_img, ref_img, sitk.Transform(),
                                      sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
        pred = sitk.GetArrayFromImage(liver_img) > 0
        if pred.shape != ref.shape:
            print(f"    {caso[:24]}: grades diferentes apos reamostragem, pulado")
            continue
        inter = float(np.logical_and(pred, ref).sum())
        dice = 2 * inter / (pred.sum() + ref.sum()) if (pred.sum() + ref.sum()) else 0.0
        recall = inter / ref.sum() if ref.sum() else 0.0
        resultado["acuracia_chaos"][caso] = {"dice": round(dice, 4), "recall": round(recall, 4)}
        print(f"    {caso[:24]}: Dice {dice:.4f}  recall {recall:.4f}")

    dices = [v["dice"] for v in resultado["acuracia_chaos"].values()]
    if dices:
        print("\n" + "=" * 70)
        print(f"Dice mediano MRSegmentator (CHAOS, n={len(dices)}): {np.median(dices):.4f}")
        print("  referencia: total_mr 0.9082 (docs/176) | liver_segments_mr 0.9256 (docs/191)")
    (OUT / "results.json").write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nsalvo em {OUT / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
