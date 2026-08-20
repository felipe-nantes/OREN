#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O modelo dedicado de figado (liver_segments_mr) segmenta melhor que o
generalista (total_mr)? Medido contra a MESMA referencia humana do CHAOS.

MOTIVACAO (docs/190): depois de confirmar que a fragmentacao ja estava
resolvida em 19/20 casos, sobrou o problema real -- SUB-SEGMENTACAO. O
total_mr captura so ~84% do figado verdadeiro (recall mediano 0,8375 contra a
referencia humana do CHAOS) e produz volumes medianos de 993 mL na coorte LLD,
com 7/20 casos abaixo de 600 mL. A uniao de 3 fases compensa parte disso, mas
esta compensando uma limitacao do modelo, nao corrigindo-a.

O liver_segments_mr e' um modelo de RM ESPECIFICO de figado (Dataset576, 120
sujeitos) contra o generalista total_mr (Dataset850/851/852, 1088 sujeitos).
Especialista com base pequena vs generalista com base grande -- pode ganhar ou
perder. Por isso se mede, nao se assume. A uniao dos seus 8 segmentos de
Couinaud da' uma mascara hepatica; a funcao ja existe no repo
(dtwin.benchmark.lld_mmri_v23_preparation.liver_segments_mr_union_segmenter) e
e' usada aqui SEM MODIFICACAO.

=======================================================================
ISOLAMENTO -- ESTE TESTE NAO PODE QUEBRAR O PRODUTO ATUAL
=======================================================================
  * NAO modifica dtwin/, webapp/, profiles/ nem viewer/ -- so' LE de la'.
  * NAO escreve nada em casos/ (onde vivem os exames de producao).
  * Escreve exclusivamente em experiments/liver_segments_mr_vs_chaos_v1/,
    que e' gitignorado, igual a todos os outros experimentos.
  * Le a entrada CHAOS em data/prepared/chaos_v21_blind/ apenas para leitura.
  * Roda o modelo em subprocesso isolado com timeout (mesmo padrao ja usado
    em producao), entao nao trava a maquina nem deixa processo orfao.
  * Nenhum caminho de decisao clinica e' tocado: isto e' medicao offline.
  Consequencia: se o gate reprovar, nada precisa ser revertido -- nao houve
  mudanca nenhuma para reverter.

=======================================================================
GATE PRE-ESPECIFICADO (escrito ANTES de rodar, nao afrouxar depois)
=======================================================================
Baseline ja medido, total_mr vs CHAOS (experiments/total_mr_vs_chaos_v1,
n=20): Dice mediano 0,9082 | recall mediano 0,8375 | razao de volume 0,8515.

O problema a resolver e' recall (figado faltando), entao o gate exige ganho
de recall SEM perder acuracia global:

  (a) recall mediano >= 0,8875   (baseline 0,8375 + 5 pontos absolutos)
  (b) Dice mediano   >= 0,8982   (baseline 0,9082 menos 1 ponto de tolerancia)
  (c) nenhum caso individual com Dice < 0,80  (baseline: pior caso 0,8650)

(a) sozinho nao basta: um modelo que vaza para o estomago tambem sobe recall.
(b) e (c) sao a trava contra isso.

Passa nos tres  -> o modelo dedicado merece um plano proprio de adocao.
Falha em qualquer -> documentar como negativo, producao segue como esta'.

RESSALVA que precisa acompanhar qualquer numero daqui (herdada de
tools/measure_total_mr_vs_chaos_reference.py): o CHAOS e' T1 SEM contraste e a
producao segmenta a fase venosa COM contraste. Isto mede os dois modelos com a
anatomia inteira em quadro e sob a mesma regra -- e' comparacao justa entre
eles, mas nao substitui uma referencia humana na propria coorte LLD.

Uso:
    .venv-win/Scripts/python.exe tools/measure_liver_segments_mr_vs_chaos_reference.py
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import SimpleITK as sitk

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ENTRADA = REPO / "data" / "prepared" / "chaos_v21_blind"
BASELINE = REPO / "experiments" / "total_mr_vs_chaos_v1" / "results.json"
SAIDA = REPO / "experiments" / "liver_segments_mr_vs_chaos_v1"
WORKER = REPO / "tools" / "liver_segments_mr_worker.py"

GATE_RECALL_MEDIANO = 0.8875
GATE_DICE_MEDIANO = 0.8982
GATE_DICE_MINIMO_POR_CASO = 0.80


def volume_ml(mascara: np.ndarray, espacamento) -> float:
    return float(mascara.sum() * math.prod(espacamento) / 1000.0)


