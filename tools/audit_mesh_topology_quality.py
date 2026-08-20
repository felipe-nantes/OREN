#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quanto da patologia da máscara sobrevive até a malha que aparece na tela?

docs/188 mediu que 84% das máscaras de produção têm Euler != 1 e 75% estão
fragmentadas. Mas essa medição foi na máscara BINÁRIA, e a malha não vem dela
diretamente: vem do campo de distância reamostrado em 0,8 mm e suavizado com
gaussiana de sigma 2,0 mm (docs/165). Suavizar fecha túneis finos.

Ou seja, a patologia da máscara pode nunca chegar à tela -- ou pode chegar
inteira. Isso decide se vale gastar esforço em reparo topológico, e por isso é o
passo 1 do plano de docs/188 §6.

Compara, com a MESMA reconstrução de produção:

  refino_atual   = _refine_mask (o que roda hoje)
  proposto       = _refine_mask + maior componente (com guarda 0,90) + buracos

Uso:
    .venv-win/Scripts/python.exe tools/audit_mesh_topology_quality.py --limit 30
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

from dtwin.stages import _mesh_from_mask, _refine_mask

LLD = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
OUT = REPO / "experiments/mesh_topology_quality_v1"

# Parâmetros idênticos a profiles/figado.yaml -> mesh
MESH = dict(level=0.5, smooth_iter=30, feature_angle=60.0, pass_band=0.1,
            isotropic_mm=0.8, gaussian_sigma_mm=2.0, max_triangles=160000)
GUARDA_MAIOR_COMPONENTE = 0.90  # mesmo limiar do gate de pesquisa


def maior_componente_com_guarda(mask: np.ndarray) -> tuple[np.ndarray, bool, float]:
    """Isola o maior componente SÓ quando ele domina a máscara.

    Abaixo da guarda o fígado está partido em pedaços grandes, e isolar apagaria
    órgão de verdade -- em um caso da coorte, 47%. Nesse regime a fragmentação é
    sintoma de segmentação ruim, não detrito a esconder.
    """
    rotulos, n = ndimage.label(mask)
    if n <= 1:
        return mask, False, 1.0
    tamanhos = np.bincount(rotulos.ravel())[1:]
    fracao = float(tamanhos.max() / tamanhos.sum())
    if fracao < GUARDA_MAIOR_COMPONENTE:
        return mask, False, fracao
    return rotulos == (int(np.argmax(tamanhos)) + 1), True, fracao


