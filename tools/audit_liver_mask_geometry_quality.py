#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Por que alguns fígados 3D ficam bons e outros ruins?

O visualizador reconstrói uma malha a partir da máscara automática. A qualidade
do que aparece na tela tem DUAS causas possíveis, e elas exigem correções
opostas:

  (A) infidelidade de reconstrução -- a malha não representa bem a máscara;
  (B) qualidade da máscara -- a máscara não representa bem o fígado.

`dtwin/viewer_artifacts.compute_mesh_metrics` já mede (A), e declara no próprio
artefato `not_segmentation_accuracy: true`. Ninguém mede (B) no fluxo, porque
não há referência humana na coorte de produção.

Este auditor ataca (B) por dois caminhos:

  1. Descreve a geometria das máscaras da coorte de produção (LLD-MMRI) com
     atributos que degradam visivelmente um render 3-D: fragmentação, buracos,
     defeitos topológicos, rugosidade de superfície, cobertura em z.

  2. Nos 20 casos do CHAOS, onde EXISTE referência humana, mede quais desses
     atributos realmente predizem baixo Dice. Isso valida quais sinais servem
     como alerta de qualidade -- em vez de escolhermos por intuição.

Uso:
    .venv-win/Scripts/python.exe tools/audit_liver_mask_geometry_quality.py
    .venv-win/Scripts/python.exe tools/audit_liver_mask_geometry_quality.py --limit 40
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage
from skimage import measure

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LLD = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
CHAOS_PRED = REPO / "experiments/total_mr_vs_chaos_v1/masks"
CHAOS_REF = REPO / "data/prepared/chaos_v21_blind"
OUT = REPO / "experiments/mask_geometry_quality_v1"


def features(mask_path: Path) -> dict | None:
    """Atributos geométricos a partir de um arquivo de máscara."""
    image = sitk.ReadImage(str(mask_path))
    return features_from_array(
        sitk.GetArrayFromImage(image) > 0,
        np.asarray(image.GetSpacing(), dtype=np.float64),
    )


def features_from_array(array: np.ndarray, spacing: np.ndarray) -> dict | None:
    """Atributos geométricos que um render 3-D expõe visualmente.

    `array` em ordem z,y,x (convenção do SimpleITK->numpy); `spacing` em x,y,z.
    """
    array = np.asarray(array, dtype=bool)
    voxels = int(array.sum())
    if voxels == 0:
        return None
    voxel_ml = float(np.prod(spacing)) / 1000.0
    volume_ml = voxels * voxel_ml

    # Fragmentação: componentes soltos viram "ilhas" flutuando no visualizador.
    labelled, n_components = ndimage.label(array)
    sizes = np.bincount(labelled.ravel())[1:]
    largest_fraction = float(sizes.max() / sizes.sum()) if sizes.size else 0.0

    # Buracos internos: aparecem como cavidades/transparências na malha.
    filled = ndimage.binary_fill_holes(array)
    hole_voxels = int(filled.sum() - voxels)

    # Defeitos topológicos: alças e túneis produzem geometria impossível para um
    # órgão. Euler = 1 para um sólido simples sem alças nem cavidades.
    try:
        euler = int(measure.euler_number(array, connectivity=1))
    except Exception:
        euler = 0

    # Rugosidade: razão entre a área real e a de uma esfera do mesmo volume.
    # 1,0 = esfera perfeita. Quanto maior, mais recortada/serrilhada a superfície.
    try:
        verts, faces, _, _ = measure.marching_cubes(
            array.astype(np.uint8), level=0.5, spacing=(spacing[2], spacing[1], spacing[0])
        )
        area_mm2 = float(measure.mesh_surface_area(verts, faces))
    except Exception:
        area_mm2 = float("nan")
    volume_mm3 = volume_ml * 1000.0
    esfera = (36.0 * math.pi * volume_mm3 ** 2) ** (1.0 / 3.0)
    rugosidade = float(area_mm2 / esfera) if esfera > 0 and np.isfinite(area_mm2) else float("nan")

    z_indices = np.flatnonzero(array.any(axis=(1, 2)))
    z_slices = int(z_indices.size)
    z_extent_mm = float(z_slices * spacing[2])
    touches_border = bool(
        z_indices.size and (z_indices.min() == 0 or z_indices.max() == array.shape[0] - 1)
    )
    anisotropy = float(spacing[2] / min(spacing[0], spacing[1]))

    return {
        "volume_ml": round(volume_ml, 1),
        "componentes": int(n_components),
        "fracao_maior_componente": round(largest_fraction, 4),
        "voxels_de_buraco": hole_voxels,
        "fracao_de_buraco": round(hole_voxels / max(voxels, 1), 5),
        "euler": euler,
        "rugosidade_vs_esfera": round(rugosidade, 3) if np.isfinite(rugosidade) else None,
        "cortes_em_z": z_slices,
        "extensao_z_mm": round(z_extent_mm, 1),
        "encosta_na_borda_z": touches_border,
        "anisotropia": round(anisotropy, 2),
        "espacamento_mm": [round(float(v), 3) for v in spacing],
    }


def dice(a: np.ndarray, b: np.ndarray) -> float:
    total = int(a.sum()) + int(b.sum())
    return 2.0 * float((a & b).sum()) / total if total else 0.0


