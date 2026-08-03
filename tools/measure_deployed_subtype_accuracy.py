"""Qual e' a acuracia de subtipo do caminho que esta' NO AR, fora da amostra?

Ha' tres numeros circulando e eles medem coisas diferentes:

  61,46%  docs/146 -- caminho de RECORTE por ROI predita, denominador honesto
  64,81%  docs/156 -- cascata de representacoes, denominador honesto
  96,43%  docs/171 -- bundle de producao em 25 casos LLD que estao NO TREINO dele

O webapp usa o bundle de producao sobre paineis de FIGADO INTEIRO, com agregacao
top2_mean -- nenhum dos tres. O numero defensavel desse caminho nunca foi medido.

Este script mede exatamente ele: mesmo estimador (multiclasse de 6 classes,
agregacao de painel, C e limiar escolhidos nos folds internos), mas em nested-OOF
-- ou seja, cada caso avaliado por um modelo que nao o viu.

Duas leituras, porque a interface faz as duas coisas:
  determinado   : em quantos casos a guarda de docs/161 permite nomear o subtipo
  acerto        : entre os nomeados, quantos estao certos
  honesto       : sobre TODOS os alvos, com nao-determinado contando como erro
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.learning.medsiglip_multiclass_classifier import (
    _load_embedding_map, build_multiclass_labels,
)
from dtwin.learning.protocol import load_protected_cases, load_protected_label_rows
from dtwin.learning.robustness import clinical_subtype_map
from dtwin.learning.visual_inference import NAMED_LESION_CLASSES, NAMED_LESION_MASS_FLOOR

REPO = Path(".").resolve()
CFG = REPO / "configs/training/hybrid_v1_protocol.yaml"
SPLITS = REPO / "configs/training/hybrid_v1_nested_splits.json"
WHOLE = REPO / "casos/qualification/hybrid_v1/medsiglip_embeddings_stage_a_v1"
OUT = REPO / "experiments/subtipo_caminho_producao_v1"
C_GRID, AGGS = [0.01, 0.1, 1.0], ["mean", "max", "top2_mean"]
SEED, MAX_ITER = 20260724, 3000

cases = load_protected_cases(CFG, REPO)
classe, _ = build_multiclass_labels(
    cases, clinical_subtype_map(load_protected_label_rows(CFG, REPO)))
dsid = {c.case_id: c.dataset_id for c in cases}
nomes = sorted(set(classe.values()))
idx = {n: i for i, n in enumerate(nomes)}
paineis, _ = _load_embedding_map(WHOLE)
splits = json.loads(SPLITS.read_text(encoding="utf-8"))

alvos = sorted(c.case_id for c in cases
               if dsid[c.case_id] == "lld_mmri" and classe.get(c.case_id) in NAMED_LESION_CLASSES)
print(f"alvos LLD com subtipo: {len(alvos)}  {dict(Counter(classe[c] for c in alvos))}")


def treinar(ids, cv):
    X, y = [], []
    for cid in ids:
        for v in paineis.get(cid, []):
            X.append(np.asarray(v, dtype=np.float64)); y.append(idx[classe[cid]])
    if not X or len(set(y)) < 2:
        return None
    m = Pipeline([("s", StandardScaler()),
                  ("c", LogisticRegression(C=cv, class_weight="balanced",
                                           max_iter=MAX_ITER, random_state=SEED))])
    m.fit(np.stack(X), np.array(y)); return m


def agregar(P, how):
    if how == "mean":
        return P.mean(axis=0)
    if how == "max":
        return P.max(axis=0)
    ordenado = np.sort(P, axis=0)[::-1]
    return ordenado[:2].mean(axis=0)


def massa_por_classe(m, cid, how):
    vecs = paineis.get(cid)
    if not vecs:
        return None
    P = m.predict_proba(np.stack([np.asarray(v, dtype=np.float64) for v in vecs]))
    med = agregar(P, how)
    cls = list(m.named_steps["c"].classes_)
    return {nomes[int(lb)]: float(med[i]) for i, lb in enumerate(cls)}


pred, determinado = {}, {}
for outer in splits["outer_folds"]:
    tr = [c for c in outer["train_case_ids"] if c in paineis]
    te = [c for c in outer["test_case_ids"] if c in paineis and c in set(alvos)]
    if not te:
        continue
    melhor, escore = None, -1.0
    for cv in C_GRID:
        for how in AGGS:
            acertos = tot = 0
            for inner in outer["inner_folds"]:
                itr = [c for c in inner["train_case_ids"] if c in paineis]
                iva = [c for c in inner["validation_case_ids"]
                       if c in paineis and classe.get(c) in NAMED_LESION_CLASSES]
                mm = treinar(itr, cv)
                if mm is None:
                    continue
                for c in iva:
                    massa = massa_por_classe(mm, c, how)
                    if not massa:
                        continue
                    nomeadas = {k: massa.get(k, 0.0) for k in NAMED_LESION_CLASSES}
                    escolhido = max(nomeadas, key=nomeadas.get)
                    acertos += escolhido == classe[c]; tot += 1
            s = acertos / tot if tot else 0.0
            if s > escore:
                melhor, escore = (cv, how), s
    cv, how = melhor
    m = treinar(tr, cv)
    for cid in te:
        massa = massa_por_classe(m, cid, how)
        if not massa:
            continue
        nomeadas = {k: massa.get(k, 0.0) for k in NAMED_LESION_CLASSES}
        soma = sum(nomeadas.values())
        determinado[cid] = soma >= NAMED_LESION_MASS_FLOOR
        pred[cid] = max(nomeadas, key=nomeadas.get)

cm = {n: Counter() for n in NAMED_LESION_CLASSES}
for cid in alvos:
    v = classe[cid]
    cm[v][pred[cid] if cid in pred else "__sem__"] += 1
rec = {n: (cm[n][n] / sum(cm[n].values()) if cm[n] else 0.0) for n in NAMED_LESION_CLASSES}
bal = sum(rec.values()) / 4
top1 = sum(cm[n][n] for n in NAMED_LESION_CLASSES) / len(alvos)
ndet = sum(1 for c in alvos if determinado.get(c))

print()
print("=" * 74)
print("SUBTIPO PELO CAMINHO DE PRODUCAO, NESTED-OOF (fora da amostra)")
print("=" * 74)
print(f"  balanceada 4 classes : {100*bal:.2f}%")
print(f"  top-1                : {100*top1:.2f}%")
print(f"  subtipo determinado  : {ndet}/{len(alvos)} ({100*ndet/len(alvos):.1f}%)")
for n in NAMED_LESION_CLASSES:
    print(f"    {n:14s} {cm[n][n]:3d}/{sum(cm[n].values()):3d}  {100*rec[n]:5.1f}%")
print()
print("  confusao (linha = verdade):")
for n in NAMED_LESION_CLASSES:
    print(f"    {n:14s} -> " + "  ".join(f"{p[:4]}:{cm[n][p]:3d}" for p in NAMED_LESION_CLASSES)
          + f"   sem:{cm[n]['__sem__']}")

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "results.json").write_text(json.dumps({
    "schema": "argos-subtipo-caminho-producao-v1",
    "estimador": "multiclasse 6 classes, agregacao de painel, C e agregacao nos folds internos",
    "avaliacao": "nested-OOF, denominador honesto (sem predicao = erro)",
    "n_alvos": len(alvos), "balanceada": bal, "top1": top1,
    "determinado": ndet, "recalls": rec,
    "confusao": {n: dict(cm[n]) for n in NAMED_LESION_CLASSES},
    "research_only": True, "clinical_use_allowed": False,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nsalvo em {OUT}")
