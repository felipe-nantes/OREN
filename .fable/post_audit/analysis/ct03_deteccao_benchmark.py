# -*- coding: utf-8 -*-
"""CT-03 fase C — benchmark de DETECÇÃO de lesão em TC (pré-registrado).

Plano aprovado pelo operador em 2026-08-28 (CT-03; meta ≥75% sens e
≥75% spec, com tipo condicional medido na fase E).

SISTEMA SOB TESTE: o detector de candidato do CT-03 — TotalSegmentator
task `liver_lesions` (Dataset591) via o caminho DE PRODUÇÃO
(dtwin.candidate_region: crop no fígado, clip, componentes conexos).

DESENHO PRÉ-REGISTRADO (antes de qualquer execução):
- O runner NÃO decide POSITIVA/NEGATIVA: ele mede grandezas contínuas por
  caso (volume total de candidato, nº de componentes, maior componente).
  O LIMIAR de decisão será tunado SÓ nos braços de TREINO (tcia_*_train +
  chaos_tuning) e congelado em evidence ANTES de abrir os braços de teste
  — análise separada (ct03_deteccao_metricas.py).
- BRAÇOS:
  * chaos_tuning: CHAOS-CT com nº de caso PAR   (n≈10, NEGATIVA, tuning)
  * chaos_teste:  CHAOS-CT com nº de caso ÍMPAR (n≈10, NEGATIVA, teste)
    (split determinístico por paridade, pré-registrado; IC largo declarado)
  * tcia_hcc_teste / tcia_crlm_teste: 40+40 do teste congelado (POSITIVA)
  * tcia_hcc_train / tcia_crlm_train: coortes de treino no D: (POSITIVA)
  * msd: 131 casos (POSITIVA) — SECUNDÁRIO: o Dataset591 (842 sujeitos,
    origem não publicada) pode conter LiTS/MSD; contaminação declarada.
- Work-dirs PRESERVADOS em D:\\datasets_ct\\_ct03_work (volume +
  mask_organ + candidato) — são a fábrica de insumos da fase D (tipo).
- Execução: TS total e liver_lesions em SUBPROCESSO por caso (isolamento
  de memória; lições do CT01-F), JSONL resumível, temp dedicado.

Args: [chaos|teste|train|msd|all] [limite]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.stages import _refine_mask  # noqa: E402  (refino DE PRODUÇÃO)

DADOS_C = Path(r"C:\datasets_ct")
DADOS_D = Path(r"D:\datasets_ct")
TRABALHO = DADOS_D / "_ct03_work"
SAIDA = RAIZ / ".fable/post_audit/evidence/CT03"
SAIDA.mkdir(parents=True, exist_ok=True)
PY = str(RAIZ / ".venv-win" / "Scripts" / "python.exe")
TS_UM = str(Path(__file__).with_name("ct01_ts_um_caso.py"))
CAND_UM = str(Path(__file__).with_name("ct03_candidato_um_caso.py"))
REFINO = {"opening": True, "radius": 2, "min_voxels": 300}
FEITOS: set[tuple[str, str]] = set()

_TMP = TRABALHO / "_tmp"
_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = os.environ["TEMP"] = str(_TMP)
tempfile.tempdir = str(_TMP)


def _um_caso(caso: str, braco: str, ground_truth: str, volume_fonte,
             work: Path) -> dict:
    """volume_fonte: Path de NIfTI OU diretório DICOM."""
    t0 = time.monotonic()
    registro: dict = {"braco": braco, "caso": caso, "ground_truth": ground_truth}
    try:
        work.mkdir(parents=True, exist_ok=True)
        vol_path = work / "volume.nii.gz"
        if not vol_path.is_file():
            fonte = Path(volume_fonte)
            if fonte.is_dir():
                reader = sitk.ImageSeriesReader()
                arquivos = reader.GetGDCMSeriesFileNames(str(fonte))
                if not arquivos:
                    registro.update(status="failed", motivo="sem_serie_dicom")
                    return registro
                reader.SetFileNames(arquivos)
                sitk.WriteImage(reader.Execute(), str(vol_path))
            else:
                sitk.WriteImage(sitk.ReadImage(str(fonte)), str(vol_path))

        mask_path = work / "mask_organ.nii.gz"
        if not mask_path.is_file():
            seg = work / "seg"
            proc = subprocess.run([PY, TS_UM, str(vol_path), str(seg)],
                                  cwd=RAIZ, capture_output=True, text=True,
                                  timeout=1800)
            liver = seg / "liver.nii.gz"
            if proc.returncode != 0 or not liver.is_file():
                registro.update(status="failed",
                                motivo=f"ts_total rc={proc.returncode}: "
                                       f"{(proc.stderr or '')[-200:]}")
                return registro
            liver_img = sitk.ReadImage(str(liver))
            m = _refine_mask(sitk.GetArrayFromImage(liver_img) > 0, **REFINO)
            if not m.any():
                registro.update(status="failed", motivo="mascara_figado_vazia")
                return registro
            mask_img = sitk.GetImageFromArray(m.astype(np.uint8))
            mask_img.CopyInformation(liver_img)
            sitk.WriteImage(mask_img, str(mask_path))

        manifest_path = work / "candidate_region.json"
        if not manifest_path.is_file():
            (work / "candidate_request.json").write_text(json.dumps({
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
            proc = subprocess.run([PY, CAND_UM, str(work)],
                                  cwd=RAIZ, capture_output=True, text=True,
                                  timeout=1800)
            if proc.returncode != 0 or not manifest_path.is_file():
                registro.update(status="failed",
                                motivo=f"candidato rc={proc.returncode}: "
                                       f"{(proc.stderr or '')[-250:]}")
                return registro
        cand = json.loads(manifest_path.read_text(encoding="utf-8"))
        componentes = cand.get("components") or []
        registro.update(
            status="ok",
            candidate_present=bool(cand.get("candidate_present")),
            component_count=int(cand.get("component_count") or 0),
            total_candidate_volume_mm3=float(
                cand.get("total_candidate_volume_mm3") or 0.0),
            maior_componente_mm3=(
                float(componentes[0]["volume_mm3"]) if componentes else 0.0),
            maior_diametro_mm=(
                float(componentes[0].get("equivalent_diameter_mm") or 0.0)
                if componentes else 0.0),
            segundos=round(time.monotonic() - t0, 1),
        )
    except Exception as exc:
        registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:250])
    return registro


def casos_chaos(qual: str):
    base = DADOS_C / "CHAOS_CT" / "Train_Sets" / "CT"
    for caso_dir in sorted(base.iterdir(), key=lambda p: int(p.name)):
        n = int(caso_dir.name)
        braco = "chaos_tuning" if n % 2 == 0 else "chaos_teste"
        if qual != "all" and braco != qual:
            continue
        if (braco, caso_dir.name) in FEITOS:
            continue
        yield caso_dir.name, braco, "NEGATIVA", caso_dir / "DICOM_anon", \
            TRABALHO / f"chaos_{caso_dir.name}"


def casos_tcia(pasta: Path, braco: str):
    if not pasta.is_dir():
        return
    for pac in sorted(p for p in pasta.iterdir() if p.is_dir()):
        if (braco, pac.name) in FEITOS:
            continue
        dcm = sorted(pac.rglob("*.dcm"))
        if not dcm:
            continue
        yield pac.name, braco, "POSITIVA", dcm[0].parent, \
            TRABALHO / f"{braco}_{pac.name}"


def casos_msd():
    base = DADOS_C / "Task03_Liver" / "imagesTr"
    for img in sorted(base.glob("*.nii.gz")):
        caso = img.name.replace(".nii.gz", "")
        if ("msd", caso) in FEITOS:
            continue
        yield caso, "msd", "POSITIVA", img, TRABALHO / f"msd_{caso}"


def main() -> None:
    quais = sys.argv[1] if len(sys.argv) > 1 else "all"
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    jsonl = SAIDA / "ct03_deteccao_resultados.jsonl"
    if jsonl.is_file():
        for ln in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if "anulado" in r:
                FEITOS.discard(tuple(r["anulado"]))
            elif r.get("status") == "ok":
                FEITOS.add((r["braco"], r["caso"]))

    fontes = []
    if quais in ("all", "chaos"):
        fontes.append(casos_chaos("all"))
    elif quais in ("chaos_tuning", "chaos_teste"):
        fontes.append(casos_chaos(quais))
    if quais in ("all", "train"):
        fontes.append(casos_tcia(DADOS_D / "TCIA_HCC_TRAIN", "tcia_hcc_train"))
        fontes.append(casos_tcia(DADOS_D / "TCIA_CRLM_TRAIN", "tcia_crlm_train"))
    if quais in ("all", "teste"):
        fontes.append(casos_tcia(DADOS_C / "TCIA_HCC", "tcia_hcc_teste"))
        fontes.append(casos_tcia(DADOS_C / "TCIA_CRLM", "tcia_crlm_teste"))
    if quais in ("all", "msd"):
        fontes.append(casos_msd())

    n = 0
    for fonte in fontes:
        for caso, braco, gt, fonte_vol, work in fonte:
            registro = _um_caso(caso, braco, gt, fonte_vol, work)
            with jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            print(json.dumps(registro, ensure_ascii=False), flush=True)
            n += 1
            if limite and n >= limite:
                print(f"LIMITE {limite} atingido", flush=True)
                return
    print("CT03_DETECCAO_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
