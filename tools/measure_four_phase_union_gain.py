#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vale a pena somar a pré-contraste como QUARTA fase na união?

O que já sabemos: pré-contraste SOZINHA reprova (docs/175, 0,92x, 3x mais
fragmentada) -- não deve substituir a venosa. Mas a mesma lógica que fez a
união de 3 fases funcionar pode se aplicar de novo: no CHAOS, a fase mais fraca
isolada (out-phase, Dice 0,8957 vs 0,9082) ainda contribuiu com 82% de precisão
ao ser adicionada à união (docs/189). O que importa não é a qualidade da fase
sozinha, é se ela erra em lugares DIFERENTES das outras.

Este script mede, nos mesmos 19 casos de experiments/three_phase_union_v1
(reaproveitando as máscaras arterial/tardia já segmentadas -- só a pré-contraste
é nova), se a união de QUATRO fases recupera mais volume que a de três, e a que
custo de fragmentação.

Gate pré-especificado: a quarta fase só se justifica se o ganho mediano sobre a
união de três for >= 5% -- abaixo disso, o custo de mais ~40-70s por exame não
compensa por uma fração de volume que pode ser ruído específico da amostra.

Uso:
    .venv-win/Scripts/python.exe tools/measure_four_phase_union_gain.py
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import (  # noqa: E402
    isolated_total_mr_liver_segmenter,
)

VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
TRES_FASES = REPO / "experiments/three_phase_union_v1"
SAIDA = REPO / "experiments/four_phase_union_v1"
GATE_GANHO_MINIMO = 0.05
FAIXA_ADULTO_ML = (900.0, 2400.0)


def descreve(mask: np.ndarray, spacing) -> dict:
    voxels = int(mask.sum())
    volume = voxels * float(np.prod(spacing)) / 1000.0
    _, n = ndimage.label(mask)
    return {"volume_ml": round(volume, 1), "componentes": int(n)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks").mkdir(exist_ok=True)
    destino_json = SAIDA / "results.json"
    feitos = json.loads(destino_json.read_text("utf-8")) if destino_json.is_file() else {}

    tres_resultado = json.loads((TRES_FASES / "results.json").read_text("utf-8"))
    casos = sorted(c for c, v in tres_resultado.items() if "erro" not in v)
    if args.limit:
        casos = casos[: args.limit]

    print("=" * 78)
    print("QUARTA FASE (pre-contraste) NA UNIAO -- vale o custo?")
    print("=" * 78)
    print(f"gate: ganho mediano >= {100*GATE_GANHO_MINIMO:.0f}% sobre a uniao de 3 fases")
    print(f"casos: {len(casos)} (reaproveitando arterial/tardia ja segmentadas)\n")

    for i, case_id in enumerate(casos, 1):
        if case_id in feitos:
            continue
        venosa_mask_path = VENOSA / case_id / "liver_mask_venous.nii.gz"
        arterial_mask_path = TRES_FASES / "masks" / f"{case_id}_arterial.nii.gz"
        delayed_mask_path = TRES_FASES / "masks" / f"{case_id}_delayed.nii.gz"
        precontraste_src = ENTRADAS / case_id / "t1_native.nii.gz"
        if not all(p.is_file() for p in
                   (venosa_mask_path, arterial_mask_path, delayed_mask_path, precontraste_src)):
            continue
        print(f"[{i}/{len(casos)}] {case_id}", flush=True)

        pre_mask_path = SAIDA / "masks" / f"{case_id}_precontraste.nii.gz"
        if not pre_mask_path.is_file():
            try:
                isolated_total_mr_liver_segmenter(
                    precontraste_src, pre_mask_path, device="gpu", fast=False,
                    timeout_seconds=300,
                )
            except Exception as exc:  # noqa: BLE001
                feitos[case_id] = {"erro": f"segmentacao pre-contraste falhou: {exc}"}
                destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
                print(f"    falhou: {exc}", flush=True)
                continue

        img_ref = sitk.ReadImage(str(venosa_mask_path))
        venosa = sitk.GetArrayFromImage(img_ref) > 0
        arterial = sitk.GetArrayFromImage(sitk.ReadImage(str(arterial_mask_path))) > 0
        tardia = sitk.GetArrayFromImage(sitk.ReadImage(str(delayed_mask_path))) > 0
        img_pre = sitk.ReadImage(str(pre_mask_path))
        pre = sitk.GetArrayFromImage(img_pre) > 0

        if not (venosa.shape == arterial.shape == tardia.shape == pre.shape):
            feitos[case_id] = {"erro": "grades divergentes"}
            destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
            print("    grades divergentes, pulado", flush=True)
            continue

        uniao3 = venosa | arterial | tardia
        uniao4 = uniao3 | pre
        sp = img_ref.GetSpacing()
        registro = {
            "uniao_3_fases": descreve(uniao3, sp),
            "uniao_4_fases": descreve(uniao4, sp),
            "acrescimo_da_precontraste_ml": round(
                (int(uniao4.sum()) - int(uniao3.sum())) * float(np.prod(sp)) / 1000.0, 1
            ),
        }
        v3 = registro["uniao_3_fases"]["volume_ml"]
        v4 = registro["uniao_4_fases"]["volume_ml"]
        registro["ganho_relativo"] = round((v4 - v3) / v3, 4) if v3 else None
        feitos[case_id] = registro
        destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
        print(f"    uniao3 {v3:>6.0f} mL  ->  uniao4 {v4:>6.0f} mL  "
              f"(+{registro['ganho_relativo']*100:.1f}%)", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if not validos:
        print("\nnenhum caso valido.")
        return 1

    v3 = np.array([v["uniao_3_fases"]["volume_ml"] for v in validos])
    v4 = np.array([v["uniao_4_fases"]["volume_ml"] for v in validos])
    ganho = (v4 - v3) / v3
    baixo, alto = FAIXA_ADULTO_ML
    comp3 = np.array([v["uniao_3_fases"]["componentes"] for v in validos])
    comp4 = np.array([v["uniao_4_fases"]["componentes"] for v in validos])

    print()
    print("=" * 78)
    print("CONCLUSAO")
    print("=" * 78)
    print(f"n={len(validos)}  (erros={len(feitos)-len(validos)})")
    print(f"volume mediano   uniao-3 {np.median(v3):.0f} mL   uniao-4 {np.median(v4):.0f} mL")
    print(f"ganho relativo   mediana {100*np.median(ganho):.1f}%   min {100*ganho.min():.1f}%   max {100*ganho.max():.1f}%")
    print(f"dentro da faixa adulta ({baixo:.0f}-{alto:.0f} mL):")
    print(f"    uniao-3   {int(((v3>=baixo)&(v3<=alto)).sum())}/{len(validos)}")
    print(f"    uniao-4   {int(((v4>=baixo)&(v4<=alto)).sum())}/{len(validos)}")
    print(f"componentes mediana   uniao-3 {np.median(comp3):.0f}   uniao-4 {np.median(comp4):.0f}")
    print()
    if np.median(ganho) >= GATE_GANHO_MINIMO:
        print(f"GATE PASSA: quarta fase recupera {100*np.median(ganho):.1f}% a mais, mediana. "
              "Justifica adicionar a pré-contraste à união de produção.")
    else:
        print(f"GATE FALHA: quarta fase recupera só {100*np.median(ganho):.1f}% a mais, mediana "
              f"(exigido {100*GATE_GANHO_MINIMO:.0f}%). Não compensa o custo extra de GPU. "
              "Manter a união em três fases.")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
