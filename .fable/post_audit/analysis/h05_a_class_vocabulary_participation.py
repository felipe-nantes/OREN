# -*- coding: utf-8 -*-
"""H-05 fase A — participação das classes *_unspecified nos scores congelados.

MEDIÇÃO PURA (human_gate: none). Nenhum label protegido é lido: usa apenas
saída de modelo (probabilidades por classe), case_id/dataset_id e os scores
já congelados. Nenhum artefato é modificado; nenhum threshold/fold muda.

Tier 2 (oficial trifásico): recomputa deterministicamente as probabilidades
por classe com os MODELOS DE FOLD CONGELADOS + EMBEDDINGS CONGELADOS,
respeitando o fold de cada caso (out-of-fold por construção), VALIDA contra
o score congelado e então decompõe o score em contribuição hcc vs
positive_unspecified (exata: mesmos top-2 painéis da agregação oficial).

Tier 1 (dev signals): lê class_probabilities já congeladas dos artefatos
monofásicos (regime da decisão 19: triagem por dev signals).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
BASE = RAIZ / "casos/qualification/hybrid_v1"
OFICIAL = BASE / "medsiglip_multiclass_oof_predictions_v1"
EMB = BASE / "medsiglip_embeddings_stage_a_v1"
SAIDA = RAIZ / ".fable/post_audit/evidence/H05-A"
SAIDA.mkdir(parents=True, exist_ok=True)

CLASSES = ["fnh", "hcc", "hemangioma", "hepatic_cyst",
           "negative_unspecified", "positive_unspecified"]
POSITIVAS = {"hcc", "positive_unspecified"}
UNSPEC = {"negative_unspecified", "positive_unspecified"}


def carrega_oficial():
    linhas = (OFICIAL / "oof_predictions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    casos = [json.loads(ln) for ln in linhas]
    embeddings = {}
    for c in casos:
        d = EMB / "embeddings" / c["case_id"]
        if d.is_dir():
            embeddings[c["case_id"]] = [
                np.load(f) for f in sorted(d.glob("*.npy"))
            ]
    return casos, embeddings


def tier2_oficial():
    casos, embeddings = carrega_oficial()
    modelos = {
        k: joblib.load(OFICIAL / f"outer_fold_{k}.joblib") for k in range(5)
    }
    fold_sel = json.loads((OFICIAL / "fold_selection.json").read_text(encoding="utf-8"))
    # A selecao inner escolheu agregacoes DIFERENTES por fold (fold 2 = max,
    # o outlier conhecido da selecao; 3-4 = mean). A decomposicao exata vale
    # para as tres: paineis selecionados = top-k por soma positiva.
    agg_por_fold = {int(f["outer_fold"]): f["aggregation"] for f in fold_sel}
    assert set(agg_por_fold.values()) <= {"mean", "max", "top2_mean"}, agg_por_fold

    max_delta = 0.0
    validados = 0
    por_caso = []
    for c in casos:
        if c["technical_failure"] or c["case_id"] not in embeddings:
            continue
        model = modelos[int(c["outer_fold"])]
        vecs = np.stack(embeddings[c["case_id"]])
        probs = np.asarray(model.predict_proba(vecs), dtype=np.float64)
        classes_modelo = list(model.named_steps["classifier"].classes_)
        # colunas na ordem de CLASSES (classes_ sao indices inteiros do
        # vocabulario ordenado — mesma ordenacao sorted() do treino)
        col = {CLASSES[int(lbl)]: j for j, lbl in enumerate(classes_modelo)}
        pos_sum = probs[:, [col["hcc"], col["positive_unspecified"]]].sum(axis=1)
        agg = agg_por_fold[int(c["outer_fold"])]
        k = {"max": 1, "top2_mean": 2, "mean": len(pos_sum)}[agg]
        ordem = np.argsort(-pos_sum)
        top2 = ordem[: min(k, len(ordem))]
        score_recomputado = float(pos_sum[top2].mean())
        delta = abs(score_recomputado - float(c["score"]))
        max_delta = max(max_delta, delta)
        validados += 1
        contrib_hcc = float(probs[top2, col["hcc"]].mean())
        contrib_pu = float(probs[top2, col["positive_unspecified"]].mean())
        # massa de classe media nos MESMOS top-2 paineis (decomposicao exata)
        massa = {nome: float(probs[top2, col[nome]].mean()) for nome in CLASSES}
        por_caso.append({
            "case_id": c["case_id"],
            "dataset_id": c["dataset_id"],
            "score_frozen": float(c["score"]),
            "delta_recompute": delta,
            "contrib_hcc": contrib_hcc,
            "contrib_positive_unspecified": contrib_pu,
            "share_pu_no_score": contrib_pu / max(score_recomputado, 1e-12),
            "massa": massa,
            "argmax_class": CLASSES[int(np.argmax([massa[n] for n in CLASSES]))],
            "prediction": c["prediction"],
        })
    return por_caso, max_delta, validados


def agrega(por_caso):
    por_coorte = defaultdict(list)
    for r in por_caso:
        por_coorte[r["dataset_id"]].append(r)
    resumo = {}
    for ds, rows in sorted(por_coorte.items()):
        n = len(rows)
        massa_media = {
            nome: float(np.mean([r["massa"][nome] for r in rows])) for nome in CLASSES
        }
        resumo[ds] = {
            "n_casos": n,
            "massa_media_por_classe": massa_media,
            "massa_unspecified_total": float(sum(massa_media[c] for c in UNSPEC)),
            "share_pu_no_score_mediana": float(np.median([r["share_pu_no_score"] for r in rows])),
            "share_pu_no_score_media": float(np.mean([r["share_pu_no_score"] for r in rows])),
            "argmax_em_unspecified_frac": float(np.mean([r["argmax_class"] in UNSPEC for r in rows])),
            "argmax_counts": {
                c: int(sum(1 for r in rows if r["argmax_class"] == c)) for c in CLASSES
            },
            # entre os PREDITOS POSITIVOS, quanto do score veio de positive_unspecified
            "share_pu_entre_positivos_media": float(np.mean(
                [r["share_pu_no_score"] for r in rows if r["prediction"] == "POSITIVE"]
            )) if any(r["prediction"] == "POSITIVE" for r in rows) else None,
        }
    return resumo


def tier1_monofasicos():
    saida = {}
    for nome in (
        "medsiglip_monophase_delayed_slice_multiclass_oof_predictions_v1",
        "medsiglip_monophase_delayed_subtype_oof_predictions_v1",
    ):
        f = BASE / nome / "oof_predictions.jsonl"
        if not f.is_file():
            continue
        rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").strip().splitlines()]
        por_coorte = defaultdict(list)
        for r in rows:
            probs = r.get("class_probabilities")
            if not isinstance(probs, dict) or r.get("technical_failure"):
                continue
            por_coorte[r.get("dataset_id", "unknown")].append(probs)
        resumo = {}
        for ds, plist in sorted(por_coorte.items()):
            classes_locais = sorted({k for p in plist for k in p})
            massa_media = {
                c: float(np.mean([p.get(c, 0.0) for p in plist])) for c in classes_locais
            }
            resumo[ds] = {
                "n_casos": len(plist),
                "classes": classes_locais,
                "massa_media_por_classe": massa_media,
                "massa_unspecified_total": float(
                    sum(v for c, v in massa_media.items() if c in UNSPEC)
                ),
            }
        saida[nome] = resumo
    return saida


def main():
    por_caso, max_delta, validados = tier2_oficial()
    resumo_oficial = agrega(por_caso)
    resultado = {
        "schema": "argos-h05-fase-a-class-participation-v1",
        "research_only": True,
        "clinical_use_allowed": False,
        "labels_protegidos_lidos": False,
        "tier2_validacao": {
            "casos_validados": validados,
            "max_abs_delta_score_recomputado_vs_congelado": max_delta,
            # criterio: 1e-5 — o delta observado (~4e-07) e ruido float32 do
            # empilhamento de embeddings, 5 ordens abaixo da granularidade de
            # qualquer threshold (0.50-0.85); scores decompostos = congelados
            # para todo fim pratico.
            "recompute_valido": bool(max_delta < 1e-5),
        },
        "tier2_oficial_por_coorte": resumo_oficial,
        "tier1_dev_monofasicos": tier1_monofasicos(),
    }
    destino = SAIDA / "h05_a_class_participation.json"
    destino.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"validacao: {validados} casos, max|delta|={max_delta:.3e}")
    for ds, r in resumo_oficial.items():
        print(f"[{ds}] n={r['n_casos']} massa_unspec={r['massa_unspecified_total']:.3f} "
              f"share_pu_score(med)={r['share_pu_no_score_mediana']:.3f} "
              f"argmax_unspec={r['argmax_em_unspecified_frac']:.3f}")
    print(f"salvo: {destino}")


if __name__ == "__main__":
    main()
