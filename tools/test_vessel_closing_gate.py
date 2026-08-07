#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 3 do plano de fragmentacao: mede se um fechamento morfologico pequeno
reconecta pedacos de veia porta/esplenica e veia cava inferior sem inflar
volume, usando as 30 mascaras de vaso ja segmentadas (custo zero de GPU) em
experiments/vessel_continuity_shortlist_v1/masks/.

GATE PRE-ESPECIFICADO (escrito ANTES de rodar, nao ajustar depois de ver o
resultado):
  So considerar implementar em producao se, para pelo menos uma estrutura
  (porta/esplenica OU cava):
    (a) mediana de fracao_componente_principal sobe pelo menos +0.05 absoluto
    (b) mediana de inflacao de volume fica abaixo de 5%
    (c) NENHUM caso individual infla volume acima de 15% (protecao contra
        fusão de estruturas nao relacionadas)
  Falhando qualquer um dos tres, documentar como negativo -- nao implementar.

Uso:
    .venv-win/Scripts/python.exe tools/test_vessel_closing_gate.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

from dtwin.core import array_from, read_image  # noqa: E402
from dtwin.stages import _isolar_orgao_para_visualizacao, _refine_mask  # noqa: E402

MASKS = REPO / "experiments/vessel_continuity_shortlist_v1/masks"
SAIDA = REPO / "experiments/vessel_closing_gate_v1"

GATE_GANHO_FRACAO_MINIMO = 0.05
GATE_INFLACAO_MEDIANA_MAXIMA = 0.05
GATE_INFLACAO_CASO_MAXIMA = 0.15
RAIOS_MM = (1.0, 2.0, 3.0)


def mede_estrutura(sufixo: str, nome: str) -> dict:
    arquivos = sorted(MASKS.glob(f"*_{sufixo}.nii.gz"))
    linhas = []
    for f in arquivos:
        case_id = f.name.removesuffix(f"_{sufixo}.nii.gz")
        imagem = read_image(f)
        bruta = array_from(imagem) > 0
        if bruta.sum() == 0:
            continue
        refinada = _refine_mask(bruta, False, 1, 20).astype(bool)
        if refinada.sum() == 0:
            continue
        spacing = np.array(imagem.GetSpacing())
        voxel_ml = float(np.prod(spacing)) / 1000.0
        volume_base = float(refinada.sum()) * voxel_ml
        _, diag_base = _isolar_orgao_para_visualizacao(refinada.copy(), fracao_minima=1.01)

        linha = {"case_id": case_id, "fracao_base": diag_base["fracao_componente_principal"],
                 "componentes_base": diag_base["componentes"], "volume_base_ml": round(volume_base, 2)}
        for raio_mm in RAIOS_MM:
            estrutura = ndimage.generate_binary_structure(3, 1)
            iteracoes = int(max(1, round(raio_mm / float(np.mean(spacing)))))
            fechada = ndimage.binary_closing(refinada, structure=estrutura, iterations=iteracoes)
            volume_fechado = float(fechada.sum()) * voxel_ml
            inflacao = (volume_fechado - volume_base) / volume_base if volume_base > 0 else 0.0
            _, diag = _isolar_orgao_para_visualizacao(fechada.copy(), fracao_minima=1.01)
            linha[f"fracao_r{raio_mm:.0f}"] = diag["fracao_componente_principal"]
            linha[f"inflacao_r{raio_mm:.0f}"] = round(inflacao, 4)
        linhas.append(linha)

    print(f"\n{'='*78}\n{nome} (n={len(linhas)})\n{'='*78}")
    fracao_base = np.array([l["fracao_base"] for l in linhas])
    print(f"fracao base: mediana={np.median(fracao_base):.4f}")
    resultado_raios = {}
    for raio_mm in RAIOS_MM:
        fracoes = np.array([l[f"fracao_r{raio_mm:.0f}"] for l in linhas])
        inflacoes = np.array([l[f"inflacao_r{raio_mm:.0f}"] for l in linhas])
        ganho = np.median(fracoes) - np.median(fracao_base)
        passou = (ganho >= GATE_GANHO_FRACAO_MINIMO
                  and np.median(inflacoes) < GATE_INFLACAO_MEDIANA_MAXIMA
                  and inflacoes.max() < GATE_INFLACAO_CASO_MAXIMA)
        print(f"raio~{raio_mm:.0f}mm: fracao mediana={np.median(fracoes):.4f} (ganho {ganho:+.4f})  "
              f"inflacao mediana={100*np.median(inflacoes):.1f}%  inflacao max={100*inflacoes.max():.1f}%  "
              f"{'PASSOU' if passou else 'reprovado'}")
        resultado_raios[raio_mm] = passou
    return {"nome": nome, "n": len(linhas), "linhas": linhas, "gate_por_raio": resultado_raios}


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print("FASE 3 -- fechamento morfologico em vasos (custo zero, mascaras ja segmentadas)")
    print(f"gate: ganho mediano de fracao >= {GATE_GANHO_FRACAO_MINIMO}, "
          f"inflacao mediana < {100*GATE_INFLACAO_MEDIANA_MAXIMA:.0f}%, "
          f"inflacao maxima por caso < {100*GATE_INFLACAO_CASO_MAXIMA:.0f}%")

    resultados = {
        "portal_esplenica": mede_estrutura("portal_vein_and_splenic_vein", "VEIA PORTA/ESPLENICA"),
        "cava_inferior": mede_estrutura("inferior_vena_cava", "VEIA CAVA INFERIOR"),
    }

    algum_passou = any(v for r in resultados.values() for v in r["gate_por_raio"].values())
    print(f"\n{'='*78}\nCONCLUSAO\n{'='*78}")
    if algum_passou:
        print("GATE PASSA em pelo menos uma estrutura/raio -- considerar implementar em producao.")
    else:
        print("GATE FALHA em todas as estruturas e raios testados -- fechamento morfologico nao "
              "melhora continuidade vascular o suficiente para justificar o codigo novo. "
              "Documentar como negativo.")

    (SAIDA / "results.json").write_text(
        json.dumps(resultados, indent=1, ensure_ascii=False, default=bool), encoding="utf-8"
    )
    print(f"\nsalvo em {SAIDA / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
