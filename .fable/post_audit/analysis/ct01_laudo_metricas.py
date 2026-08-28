# -*- coding: utf-8 -*-
"""Agrega o JSONL do benchmark de laudo CT-01-F nas métricas pré-registradas.

Endpoint PRIMÁRIO: % de acerto do TIPO nos braços TCIA (ordem do operador,
2026-08-27). Secundários: detecção (sens/spec, INCONCLUSIVA à parte) e
volumetria (só braços com máscara de referência). Falha técnica permanece
no denominador de todos os endpoints.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
JSONL = RAIZ / ".fable/post_audit/evidence/CT01-F/ct01_laudo_resultados.jsonl"
SAIDA = RAIZ / ".fable/post_audit/evidence/CT01-F/ct01_laudo_metricas.json"

BRACOS_TIPO = ("tcia_hcc", "tcia_crlm")
BRACOS_POS = ("msd_task03", "tcia_hcc", "tcia_crlm")


def _pct(k: int, n: int) -> float | None:
    return round(100.0 * k / n, 1) if n else None


def main() -> None:
    registros: dict[tuple[str, str], dict] = {}
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if "anulado" in r:  # marcador de invalidação, não é caso
            continue
        chave = (r.get("braco"), r.get("caso"))
        atual = registros.get(chave)
        # reexecuções: o registro ok mais recente vence; failed só se único
        if atual is None or (r.get("status") == "ok"):
            registros[chave] = r
    casos = list(registros.values())

    resumo: dict = {"schema": "argos-ct01f-laudo-metricas-v1",
                    "research_only": True, "clinical_use_allowed": False}

    # ---- PRIMÁRIO: tipo ----------------------------------------------------
    tipo: dict = {}
    for braco in BRACOS_TIPO:
        arm = [r for r in casos if r["braco"] == braco]
        ok = [r for r in arm if r.get("status") == "ok"]
        acertos = sum(1 for r in ok if r.get("acerto_tipo"))
        tipo[braco] = {
            "n": len(arm), "n_ok": len(ok),
            "n_failed": len(arm) - len(ok),
            "acertos_tipo": acertos,
            "pct_acerto_tipo": _pct(acertos, len(arm)),
            "distribuicao_tipo_hipotese": dict(Counter(
                str(r.get("tipo_hipotese")) for r in ok)),
            "distribuicao_tipo_parse": dict(Counter(
                str(r.get("tipo_parse")) for r in ok)),
            "distribuicao_deteccao": dict(Counter(
                str(r.get("resultado_hipotese")) for r in ok)),
        }
    arm_all = [r for r in casos if r["braco"] in BRACOS_TIPO]
    ok_all = [r for r in arm_all if r.get("status") == "ok"]
    ac_all = sum(1 for r in ok_all if r.get("acerto_tipo"))
    tipo["combinado"] = {"n": len(arm_all),
                         "acertos_tipo": ac_all,
                         "pct_acerto_tipo": _pct(ac_all, len(arm_all))}
    resumo["primario_tipo"] = tipo

    # ---- Secundário: detecção ----------------------------------------------
    pos = [r for r in casos if r["braco"] in BRACOS_POS]
    neg = [r for r in casos if r["braco"] == "chaos_ct"]
    pos_ok = [r for r in pos if r.get("status") == "ok"]
    neg_ok = [r for r in neg if r.get("status") == "ok"]
    det = {
        "positivos": {
            "n": len(pos), "n_ok": len(pos_ok),
            "POSITIVA": sum(1 for r in pos_ok if r.get("resultado_hipotese") == "POSITIVA"),
            "INCONCLUSIVA": sum(1 for r in pos_ok if r.get("resultado_hipotese") == "INCONCLUSIVA"),
            "sensibilidade_pct": _pct(
                sum(1 for r in pos_ok if r.get("resultado_hipotese") == "POSITIVA"),
                len(pos)),
        },
        "negativos_chaos": {
            "n": len(neg), "n_ok": len(neg_ok),
            "NEGATIVA": sum(1 for r in neg_ok if r.get("resultado_hipotese") == "NEGATIVA"),
            "INCONCLUSIVA": sum(1 for r in neg_ok if r.get("resultado_hipotese") == "INCONCLUSIVA"),
            "especificidade_pct": _pct(
                sum(1 for r in neg_ok if r.get("resultado_hipotese") == "NEGATIVA"),
                len(neg)),
        },
    }
    for braco in ("chaos_ct", "msd_task03", *BRACOS_TIPO):
        arm_ok = [r for r in casos if r["braco"] == braco and r.get("status") == "ok"]
        det[f"deteccao_{braco}"] = dict(Counter(
            str(r.get("resultado_hipotese")) for r in arm_ok))
    resumo["secundario_deteccao"] = det

    # ---- Secundário: volumetria (só braços com referência) -----------------
    volumetria: dict = {}
    for braco in ("chaos_ct", "msd_task03"):
        ok = [r for r in casos
              if r["braco"] == braco and r.get("status") == "ok" and r.get("razao")]
        if not ok:
            continue
        razoes = [r["razao"] for r in ok]
        dices = [r["dice"] for r in ok if r.get("dice") is not None]
        bloco = {
            "n": len(ok),
            "razao_mediana": round(float(np.median(razoes)), 4),
            "razao_iqr": [round(float(q), 4)
                          for q in np.percentile(razoes, [25, 75])],
            "dice_mediana": round(float(np.median(dices)), 4) if dices else None,
            "dice_min": round(float(np.min(dices)), 4) if dices else None,
        }
        cargas = [r["carga_tumoral"] for r in ok if "carga_tumoral" in r]
        if len(cargas) >= 10:
            from scipy.stats import spearmanr

            erros = [abs(1.0 - r["razao"]) for r in ok if "carga_tumoral" in r]
            rho, p = spearmanr(erros, cargas)
            bloco["spearman_erro_vs_carga"] = {
                "rho": round(float(rho), 4), "p": round(float(p), 4)}
            enriq = [r["enriquecimento_tumor_no_perdido"] for r in ok
                     if r.get("enriquecimento_tumor_no_perdido") is not None]
            bloco["enriquecimento_tumor_no_perdido_mediana"] = (
                round(float(np.median(enriq)), 2) if enriq else None)
        volumetria[braco] = bloco
    resumo["secundario_volumetria"] = volumetria

    resumo["n_registros"] = len(casos)
    resumo["falhas"] = [
        {"braco": r["braco"], "caso": r["caso"], "motivo": str(r.get("motivo"))[:120]}
        for r in casos if r.get("status") != "ok"
    ]
    SAIDA.write_text(json.dumps(resumo, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"salvo: {SAIDA}", file=sys.stderr)


if __name__ == "__main__":
    main()
