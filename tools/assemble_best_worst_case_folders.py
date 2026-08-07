#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monta as pastas '10_melhores' e '10_piores' a partir de
experiments/final_10_melhores_10_piores_v1/results.json.

Para cada caso selecionado, copia:
  - mask_organ_venosa.nii.gz  (mascara venosa original, base da metrica de
    integridade hepatica)
  - mask_vessel_liver_total_mr.nii.gz  (figado re-segmentado junto com os
    vasos, mesma chamada -- referencia de consistencia)
  - mask_vessel_portal_esplenica.nii.gz
  - mask_vessel_cava_inferior.nii.gz
  - scorecard.json  (todas as metricas e o score final deste caso)

Saida (gitignorada, casos/ nunca vai para o repositorio):
    casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1/

Uso:
    .venv-win/Scripts/python.exe tools/assemble_best_worst_case_folders.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINAL = REPO / "experiments/final_10_melhores_10_piores_v1/results.json"
VENOSA_DIR = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
VASOS_DIR = REPO / "experiments/vessel_continuity_shortlist_v1/masks"
SAIDA = REPO / "casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1"

CRITERIO = (
    "Criterio: score_final = media(percentil_de_integridade_hepatica, "
    "percentil_de_continuidade_vascular), calculado sobre uma shortlist de 30 "
    "candidatos (15 melhores + 15 piores por integridade hepatica isolada, "
    "escolhidos a custo zero a partir de experiments/mask_geometry_quality_v1). "
    "Integridade hepatica combina fracao do maior componente, numero de "
    "componentes conexos, caracteristica de Euler e rugosidade de superficie "
    "(docs/188: estes quatro sinais formam uma sindrome, nao problemas "
    "independentes). Continuidade vascular usa os mesmos dois sinais "
    "(fragmentacao e fracao do maior componente) aplicados a veia "
    "porta/esplenica e veia cava inferior, segmentadas via TotalSegmentator "
    "total_mr na fase venosa. research_only=True; nao usar para decisao clinica."
)


def montar_grupo(nome: str, linhas: list[dict]) -> None:
    pasta = SAIDA / nome
    pasta.mkdir(parents=True, exist_ok=True)
    for r in linhas:
        case_id = r["case_id"]
        destino = pasta / case_id
        destino.mkdir(parents=True, exist_ok=True)

        venosa_src = VENOSA_DIR / case_id / "liver_mask_venous.nii.gz"
        if venosa_src.is_file():
            shutil.copyfile(venosa_src, destino / "mask_organ_venosa.nii.gz")

        for sufixo, alvo in (
            ("_liver.nii.gz", "mask_vessel_liver_total_mr.nii.gz"),
            ("_portal_vein_and_splenic_vein.nii.gz", "mask_vessel_portal_esplenica.nii.gz"),
            ("_inferior_vena_cava.nii.gz", "mask_vessel_cava_inferior.nii.gz"),
        ):
            src = VASOS_DIR / f"{case_id}{sufixo}"
            if src.is_file():
                shutil.copyfile(src, destino / alvo)

        (destino / "scorecard.json").write_text(
            json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    print(f"  {nome}: {len(linhas)} casos em {pasta}")


def main() -> int:
    dados = json.loads(FINAL.read_text("utf-8"))
    SAIDA.mkdir(parents=True, exist_ok=True)

    montar_grupo("10_melhores", dados["10_melhores"])
    montar_grupo("10_piores", dados["10_piores"])

    resumo = {
        "schema": "oren-analise-10-melhores-10-piores-v1",
        "criterio": CRITERIO,
        "10_melhores_case_ids": [r["case_id"] for r in dados["10_melhores"]],
        "10_piores_case_ids": [r["case_id"] for r in dados["10_piores"]],
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (SAIDA / "LEIA-ME.json").write_text(
        json.dumps(resumo, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nresumo salvo em {SAIDA / 'LEIA-ME.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
