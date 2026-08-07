#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Combina integridade hepatica (etapa barata, 321 casos) com continuidade
vascular (etapa cara, shortlist de 30) num score final, e seleciona os 10
melhores e 10 piores.

Formula pre-especificada (escrita antes de rodar este script, ou seja, antes
de ver o resultado da etapa de vasos -- mesma disciplina de gate do resto do
projeto):

    Para cada um dos ~30 candidatos da shortlist:
        score_vaso(estrutura) = media(fracao_maior_componente, 1/componentes)
                                 se presente; 0 se ausente (falha total)
        score_vasos = media(score_vaso(porta), score_vaso(cava))

    Dentro da shortlist:
        percentil_figado  = percentil (rank/n) de score_integridade_figado
        percentil_vasos   = percentil (rank/n) de score_vasos
        score_final       = media(percentil_figado, percentil_vasos)  -- 50/50

    10 melhores = maior score_final; 10 piores = menor score_final.

Uso:
    .venv-win/Scripts/python.exe tools/combine_final_liver_vessel_score.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RANKING = REPO / "experiments/liver_integrity_ranking_v1/results.json"
VASOS = REPO / "experiments/vessel_continuity_shortlist_v1/results.json"
SAIDA = REPO / "experiments/final_10_melhores_10_piores_v1"


def score_vaso(info: dict | None) -> float:
    if not info or not info.get("presente"):
        return 0.0
    comp = max(1, int(info.get("componentes", 1)))
    frac = float(info.get("fracao_maior_componente", 0.0))
    return round((frac + 1.0 / comp) / 2.0, 5)


def percentil(valor: float, todos: list[float]) -> float:
    ordenado = sorted(todos)
    n = len(ordenado)
    menores_ou_iguais = sum(1 for v in ordenado if v <= valor)
    return round(menores_ou_iguais / n, 5) if n else 0.0


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    ranking = json.loads(RANKING.read_text("utf-8"))
    vasos = json.loads(VASOS.read_text("utf-8"))

    figado_por_caso = {r["case_id"]: r for r in ranking["ranking_completo"]}
    candidatos = sorted(set(
        ranking["shortlist_melhores_case_ids"] + ranking["shortlist_piores_case_ids"]
    ))

    linhas = []
    faltando_vasos = []
    for case_id in candidatos:
        v = vasos.get(case_id)
        if not v or "erro" in v:
            faltando_vasos.append(case_id)
            continue
        sv = score_vaso(v.get("portal_vein_and_splenic_vein"))
        sc = score_vaso(v.get("inferior_vena_cava"))
        linhas.append({
            "case_id": case_id,
            "score_integridade_figado": figado_por_caso[case_id]["score_integridade_figado"],
            "score_vaso_porta": sv,
            "score_vaso_cava": sc,
            "score_vasos": round((sv + sc) / 2.0, 5),
            "figado_detalhe": figado_por_caso[case_id],
            "vasos_detalhe": v,
        })

    if faltando_vasos:
        print(f"AVISO: {len(faltando_vasos)} candidatos sem dado de vasos (excluidos): {faltando_vasos}")

    scores_figado = [r["score_integridade_figado"] for r in linhas]
    scores_vasos = [r["score_vasos"] for r in linhas]
    for r in linhas:
        p_figado = percentil(r["score_integridade_figado"], scores_figado)
        p_vasos = percentil(r["score_vasos"], scores_vasos)
        r["percentil_figado"] = p_figado
        r["percentil_vasos"] = p_vasos
        r["score_final"] = round((p_figado + p_vasos) / 2.0, 5)

    linhas.sort(key=lambda r: r["score_final"], reverse=True)
    melhores = linhas[:10]
    piores = linhas[-10:]

    print("=" * 78)
    print(f"SCORE FINAL -- {len(linhas)} candidatos avaliados (figado + vasos)")
    print("=" * 78)
    print("\n10 MELHORES:")
    for r in melhores:
        print(f"  {r['case_id']}  final={r['score_final']:.3f}  "
              f"(figado pct={r['percentil_figado']:.2f}  vasos pct={r['percentil_vasos']:.2f})")
    print("\n10 PIORES:")
    for r in piores:
        print(f"  {r['case_id']}  final={r['score_final']:.3f}  "
              f"(figado pct={r['percentil_figado']:.2f}  vasos pct={r['percentil_vasos']:.2f})")

    resultado = {
        "schema": "oren-final-liver-vessel-ranking-v1",
        "n_candidatos": len(linhas),
        "faltando_vasos": faltando_vasos,
        "10_melhores": melhores,
        "10_piores": piores,
        "todos_avaliados": linhas,
        "research_only": True,
    }
    (SAIDA / "results.json").write_text(
        json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