def percentis(values: list[float], rotulo: str) -> str:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return f"  {rotulo:<28} (sem dados)"
    return (f"  {rotulo:<28} p10 {np.percentile(arr,10):>8.2f} | mediana "
            f"{np.median(arr):>8.2f} | p90 {np.percentile(arr,90):>8.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("GEOMETRIA DAS MASCARAS — o que faz um figado 3D ficar bom ou ruim")
    print("=" * 78)

    # ---------------- coorte de producao (sem referencia humana) -------------
    lld_paths = sorted(LLD.rglob("liver_mask_venous.nii.gz"))
    if args.limit:
        lld_paths = lld_paths[: args.limit]
    lld: dict[str, dict] = {}
    print(f"\nLLD-MMRI (producao): {len(lld_paths)} mascaras")
    for i, path in enumerate(lld_paths, 1):
        item = features(path)
        if item is not None:
            lld[path.parent.name] = item
        if i % 80 == 0 or i == len(lld_paths):
            print(f"  {i}/{len(lld_paths)}", flush=True)

    if lld:
        print()
        print("  distribuicao dos atributos:")
        for chave, rotulo in (
            ("volume_ml", "volume (mL)"),
            ("componentes", "componentes conexos"),
            ("fracao_de_buraco", "fracao de buracos"),
            ("euler", "caracteristica de Euler"),
            ("rugosidade_vs_esfera", "rugosidade (1,0=esfera)"),
            ("cortes_em_z", "cortes em z"),
            ("anisotropia", "anisotropia z/xy"),
        ):
            print(percentis([v[chave] for v in lld.values()], rotulo))
        n = len(lld)
        frag = sum(1 for v in lld.values() if v["componentes"] > 1)
        alcas = sum(1 for v in lld.values() if v["euler"] != 1)
        buraco = sum(1 for v in lld.values() if v["fracao_de_buraco"] > 0.001)
        poucos = sum(1 for v in lld.values() if v["cortes_em_z"] < 25)
        borda = sum(1 for v in lld.values() if v["encosta_na_borda_z"])
        print()
        print(f"  fragmentadas (>1 componente)     : {frag:>4}/{n}  ({100*frag/n:.0f}%)")
        print(f"  com defeito topologico (Euler!=1): {alcas:>4}/{n}  ({100*alcas/n:.0f}%)")
        print(f"  com buracos internos (>0,1%)     : {buraco:>4}/{n}  ({100*buraco/n:.0f}%)")
        print(f"  com menos de 25 cortes em z      : {poucos:>4}/{n}  ({100*poucos/n:.0f}%)")
        print(f"  encostando na borda em z         : {borda:>4}/{n}  ({100*borda/n:.0f}%)")

    # ---------------- CHAOS: qual atributo PREDIZ baixo Dice? ---------------
    print()
    print("-" * 78)
    print("CHAOS — quais atributos realmente predizem erro (referencia humana)")
    print("-" * 78)
    linhas = []
    for pred_path in sorted(CHAOS_PRED.glob("*.nii.gz")):
        case_id = pred_path.name.replace(".nii.gz", "")
        ref_path = CHAOS_REF / case_id / "liver_mask.nii.gz"
        if not ref_path.is_file():
            continue
        pred_image = sitk.ReadImage(str(pred_path))
        pred = sitk.GetArrayFromImage(pred_image) > 0
        ref = sitk.GetArrayFromImage(sitk.ReadImage(str(ref_path))) > 0
        if pred.shape != ref.shape:
            continue
        item = features_from_array(
            pred, np.asarray(pred_image.GetSpacing(), dtype=np.float64)
        )
        if item is None:
            continue
        item["dice"] = round(dice(pred, ref), 4)
        item["case_id"] = case_id
        linhas.append(item)

    if linhas:
        print(f"\n  n={len(linhas)}   Dice mediano {np.median([l['dice'] for l in linhas]):.3f}")
        print("\n  correlacao de cada atributo com o Dice (Spearman):")
        from scipy.stats import spearmanr
        dices = [l["dice"] for l in linhas]
        for chave in ("volume_ml", "componentes", "fracao_maior_componente",
                      "fracao_de_buraco", "euler", "rugosidade_vs_esfera",
                      "cortes_em_z", "anisotropia"):
            valores = [l[chave] for l in linhas]
            valores = [float(v) if v is not None else np.nan for v in valores]
            if len(set(valores)) < 2 or not np.all(np.isfinite(valores)):
                print(f"    {chave:<26} (constante ou invalido)")
                continue
            rho, p = spearmanr(valores, dices)
            marca = "  <== forte" if abs(rho) >= 0.6 and p < 0.05 else ""
            print(f"    {chave:<26} rho {rho:+.3f}   p {p:.4f}{marca}")

        print("\n  piores e melhores por Dice:")
        for row in sorted(linhas, key=lambda r: r["dice"])[:3]:
            print(f"    PIOR  dice {row['dice']:.3f}  vol {row['volume_ml']:>7.0f} mL  "
                  f"comp {row['componentes']}  rug {row['rugosidade_vs_esfera']}  euler {row['euler']}")
        for row in sorted(linhas, key=lambda r: -r["dice"])[:3]:
            print(f"    MELHOR dice {row['dice']:.3f}  vol {row['volume_ml']:>7.0f} mL  "
                  f"comp {row['componentes']}  rug {row['rugosidade_vs_esfera']}  euler {row['euler']}")

    payload = {
        "schema": "oren-mask-geometry-quality-v1",
        "lld": lld,
        "chaos": linhas,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (OUT / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nsalvo em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
