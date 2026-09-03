# -*- coding: utf-8 -*-
"""RIM-01 fase F — benchmark volumétrico do modo RIM contra referência humana.

PROTOCOLO PRÉ-REGISTRADO (antes de qualquer execução; plano RIM-01
aprovado pelo operador 2026-08-28, ordem "siga pra fase f" 2026-09-01).

O QUE está sob teste: a segmentação renal (UNIÃO kidney_left+kidney_right)
dos perfis profiles/rins.yaml (RM) e profiles/rins_ct.yaml (TC) — mesma
task do TotalSegmentator usada em produção (total_mr / total), mesmos
argumentos (device=gpu, fast=False), via dtwin.stages._refine_mask com os
parâmetros de refino.orgao dos perfis (opening=True, radius=2,
min_voxels=300 — idênticos ao fígado, herdados sem recalibração).

BRAÇOS:
- CHAOS-MR (n=20, rim saudável): DICOM local (C:\\datasets_ct\\CHAOS_MR),
  fase T1DUAL escolhida POR CASO (InPhase preferida; OutPhase se a
  contagem de cortes da InPhase não bater com o Ground — achado real:
  sujeito 1 tem InPhase truncada a 24/35 cortes, OutPhase completa;
  19/20 sujeitos têm InPhase==OutPhase==Ground, verificado antes de
  qualquer execução). Referência = Ground PNG por corte, convenção
  documentada do CHAOS (0=fundo, 63=fígado, 126=rim direito,
  189=rim esquerdo, 252=baço).
- KiTS (n=40, rim com tumor — Task03-style): NIfTI local
  (C:\\datasets_ct\\KiTS), imaging.nii.gz + segmentation.nii.gz
  (0=fundo, 1=rim, 2=tumor — convenção KiTS19; rim completo = label>=1,
  igual ao tratamento fígado+tumor do CT01-F/CT03).

ENDPOINTS (pré-registrados):
- PRIMÁRIO (os dois braços, comparável entre RM e TC): razão
  volume-predito/volume-referência do PAR UNIDO (mediana e IQR por
  braço); Dice do par unido. KiTS não distingue lado — por isso a
  união é o endpoint primário, não o volume por lado.
- SECUNDÁRIO (só CHAOS-MR, que tem rótulo por lado): Dice por lado
  (rim_esquerdo vs Ground-189, rim_direito vs Ground-126). Ambiguidade
  de lateralidade (o par pode estar trocado por convenção de eixo)
  resolvida por caso testando as duas correspondências e mantendo a de
  maior Dice combinado — mesma técnica declarada do CT01-F para a
  ambiguidade de ordem-z do CHAOS-CT.
- Ambiguidade de ordem-z (Ground empilhado na ordem do DICOM ou
  invertida): resolvida por caso, maior Dice entre as duas ordens,
  reportada — idêntico ao CT01-F.
- Falha técnica no denominador (conta como falha), como no CT01-F/CT03.

DECISÕES DE MÉTODO (declaradas):
- Sem qualquer correção de volume (correcao_aplicada=False, princípio D5
  herdado do CT-01).
- GPU compartilhada: este runner AGUARDA a campanha CT-03 (que roda TS
  concorrentemente) liberar a GPU antes de começar — lição registrada
  em memória após um crash nativo por contenção de GPU em 2026-09-01.
- Nada de fígado é tocado; nenhum contrato congelado participa.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
Path(r"E:\argos_work\_rimf_tmp").mkdir(parents=True, exist_ok=True)

from dtwin.stages import _refine_mask  # noqa: E402  (refino DE PRODUÇÃO)

DADOS = Path(r"C:\datasets_ct")
SAIDA = RAIZ / ".fable/post_audit/evidence/RIM-F"
SAIDA.mkdir(parents=True, exist_ok=True)
PY = str(RAIZ / ".venv-win" / "Scripts" / "python.exe")
TS_UM = str(Path(__file__).with_name("rim_f_ts_um_caso.py"))
REFINO = {"opening": True, "radius": 2, "min_voxels": 300}  # rins.yaml/rins_ct.yaml


def _jsonl_path(braco: str) -> Path:
    return SAIDA / f"rimf_{braco}_resultados.jsonl"


def _casos_ja_feitos(braco: str) -> set[str]:
    """Casos 'ok' persistidos (2026-09-02: achado real — a campanha CT-03
    voltou a rodar sozinha e colidiu com este runner na GPU, matando o
    braço kits em silêncio aos 11/40; sem isto, retomar custava o braço
    inteiro de novo)."""
    path = _jsonl_path(braco)
    feitos: set[str] = set()
    if not path.is_file():
        return feitos
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if "anulado" in r:
            feitos.discard(r["anulado"])
        elif r.get("status") == "ok":
            feitos.add(r["caso"])
    return feitos


def _persiste(braco: str, registro: dict) -> None:
    with _jsonl_path(braco).open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    s = float(a.sum() + b.sum())
    return (2.0 * inter / s) if s else 0.0


def _segmenta_rins(volume_path: Path, tmp: Path, task: str):
    """TS task=total/total_mr fast=False -> (união refinada, esq, dir)."""
    seg_dir = tmp / "seg"
    seg_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [PY, TS_UM, str(volume_path), str(seg_dir), task],
        cwd=RAIZ, capture_output=True, text=True, timeout=1800,
    )
    esq_path, dir_path = seg_dir / "kidney_left.nii.gz", seg_dir / "kidney_right.nii.gz"
    if proc.returncode != 0 or not (esq_path.is_file() and dir_path.is_file()):
        return None, None, None, f"rc={proc.returncode}: {(proc.stderr or '')[-300:]}"
    esq_img = sitk.ReadImage(str(esq_path))
    dir_img = sitk.ReadImage(str(dir_path))
    esq = sitk.GetArrayFromImage(esq_img) > 0
    dir_ = sitk.GetArrayFromImage(dir_img) > 0
    uniao = _refine_mask(esq | dir_, **REFINO)
    return uniao, esq, dir_, None


def braco_chaos_mr() -> list[dict]:
    from PIL import Image

    base = DADOS / "CHAOS_MR" / "Train_Sets" / "MR"
    feitos = _casos_ja_feitos("chaos_mr")
    resultados = []
    for caso_dir in sorted(base.iterdir(), key=lambda p: int(p.name)):
        caso = caso_dir.name
        if caso in feitos:
            continue
        t0 = time.monotonic()
        registro: dict = {"braco": "chaos_mr", "caso": caso}
        try:
            ground_dir = caso_dir / "T1DUAL" / "Ground"
            pngs = sorted(ground_dir.glob("*.png"))
            rotulos = np.stack([np.array(Image.open(p)) for p in pngs])

            # Fase escolhida por CONTAGEM DE CORTES batendo com o Ground —
            # 19/20 sujeitos têm InPhase==OutPhase==Ground; 1 exceção
            # observada (sujeito 1: InPhase truncada, OutPhase completa).
            # Preferência declarada: InPhase se bater; senão OutPhase.
            fase_escolhida = None
            for nome_fase in ("InPhase", "OutPhase"):
                fase_dir = caso_dir / "T1DUAL" / "DICOM_anon" / nome_fase
                if len(list(fase_dir.glob("*.dcm"))) == len(pngs):
                    fase_escolhida = nome_fase
                    break
            if fase_escolhida is None:
                raise RuntimeError(
                    f"nenhuma fase bate com {len(pngs)} cortes do Ground"
                )
            registro["fase_t1dual"] = fase_escolhida
            fase_dir = caso_dir / "T1DUAL" / "DICOM_anon" / fase_escolhida
            reader = sitk.ImageSeriesReader()
            arquivos = reader.GetGDCMSeriesFileNames(str(fase_dir))
            if not arquivos:
                raise RuntimeError(f"GDCM nao le a serie {fase_escolhida}")
            reader.SetFileNames(arquivos)
            vol = reader.Execute()
            voxel_ml = float(np.prod(vol.GetSpacing())) / 1000.0
            # convenção CHAOS: 126=rim direito, 189=rim esquerdo
            ref_dir_stack = (rotulos > 100) & (rotulos < 160)
            ref_esq_stack = (rotulos > 160) & (rotulos < 220)
            ref_uniao_stack = ref_dir_stack | ref_esq_stack

            with tempfile.TemporaryDirectory(dir=r"E:\argos_work\_rimf_tmp") as td:
                tmp = Path(td)
                vol_path = tmp / "volume.nii.gz"
                sitk.WriteImage(vol, str(vol_path))
                pred_uniao, pred_esq, pred_dir, erro = _segmenta_rins(
                    vol_path, tmp, "total_mr"
                )
            if erro is not None:
                registro.update(status="failed", motivo=erro)
                resultados.append(registro)
                _persiste("chaos_mr", registro)
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                continue
            if pred_uniao.shape != ref_uniao_stack.shape:
                registro.update(status="failed",
                                motivo=f"shape pred{pred_uniao.shape} != "
                                       f"ref{ref_uniao_stack.shape}")
                resultados.append(registro)
                _persiste("chaos_mr", registro)
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                continue

            # ambiguidade de ordem-z: maior Dice da união entre as duas ordens
            d_direto = _dice(pred_uniao, ref_uniao_stack)
            d_flip = _dice(pred_uniao, ref_uniao_stack[::-1])
            if d_flip > d_direto:
                ref_uniao, ref_esq, ref_dir, ordem = (
                    ref_uniao_stack[::-1], ref_esq_stack[::-1],
                    ref_dir_stack[::-1], "z_invertido",
                )
                dice_uniao = d_flip
            else:
                ref_uniao, ref_esq, ref_dir, ordem = (
                    ref_uniao_stack, ref_esq_stack, ref_dir_stack, "z_direto",
                )
                dice_uniao = d_direto

            vol_pred = float(pred_uniao.sum()) * voxel_ml
            vol_ref = float(ref_uniao.sum()) * voxel_ml
            registro.update(
                status="ok", ordem_z=ordem, dice_uniao=round(dice_uniao, 4),
                vol_pred_ml=round(vol_pred, 1), vol_ref_ml=round(vol_ref, 1),
                razao=round(vol_pred / vol_ref, 4) if vol_ref else None,
            )

            # secundário: por lado, ambiguidade de lateralidade resolvida
            d_direta = _dice(pred_esq, ref_esq) + _dice(pred_dir, ref_dir)
            d_trocada = _dice(pred_esq, ref_dir) + _dice(pred_dir, ref_esq)
            if d_trocada > d_direta:
                lateralidade = "trocada"
                dice_esq, dice_dir = _dice(pred_esq, ref_dir), _dice(pred_dir, ref_esq)
            else:
                lateralidade = "direta"
                dice_esq, dice_dir = _dice(pred_esq, ref_esq), _dice(pred_dir, ref_dir)
            registro.update(
                lateralidade=lateralidade,
                dice_rim_esquerdo=round(dice_esq, 4),
                dice_rim_direito=round(dice_dir, 4),
                segundos=round(time.monotonic() - t0, 1),
            )
        except Exception as exc:
            registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:250])
        resultados.append(registro)
        _persiste("chaos_mr", registro)
        print(json.dumps(registro, ensure_ascii=False), flush=True)
    return resultados


def braco_kits() -> list[dict]:
    base = DADOS / "KiTS"
    feitos = _casos_ja_feitos("kits")
    resultados = []
    for caso_dir in sorted(base.iterdir(), key=lambda p: p.name):
        img_path = caso_dir / "imaging.nii.gz"
        lbl_path = caso_dir / "segmentation.nii.gz"
        if not (img_path.is_file() and lbl_path.is_file()):
            continue
        caso = caso_dir.name
        if caso in feitos:
            continue
        t0 = time.monotonic()
        registro: dict = {"braco": "kits", "caso": caso}
        try:
            lbl = sitk.GetArrayFromImage(sitk.ReadImage(str(lbl_path)))
            img = sitk.ReadImage(str(img_path))
            voxel_ml = float(np.prod(img.GetSpacing())) / 1000.0
            ref_uniao = lbl >= 1  # rim completo (inclui tumor, convenção KiTS19)
            tumor = lbl == 2

            with tempfile.TemporaryDirectory(dir=r"E:\argos_work\_rimf_tmp") as td:
                pred_uniao, _esq, _dir, erro = _segmenta_rins(img_path, Path(td), "total")
            if erro is not None:
                registro.update(status="failed", motivo=erro)
                resultados.append(registro)
                _persiste("kits", registro)
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                continue
            if pred_uniao.shape != ref_uniao.shape:
                registro.update(status="failed",
                                motivo=f"shape pred{pred_uniao.shape} != ref{ref_uniao.shape}")
                resultados.append(registro)
                _persiste("kits", registro)
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                continue

            vol_pred = float(pred_uniao.sum()) * voxel_ml
            vol_ref = float(ref_uniao.sum()) * voxel_ml
            perdido = np.logical_and(ref_uniao, ~pred_uniao)
            ft_ref = float(tumor.sum()) / float(ref_uniao.sum()) if ref_uniao.sum() else 0.0
            ft_perd = (float(np.logical_and(perdido, tumor).sum()) / float(perdido.sum())
                      if perdido.sum() else 0.0)
            registro.update(
                status="ok", dice_uniao=round(_dice(pred_uniao, ref_uniao), 4),
                vol_pred_ml=round(vol_pred, 1), vol_ref_ml=round(vol_ref, 1),
                razao=round(vol_pred / vol_ref, 4) if vol_ref else None,
                carga_tumoral=round(ft_ref, 4),
                enriquecimento_tumor_no_perdido=round(ft_perd / ft_ref, 2) if ft_ref else None,
                segundos=round(time.monotonic() - t0, 1),
            )
        except Exception as exc:
            registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:250])
        resultados.append(registro)
        _persiste("kits", registro)
        print(json.dumps(registro, ensure_ascii=False), flush=True)
    return resultados


def _carrega_jsonl_completo(braco: str) -> list[dict]:
    """Estado ACUMULADO (não só o desta chamada) — vira o resumo final,
    para que uma retomada parcial some corretamente ao que já rodou."""
    path = _jsonl_path(braco)
    if not path.is_file():
        return []
    vistos: dict[str, dict] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if "anulado" in r:
            vistos.pop(r["anulado"], None)
            continue
        chave = r["caso"]
        if chave not in vistos or r.get("status") == "ok":
            vistos[chave] = r
    return sorted(vistos.values(), key=lambda r: r["caso"])


def _resumo(resultados: list[dict]) -> dict:
    ok = [r for r in resultados if r.get("status") == "ok"]
    razoes = [r["razao"] for r in ok if r.get("razao")]
    dices = [r["dice_uniao"] for r in ok if r.get("dice_uniao") is not None]
    resumo = {
        "n_total": len(resultados), "n_ok": len(ok),
        "n_failed": len(resultados) - len(ok),
        "razao_mediana": round(float(np.median(razoes)), 4) if razoes else None,
        "razao_iqr": [round(float(q), 4) for q in np.percentile(razoes, [25, 75])] if razoes else None,
        "dice_uniao_mediana": round(float(np.median(dices)), 4) if dices else None,
        "dice_uniao_min": round(float(np.min(dices)), 4) if dices else None,
    }
    lados_esq = [r["dice_rim_esquerdo"] for r in ok if "dice_rim_esquerdo" in r]
    if lados_esq:
        lados_dir = [r["dice_rim_direito"] for r in ok if "dice_rim_direito" in r]
        resumo["dice_rim_esquerdo_mediana"] = round(float(np.median(lados_esq)), 4)
        resumo["dice_rim_direito_mediana"] = round(float(np.median(lados_dir)), 4)
        resumo["lateralidade_trocada_n"] = sum(
            1 for r in ok if r.get("lateralidade") == "trocada")
    cargas = [r["carga_tumoral"] for r in ok if "carga_tumoral" in r]
    if cargas:
        from scipy.stats import spearmanr

        erros = [abs(1.0 - r["razao"]) for r in ok if "carga_tumoral" in r]
        rho, p = spearmanr(erros, cargas)
        resumo["spearman_erro_vs_carga_tumoral"] = {"rho": round(float(rho), 4), "p": round(float(p), 4)}
    return resumo


def main() -> None:
    braco = sys.argv[1] if len(sys.argv) > 1 else "chaos_mr"
    braco_chaos_mr() if braco == "chaos_mr" else braco_kits()
    resultados = _carrega_jsonl_completo(braco)  # acumulado, não só esta chamada
    payload = {
        "schema": "argos-rim01f-volumetric-benchmark-v1",
        "research_only": True, "clinical_use_allowed": False,
        "correcao_aplicada": False,
        "engine": ("totalsegmentator task=total_mr/total fast=False device=gpu "
                   "(uniao kidney_left+kidney_right) + "
                   "dtwin.stages._refine_mask(opening,2,300)"),
        "braco": braco,
        "resumo": _resumo(resultados),
        "casos": resultados,
    }
    destino = SAIDA / f"rimf_{braco}_resultados.json"
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESUMO:", json.dumps(payload["resumo"], ensure_ascii=False), flush=True)
    print(f"salvo: {destino}", flush=True)
    print("RIM_F_BRACO_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
