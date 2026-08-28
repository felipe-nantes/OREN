# -*- coding: utf-8 -*-
"""CT-01-F — benchmark volumétrico do modo CT contra referência humana.

PROTOCOLO PRÉ-REGISTRADO (antes de qualquer execução; autorização do
operador 2026-08-27: "Faca o reparo e prossiga com o benchmark").

O QUE está sob teste: a segmentação hepática do MODO CT do OREN —
TotalSegmentator task `total`, fast=False (mesmos argumentos do caminho de
exame individual em stages.py stage3) + o refino do órgão DE PRODUÇÃO
(`dtwin.stages._refine_mask`, importado, com os parâmetros do
profiles/figado_ct.yaml: opening=True, radius=2, min_voxels=300).

BRAÇOS:
- CHAOS-CT (n=20, fígado saudável): DICOM em C:/datasets_ct/CHAOS_CT;
  referência = máscaras Ground por corte (PNG). Réplica do braço saudável
  do protocolo Volyrics (docs/249 daquele repo).
- MSD Task03_Liver (n=131, com tumores): NIfTI + labels (1=fígado,
  2=tumor; fígado completo = label>=1). AMPLIA o braço tumoral do Volyrics
  (n=20 IRCAD) para toda a coorte de treino do MSD — pré-registrado como
  TODOS os 131 casos, sem seleção.

ENDPOINTS (pré-registrados):
- Primários: razão volume-predito/volume-referência por caso (mediana e
  IQR por braço); Dice fígado.
- Secundários (MSD): Spearman entre |1-razão| e carga tumoral
  (vol_tumor/vol_fígado); enriquecimento de tumor no volume perdido
  (fração de voxels de tumor em ref\\pred ÷ fração de tumor na ref).
- Falhas: caso em que a segmentação não produz fígado = registrado como
  falha, no denominador.

DECISÕES DE MÉTODO (declaradas):
- CHAOS: alinhamento PNG↔DICOM resolvido deterministicamente testando as
  duas ordens de z e mantendo a de maior Dice (a ordem dos PNGs vs posição
  física varia por convenção de exportação; a escolha é reportada por caso).
- Sem qualquer correção de volume (correcao_aplicada=False, princípio D5).
- Nada de RM é tocado; nenhum contrato congelado participa.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.stages import _refine_mask  # noqa: E402  (refino DE PRODUÇÃO)

DADOS = Path(r"C:\datasets_ct")
SAIDA = RAIZ / ".fable/post_audit/evidence/CT01-F"
SAIDA.mkdir(parents=True, exist_ok=True)

REFINO = {"opening": True, "radius": 2, "min_voxels": 300}  # figado_ct.yaml


def _segmenta_figado(volume_path: Path, tmp: Path) -> "np.ndarray | None":
    """TS task=total fast=False (args do stage3) -> máscara refinada (zyx)."""
    from totalsegmentator.python_api import totalsegmentator

    seg_dir = tmp / "seg"
    seg_dir.mkdir(parents=True, exist_ok=True)
    totalsegmentator(
        input=str(volume_path), output=str(seg_dir), task="total",
        device="gpu", fast=False, quiet=True,
    )
    liver = seg_dir / "liver.nii.gz"
    if not liver.is_file():
        return None
    m = sitk.GetArrayFromImage(sitk.ReadImage(str(liver))) > 0
    return _refine_mask(m, **REFINO)


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    s = float(a.sum() + b.sum())
    return (2.0 * inter / s) if s else 0.0


def braco_chaos() -> list[dict]:
    from PIL import Image

    base = DADOS / "CHAOS_CT" / "Train_Sets" / "CT"
    resultados = []
    for caso_dir in sorted(base.iterdir(), key=lambda p: int(p.name)):
        caso = caso_dir.name
        t0 = time.monotonic()
        registro: dict = {"braco": "chaos_ct", "caso": caso}
        try:
            reader = sitk.ImageSeriesReader()
            arquivos = reader.GetGDCMSeriesFileNames(str(caso_dir / "DICOM_anon"))
            reader.SetFileNames(arquivos)
            vol = reader.Execute()
            espacamento = vol.GetSpacing()
            voxel_ml = float(np.prod(espacamento)) / 1000.0

            pngs = sorted((caso_dir / "Ground").glob("*.png"))
            ref_stack = np.stack([
                np.array(Image.open(p)) > 0 for p in pngs
            ]).astype(bool)

            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                vol_path = tmp / "volume.nii.gz"
                sitk.WriteImage(vol, str(vol_path))
                pred = _segmenta_figado(vol_path, tmp)
            if pred is None or not pred.any():
                registro.update(status="failed", motivo="sem_mascara_de_figado")
                resultados.append(registro)
                continue
            if pred.shape != ref_stack.shape:
                registro.update(status="failed",
                                motivo=f"shape pred{pred.shape} != ref{ref_stack.shape}")
                resultados.append(registro)
                continue
            # ordem de z do Ground: determinística pela maior sobreposição
            d_direto = _dice(pred, ref_stack)
            d_flip = _dice(pred, ref_stack[::-1])
            if d_flip > d_direto:
                ref, ordem = ref_stack[::-1], "z_invertido"
                dice = d_flip
            else:
                ref, ordem = ref_stack, "z_direto"
                dice = d_direto
            vol_pred = float(pred.sum()) * voxel_ml
            vol_ref = float(ref.sum()) * voxel_ml
            registro.update(
                status="ok", ordem_z=ordem, dice=round(dice, 4),
                vol_pred_ml=round(vol_pred, 1), vol_ref_ml=round(vol_ref, 1),
                razao=round(vol_pred / vol_ref, 4) if vol_ref else None,
                segundos=round(time.monotonic() - t0, 1),
            )
        except Exception as exc:
            registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:200])
        resultados.append(registro)
        print(json.dumps(registro, ensure_ascii=False), flush=True)
    return resultados


def braco_msd() -> list[dict]:
    base = DADOS / "Task03_Liver"
    resultados = []
    for img_path in sorted((base / "imagesTr").glob("*.nii.gz")):
        caso = img_path.name.replace(".nii.gz", "")
        lbl_path = base / "labelsTr" / img_path.name
        t0 = time.monotonic()
        registro: dict = {"braco": "msd_task03", "caso": caso}
        try:
            lbl = sitk.GetArrayFromImage(sitk.ReadImage(str(lbl_path)))
            img = sitk.ReadImage(str(img_path))
            voxel_ml = float(np.prod(img.GetSpacing())) / 1000.0
            ref = lbl >= 1              # fígado completo (inclui tumor)
            tumor = lbl == 2
            with tempfile.TemporaryDirectory() as td:
                pred = _segmenta_figado(img_path, Path(td))
            if pred is None or not pred.any():
                registro.update(status="failed", motivo="sem_mascara_de_figado")
                resultados.append(registro)
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                continue
            vol_pred = float(pred.sum()) * voxel_ml
            vol_ref = float(ref.sum()) * voxel_ml
            perdido = np.logical_and(ref, ~pred)
            frac_tumor_ref = float(tumor.sum()) / float(ref.sum()) if ref.sum() else 0.0
            frac_tumor_perdido = (
                float(np.logical_and(perdido, tumor).sum()) / float(perdido.sum())
                if perdido.sum() else 0.0
            )
            registro.update(
                status="ok", dice=round(_dice(pred, ref), 4),
                vol_pred_ml=round(vol_pred, 1), vol_ref_ml=round(vol_ref, 1),
                razao=round(vol_pred / vol_ref, 4) if vol_ref else None,
                carga_tumoral=round(frac_tumor_ref, 4),
                vol_tumor_ml=round(float(tumor.sum()) * voxel_ml, 1),
                frac_tumor_no_perdido=round(frac_tumor_perdido, 4),
                enriquecimento_tumor_no_perdido=(
                    round(frac_tumor_perdido / frac_tumor_ref, 2)
                    if frac_tumor_ref > 0 else None
                ),
                segundos=round(time.monotonic() - t0, 1),
            )
        except Exception as exc:
            registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:200])
        resultados.append(registro)
        print(json.dumps(registro, ensure_ascii=False), flush=True)
    return resultados


def _resumo(resultados: list[dict]) -> dict:
    ok = [r for r in resultados if r.get("status") == "ok"]
    razoes = [r["razao"] for r in ok if r.get("razao")]
    dices = [r["dice"] for r in ok if r.get("dice") is not None]
    resumo = {
        "n_total": len(resultados),
        "n_ok": len(ok),
        "n_failed": len(resultados) - len(ok),
        "razao_mediana": round(float(np.median(razoes)), 4) if razoes else None,
        "razao_iqr": [round(float(q), 4) for q in np.percentile(razoes, [25, 75])] if razoes else None,
        "dice_mediana": round(float(np.median(dices)), 4) if dices else None,
        "dice_min": round(float(np.min(dices)), 4) if dices else None,
    }
    cargas = [r["carga_tumoral"] for r in ok if "carga_tumoral" in r]
    if cargas:
        from scipy.stats import spearmanr

        erros = [abs(1.0 - r["razao"]) for r in ok if "carga_tumoral" in r]
        rho, p = spearmanr(erros, cargas)
        resumo["spearman_erro_vs_carga"] = {"rho": round(float(rho), 4), "p": round(float(p), 4)}
        enriq = [r["enriquecimento_tumor_no_perdido"] for r in ok
                 if r.get("enriquecimento_tumor_no_perdido") is not None]
        resumo["enriquecimento_tumor_no_perdido_mediana"] = (
            round(float(np.median(enriq)), 2) if enriq else None
        )
    return resumo


def main() -> None:
    braco = sys.argv[1] if len(sys.argv) > 1 else "chaos"
    resultados = braco_chaos() if braco == "chaos" else braco_msd()
    payload = {
        "schema": "argos-ct01f-volumetric-benchmark-v1",
        "research_only": True,
        "clinical_use_allowed": False,
        "correcao_aplicada": False,
        "engine": "totalsegmentator task=total fast=False device=gpu + dtwin.stages._refine_mask(opening,2,300)",
        "braco": braco,
        "resumo": _resumo(resultados),
        "casos": resultados,
    }
    destino = SAIDA / f"ct01f_{braco}_resultados.json"
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESUMO:", json.dumps(payload["resumo"], ensure_ascii=False), flush=True)
    print(f"salvo: {destino}", flush=True)


if __name__ == "__main__":
    main()
