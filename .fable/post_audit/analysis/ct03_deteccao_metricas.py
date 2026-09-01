# -*- coding: utf-8 -*-
"""CT-03 fase C — análise PRÉ-REGISTRADA do benchmark de detecção.

Regras congeladas ANTES de abrir os braços de teste (plano CT-03):
1. LIMIAR de decisão: escolhido SÓ nos braços de tuning
   (tcia_hcc_train + tcia_crlm_train como positivos; chaos_tuning como
   negativos) maximizando o índice de Youden (sens+spec-1) sobre a
   grade de limiares = valores distintos de total_candidate_volume_mm3
   observados no tuning. Empate: menor limiar. O limiar é GRAVADO em
   evidence (ct03_limiar_congelado.json) na primeira execução com
   braços de tuning completos e NUNCA recalculado depois (imutável).
2. Decisão de caso: POSITIVA se total_candidate_volume_mm3 >= limiar.
3. TESTE (primário): sensibilidade em tcia_hcc_teste+tcia_crlm_teste
   (n=80), especificidade em chaos_teste (n~10, IC largo declarado).
   Metas: >=75% e >=75% (IC95 Wilson reportado).
4. MSD: braço SECUNDÁRIO (contaminação Dataset591 declarada).
5. Falha técnica no denominador (conta como erro), como no CT01-F.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
EVID = RAIZ / ".fable/post_audit/evidence/CT03"
JSONL = EVID / "ct03_deteccao_resultados.jsonl"
LIMIAR_PATH = EVID / "ct03_limiar_congelado.json"

BRACOS_TUNING_POS = ("tcia_hcc_train", "tcia_crlm_train")
BRACO_TUNING_NEG = "chaos_tuning"
BRACOS_TESTE_POS = ("tcia_hcc_teste", "tcia_crlm_teste")
BRACO_TESTE_NEG = "chaos_teste"


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    delta = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - delta), min(1.0, centro + delta))


def _carrega() -> dict[tuple[str, str], dict]:
    registros: dict[tuple[str, str], dict] = {}
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if "anulado" in r:
            registros.pop(tuple(r["anulado"]), None)
            continue
        chave = (r.get("braco"), r.get("caso"))
        if chave not in registros or r.get("status") == "ok":
            registros[chave] = r
    return registros


def _volume(r: dict) -> float:
    return float(r.get("total_candidate_volume_mm3") or 0.0)


def _congela_limiar(registros) -> dict | None:
    if LIMIAR_PATH.is_file():
        return json.loads(LIMIAR_PATH.read_text(encoding="utf-8"))
    pos = [r for (b, _), r in registros.items()
           if b in BRACOS_TUNING_POS and r.get("status") == "ok"]
    neg = [r for (b, _), r in registros.items()
           if b == BRACO_TUNING_NEG and r.get("status") == "ok"]
    n_pos_esperado = 222
    n_neg_esperado = 10
    if len(pos) < n_pos_esperado or len(neg) < n_neg_esperado:
        print(f"tuning incompleto: {len(pos)}/{n_pos_esperado} positivos, "
              f"{len(neg)}/{n_neg_esperado} negativos — limiar NÃO congelado")
        return None
    grade = sorted({_volume(r) for r in pos + neg})
    melhor = None
    for limiar in grade:
        sens = sum(1 for r in pos if _volume(r) >= limiar) / len(pos)
        spec = sum(1 for r in neg if _volume(r) < limiar) / len(neg)
        youden = sens + spec - 1.0
        if melhor is None or youden > melhor["youden"] + 1e-12:
            melhor = {"limiar_mm3": limiar, "youden": youden,
                      "sens_tuning": sens, "spec_tuning": spec}
    payload = {
        "schema": "argos-ct03-limiar-congelado-v1",
        "research_only": True,
        "regra": "Youden maximo na grade de volumes observados no tuning; "
                 "empate resolve pro menor limiar; IMUTAVEL apos gravado",
        "n_tuning_pos": len(pos), "n_tuning_neg": len(neg),
        **melhor,
    }
    LIMIAR_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"LIMIAR CONGELADO: {melhor['limiar_mm3']:.1f} mm3 "
          f"(Youden {melhor['youden']:.3f})")
    return payload


def _braco(registros, bracos, limiar, positivo: bool) -> dict:
    casos = [r for (b, _), r in registros.items() if b in bracos]
    ok = [r for r in casos if r.get("status") == "ok"]
    if positivo:
        acertos = sum(1 for r in ok if _volume(r) >= limiar)
    else:
        acertos = sum(1 for r in ok if _volume(r) < limiar)
    n = len(casos)
    lo, hi = _wilson(acertos, n)
    return {"n": n, "n_ok": len(ok), "acertos": acertos,
            "pct": round(100 * acertos / n, 1) if n else None,
            "ic95": [round(100 * lo, 1), round(100 * hi, 1)]}


def main() -> None:
    registros = _carrega()
    limiar_info = _congela_limiar(registros)
    if limiar_info is None:
        return
    limiar = float(limiar_info["limiar_mm3"])
    resumo = {
        "schema": "argos-ct03-deteccao-metricas-v1",
        "research_only": True,
        "clinical_use_allowed": False,
        "limiar_mm3": limiar,
        "primario_sensibilidade_teste": _braco(
            registros, BRACOS_TESTE_POS, limiar, positivo=True),
        "primario_especificidade_teste": _braco(
            registros, (BRACO_TESTE_NEG,), limiar, positivo=False),
        "secundario_msd_contaminacao_declarada": _braco(
            registros, ("msd",), limiar, positivo=True),
        "tuning_sens": limiar_info.get("sens_tuning"),
        "tuning_spec": limiar_info.get("spec_tuning"),
    }
    sens = resumo["primario_sensibilidade_teste"]["pct"] or 0
    spec = resumo["primario_especificidade_teste"]["pct"] or 0
    resumo["gate_75_75_deteccao"] = bool(sens >= 75.0 and spec >= 75.0)
    destino = EVID / "ct03_deteccao_metricas.json"
    destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"salvo: {destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
