#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mede o `total_mr` contra a referência humana do CHAOS, caso a caso.

A pergunta que isto responde: os fígados de ~640 mL que o pipeline produz na
coorte LLD são sub-segmentação do modelo, ou são fígados pequenos de verdade?
Sem referência humana as duas explicações cabem, e tanto o piso do gate quanto
qualquer conserto da máscara viram chute (docs/175 §6).

O CHAOS traz máscara hepática anotada por humano, já na MESMA grade do
`t1_in.nii.gz` preparado, então Dice e razão de volume saem sem reamostragem.

Ressalva que precisa acompanhar o número: o CHAOS é T1 SEM contraste, e o
pipeline segmenta a fase venosa COM contraste. docs/165 mostrou que a fase muda
o resultado. Isto mede o modelo com a anatomia inteira em quadro; não substitui
uma referência na própria coorte.

Grava a cada caso: uma interrupção no meio não perde o que já rodou.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import isolated_total_mr_liver_segmenter

ENTRADA = REPO / "data" / "prepared" / "chaos_v21_blind"
SAIDA = REPO / "experiments" / "total_mr_vs_chaos_v1"


def volume_ml(mascara: np.ndarray, espacamento) -> float:
    return float(mascara.sum() * math.prod(espacamento) / 1000.0)


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / "results.json"
    feitos = json.loads(destino.read_text("utf-8")) if destino.is_file() else {}

    casos = sorted(d for d in ENTRADA.iterdir() if d.is_dir())
    for i, caso in enumerate(casos, 1):
        if caso.name in feitos:
            continue
        fonte = caso / "t1_in.nii.gz"
        referencia = caso / "liver_mask.nii.gz"
        if not (fonte.is_file() and referencia.is_file()):
            continue
        predita = SAIDA / "masks" / f"{caso.name}.nii.gz"
        print(f"[{i}/{len(casos)}] {caso.name}", flush=True)
        try:
            isolated_total_mr_liver_segmenter(
                fonte, predita, device="gpu", fast=False, timeout_seconds=600
            )
        except Exception as exc:
            feitos[caso.name] = {"erro": f"{type(exc).__name__}: {exc}"}
            destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
            print(f"    falhou: {exc}", flush=True)
            continue

        img_ref = sitk.ReadImage(str(referencia))
        ref = sitk.GetArrayFromImage(img_ref) > 0
        pred = sitk.GetArrayFromImage(sitk.ReadImage(str(predita))) > 0
        if ref.shape != pred.shape:
            feitos[caso.name] = {"erro": f"grades diferentes {ref.shape} vs {pred.shape}"}
            destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
            continue

        sp = img_ref.GetSpacing()
        v_ref, v_pred = volume_ml(ref, sp), volume_ml(pred, sp)
        intersecao = float((ref & pred).sum())
        dice = 2 * intersecao / (ref.sum() + pred.sum()) if (ref.sum() + pred.sum()) else 0.0
        feitos[caso.name] = {
            "volume_referencia_ml": round(v_ref, 1),
            "volume_predito_ml": round(v_pred, 1),
            "razao_predito_referencia": round(v_pred / v_ref, 3) if v_ref else None,
            "dice": round(dice, 4),
            "recall_do_figado": round(intersecao / ref.sum(), 4) if ref.sum() else None,
        }
        destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
        print(f"    ref {v_ref:.0f} mL | predito {v_pred:.0f} mL | dice {dice:.3f}", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if validos:
        raz = np.array([v["razao_predito_referencia"] for v in validos])
        dic = np.array([v["dice"] for v in validos])
        print()
        print(f"n={len(validos)}  (erros: {len(feitos)-len(validos)})")
        print(f"  Dice mediano                : {np.median(dic):.3f}")
        print(f"  razao predito/referencia    : mediana {np.median(raz):.2f}  "
              f"min {raz.min():.2f}  max {raz.max():.2f}")
        print(f"  casos com menos de 70% do volume de referencia: {(raz<0.7).sum()}/{len(raz)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
