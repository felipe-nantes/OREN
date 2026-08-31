# -*- coding: utf-8 -*-
"""Smoke do detector de lesão TC (CT-03 fase B): 2 casos HCC reais.

Por caso: DICOM→volume → TS total (subprocesso, helper do CT01-F) →
refino de produção → mask_organ → request com task liver_lesions →
dtwin.candidate_region.generate_candidate_region → imprime o manifesto.
Work-dirs preservados em C:/datasets_ct/_bench_work/ct03_smoke_* para
inspeção no viewer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.candidate_region import generate_candidate_region  # noqa: E402
from dtwin.stages import _refine_mask  # noqa: E402

PY = str(RAIZ / ".venv-win" / "Scripts" / "python.exe")
TS_UM = str(RAIZ / ".fable" / "post_audit" / "analysis" / "ct01_ts_um_caso.py")
CASOS = ["HCC_001", "HCC_003"]
REFINO = {"opening": True, "radius": 2, "min_voxels": 300}


def main() -> None:
    for pid in CASOS:
        t0 = time.monotonic()
        origem = Path(r"C:\datasets_ct\TCIA_HCC") / pid
        work = Path(r"C:\datasets_ct\_bench_work") / f"ct03_smoke_{pid}"
        work.mkdir(parents=True, exist_ok=True)
        dcm = sorted(origem.rglob("*.dcm"))
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(dcm[0].parent)))
        vol = reader.Execute()
        vol_path = work / "volume.nii.gz"
        sitk.WriteImage(vol, str(vol_path))

        seg = work / "seg"
        proc = subprocess.run([PY, TS_UM, str(vol_path), str(seg)],
                              cwd=RAIZ, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            print(f"{pid}: TS total falhou rc={proc.returncode}: "
                  f"{(proc.stderr or '')[-200:]}", flush=True)
            continue
        liver_img = sitk.ReadImage(str(seg / "liver.nii.gz"))
        m = _refine_mask(sitk.GetArrayFromImage(liver_img) > 0, **REFINO)
        mask_img = sitk.GetImageFromArray(m.astype(np.uint8))
        mask_img.CopyInformation(liver_img)
        sitk.WriteImage(mask_img, str(work / "mask_organ.nii.gz"))

        req = work / "candidate_request.json"
        req.write_text(json.dumps({
            "schema": "argos-candidate-request-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "modality": "CT",
            "task": "liver_lesions",
            "screening_decision_frozen": True,
            "prediction": "not_applicable_ct_detector_is_primary_reader",
            "used_by_screening_inference": False,
            "ground_truth_included": False,
            "research_only": True,
        }, indent=2), encoding="utf-8")
        try:
            resultado = generate_candidate_region(work, device="gpu", request_path=req)
            print(json.dumps({
                "caso": pid,
                "status": resultado.get("status"),
                "candidate_present": resultado.get("candidate_present"),
                "component_count": resultado.get("component_count"),
                "total_candidate_volume_mm3": resultado.get("total_candidate_volume_mm3"),
                "task": resultado.get("task"),
                "model_version": resultado.get("model_version"),
                "segundos": round(time.monotonic() - t0, 1),
            }, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(f"{pid}: DETECTOR FALHOU {type(exc).__name__}: {exc}", flush=True)
    print("SMOKE_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
