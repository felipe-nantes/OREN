#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mede continuidade vascular (veia porta/esplenica + veia cava inferior) nos
candidatos da shortlist de experiments/liver_integrity_ranking_v1/results.json
(15 melhores + 15 piores por integridade hepatica, ja calculada a custo zero).

So roda TotalSegmentator nesses ~30 casos (nao nos 321) -- o mesmo padrao de
funil caro-so-na-shortlist usado em tools/measure_four_phase_union_gain.py.

Cada rotulo (portal_vein_and_splenic_vein, inferior_vena_cava) e' medido com
os mesmos atributos ja validados para o figado em docs/188: componentes
conexos e fracao do maior componente -- fragmentacao vascular e' o analogo
direto do que a "sindrome" mediu para o figado.

Uso:
    .venv-win/Scripts/python.exe tools/measure_vessel_continuity_shortlist.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import isolated_total_mr_liver_segmenter  # noqa: E402

RANKING = REPO / "experiments/liver_integrity_ranking_v1/results.json"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
SAIDA = REPO / "experiments/vessel_continuity_shortlist_v1"
WORKER = REPO / "tools/vessel_continuity_segment_worker.py"


def continuidade(mask_path: Path) -> dict | None:
    if not mask_path.is_file():
        return None
    image = sitk.ReadImage(str(mask_path))
    array = sitk.GetArrayFromImage(image) > 0
    voxels = int(array.sum())
    if voxels == 0:
        return {"presente": False, "voxels": 0}
    labelled, n = ndimage.label(array)
    sizes = np.bincount(labelled.ravel())[1:]
    return {
        "presente": True,
        "voxels": voxels,
        "componentes": int(n),
        "fracao_maior_componente": round(float(sizes.max() / sizes.sum()), 4),
    }


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks").mkdir(exist_ok=True)
    destino_json = SAIDA / "results.json"
    feitos = json.loads(destino_json.read_text("utf-8")) if destino_json.is_file() else {}

    ranking = json.loads(RANKING.read_text("utf-8"))
    candidatos = sorted(set(
        ranking["shortlist_melhores_case_ids"] + ranking["shortlist_piores_case_ids"]
    ))

    print("=" * 78)
    print("CONTINUIDADE VASCULAR NA SHORTLIST -- veia porta/esplenica + cava inferior")
    print("=" * 78)
    print(f"candidatos: {len(candidatos)} (15 melhores + 15 piores por integridade hepatica)\n")

    for i, case_id in enumerate(candidatos, 1):
        if case_id in feitos and "erro" not in feitos[case_id]:
            continue
        fonte = ENTRADAS / case_id / "t1_venous.nii.gz"
        if not fonte.is_file():
            feitos[case_id] = {"erro": "t1_venous ausente"}
            destino_json.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
            continue
        print(f"[{i}/{len(candidatos)}] {case_id}", flush=True)
        liver_out = SAIDA / "masks" / f"{case_id}_liver.nii.gz"
        try:
            receipt = isolated_total_mr_liver_segmenter(
                fonte, liver_out, device="gpu", fast=False, timeout_seconds=600,
                worker_path=WORKER,
            )
        except Exception as exc:  # noqa: BLE001
            feitos[case_id] = {"erro": str(exc)}
            destino_json.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"    falhou: {exc}", flush=True)
            continue

        base = f"{case_id}"
        portal_path = SAIDA / "masks" / f"{base}_portal_vein_and_splenic_vein.nii.gz"
        cava_path = SAIDA / "masks" / f"{base}_inferior_vena_cava.nii.gz"
        registro = {
            "receipt": {k: v for k, v in receipt.items() if k != "roi_subset"},
            "portal_vein_and_splenic_vein": continuidade(portal_path),
            "inferior_vena_cava": continuidade(cava_path),
        }
        feitos[case_id] = registro
        destino_json.write_text(json.dumps(feitos, indent=1, ensure_ascii=False), encoding="utf-8")
        pv = registro["portal_vein_and_splenic_vein"] or {}
        cv = registro["inferior_vena_cava"] or {}
        print(f"    porta: comp={pv.get('componentes')} frac={pv.get('fracao_maior_componente')}   "
              f"cava: comp={cv.get('componentes')} frac={cv.get('fracao_maior_componente')}", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    print(f"\nfeito: {len(validos)}/{len(candidatos)} validos")
    print(f"salvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
