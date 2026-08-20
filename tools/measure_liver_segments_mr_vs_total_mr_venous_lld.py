#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE A (docs/192, plano de adocao do liver_segments_mr) -- o regime REAL.

docs/191 provou que o liver_segments_mr bate o total_mr contra referencia
humana no CHAOS (20/20 casos). Mas o CHAOS e' T1 SEM contraste, e a producao
segmenta a fase venosa COM contraste. docs/165 ja' mostrou que a fase muda o
resultado. Esta e' a lacuna que decide tudo: o ganho se transfere para o realce
dinamico, ou nao?

Nao existe ground truth de FIGADO no LLD. Mas existe ground truth de LESAO (335
mascaras humanas em lesion_masks_cv_v1, vinculadas aos ids anonimizados pelo
mapping em external_protocol_v1/protected_source/mapping.jsonl). Lesao hepatica
e' intra-hepatica por definicao, entao a fracao dos voxels de lesao anotada que
caem DENTRO da mascara de figado e' uma ancora de acuracia REAL: figado que nao
cobre a lesao anotada esta' errado ali. Uso estritamente de avaliacao -- o flag
lesion_masks_allowed_in_inference=False continua respeitado, nada disso entra
em inferencia.

=======================================================================
ISOLAMENTO -- NAO PODE QUEBRAR O PRODUTO
=======================================================================
  * NAO modifica dtwin/, webapp/, profiles/, viewer/.
  * NAO escreve em casos/ (le a entrada venosa e as mascaras apenas para ler).
  * Escreve so' em experiments/liver_segments_mr_vs_lld_venous_v1/ (gitignorado).
  * Baseline total_mr ja' existe (external_segmentation_audit335_fullres_v1),
    custo zero; so' o modelo novo roda GPU.
  * Subprocesso isolado com timeout (tools/liver_segments_mr_worker.py).

=======================================================================
GATE PRE-ESPECIFICADO (escrito ANTES de rodar; nao afrouxar depois)
=======================================================================
Amostra: 60 casos sorteados dos 321 elegiveis, SEMENTE FIXA declarada abaixo
(evita o vies de selecao por extremos dos 20 casos de docs/190).

  (a) cobertura mediana de lesao sobe >= +2 pontos absolutos
      -- o criterio que importa: mede figado REAL recuperado, nao volume
         inflado. Sobe se o modelo novo passa a incluir regiao de lesao que o
         total_mr deixava de fora.
  (b) volume mediano sobe E a fracao de casos na faixa adulta (900-2400 mL)
      NAO cai -- trava contra "maior porem pior".
  (c) fracao mediana do maior componente NAO piora -- trava contra ganhar
      volume as custas de fragmentar.

Passa nos TRES -> o ganho do CHAOS se transferiu; segue para a Fase B (adocao
so' na visualizacao). Falha em QUALQUER UM -> parar, documentar negativo,
manter total_mr.

RESSALVA que acompanha o numero: cobertura de lesao mede se o figado inclui a
regiao certa, nao se a BORDA do figado esta' correta -- um figado inflado que
cobre tudo tambem pontua bem em (a). Por isso (b) e (c) existem. Ainda assim,
sem referencia de figado inteiro no LLD, esta e' a melhor ancora possivel no
regime real.

Uso:
    .venv-win/Scripts/python.exe tools/measure_liver_segments_mr_vs_total_mr_venous_lld.py
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

MAPPING = REPO / "casos/qualification/lld_mmri_v23/prepared/external_protocol_v1/protected_source/mapping.jsonl"
LESOES = REPO / "casos/qualification/lld_mmri_v23/lesion_masks_cv_v1"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
BASELINE_TMR = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
SAIDA = REPO / "experiments/liver_segments_mr_vs_lld_venous_v1"
WORKER = REPO / "tools/liver_segments_mr_worker.py"

SEMENTE = 20260807  # fixa, declarada antes de rodar (data do experimento)
N_AMOSTRA = 60
FAIXA_ADULTO_ML = (900.0, 2400.0)
GATE_GANHO_COBERTURA = 0.02  # +2 pontos absolutos na mediana


def volume_ml(mask: np.ndarray, spacing) -> float:
    return float(mask.sum() * math.prod(spacing) / 1000.0)


def fracao_maior_componente(mask: np.ndarray) -> float:
    if mask.sum() == 0:
        return 0.0
    rotulos, n = ndimage.label(mask)
    if n <= 1:
        return 1.0
    tam = np.bincount(rotulos.ravel())[1:]
    return float(tam.max() / tam.sum())


def cobertura_lesao(figado: np.ndarray, lesao: np.ndarray) -> float | None:
    total = float(lesao.sum())
    if total == 0:
        return None
    return float(np.logical_and(figado, lesao).sum()) / total


def segmenta_isolado(source: Path, output: Path, *, timeout_seconds: int = 900) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = output.parent / f".{output.name}.{uuid.uuid4().hex[:8]}.json"
    cmd = [sys.executable, str(WORKER), "--source", str(source), "--output", str(output),
           "--receipt", str(receipt), "--device", "gpu"]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    p = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, creationflags=flags)
    try:
        out, err = p.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False)
        p.communicate()
        output.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise RuntimeError(f"timeout de {timeout_seconds}s")
    receipt.unlink(missing_ok=True)
    if p.returncode != 0:
        raise RuntimeError((err or out or "sem detalhe").strip()[-800:])