def segmenta_isolado(source: Path, output: Path, *, timeout_seconds: int = 900) -> dict:
    """Subprocesso com timeout: um modelo travado nao trava esta medicao."""
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.parent / f".{output.name}.{uuid.uuid4().hex[:8]}.receipt.json"
    command = [
        sys.executable, str(WORKER),
        "--source", str(source), "--output", str(output),
        "--receipt", str(receipt_path), "--device", "gpu",
    ]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, creationflags=creationflags)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, check=False)
        process.communicate()
        output.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise RuntimeError(f"timeout de {timeout_seconds}s")
    try:
        if process.returncode != 0:
            raise RuntimeError((stderr or stdout or "sem detalhe").strip()[-800:])
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    finally:
        receipt_path.unlink(missing_ok=True)


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / "results.json"
    feitos = json.loads(destino.read_text("utf-8")) if destino.is_file() else {}

    casos = sorted(d for d in ENTRADA.iterdir() if d.is_dir())
    print("=" * 78)
    print("liver_segments_mr (dedicado) vs total_mr (generalista) -- referencia CHAOS")
    print("=" * 78)
    print(f"gate: recall mediano >= {GATE_RECALL_MEDIANO} | "
          f"Dice mediano >= {GATE_DICE_MEDIANO} | nenhum caso Dice < {GATE_DICE_MINIMO_POR_CASO}")
    print(f"casos: {len(casos)}\n")

    for i, caso in enumerate(casos, 1):
        if caso.name in feitos:
            continue
        fonte = caso / "t1_in.nii.gz"
        referencia = caso / "liver_mask.nii.gz"
        if not (fonte.is_file() and referencia.is_file()):
            continue
        predita = SAIDA / "masks" / f"{caso.name}.nii.gz"
        print(f"[{i}/{len(casos)}] {caso.name}", flush=True)
        if not predita.is_file():
            try:
                segmenta_isolado(fonte, predita)
            except Exception as exc:
                feitos[caso.name] = {"erro": f"{type(exc).__name__}: {exc}"}
                destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
                print(f"    falhou: {exc}", flush=True)
                continue

        img_ref = sitk.ReadImage(str(referencia))
        ref = sitk.GetArrayFromImage(img_ref) > 0
        pred = sitk.GetArrayFromImage(sitk.ReadImage(str(predita))) > 0
        if ref.shape != pred.shape:
            feitos[caso.name] = {"erro": f"grades diferentes {ref.shape} vs {pred.shape}"}
            destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
            print("    grades diferentes, pulado", flush=True)
            continue

        interseccao = float(np.logical_and(ref, pred).sum())
        dice = (2.0 * interseccao / (ref.sum() + pred.sum())) if (ref.sum() + pred.sum()) else 0.0
        recall = (interseccao / ref.sum()) if ref.sum() else 0.0
        espac = img_ref.GetSpacing()
        v_ref, v_pred = volume_ml(ref, espac), volume_ml(pred, espac)
        feitos[caso.name] = {
            "volume_referencia_ml": round(v_ref, 1),
            "volume_predito_ml": round(v_pred, 1),
            "razao_predito_referencia": round(v_pred / v_ref, 4) if v_ref else None,
            "dice": round(dice, 4),
            "recall_do_figado": round(recall, 4),
        }
        destino.write_text(json.dumps(feitos, indent=2), encoding="utf-8")
        print(f"    Dice {dice:.4f}  recall {recall:.4f}  "
              f"vol {v_pred:.0f} / {v_ref:.0f} mL", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if not validos:
        print("\nnenhum caso valido.")
        return 1

    base = json.loads(BASELINE.read_text("utf-8"))
    base_validos = [v for v in base.values() if isinstance(v, dict) and "dice" in v]
    b_dice = np.array([v["dice"] for v in base_validos])
    b_rec = np.array([v["recall_do_figado"] for v in base_validos])
    b_raz = np.array([v["razao_predito_referencia"] for v in base_validos])

    n_dice = np.array([v["dice"] for v in validos])
    n_rec = np.array([v["recall_do_figado"] for v in validos])
    n_raz = np.array([v["razao_predito_referencia"] for v in validos])

    print()
    print("=" * 78)
    print("COMPARACAO HEAD-TO-HEAD (mesma referencia humana, mesmos casos)")
    print("=" * 78)
    print(f"{'metrica':<26} {'total_mr':>12} {'liver_segments_mr':>19} {'delta':>10}")
    for nome, b, n in (("Dice mediano", b_dice, n_dice),
                        ("recall mediano", b_rec, n_rec),
                        ("razao volume mediana", b_raz, n_raz)):
        print(f"{nome:<26} {np.median(b):>12.4f} {np.median(n):>19.4f} "
              f"{np.median(n)-np.median(b):>+10.4f}")
    print(f"{'Dice minimo':<26} {b_dice.min():>12.4f} {n_dice.min():>19.4f} "
          f"{n_dice.min()-b_dice.min():>+10.4f}")
    print(f"\nn: total_mr={len(base_validos)}  liver_segments_mr={len(validos)} "
          f"(erros={len(feitos)-len(validos)})")

    ok_recall = float(np.median(n_rec)) >= GATE_RECALL_MEDIANO
    ok_dice = float(np.median(n_dice)) >= GATE_DICE_MEDIANO
    ok_piso = float(n_dice.min()) >= GATE_DICE_MINIMO_POR_CASO
    print()
    print("=" * 78)
    print("GATE")
    print("=" * 78)
    print(f"(a) recall mediano >= {GATE_RECALL_MEDIANO}      : "
          f"{np.median(n_rec):.4f}  {'PASSA' if ok_recall else 'FALHA'}")
    print(f"(b) Dice mediano   >= {GATE_DICE_MEDIANO}      : "
          f"{np.median(n_dice):.4f}  {'PASSA' if ok_dice else 'FALHA'}")
    print(f"(c) nenhum caso Dice < {GATE_DICE_MINIMO_POR_CASO}       : "
          f"minimo {n_dice.min():.4f}  {'PASSA' if ok_piso else 'FALHA'}")
    print()
    if ok_recall and ok_dice and ok_piso:
        print("GATE PASSA nos tres criterios -- o modelo dedicado recupera figado que o "
              "generalista perde, sem perder acuracia. Justifica um plano proprio de adocao.")
    else:
        print("GATE FALHA -- manter total_mr em producao. Nenhuma mudanca foi feita: "
              "este teste rodou 100% isolado, so' escreveu em experiments/.")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
