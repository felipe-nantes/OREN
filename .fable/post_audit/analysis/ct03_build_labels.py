# -*- coding: utf-8 -*-
"""CT-03 fase D.1 — labels protegidos por DIAGNÓSTICO DE COORTE (TCIA).

Gera os arquivos de labels do classificador de tipo TC:
- casos/qualification/ct03_v1/protected_ground_truth/labels.jsonl (TREINO)
- casos/qualification/ct03_v1/holdout_test_labels/labels.jsonl (TESTE
  congelado 40+40 — usado SÓ pela avaliação externa, nunca pelo treino)

Proveniência dos labels: diagnóstico por construção da coorte —
HCC-TACE-Seg = hcc (doi:10.7937/TCIA.5FNA-0924); Colorectal-Liver-
Metastases = metastasis (doi:10.7937/QXK2-QG03). CC-BY 4.0. A seleção de
pacientes/séries é a MESMA regra pré-registrada do CT01-F (ordem
lexicográfica de PatientID; primeiros 40 = teste, resto = treino; série
de maior ImageCount por paciente).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

BASE = Path(r"C:\datasets_ct")
DESTINO = RAIZ / "casos/qualification/ct03_v1"
N_TESTE = 40
COORTES = {
    "HCC": {
        "series_json": BASE / "_hcc_series.json",
        "clinical_subtype": "hcc",
        "positive_subtype": "hcc_suspicious",
        "doi": "10.7937/TCIA.5FNA-0924",
        "colecao": "HCC-TACE-Seg",
    },
    "CRLM": {
        "series_json": BASE / "_crlm_series.json",
        "clinical_subtype": "metastasis",
        "positive_subtype": "metastasis_suspicious",
        "doi": "10.7937/QXK2-QG03",
        "colecao": "Colorectal-Liver-Metastases",
    },
}


def _pacientes(series_json: Path) -> list[str]:
    dados = json.loads(series_json.read_text(encoding="utf-8"))
    return sorted({s["PatientID"] for s in dados if s.get("Modality") == "CT"})


def _linha(pid: str, spec: dict) -> dict:
    return {
        "schema": "argos-protected-training-label-v1",
        "case_id": pid,
        "patient_group_id": pid,
        "dataset_id": "tcia_ct_type_v1",
        "label": "POSITIVE",
        "positive_subtype": spec["positive_subtype"],
        "clinical_subtype": spec["clinical_subtype"],
        "label_provenance": (
            f"diagnóstico por construção da coorte TCIA {spec['colecao']} "
            f"(doi:{spec['doi']}, CC-BY 4.0)"
        ),
        "research_only": True,
        "clinical_use_allowed": False,
    }


def main() -> None:
    treino: list[dict] = []
    teste: list[dict] = []
    for spec in COORTES.values():
        pacientes = _pacientes(spec["series_json"])
        for i, pid in enumerate(pacientes):
            (teste if i < N_TESTE else treino).append(_linha(pid, spec))
    for nome, linhas in (("protected_ground_truth", treino),
                        ("holdout_test_labels", teste)):
        pasta = DESTINO / nome
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / "labels.jsonl"
        if destino.exists():
            print(f"{destino} já existe — imutável, não sobrescrevo")
            continue
        with destino.open("w", encoding="utf-8", newline="\n") as f:
            for linha in sorted(linhas, key=lambda r: r["case_id"]):
                f.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"{destino}: {len(linhas)} casos")
    resumo = {
        "treino": len(treino), "teste": len(teste),
        "regra": "primeiros 40 PatientID lexicograficos por coorte = teste "
                 "congelado (mesma selecao pre-registrada do CT01-F)",
    }
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
