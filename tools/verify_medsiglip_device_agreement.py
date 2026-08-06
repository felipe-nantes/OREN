#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mede se trocar o dispositivo do MedSigLIP muda alguma DECISÃO.

Por que isto existe: o bundle de produção foi treinado sobre embeddings
extraídos em float16/CUDA. Rodar o mesmo encoder congelado em MPS (Apple
Silicon) produz números próximos, não idênticos. "Próximos" não basta -- o que
importa é se a diferença atravessa o limiar de decisão (0,4749) em algum caso.

O teste é o único que responde isso: reextrai os mesmos painéis com o config
atual, classifica os dois conjuntos com o MESMO bundle congelado, e compara
decisão a decisão. Similaridade de cosseno é reportada como diagnóstico; o
critério de aprovação é concordância de decisão, não de vetor.

Uso no Mac:

    .venv/bin/python tools/verify_medsiglip_device_agreement.py
    .venv/bin/python tools/verify_medsiglip_device_agreement.py --limit 40

Sai com código 1 se qualquer decisão divergir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.learning.medsiglip_embeddings import (  # noqa: E402
    HuggingFaceMedSigLIPBackend,
    load_embedding_config,
)
from dtwin.learning.visual_inference import (  # noqa: E402
    classify_embeddings,
    load_production_bundle,
)

REFERENCE = REPO / "casos/qualification/hybrid_v1/medsiglip_embeddings_stage_a_v1"
PANELS = REPO / "casos/qualification/hybrid_v1/candidate_dataset_stage_a_v1"
BUNDLE = REPO / "casos/qualification/hybrid_v1/medsiglip_multiclass_production_bundle_v1"
DEFAULT_CONFIG = REPO / "configs/training/medsiglip_frozen_mps_v1.yaml"


def _records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="config de embedding a verificar (padrão: MPS)")
    parser.add_argument("--limit", type=int, default=None,
                        help="verificar apenas os N primeiros casos")
    args = parser.parse_args()

    for path, what in ((REFERENCE, "cache de referência"), (PANELS, "painéis"), (BUNDLE, "bundle")):
        if not path.is_dir():
            print(f"ERRO: {what} não encontrado em {path}", file=sys.stderr)
            print("Este verificador exige os artefatos de qualificação locais.", file=sys.stderr)
            return 2

    print("=" * 78)
    print("CONCORDÂNCIA DE DISPOSITIVO DO MedSigLIP — o que muda de DECISÃO?")
    print("=" * 78)

    config = load_embedding_config(args.config)
    print(f"config verificado : {args.config.relative_to(REPO)}")
    print(f"  device          : {config.get('device')}")
    print(f"  dtype           : {config.get('dtype')}")

    reference_manifest = json.loads((REFERENCE / "embedding_manifest.json").read_text(encoding="utf-8"))
    print(f"referência        : {reference_manifest.get('embedding_count')} embeddings congelados")

    panel_records = {
        (r["case_id"], r["candidate_id"]): r
        for r in _records(PANELS / "candidate_records.jsonl")
    }
    by_case: dict[str, list[dict]] = {}
    for record in _records(REFERENCE / "embedding_records.jsonl"):
        by_case.setdefault(str(record["case_id"]), []).append(record)
    cases = sorted(by_case)
    if args.limit is not None:
        cases = cases[: args.limit]
    print(f"casos avaliados   : {len(cases)}")
    print()

    backend = HuggingFaceMedSigLIPBackend(config)
    bundle = load_production_bundle(BUNDLE)

    from PIL import Image

    cosines: list[float] = []
    score_deltas: list[float] = []
    flips: list[dict] = []
    subtype_flips: list[dict] = []
    skipped = 0

    for index, case_id in enumerate(cases, 1):
        rows = sorted(by_case[case_id], key=lambda r: str(r["candidate_id"]))
        reference_vectors, new_vectors = [], []
        for row in rows:
            key = (str(row["case_id"]), str(row["candidate_id"]))
            panel = panel_records.get(key)
            if panel is None:
                continue
            image_path = REPO / str(panel["image_path"])
            reference_path = REFERENCE / str(row["embedding_path"])
            if not image_path.is_file() or not reference_path.is_file():
                continue
            with Image.open(image_path) as handle:
                vector = backend.embed([handle.convert("RGB")])[0]
            reference_vectors.append(np.load(reference_path).astype(np.float64))
            new_vectors.append(np.asarray(vector, dtype=np.float64))
        if not reference_vectors:
            skipped += 1
            continue

        reference_matrix = np.stack(reference_vectors)
        new_matrix = np.stack(new_vectors)
        for a, b in zip(reference_vectors, new_vectors):
            cosines.append(float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))

        reference_decision = classify_embeddings(bundle, reference_matrix)
        new_decision = classify_embeddings(bundle, new_matrix)
        score_deltas.append(abs(float(reference_decision["score"]) - float(new_decision["score"])))
        if reference_decision["prediction"] != new_decision["prediction"]:
            flips.append({
                "case_id": case_id,
                "referencia": reference_decision["prediction"],
                "novo": new_decision["prediction"],
                "score_referencia": round(float(reference_decision["score"]), 6),
                "score_novo": round(float(new_decision["score"]), 6),
            })
        reference_subtype = (reference_decision.get("subtype") or {}).get("subtype")
        new_subtype = (new_decision.get("subtype") or {}).get("subtype")
        if reference_subtype != new_subtype:
            subtype_flips.append({
                "case_id": case_id, "referencia": reference_subtype, "novo": new_subtype,
            })
        if index % 20 == 0 or index == len(cases):
            print(f"  {index}/{len(cases)} casos  |  decisões divergentes: {len(flips)}", flush=True)

    print()
    print("-" * 78)
    print("DIAGNÓSTICO (não é o critério de aprovação)")
    print("-" * 78)
    if cosines:
        array = np.asarray(cosines)
        print(f"  similaridade de cosseno por painel : mín {array.min():.6f}  mediana {np.median(array):.6f}")
    if score_deltas:
        deltas = np.asarray(score_deltas)
        print(f"  |Δ| do score de triagem por caso   : máx {deltas.max():.6f}  mediana {np.median(deltas):.6f}")
        print(f"  (limiar de decisão do bundle       : {bundle.threshold:.6f})")
    if skipped:
        print(f"  casos sem painel local disponível  : {skipped}")

    print()
    print("=" * 78)
    print("CRITÉRIO DE APROVAÇÃO — concordância de decisão")
    print("=" * 78)
    print(f"  decisões binárias divergentes : {len(flips)}")
    print(f"  subtipos divergentes          : {len(subtype_flips)}")
    for row in flips[:10]:
        print(f"    BINÁRIO {row['case_id']}: {row['referencia']} -> {row['novo']} "
              f"(score {row['score_referencia']} -> {row['score_novo']})")
    for row in subtype_flips[:10]:
        print(f"    SUBTIPO {row['case_id']}: {row['referencia']} -> {row['novo']}")

    print()
    if flips or subtype_flips:
        print("  REPROVADO. Este dispositivo muda decisões em relação à referência.")
        print("  Os números do protocolo NÃO se transferem para este caminho sem")
        print("  uma remedição própria. Não apresente métricas de CUDA como se")
        print("  valessem aqui.")
        return 1
    print("  APROVADO. Nenhuma decisão mudou nos casos verificados.")
    print("  Isso não é prova de equivalência universal -- é evidência de que, na")
    print("  amostra verificada, a troca de dispositivo não atravessa o limiar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
