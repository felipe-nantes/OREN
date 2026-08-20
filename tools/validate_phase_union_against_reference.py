#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A união de fases recupera fígado, ou só acumula erro?

No LLD mediu-se que venosa e pré-contraste concordam com Dice de apenas 0,64 e
que a união eleva o volume mediano de 569 para 737 mL. Isso mostra que cada fase
encontra partes diferentes -- mas união SEMPRE cresce, e crescer não prova
acertar. Pode estar somando fígado real ou somando erro de cada fase.

Só há um jeito de decidir: medir contra referência humana. O CHAOS tem anotação
humana e duas séries T1 do mesmo exame (in-phase e out-of-phase), então permite
exatamente este teste:

  se Dice(união, humano) > Dice(fase isolada, humano)  -> recupera fígado real
  se Dice(união, humano) < Dice(fase isolada, humano)  -> acumula erro

O braço in-phase já foi segmentado em docs/176. Este script segmenta o
out-of-phase e compara os três.

Uso:
    .venv-win/Scripts/python.exe tools/validate_phase_union_against_reference.py
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import (
    isolated_total_mr_liver_segmenter,
)

CHAOS = REPO / "data/prepared/chaos_v21_blind"
IN_PHASE = REPO / "experiments/total_mr_vs_chaos_v1/masks"      # docs/176
SAIDA = REPO / "experiments/phase_union_validation_v1"


def dice(a: np.ndarray, b: np.ndarray) -> float:
    total = int(a.sum()) + int(b.sum())
    return 2.0 * float((a & b).sum()) / total if total else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks_out_phase").mkdir(exist_ok=True)
    destino = SAIDA / "results.json"
    feitos = json.loads(destino.read_text("utf-8")) if destino.is_file() else {}

    casos = sorted(d.name for d in CHAOS.iterdir() if d.is_dir())
    if args.limit:
        casos = casos[: args.limit]

    print("=" * 78)
    print("UNIAO DE FASES CONTRA REFERENCIA HUMANA (CHAOS)")
    print("=" * 78)
    print(f"casos: {len(casos)}\n")

    for i, case_id in enumerate(casos, 1):
        if case_id in feitos:
            continue
        ref_path = CHAOS / case_id / "liver_mask.nii.gz"
        out_path = CHAOS / case_id / "t1_out.nii.gz"
        in_mask = IN_PHASE / f"{case_id}.nii.gz"
        if not (ref_path.is_file() and out_path.is_file() and in_mask.is_file()):
            continue
        predita_out = SAIDA / "masks_out_phase" / f"{case_id}.nii.gz"
        print(f"[{i}/{len(casos)}] {case_id}", flush=True)
        if not predita_out.is_file():
            try:
                isolated_total_mr_liver_segmenter(
                    out_path, predita_out, device="gpu", fast=False, timeout_seconds=600
                )
            except Exception as exc:
                feitos[case_id] = {"erro": f"{type(exc).__name__}: {exc}"}
                destino.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
                print(f"    falhou: {exc}", flush=True)
                continue

        ref_img = sitk.ReadImage(str(ref_path))
        ref = sitk.GetArrayFromImage(ref_img) > 0
        m_in = sitk.GetArrayFromImage(sitk.ReadImage(str(in_mask))) > 0
        m_out = sitk.GetArrayFromImage(sitk.ReadImage(str(predita_out))) > 0
        if not (ref.shape == m_in.shape == m_out.shape):
            feitos[case_id] = {"erro": "grades divergentes"}
            destino.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
            continue

        ml = float(np.prod(ref_img.GetSpacing())) / 1000.0
        uniao = m_in | m_out
        registro = {
            "dice_in_phase": round(dice(m_in, ref), 4),
            "dice_out_phase": round(dice(m_out, ref), 4),
            "dice_uniao": round(dice(uniao, ref), 4),
            "dice_entre_as_fases": round(dice(m_in, m_out), 4),
            "volume_referencia_ml": round(int(ref.sum()) * ml, 1),
            "volume_in_ml": round(int(m_in.sum()) * ml, 1),
            "volume_uniao_ml": round(int(uniao.sum()) * ml, 1),
            # Onde a união cresce, ela acerta? Fração do que foi ACRESCENTADO
            # pela união que de fato é fígado segundo o humano.
            "precisao_do_acrescimo": None,
        }
        acrescimo = uniao & ~m_in
        if int(acrescimo.sum()) > 0:
            registro["precisao_do_acrescimo"] = round(
                float((acrescimo & ref).sum()) / float(acrescimo.sum()), 4
            )
        feitos[case_id] = registro
        destino.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
        print(f"    dice  in {registro['dice_in_phase']:.3f}  "
              f"out {registro['dice_out_phase']:.3f}  "
              f"uniao {registro['dice_uniao']:.3f}   "
              f"precisao do acrescimo {registro['precisao_do_acrescimo']}", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if not validos:
        print("\nnenhum caso valido.")
        return 1

    d_in = np.array([v["dice_in_phase"] for v in validos])
    d_out = np.array([v["dice_out_phase"] for v in validos])
    d_uni = np.array([v["dice_uniao"] for v in validos])
    entre = np.array([v["dice_entre_as_fases"] for v in validos])
    prec = np.array([v["precisao_do_acrescimo"] for v in validos
                     if v["precisao_do_acrescimo"] is not None])

    print()
    print("-" * 78)
    print(f"RESULTADO  (n={len(validos)})")
    print("-" * 78)
    print(f"  Dice contra o humano:")
    print(f"    in-phase isolado  mediana {np.median(d_in):.4f}")
    print(f"    out-phase isolado mediana {np.median(d_out):.4f}")
    print(f"    UNIAO             mediana {np.median(d_uni):.4f}")
    print()
    melhor_isolado = np.maximum(d_in, d_out)
    ganho = d_uni - melhor_isolado
    print(f"  uniao menos a MELHOR fase isolada: mediana {np.median(ganho):+.4f}")
    print(f"    casos em que a uniao melhorou : {int((ganho > 0).sum())}/{len(validos)}")
    print(f"    casos em que a uniao piorou   : {int((ganho < 0).sum())}/{len(validos)}")
    print()
    print(f"  concordancia entre as duas fases (Dice): mediana {np.median(entre):.4f}")
    if prec.size:
        print(f"  precisao do que a uniao ACRESCENTA     : mediana {np.median(prec):.4f}")
        print(f"    (fracao do acrescimo que o humano confirma ser figado)")
    print()
    if np.median(ganho) > 0:
        print("  A UNIAO RECUPERA FIGADO REAL nesta coorte.")
    else:
        print("  A UNIAO NAO MELHORA contra a referencia: cresce acumulando erro.")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
