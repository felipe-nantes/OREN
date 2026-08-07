#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ranqueia os 321 casos LLD-MMRI por integridade/continuidade do figado,
usando SOMENTE dados ja medidos (custo zero) em
experiments/mask_geometry_quality_v1/results.json.

docs/188 mediu, nos mesmos 321 casos, que fragmentacao (componentes),
defeito topologico (Euler), rugosidade de superficie e fracao do maior
componente formam uma SINDROME -- andam juntos, e volume baixo prediz os
quatro (Spearman rho ate -0,623, p ate 5,7e-36). Este script combina os
quatro sinais ja validados (nao inventa um novo) num score composto, para
gerar uma pre-lista de candidatos antes de qualquer segmentacao nova de
vasos (etapa cara, tools/segment_vessel_continuity_shortlist.py).

Formula pre-especificada (escrita antes de olhar o ranking resultante):
    score_figado = media de 4 percentis de "bondade" em [0,1]:
        - fracao_maior_componente        (mais perto de 1.0 = melhor)
        - 1 / componentes                (menos ilhas = melhor)
        - 1 / (1 + |euler - 1|)          (euler=1 = solido simples = melhor)
        - 1 / rugosidade_vs_esfera       (mais perto de esfera = melhor)
    penalidade: -0.15 se encosta_na_borda_z (corte de FOV, artefato de dado)
    penalidade: -0.10 se fracao_de_buraco > 0.001 (cavidade interna)

Uso:
    .venv-win/Scripts/python.exe tools/rank_liver_integrity_candidates.py --shortlist 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "experiments/mask_geometry_quality_v1/results.json"
OUT = REPO / "experiments/liver_integrity_ranking_v1"


def score_case(item: dict) -> dict:
    comp = max(1, int(item["componentes"]))
    euler = int(item["euler"])
    rug = item.get("rugosidade_vs_esfera")
    frac = float(item["fracao_maior_componente"])

    s_frac = frac
    s_comp = 1.0 / comp
    s_euler = 1.0 / (1.0 + abs(euler - 1))
    s_rug = (1.0 / rug) if (rug and rug > 0) else 0.0

    base = (s_frac + s_comp + s_euler + s_rug) / 4.0
    penalidade = 0.0
    if item.get("encosta_na_borda_z"):
        penalidade += 0.15
    if item.get("fracao_de_buraco", 0.0) > 0.001:
        penalidade += 0.10
    score = round(base - penalidade, 5)
    return {
        "score_integridade_figado": score,
        "componentes": comp,
        "euler": euler,
        "rugosidade_vs_esfera": rug,
        "fracao_maior_componente": frac,
        "volume_ml": item.get("volume_ml"),
        "encosta_na_borda_z": bool(item.get("encosta_na_borda_z")),
        "fracao_de_buraco": item.get("fracao_de_buraco"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shortlist", type=int, default=15,
                         help="quantos candidatos por lado (melhor/pior) entram na shortlist cara")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    payload = json.loads(SRC.read_text(encoding="utf-8"))
    lld = payload["lld"]

    ranked = []
    for case_id, item in lld.items():
        row = score_case(item)
        row["case_id"] = case_id
        ranked.append(row)
    ranked.sort(key=lambda r: r["score_integridade_figado"], reverse=True)

    for i, row in enumerate(ranked, 1):
        row["rank"] = i

    shortlist_melhores = ranked[: args.shortlist]
    shortlist_piores = ranked[-args.shortlist:]

    print("=" * 78)
    print(f"RANKING DE INTEGRIDADE HEPATICA -- {len(ranked)} casos (custo zero)")
    print("=" * 78)
    print("\nTOP 5 (melhores):")
    for row in ranked[:5]:
        print(f"  #{row['rank']:>3} {row['case_id']}  score {row['score_integridade_figado']:.3f}  "
              f"comp {row['componentes']} euler {row['euler']} rug {row['rugosidade_vs_esfera']} "
              f"vol {row['volume_ml']:.0f}mL")
    print("\nBOTTOM 5 (piores):")
    for row in ranked[-5:]:
        print(f"  #{row['rank']:>3} {row['case_id']}  score {row['score_integridade_figado']:.3f}  "
              f"comp {row['componentes']} euler {row['euler']} rug {row['rugosidade_vs_esfera']} "
              f"vol {row['volume_ml']:.0f}mL")

    resultado = {
        "schema": "oren-liver-integrity-ranking-v1",
        "n_total": len(ranked),
        "shortlist_size_por_lado": args.shortlist,
        "ranking_completo": ranked,
        "shortlist_melhores_case_ids": [r["case_id"] for r in shortlist_melhores],
        "shortlist_piores_case_ids": [r["case_id"] for r in shortlist_piores],
        "research_only": True,
    }
    (OUT / "results.json").write_text(
        json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nshortlist cara (proxima etapa -- vasos): "
          f"{args.shortlist} melhores + {args.shortlist} piores = {2*args.shortlist} casos")
    print(f"salvo em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
