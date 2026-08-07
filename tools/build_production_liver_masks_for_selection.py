#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 1 do plano de fragmentacao: mede o que realmente sobra depois das
mitigacoes que JA existem em producao, nos 20 casos selecionados como
melhores/piores.

A galeria original (tools/render_best_worst_gallery.py, primeira versao)
montou o figado direto da mascara venosa crua via _mesh_from_mask, pulando
tres coisas que rodam para todo caso real (dtwin/stages.py:stage5_refine):

  1. uniao de fases (_fonte_da_malha_do_orgao + webapp._build_union_liver_mask)
  2. _refine_mask (abertura + remove_small_objects)
  3. _isolar_orgao_para_visualizacao (guarda: so isola o componente principal
     quando ele ja domina >=90% da massa; docs/188, commit b52c87e)

Este script reproduz a SEQUENCIA EXATA de producao para os 20 casos, e grava:
  - mask_organ_clean_producao.nii.gz  (o que de fato vira malha em producao)
  - diagnostico_producao.json         (uniao incluida? guarda isolou? por que?)

Uso:
    .venv-win/Scripts/python.exe tools/build_production_liver_masks_for_selection.py
"""
from __future__ import annotations

import json
import shutil
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import SimpleITK as sitk  # noqa: E402

from dtwin.core import Case, array_from, array_to_image, read_image, save_image  # noqa: E402
from dtwin.stages import _fonte_da_malha_do_orgao, _isolar_orgao_para_visualizacao, _refine_mask  # noqa: E402
from webapp.server import _build_union_liver_mask  # noqa: E402
from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED  # noqa: E402

SELECAO = REPO / "casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
WORK = REPO / "experiments/best_worst_gallery_v1/_work"


def processa_caso(grupo: str, pasta_caso: Path) -> dict:
    case_id = pasta_caso.name
    venosa_src = pasta_caso / "mask_organ_venosa.nii.gz"
    if not venosa_src.is_file():
        return {"erro": "mask_organ_venosa ausente"}

    case_dir = WORK / grupo / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    shutil.copyfile(venosa_src, case_dir / "mask_organ.nii.gz")

    arterial_src = ENTRADAS / case_id / "t1_arterial.nii.gz"
    delayed_src = ENTRADAS / case_id / "t1_delayed.nii.gz"
    uniao_info = _build_union_liver_mask(
        case_dir, {ARTERIAL: arterial_src, DELAYED: delayed_src}
    )

    fonte = _fonte_da_malha_do_orgao(Case(root=case_dir))
    imagem = read_image(fonte)
    bruta = array_from(imagem) > 0
    volume_bruto_ml = float(bruta.sum()) * float(np.prod(imagem.GetSpacing())) / 1000.0

    limpo = _refine_mask(bruta, True, 2, 300).astype(bool)
    limpo, diagnostico = _isolar_orgao_para_visualizacao(limpo)
    volume_limpo_ml = float(limpo.sum()) * float(np.prod(imagem.GetSpacing())) / 1000.0

    saida = array_to_image(limpo.astype(np.uint8), imagem, np.uint8)
    save_image(saida, pasta_caso / "mask_organ_clean_producao.nii.gz")

    resultado = {
        "case_id": case_id,
        "grupo": grupo,
        "uniao_status": uniao_info.get("status"),
        "uniao_fases_incluidas": uniao_info.get("phases_included"),
        "uniao_fases_falhas": uniao_info.get("phase_failures"),
        "fonte_usada": fonte.name,
        "volume_bruto_ml": round(volume_bruto_ml, 1),
        "volume_apos_refino_e_guarda_ml": round(volume_limpo_ml, 1),
        "diagnostico_guarda": diagnostico,
    }
    (pasta_caso / "diagnostico_producao.json").write_text(
        json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    shutil.rmtree(case_dir, ignore_errors=True)
    return resultado


def main() -> int:
    resultados = []
    grupos = [("10_melhores", SELECAO / "10_melhores"), ("10_piores", SELECAO / "10_piores")]
    casos = [(g, p) for g, pasta in grupos for p in sorted(pasta.iterdir()) if p.is_dir()]

    print(f"FASE 1 -- reproduzindo o caminho real de producao em {len(casos)} casos\n")
    for i, (grupo, pasta_caso) in enumerate(casos, 1):
        diag_existente = pasta_caso / "diagnostico_producao.json"
        if diag_existente.is_file():
            print(f"[{i}/{len(casos)}] {grupo}/{pasta_caso.name}: ja feito, pulando", flush=True)
            resultados.append(json.loads(diag_existente.read_text("utf-8")))
            continue
        print(f"[{i}/{len(casos)}] {grupo}/{pasta_caso.name}", flush=True)
        try:
            r = processa_caso(grupo, pasta_caso)
        except Exception as exc:  # noqa: BLE001
            r = {"case_id": pasta_caso.name, "grupo": grupo, "erro": str(exc)}
            print(f"    falhou: {exc}", flush=True)
        else:
            d = r.get("diagnostico_guarda", {})
            print(f"    uniao={r.get('uniao_status')} fases={r.get('uniao_fases_incluidas')}  "
                  f"vol {r.get('volume_bruto_ml')} -> {r.get('volume_apos_refino_e_guarda_ml')} mL  "
                  f"isolado={d.get('isolado')} motivo={d.get('motivo')}", flush=True)
        resultados.append(r)

    validos = [r for r in resultados if "erro" not in r]
    isolados = [r for r in validos if r["diagnostico_guarda"]["isolado"]]
    bloqueados = [r for r in validos if not r["diagnostico_guarda"]["isolado"]
                  and r["diagnostico_guarda"]["motivo"] == "orgao_partido_isolar_apagaria_anatomia"]
    unicos = [r for r in validos if r["diagnostico_guarda"]["motivo"] == "componente_unico_nada_a_isolar"]

    print("\n" + "=" * 78)
    print("RESUMO FASE 1")
    print("=" * 78)
    print(f"n={len(validos)} (erros={len(resultados)-len(validos)})")
    print(f"ja era componente unico          : {len(unicos)}")
    print(f"guarda isolou (ja resolvido)     : {len(isolados)}")
    print(f"guarda bloqueou (problema real)  : {len(bloqueados)}")
    if bloqueados:
        print("\ncasos com fragmentacao genuina (guarda bloqueou):")
        for r in bloqueados:
            print(f"  {r['grupo']}/{r['case_id']}  fracao={r['diagnostico_guarda']['fracao_componente_principal']}")

    saida_json = REPO / "experiments/best_worst_gallery_v1/fase1_diagnostico_producao.json"
    saida_json.write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nsalvo em {saida_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
