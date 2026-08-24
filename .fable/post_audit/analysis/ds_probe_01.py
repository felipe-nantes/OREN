# -*- coding: utf-8 -*-
"""DS-PROBE-01 — localizacao do sinal de dominio por variante de representacao.

MEDICAO PURA sobre artefatos congelados (H-01 / W-031 / SR-007). Nada do
sistema muda; o outer OOF nao e lido como metrica de desenvolvimento (as
predicoes OOF entram apenas como VARIAVEL DE CONDICIONAMENTO da probe de
origem — proxy declarado, ja que os labels verdadeiros protegidos estao
ausentes desta maquina por design).

Probe: StandardScaler + LogisticRegression (seed fixa), StratifiedGroupKFold
por patient_group_id, AUC sobre os scores out-of-fold agrupados. Controle de
degenerescencia: permutacao de y com seed fixa (esperado ~0,5).
Reprodutibilidade: o script roda a analise DUAS vezes e exige igualdade
exata dos resultados.
"""
import json
import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 20260824
RAIZ = Path(r"C:/Users/profurg/Desktop/sander/argos-main/casos/qualification/hybrid_v1")
SAIDA = Path(r"C:/Users/profurg/Desktop/sander/argos-main/.fable/post_audit/evidence/DS-PROBE-01")

FAMILIAS = {
    "stage_a_global": "medsiglip_embeddings_stage_a_v1",
    "monophase_venous": "medsiglip_monophase_embeddings_v1",
    "monophase_arterial": "medsiglip_monophase_arterial_embeddings_v1",
    "monophase_delayed": "medsiglip_monophase_delayed_embeddings_v1",
}

PROIBIDOS = {"label", "ground_truth", "positive_subtype", "negative_subtype"}


def carrega_familia(nome_dir: str):
    """case_id -> (embedding medio dos paineis, dataset_id, patient_group_id)."""
    base = RAIZ / nome_dir
    registros = [
        json.loads(l)
        for l in (base / "embedding_records.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    for r in registros:
        chaves_proibidas = PROIBIDOS & set(r)
        assert not chaves_proibidas, f"registro contem campo proibido: {chaves_proibidas}"
        assert r.get("ground_truth_read") is False and r.get("label_attached") is False
    por_caso = defaultdict(list)
    meta = {}
    for r in registros:
        cid = str(r["case_id"])
        vetor = np.load(base / r["embedding_path"], allow_pickle=False)
        assert vetor.shape == (1152,), f"shape inesperado {vetor.shape} em {cid}"
        por_caso[cid].append(vetor.astype(np.float64))
        meta[cid] = (str(r["dataset_id"]), str(r["patient_group_id"]))
    case_ids = sorted(por_caso)
    X = np.stack([np.mean(por_caso[c], axis=0) for c in case_ids])
    datasets = [meta[c][0] for c in case_ids]
    grupos = np.array([meta[c][1] for c in case_ids])
    rotulos_unicos = sorted(set(datasets))
    assert len(rotulos_unicos) == 2, f"probe de origem exige 2 coortes; achei {rotulos_unicos}"
    y = np.array([rotulos_unicos.index(d) for d in datasets])
    return case_ids, X, y, grupos, rotulos_unicos


def probe_auc(X, y, grupos, seed: int) -> float:
    """AUC dos scores out-of-fold agrupados (deterministico)."""
    if len(np.unique(y)) < 2 or min(np.bincount(y)) < 5:
        return float("nan")
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    scores = np.zeros(len(y))
    for treino, teste in cv.split(X, y, grupos):
        modelo = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, C=1.0, random_state=seed),
        )
        modelo.fit(X[treino], y[treino])
        scores[teste] = modelo.decision_function(X[teste])
    return float(roc_auc_score(y, scores))


def carrega_predicoes_oficiais():
    """case_id -> predicao OOF congelada (POSITIVE/NEGATIVE). Sem ground truth."""
    caminho = RAIZ / "medsiglip_multiclass_oof_predictions_v1" / "oof_predictions.jsonl"
    pred = {}
    for l in caminho.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        assert "label" not in r and "ground_truth" not in r
        pred[str(r["case_id"])] = str(r.get("prediction"))
    return pred


def analise_completa():
    rng = np.random.default_rng(SEED)
    predicoes = carrega_predicoes_oficiais()
    resultado = {"seed": SEED, "familias": {}}
    for nome, dir_ in FAMILIAS.items():
        case_ids, X, y, grupos, rotulos = carrega_familia(dir_)
        n_por_coorte = {rotulos[i]: int((y == i).sum()) for i in range(2)}
        global_auc = probe_auc(X, y, grupos, SEED)
        y_perm = rng.permutation(y)
        controle = probe_auc(X, y_perm, grupos, SEED)
        cond = {}
        for alvo in ("POSITIVE", "NEGATIVE"):
            mascara = np.array([predicoes.get(c) == alvo for c in case_ids])
            cobertura = int(mascara.sum())
            if cobertura >= 30:
                cond[f"pred_{alvo}"] = {
                    "n": cobertura,
                    "auc": probe_auc(X[mascara], y[mascara], grupos[mascara], SEED),
                }
            else:
                cond[f"pred_{alvo}"] = {"n": cobertura, "auc": None}
        sem_pred = int(sum(1 for c in case_ids if c not in predicoes))
        resultado["familias"][nome] = {
            "dir": dir_,
            "casos": len(case_ids),
            "por_coorte": n_por_coorte,
            "casos_sem_predicao_oficial": sem_pred,
            "auc_origem_global": round(global_auc, 6),
            "auc_controle_permutado": round(controle, 6),
            "condicionada_por_predicao": {
                k: {"n": v["n"], "auc": round(v["auc"], 6) if v["auc"] is not None else None}
                for k, v in cond.items()
            },
        }
    return resultado


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    r1 = analise_completa()
    r2 = analise_completa()
    j1, j2 = json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True)
    assert j1 == j2, "REPRODUTIBILIDADE FALHOU: duas execucoes divergiram"
    r1["reproducibilidade"] = {
        "execucoes": 2,
        "identicas": True,
        "sha256_do_resultado": hashlib.sha256(j1.encode()).hexdigest(),
    }
    destino = SAIDA / "probe_results_2026-08-24.json"
    destino.write_text(json.dumps(r1, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(r1, indent=2, ensure_ascii=False))
    print(f"\nsalvo em {destino}")


if __name__ == "__main__":
    main()