def carrega_crosswalk() -> dict[str, str]:
    linhas = [json.loads(l) for l in MAPPING.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["source_subject_id"]: r["case_id"] for r in linhas}


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks").mkdir(exist_ok=True)
    destino = SAIDA / "results.json"
    feitos = json.loads(destino.read_text("utf-8")) if destino.is_file() else {}

    cw = carrega_crosswalk()
    anon_por_arquivo = {}
    for f in sorted(os.listdir(LESOES)):
        sid = f.split("_")[0]
        anon = cw.get(sid)
        if not anon:
            continue
        if (ENTRADAS / anon / "t1_venous.nii.gz").is_file() and \
           (BASELINE_TMR / anon / "liver_mask_venous.nii.gz").is_file():
            anon_por_arquivo[anon] = f

    elegiveis = sorted(anon_por_arquivo)
    rng = random.Random(SEMENTE)
    amostra = sorted(rng.sample(elegiveis, min(N_AMOSTRA, len(elegiveis))))

    print("=" * 78)
    print("FASE A -- liver_segments_mr vs total_mr na fase VENOSA COM CONTRASTE")
    print("=" * 78)
    print(f"ancora: cobertura de lesao anotada (ground truth humano) | semente={SEMENTE}")
    print(f"gate: (a) cobertura mediana +{100*GATE_GANHO_COBERTURA:.0f}pts | "
          f"(b) volume sobe e faixa adulta nao cai | (c) maior componente nao piora")
    print(f"amostra: {len(amostra)} de {len(elegiveis)} elegiveis\n")

    for i, anon in enumerate(amostra, 1):
        if anon in feitos:
            continue
        print(f"[{i}/{len(amostra)}] {anon}", flush=True)
        venosa_src = ENTRADAS / anon / "t1_venous.nii.gz"
        tmr_mask = BASELINE_TMR / anon / "liver_mask_venous.nii.gz"
        lesao_mask = LESOES / anon_por_arquivo[anon]
        lsm_mask = SAIDA / "masks" / f"{anon}.nii.gz"

        if not lsm_mask.is_file():
            try:
                segmenta_isolado(venosa_src, lsm_mask)
            except Exception as exc:
                feitos[anon] = {"erro": f"{type(exc).__name__}: {exc}"}
                destino.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
                print(f"    falhou: {exc}", flush=True)
                continue

        img = sitk.ReadImage(str(tmr_mask))
        spacing = img.GetSpacing()
        tmr = sitk.GetArrayFromImage(img) > 0
        lsm = sitk.GetArrayFromImage(sitk.ReadImage(str(lsm_mask))) > 0
        les = sitk.GetArrayFromImage(sitk.ReadImage(str(lesao_mask))) > 0
        if not (tmr.shape == lsm.shape == les.shape):
            feitos[anon] = {"erro": f"grades divergentes tmr{tmr.shape} lsm{lsm.shape} les{les.shape}"}
            destino.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
            print("    grades divergentes, pulado", flush=True)
            continue

        reg = {
            "total_mr": {
                "volume_ml": round(volume_ml(tmr, spacing), 1),
                "fracao_maior_componente": round(fracao_maior_componente(tmr), 4),
                "cobertura_lesao": cobertura_lesao(tmr, les),
            },
            "liver_segments_mr": {
                "volume_ml": round(volume_ml(lsm, spacing), 1),
                "fracao_maior_componente": round(fracao_maior_componente(lsm), 4),
                "cobertura_lesao": cobertura_lesao(lsm, les),
            },
            "voxels_lesao": int(les.sum()),
        }
        for m in ("total_mr", "liver_segments_mr"):
            c = reg[m]["cobertura_lesao"]
            reg[m]["cobertura_lesao"] = round(c, 4) if c is not None else None
        feitos[anon] = reg
        destino.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
        ct, cl = reg["total_mr"]["cobertura_lesao"], reg["liver_segments_mr"]["cobertura_lesao"]
        print(f"    cobertura lesao  tmr {ct}  lsm {cl}   "
              f"vol {reg['total_mr']['volume_ml']:.0f} -> {reg['liver_segments_mr']['volume_ml']:.0f} mL",
              flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    com_lesao = [v for v in validos if v["total_mr"]["cobertura_lesao"] is not None
                 and v["liver_segments_mr"]["cobertura_lesao"] is not None]
    if not com_lesao:
        print("\nnenhum caso valido com lesao.")
        return 1

    ct = np.array([v["total_mr"]["cobertura_lesao"] for v in com_lesao])
    cl = np.array([v["liver_segments_mr"]["cobertura_lesao"] for v in com_lesao])
    vt = np.array([v["total_mr"]["volume_ml"] for v in validos])
    vl = np.array([v["liver_segments_mr"]["volume_ml"] for v in validos])
    ft = np.array([v["total_mr"]["fracao_maior_componente"] for v in validos])
    fl = np.array([v["liver_segments_mr"]["fracao_maior_componente"] for v in validos])
    baixo, alto = FAIXA_ADULTO_ML
    faixa_t = int(((vt >= baixo) & (vt <= alto)).sum())
    faixa_l = int(((vl >= baixo) & (vl <= alto)).sum())

    print("\n" + "=" * 78)
    print("RESULTADO (mesmos casos, fase venosa com contraste)")
    print("=" * 78)
    print(f"{'metrica':<32} {'total_mr':>12} {'liver_segments_mr':>19} {'delta':>10}")
    print(f"{'cobertura lesao (mediana)':<32} {np.median(ct):>12.4f} {np.median(cl):>19.4f} {np.median(cl)-np.median(ct):>+10.4f}")
    print(f"{'volume mL (mediana)':<32} {np.median(vt):>12.0f} {np.median(vl):>19.0f} {np.median(vl)-np.median(vt):>+10.0f}")
    print(f"{'na faixa adulta (n)':<32} {faixa_t:>12d} {faixa_l:>19d} {faixa_l-faixa_t:>+10d}")
    print(f"{'maior componente (mediana)':<32} {np.median(ft):>12.4f} {np.median(fl):>19.4f} {np.median(fl)-np.median(ft):>+10.4f}")
    print(f"\nn={len(validos)} (com lesao anotada={len(com_lesao)}, erros={len(feitos)-len(validos)})")

    cob_melhorou = int((cl > ct).sum())
    print(f"cobertura de lesao melhorou em {cob_melhorou}/{len(com_lesao)} casos")

    ok_a = (np.median(cl) - np.median(ct)) >= GATE_GANHO_COBERTURA
    ok_b = (np.median(vl) > np.median(vt)) and (faixa_l >= faixa_t)
    ok_c = np.median(fl) >= np.median(ft)
    print("\n" + "=" * 78)
    print("GATE")
    print("=" * 78)
    print(f"(a) cobertura mediana +{100*GATE_GANHO_COBERTURA:.0f}pts : "
          f"{100*(np.median(cl)-np.median(ct)):+.1f}pts  {'PASSA' if ok_a else 'FALHA'}")
    print(f"(b) volume sobe e faixa nao cai   : "
          f"vol {np.median(vl)-np.median(vt):+.0f} mL, faixa {faixa_l-faixa_t:+d}  {'PASSA' if ok_b else 'FALHA'}")
    print(f"(c) maior componente nao piora    : "
          f"{np.median(fl)-np.median(ft):+.4f}  {'PASSA' if ok_c else 'FALHA'}")
    print()
    if ok_a and ok_b and ok_c:
        print("GATE PASSA -- o ganho do CHAOS se transferiu para o realce dinamico. "
              "Justifica a Fase B (adocao so' na visualizacao).")
    else:
        print("GATE FALHA -- manter total_mr. Nada foi alterado: teste 100% isolado, "
              "so' escreveu em experiments/.")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
