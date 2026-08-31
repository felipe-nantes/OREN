# -*- coding: utf-8 -*-
"""CT-03 fase D.2 — manifesto label-blind + dataset de cortes axiais (TC).

Insumos: work-dirs preservados do benchmark de detecção
(D:\\datasets_ct\\_ct03_work\\tcia_*_train_<PatientID>\\{volume.nii.gz,
mask_organ.nii.gz}). O manifesto declara ground_truth_read=False e
lesion_mask_present=False (a máscara é do FÍGADO, produzida pelo TS sem
labels) — prova de cegueira exigida por is_proven_label_blind_input.

Saída imutável: casos/qualification/ct03_v1/prepared/slice_candidates_v1
via dtwin.learning.monophase_slice_candidates (renderização 448x448,
janela de intensidade percentil 1/99 dentro do fígado, bbox+margem —
caminho agnóstico a modalidade, v1 do plano CT-03).

Uso: python ct03_build_slices.py [limite_casos]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.core import sha256_of  # noqa: E402
from dtwin.learning.monophase_slice_candidates import (  # noqa: E402
    build_monophase_slice_candidates,
)

WORK = Path(r"D:\datasets_ct\_ct03_work")
MANIFESTO = Path(r"C:\datasets_ct\_ct03_slices_input.jsonl")
SAIDA = RAIZ / "casos/qualification/ct03_v1/prepared/slice_candidates_v1"
PROTOCOLO = RAIZ / "configs/training/ct03_ct_type_protocol_v1.lock.json"
SPLITS = RAIZ / "configs/training/ct03_ct_type_nested_splits.json"


def montar_manifesto() -> int:
    linhas = []
    for prefixo in ("tcia_hcc_train_", "tcia_crlm_train_"):
        for pasta in sorted(WORK.glob(f"{prefixo}*")):
            volume = pasta / "volume.nii.gz"
            mask = pasta / "mask_organ.nii.gz"
            if not (volume.is_file() and mask.is_file()):
                continue
            case_id = pasta.name[len(prefixo):]
            linhas.append({
                "case_id": case_id,
                "ground_truth_read": False,
                "lesion_mask_present": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "files": [
                    {"role": "ct_portal",
                     "relative_path": f"{pasta.name}/volume.nii.gz",
                     "sha256": sha256_of(volume)},
                    {"role": "liver_mask_ct",
                     "relative_path": f"{pasta.name}/mask_organ.nii.gz",
                     "sha256": sha256_of(mask)},
                ],
            })
    with MANIFESTO.open("w", encoding="utf-8", newline="\n") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
    return len(linhas)


def main() -> None:
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = montar_manifesto()
    print(f"manifesto: {n} casos com volume+mascara prontos", flush=True)
    if n == 0:
        print("nada a renderizar ainda (aguarde a campanha de deteccao)")
        return
    resultado = build_monophase_slice_candidates(
        input_manifest_path=MANIFESTO,
        input_files_root=WORK,
        protocol_path=PROTOCOLO,
        splits_path=SPLITS,
        workspace_root=RAIZ,
        output_root=SAIDA,
        dataset_id="tcia_ct_type_v1",
        phase_role="ct_portal",
        liver_mask_role="liver_mask_ct",
        limit_cases=limite,
    )
    print(json.dumps({k: resultado.get(k) for k in
                      ("candidate_count", "case_count", "failure_count",
                       "dataset_signature") if k in resultado},
                     ensure_ascii=False), flush=True)
    print("SLICES_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
