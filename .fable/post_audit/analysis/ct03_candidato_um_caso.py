# -*- coding: utf-8 -*-
"""Executa UMA localização de candidato TC isolada em subprocesso (CT-03).

Mesmo motivo do ct01_ts_um_caso.py: o runner de benchmark é um processo
longo e o TS in-process acumula memória até WinError 1455. O caso recebe
o request com task liver_lesions e produz candidate_region.json +
mask_candidate.nii.gz via dtwin.candidate_region (caminho de produção).

Uso: python ct03_candidato_um_caso.py <case_dir>
(case_dir precisa conter volume.nii.gz, mask_organ.nii.gz e
candidate_request.json)
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))


def main() -> None:
    case_dir = Path(sys.argv[1])
    from dtwin.candidate_region import generate_candidate_region

    generate_candidate_region(
        case_dir, device="gpu",
        request_path=case_dir / "candidate_request.json",
    )


if __name__ == "__main__":
    main()
