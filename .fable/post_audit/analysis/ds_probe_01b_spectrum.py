# -*- coding: utf-8 -*-
"""DS-PROBE-01b — localizacao DIMENSIONAL do sinal de origem (extensao da 01).

Como a probe de origem satura (AUC 1,0) em todas as variantes de fase, a
pergunta que resta e espectral: o sinal vive em poucos componentes (mitigacao
dirigida plausivel) ou e difuso (remocao e esperanca va)? Medicao pura:
(a) AUC da probe usando apenas os top-k componentes principais;
(b) AUC da probe no RESIDUO apos deflacionar k direcoes discriminantes de
    origem (deflacao iterativa: a cada passo remove-se a direcao do
    classificador logistico ajustado no residuo corrente).
PCA e deflacao sao ajustadas SO no treino de cada fold (sem vazamento).
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

SEED = 20260824
RAIZ = Path(r"C:/Users/profurg/Desktop/sander/argos-main/casos/qualification/hybrid_v1")
SAIDA = Path(r"C:/Users/profurg/Desktop/sander/argos-main/.fable/post_audit/evidence/DS-PROBE-01")
FAMILIA = "medsiglip_embeddings_stage_a_v1"  # representacao de producao (stage A)


def carrega():
    base = RAIZ / FAMILIA
    registros = [
        json.loads(l)
        for l in (base / "embedding_records.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    por_caso = defaultdict(list)
    meta = {}
    for r in registros:
        cid = str(r["case_id"])
        por_caso[cid].append(np.load(base / r["embedding_path"], allow_pickle=False).astype(np.float64))
        meta[cid] = (str(r["dataset_id"]), str(r["patient_group_id"]))
    case_ids = sorted(por_caso)
    X = np.stack([np.mean(por_caso[c], axis=0) for c in case_ids])
    rotulos = sorted({meta[c][0] for c in case_ids})
    y = np.array([rotulos.index(meta[c][0]) for c in case_ids])
    grupos = np.array([meta[c][1] for c in case_ids])
    return X, y, grupos


def auc_oof(transforma_fit, transforma_apply, X, y, grupos):
    """AUC out-of-fold com transformacao ajustada so no treino."""
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    scores = np.zeros(len(y))
    for tr, te in cv.split(X, y, grupos):
        escala = StandardScaler().fit(X[tr])
        Xtr, Xte = escala.transform(X[tr]), escala.transform(X[te])
        estado = transforma_fit(Xtr, y[tr])
        Xtr2, Xte2 = transforma_apply(Xtr, estado), transforma_apply(Xte, estado)
        clf = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED).fit(Xtr2, y[tr])
        scores[te] = clf.decision_function(Xte2)
    return float(roc_auc_score(y, scores))


def main():
    X, y, grupos = carrega()

    # (a) apenas top-k PCs
    topk = {}
    for k in (1, 2, 4, 8, 16, 32, 64):
        fit = lambda Xtr, ytr, k=k: PCA(n_components=k, random_state=SEED).fit(Xtr)
        aplica = lambda Xq, pca: pca.transform(Xq)
        topk[k] = round(auc_oof(fit, aplica, X, y, grupos), 6)

    # (b) residuo apos deflacionar k direcoes discriminantes de origem
    def fit_deflacao(Xtr, ytr, k):
        direcoes = []
        Xc = Xtr.copy()
        for _ in range(k):
            w = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED).fit(Xc, ytr).coef_[0]
            w = w / np.linalg.norm(w)
            direcoes.append(w)
            Xc = Xc - np.outer(Xc @ w, w)
        return np.stack(direcoes)

    def aplica_deflacao(Xq, direcoes):
        Xc = Xq.copy()
        for w in direcoes:
            Xc = Xc - np.outer(Xc @ w, w)
        return Xc

    residuo = {}
    for k in (1, 2, 4, 8, 16, 32):
        residuo[k] = round(
            auc_oof(lambda a, b, k=k: fit_deflacao(a, b, k), aplica_deflacao, X, y, grupos), 6
        )

    resultado = {
        "familia": FAMILIA,
        "seed": SEED,
        "n_casos": int(len(y)),
        "auc_por_topk_pcs": topk,
        "auc_residuo_apos_deflacionar_k_direcoes": residuo,
        "leitura": "topk alto com k pequeno = sinal em subespaco de baixa dimensao; "
                   "residuo alto mesmo com k grande = sinal difuso/replicado",
    }
    destino = SAIDA / "spectrum_results_2026-08-24.json"
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