def metricas_da_malha(mesh) -> dict:
    if mesh is None:
        return {"falhou": True}
    borda = mesh.extract_feature_edges(
        boundary_edges=True, non_manifold_edges=True,
        feature_edges=False, manifold_edges=False,
    )
    corpos = mesh.split_bodies()
    area_mm2 = float(mesh.area)
    volume_mm3 = abs(float(mesh.volume))
    esfera = (36.0 * np.pi * volume_mm3 ** 2) ** (1.0 / 3.0) if volume_mm3 > 0 else 0.0
    return {
        "falhou": False,
        "volume_ml": round(volume_mm3 / 1000.0, 1),
        "triangulos": int(mesh.n_cells),
        "arestas_de_borda": int(borda.n_cells),
        "estanque_e_manifold": bool(borda.n_cells == 0),
        "corpos": int(len(corpos)),
        "rugosidade_vs_esfera": round(area_mm2 / esfera, 3) if esfera > 0 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    caminhos = sorted(LLD.rglob("liver_mask_venous.nii.gz"))
    random.seed(20260805)
    caminhos = random.sample(caminhos, min(args.limit, len(caminhos)))

    print("=" * 78)
    print("TOPOLOGIA DA MALHA FINAL — o que de fato chega à tela")
    print("=" * 78)
    print(f"reconstrução: isotrópico {MESH['isotropic_mm']} mm, sigma "
          f"{MESH['gaussian_sigma_mm']} mm, Taubin {MESH['smooth_iter']}x")
    print(f"casos: {len(caminhos)}\n")

    linhas = []
    temporario = OUT / "_tmp_mask.nii.gz"
    for i, caminho in enumerate(caminhos, 1):
        imagem = sitk.ReadImage(str(caminho))
        bruta = sitk.GetArrayFromImage(imagem) > 0
        if not bruta.any():
            continue

        atual = _refine_mask(bruta, True, 2, 300).astype(bool)
        isolado, aplicou, fracao = maior_componente_com_guarda(atual)
        proposto = ndimage.binary_fill_holes(isolado)

        registro = {"case_id": caminho.parent.name,
                    "fracao_maior_componente": round(fracao, 4),
                    "guarda_permitiu_isolar": aplicou}
        for nome, arranjo in (("refino_atual", atual), ("proposto", proposto)):
            saida = sitk.GetImageFromArray(arranjo.astype(np.uint8))
            saida.CopyInformation(imagem)
            sitk.WriteImage(saida, str(temporario))
            try:
                malha = _mesh_from_mask(
                    temporario, MESH["level"], MESH["smooth_iter"],
                    MESH["feature_angle"], pass_band=MESH["pass_band"],
                    isotropic_mm=MESH["isotropic_mm"],
                    gaussian_sigma_mm=MESH["gaussian_sigma_mm"],
                    max_triangles=MESH["max_triangles"],
                )
                registro[nome] = metricas_da_malha(malha)
            except Exception as exc:
                registro[nome] = {"falhou": True, "erro": f"{type(exc).__name__}: {exc}"}
        linhas.append(registro)
        if i % 5 == 0 or i == len(caminhos):
            print(f"  {i}/{len(caminhos)}", flush=True)
    temporario.unlink(missing_ok=True)

    def resumo(chave: str) -> None:
        validos = [r[chave] for r in linhas if not r[chave].get("falhou")]
        if not validos:
            print(f"  {chave:<16} (nenhuma malha gerada)")
            return
        n = len(validos)
        estanques = sum(1 for v in validos if v["estanque_e_manifold"])
        unico = sum(1 for v in validos if v["corpos"] == 1)
        rug = [v["rugosidade_vs_esfera"] for v in validos if v["rugosidade_vs_esfera"]]
        print(f"  {chave:<16} n={n:<4} estanque {100*estanques/n:>3.0f}%  "
              f"corpo único {100*unico/n:>3.0f}%  "
              f"corpos mediana {np.median([v['corpos'] for v in validos]):>4.0f}  "
              f"rugosidade {np.median(rug):.2f}")

    print()
    print("-" * 78)
    print("RESULTADO — malha final")
    print("-" * 78)
    resumo("refino_atual")
    resumo("proposto")

    # Três situações distintas -- confundi-las faz o relatório dizer que há
    # fígados partidos onde só havia máscara já limpa.
    unico = [r for r in linhas if r["fracao_maior_componente"] >= 0.9999]
    isolou = [r for r in linhas if r["guarda_permitiu_isolar"]]
    bloqueado = [r for r in linhas
                 if r["fracao_maior_componente"] < GUARDA_MAIOR_COMPONENTE]
    print()
    print("  o que a limpeza fez, caso a caso:")
    print(f"    já era componente único (nada a isolar) : {len(unico)}/{len(linhas)}")
    print(f"    guarda PERMITIU isolar (fração ≥ {GUARDA_MAIOR_COMPONENTE:.2f}) : {len(isolou)}/{len(linhas)}")
    print(f"    guarda BLOQUEOU — fígado partido         : {len(bloqueado)}/{len(linhas)}")
    for r in bloqueado[:5]:
        print(f"      {r['case_id']}  fração do maior componente {r['fracao_maior_componente']:.3f}")

    def corpo_unico(chave: str, subconjunto: list[dict]) -> str:
        validos = [r[chave] for r in subconjunto if not r[chave].get("falhou")]
        if not validos:
            return "sem casos"
        pct = 100.0 * sum(1 for v in validos if v["corpos"] == 1) / len(validos)
        return f"{pct:.0f}% de corpo único (n={len(validos)})"

    if isolou:
        print()
        print("  efeito medido SÓ onde a limpeza agiu:")
        print(f"    antes  : {corpo_unico('refino_atual', isolou)}")
        print(f"    depois : {corpo_unico('proposto', isolou)}")

    (OUT / "results.json").write_text(
        json.dumps({"schema": "oren-mesh-topology-quality-v1",
                    "parametros_malha": MESH,
                    "guarda_maior_componente": GUARDA_MAIOR_COMPONENTE,
                    "casos": linhas,
                    "research_only": True, "clinical_use_allowed": False},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\nsalvo em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
