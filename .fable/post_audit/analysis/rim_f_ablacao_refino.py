# -*- coding: utf-8 -*-
"""RIM-01 fase F — ablação do refino (achado do braço CHAOS-MR).

Teste direto da hipótese: a razão de volume baixa em RM (mediana 0,665
no braço chaos_mr) vem da erosão morfológica (opening, radius=2 VOXELS)
do refino, que corresponde a ~3mm no voxel grosso do CHAOS-MR (1,44mm
in-plane) contra ~1mm no voxel fino do KiTS (~0,5-0,92mm) — hipótese
registrada após ver KiTS ter razão muito melhor (0,847) com o MESMO
refino. Roda a MESMA segmentação bruta (TS total_mr, uma vez por caso)
e compara 3 variantes de refino sobre a mesma máscara bruta: produção
(opening radius=2), sem abertura (opening=False), e abertura leve
(radius=1) — nos 3 piores casos do braço primário (33, 36, 5).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.stages import _refine_mask  # noqa: E402

DADOS = Path(r"C:\datasets_ct\CHAOS_MR\Train_Sets\MR")
PY = str(RAIZ / ".venv-win" / "Scripts" / "python.exe")
TS_UM = str(RAIZ / ".fable/post_audit/analysis/rim_f_ts_um_caso.py")
CASOS = ["33", "36", "5"]
VARIANTES = {
    "producao_opening_r2": {"opening": True, "radius": 2, "min_voxels": 300},
    "sem_abertura": {"opening": False, "radius": 2, "min_voxels": 300},
    "abertura_leve_r1": {"opening": True, "radius": 1, "min_voxels": 300},
}


def _dice(a, b) -> float:
    inter = float(np.logical_and(a, b).sum())
    s = float(a.sum() + b.sum())
    return (2.0 * inter / s) if s else 0.0


def main() -> None:
    from PIL import Image

    for caso in CASOS:
        caso_dir = DADOS / caso
        pngs = sorted((caso_dir / "T1DUAL" / "Ground").glob("*.png"))
        rotulos = np.stack([np.array(Image.open(p)) for p in pngs])
        ref_uniao = ((rotulos > 100) & (rotulos < 160)) | ((rotulos > 160) & (rotulos < 220))

        fase_dir = caso_dir / "T1DUAL" / "DICOM_anon" / "InPhase"
        reader = sitk.ImageSeriesReader()
        arquivos = reader.GetGDCMSeriesFileNames(str(fase_dir))
        reader.SetFileNames(arquivos)
        vol = reader.Execute()
        voxel_ml = float(np.prod(vol.GetSpacing())) / 1000.0

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            vol_path = tmp / "volume.nii.gz"
            sitk.WriteImage(vol, str(vol_path))
            seg_dir = tmp / "seg"
            seg_dir.mkdir()
            proc = subprocess.run(
                [PY, TS_UM, str(vol_path), str(seg_dir), "total_mr"],
                cwd=RAIZ, capture_output=True, text=True, timeout=1800,
            )
            if proc.returncode != 0:
                print(f"{caso}: TS falhou rc={proc.returncode}: {proc.stderr[-200:]}")
                continue
            esq = sitk.GetArrayFromImage(sitk.ReadImage(str(seg_dir / "kidney_left.nii.gz"))) > 0
            dir_ = sitk.GetArrayFromImage(sitk.ReadImage(str(seg_dir / "kidney_right.nii.gz"))) > 0
        bruto = esq | dir_

        # ordem-z: mesma resolução do braço primário (maior Dice da MÁSCARA BRUTA)
        d_direto = _dice(bruto, ref_uniao)
        d_flip = _dice(bruto, ref_uniao[::-1])
        ref = ref_uniao[::-1] if d_flip > d_direto else ref_uniao

        vol_ref_ml = float(ref.sum()) * voxel_ml
        vol_bruto_ml = float(bruto.sum()) * voxel_ml
        print(json.dumps({
            "caso": caso, "variante": "bruto_sem_refino",
            "vol_ml": round(vol_bruto_ml, 1), "vol_ref_ml": round(vol_ref_ml, 1),
            "razao": round(vol_bruto_ml / vol_ref_ml, 4),
            "dice": round(_dice(bruto, ref), 4),
        }, ensure_ascii=False), flush=True)
        for nome, params in VARIANTES.items():
            m = _refine_mask(bruto, **params)
            vol_ml = float(m.sum()) * voxel_ml
            print(json.dumps({
                "caso": caso, "variante": nome,
                "vol_ml": round(vol_ml, 1), "vol_ref_ml": round(vol_ref_ml, 1),
                "razao": round(vol_ml / vol_ref_ml, 4) if vol_ref_ml else None,
                "dice": round(_dice(m, ref), 4),
            }, ensure_ascii=False), flush=True)
    print("ABLACAO_COMPLETA", flush=True)


if __name__ == "__main__":
    main()
