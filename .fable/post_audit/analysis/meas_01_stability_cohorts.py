# -*- coding: utf-8 -*-
"""MEAS-01 — H-03 (estabilidade do mecanismo de seleção) + H-04 (decomposição
por coorte). MEDIÇÃO label-free sobre artefatos congelados: fold_selection
(hiperparâmetros e métricas INNER por fold), oof_predictions (scores e
thresholds por caso; sem labels) e evaluation.by_dataset (agregados já
publicados). Nenhuma métrica nova do outer é produzida; nenhuma regra é
adotada. Determinístico (sem RNG)."""
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

RAIZ = Path(r"C:/Users/profurg/Desktop/sander/argos-main/casos/qualification/hybrid_v1")
SAIDA = Path(r"C:/Users/profurg/Desktop/sander/argos-main/.fable/post_audit/evidence/MEAS-01")


def wilson(sucessos: int, total: int, z: float = 1.959963984540054):
    if total <= 0:
        return [0.0, 0.0]
    p = sucessos / total
    den = 1 + z * z / total
    centro = (p + z * z / (2 * total)) / den
    margem = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return [round(max(0.0, centro - margem), 4), round(min(1.0, centro + margem), 4)]


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)

    # ------------------- H-03: estabilidade do mecanismo -------------------
    sel = json.loads((RAIZ / "medsiglip_multiclass_oof_predictions_v1/fold_selection.json").read_text(encoding="utf-8"))
    folds = []
    for f in sel:
        m = f["inner_metrics"]
        folds.append({
            "outer_fold": f["outer_fold"], "c": f["c_value"], "aggregation": f["aggregation"],
            "threshold": round(f["threshold"], 4),
            "inner_sens": round(m["sensitivity"], 4), "inner_spec": round(m["specificity"], 4),
            "inner_bal": round(m["balanced_accuracy"], 4), "inner_failures": m["technical_failures"],
        })
    thresholds = [f["threshold"] for f in folds]
    inner_bal = [f["inner_bal"] for f in folds]
    h03 = {
        "selecao_por_fold": folds,
        "dispersao": {
            "c_distintos": sorted({f["c"] for f in folds}),
            "aggregations_distintas": sorted({f["aggregation"] for f in folds}),
            "threshold_min_max": [min(thresholds), max(thresholds)],
            "threshold_amplitude": round(max(thresholds) - min(thresholds), 4),
            "inner_bal_min_max": [min(inner_bal), max(inner_bal)],
        },
    }

    # scores congelados (sem labels)
    linhas = (RAIZ / "medsiglip_multiclass_oof_predictions_v1/oof_predictions.jsonl").read_text(encoding="utf-8").splitlines()
    casos = [json.loads(l) for l in linhas if l.strip()]
    computaveis = [c for c in casos if not c["technical_failure"]]
    thr_por_fold = {f["outer_fold"]: f["threshold"] for f in folds}

    # fragilidade: score a menos de delta do threshold do proprio fold
    fragilidade = {}
    for delta in (0.02, 0.05, 0.10):
        n = sum(1 for c in computaveis if abs(c["score"] - thr_por_fold[c["outer_fold"]]) < delta)
        fragilidade[str(delta)] = {"casos": n, "fracao": round(n / len(computaveis), 4)}

    # transplante de threshold: aplicar thr do fold j a todos os computaveis
    flips_por_thr = {}
    base_pred = [(c["score"] >= thr_por_fold[c["outer_fold"]]) for c in computaveis]
    for j, thr_j in sorted(thr_por_fold.items()):
        alt = [(c["score"] >= thr_j) for c in computaveis]
        flips = sum(1 for a, b in zip(base_pred, alt) if a != b)
        flips_por_thr[f"fold_{j}_thr_{thr_j:.3f}"] = {"flips": flips, "fracao": round(flips / len(computaveis), 4)}

    thr_global = median(thresholds)
    alt = [(c["score"] >= thr_global) for c in computaveis]
    flips_global = sum(1 for a, b in zip(base_pred, alt) if a != b)
    h03["fragilidade_score_vs_threshold_do_fold"] = fragilidade
    h03["transplante_de_threshold"] = flips_por_thr
    h03["contrafactual_threshold_global_mediano"] = {
        "threshold": round(thr_global, 4), "flips": flips_global,
        "fracao": round(flips_global / len(computaveis), 4),
    }
    h03["n_computaveis"] = len(computaveis)

    # ------------------- H-04: decomposicao por coorte ---------------------
    ev = json.loads((RAIZ / "medsiglip_multiclass_oof_evaluation_v1/evaluation.json").read_text(encoding="utf-8"))
    por = {}
    for ds, m in ev["by_dataset"].items():
        pos, neg = m["tp"] + m["fn"], m["tn"] + m["fp"]
        por[ds] = {
            "n": m["case_count"], "pos": pos, "neg": neg, "falhas": m["technical_failures"],
            "sens": round(m["tp"] / pos, 4), "spec": round(m["tn"] / neg, 4),
            "sens_ic95": wilson(m["tp"], pos), "spec_ic95": wilson(m["tn"], neg),
        }
    # esquemas de peso declarados a priori
    def agrega(pesos: dict):
        s = sum(por[d]["sens"] * w for d, w in pesos.items())
        e = sum(por[d]["spec"] * w for d, w in pesos.items())
        return {"sens": round(s, 4), "spec": round(e, 4), "bal": round((s + e) / 2, 4)}

    datasets = list(por)
    total_casos = sum(por[d]["n"] for d in datasets)
    oficial = {d: por[d]["n"] / total_casos for d in datasets}
    igual3 = {d: 1 / len(datasets) for d in datasets}
    osw = [d for d in datasets if "openswiss" in d]
    lld = [d for d in datasets if d not in osw]
    n_osw = sum(por[d]["n"] for d in osw)
    igual2 = {**{d: 0.5 / len(lld) for d in lld}, **{d: 0.5 * por[d]["n"] / n_osw for d in osw}}
    esquemas = {
        "oficial_peso_por_caso": agrega(oficial),
        "igual_peso_3_coortes": agrega(igual3),
        "igual_peso_lld_vs_osw_agrupada": agrega(igual2),
    }
    bals = [v["bal"] for v in esquemas.values()]
    h04 = {
        "por_coorte": por,
        "agregado_por_esquema": esquemas,
        "indice_dependencia_composicao_pp": round((max(bals) - min(bals)) * 100, 2),
    }

    resultado = {"h03_estabilidade": h03, "h04_coortes": h04}
    destino = SAIDA / "meas01_results_2026-08-24.json"
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
