#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A fase pré-contraste recupera mais fígado que a venosa?

Cadeia de evidência que motiva este piloto:

  docs/176  o segmentador atinge Dice 0,908 contra anotação humana em T1 SEM
            contraste (CHAOS), e degrada na fase venosa COM contraste;
  docs/165  no MESMO exame: arterial 122 mL, venosa 486, tardia 607;
  docs/188  volume baixo é o mesmo caso fragmentado e rugoso -- uma síndrome só.

O pipeline segmenta na VENOSA, que é justamente a condição ruim. O LLD-MMRI traz
`t1_native` (pré-contraste) em 321/321 casos -- ou seja, a condição em que o
modelo é validado está disponível e nunca foi usada.

Este piloto mede, nos mesmos pacientes: quanto de órgão a pré-contraste recupera
sobre a venosa, e se a máscara sai geometricamente utilizável.

NÃO altera nada do pipeline. É medição.

Uso:
    .venv-win/Scripts/python.exe tools/pilot_precontrast_liver_segmentation.py --limit 12
"""
from __future__ import annotations

import argparse
import json
import random
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

ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
SAIDA = REPO / "experiments/precontrast_segmentation_v1"
FAIXA_ADULTO_ML = (900.0, 2400.0)


def geometria_igual(a: sitk.Image, b: sitk.Image, tol: float = 1e-4) -> bool:
    return (
        a.GetSize() == b.GetSize()
        and np.allclose(a.GetSpacing(), b.GetSpacing(), atol=tol)
        and np.allclose(a.GetOrigin(), b.GetOrigin(), atol=1e-2)
        and np.allclose(a.GetDirection(), b.GetDirection(), atol=tol)
    )


def descreve(mask: np.ndarray, spacing) -> dict:
    voxels = int(mask.sum())
    volume = voxels * float(np.prod(spacing)) / 1000.0
    rotulos, n = ndimage.label(mask)
    if n:
        tamanhos = np.bincount(rotulos.ravel())[1:]
        fracao = float(tamanhos.max() / tamanhos.sum())
    else:
        fracao = 0.0
    z = np.flatnonzero(mask.any(axis=(1, 2)))
    return {
        "volume_ml": round(volume, 1),
        "componentes": int(n),
        "fracao_componente_principal": round(fracao, 4),
        "cortes_em_z": int(z.size),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks").mkdir(exist_ok=True)
    destino = SAIDA / "results.json"
    feitos = json.loads(destino.read_text("utf-8")) if destino.is_file() else {}

    casos = sorted(d.name for d in ENTRADAS.iterdir() if d.is_dir())
    random.seed(20260805)
    casos = random.sample(casos, min(args.limit, len(casos)))

    print("=" * 78)
    print("PRE-CONTRASTE vs VENOSA — quanto de figado a fase certa recupera")
    print("=" * 78)
    print(f"casos: {len(casos)}\n")

    for i, case_id in enumerate(casos, 1):
        if case_id in feitos:
            continue
        nativa = ENTRADAS / case_id / "t1_native.nii.gz"
        venosa_mask = VENOSA / case_id / "liver_mask_venous.nii.gz"
        venosa_img = ENTRADAS / case_id / "t1_venous.nii.gz"
        if not (nativa.is_file() and venosa_mask.is_file() and venosa_img.is_file()):
            continue
        print(f"[{i}/{len(casos)}] {case_id}", flush=True)
        predita = SAIDA / "masks" / f"{case_id}.nii.gz"
        if not predita.is_file():
            try:
                isolated_total_mr_liver_segmenter(
                    nativa, predita, device="gpu", fast=False, timeout_seconds=600
                )
            except Exception as exc:  # noqa: BLE001
                feitos[case_id] = {"erro": f"{type(exc).__name__}: {exc}"}
                destino.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
                print(f"    falhou: {exc}", flush=True)
                continue

        img_nativa = sitk.ReadImage(str(nativa))
        img_venosa = sitk.ReadImage(str(venosa_img))
        pre = sitk.GetArrayFromImage(sitk.ReadImage(str(predita))) > 0
        ven = sitk.GetArrayFromImage(sitk.ReadImage(str(venosa_mask))) > 0

        registro = {
            "pre_contraste": descreve(pre, img_nativa.GetSpacing()),
            "venosa": descreve(ven, sitk.ReadImage(str(venosa_mask)).GetSpacing()),
            "grades_iguais_native_vs_venous": bool(geometria_igual(img_nativa, img_venosa)),
        }
        pv_, vv = registro["pre_contraste"]["volume_ml"], registro["venosa"]["volume_ml"]
        registro["razao_pre_sobre_venosa"] = round(pv_ / vv, 3) if vv else None
        feitos[case_id] = registro
        destino.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
        print(f"    venosa {vv:>7.0f} mL  ->  pre-contraste {pv_:>7.0f} mL"
              f"   ({registro['razao_pre_sobre_venosa']}x)", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if not validos:
        print("\nnenhum caso valido.")
        return 1

    pre = np.array([v["pre_contraste"]["volume_ml"] for v in validos])
    ven = np.array([v["venosa"]["volume_ml"] for v in validos])
    razao = pre / np.where(ven > 0, ven, np.nan)
    baixo, alto = FAIXA_ADULTO_ML

    print()
    print("-" * 78)
    print(f"RESULTADO  (n={len(validos)}, erros={len(feitos)-len(validos)})")
    print("-" * 78)
    print(f"  volume mediano   venosa {np.median(ven):>7.0f} mL"
          f"   pre-contraste {np.median(pre):>7.0f} mL")
    print(f"  razao pre/venosa mediana {np.nanmedian(razao):.2f}x"
          f"   min {np.nanmin(razao):.2f}   max {np.nanmax(razao):.2f}")
    print(f"  dentro da faixa adulta ({baixo:.0f}-{alto:.0f} mL):")
    print(f"      venosa        {int(((ven>=baixo)&(ven<=alto)).sum())}/{len(validos)}")
    print(f"      pre-contraste {int(((pre>=baixo)&(pre<=alto)).sum())}/{len(validos)}")
    comp_pre = np.array([v["pre_contraste"]["componentes"] for v in validos])
    comp_ven = np.array([v["venosa"]["componentes"] for v in validos])
    print(f"  componentes mediana   venosa {np.median(comp_ven):.0f}"
          f"   pre-contraste {np.median(comp_pre):.0f}")
    mesmas = sum(1 for v in validos if v["grades_iguais_native_vs_venous"])
    print(f"  grade da pre-contraste identica a' da venosa: {mesmas}/{len(validos)}")
    if mesmas < len(validos):
        print("      (onde diferir, a mascara precisa ser reamostrada para a grade venosa)")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
