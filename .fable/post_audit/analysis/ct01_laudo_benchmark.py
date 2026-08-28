# -*- coding: utf-8 -*-
"""Benchmark do LAUDO em TC — detecção zero-shot MedGemma (protocolo pré-registrado).

Autorização: Felipe, 2026-08-27 ("o benchmark ... é do laudo completo assim
como foi feito com as rm, medindo a porcentagem de acerto na deteccao de
lesao e na identificacao do tipo").

SISTEMA SOB TESTE: o braço de laudo do OREN (painéis + MedGemma 1.5 4B via
gateway local) aplicado ZERO-SHOT a TC, com prompt idêntico ao de RM exceto
a frase de modalidade (configs/medgemma_local_4b_ct_benchmark.yaml). O
classificador MedSigLIP (Etapa C) NÃO participa: é cabeça treinada e
congelada sobre RM — rodá-lo em TC seria medição sem sentido.

COORTE (ground truth por construção da coorte, mesmo paradigma dos labels
de RM — diagnóstico conhecido em nível de caso/coorte):
- NEGATIVOS: CHAOS-CT n=20 (fígado saudável, referência humana).
- POSITIVOS sem tipo: MSD Task03_Liver n=131 (tumor marcado; sem tipo).
- POSITIVOS com TIPO: TCIA HCC-TACE-Seg n=40 (todos HCC confirmado) +
  TCIA Colorectal-Liver-Metastases n=40 (todos metástase colorretal).
  Seleção pré-registrada e cega a imagem: primeiros 40 PatientID em ordem
  lexicográfica; por paciente, a série CT de maior ImageCount.

ENDPOINTS PRÉ-REGISTRADOS (revisão 2026-08-27, ANTES de qualquer caso
válido executar — ordem do operador: "% de acerto do tipo é a métrica
principal, não dispensando as demais"):
- PRIMÁRIO — % de acerto do TIPO (braços TCIA, n=80): o prompt exige
  prefixo "TIPO_HIPOTESE: <v>" em resumo_do_achado, vocabulário fechado
  {hcc, metastase, hemangioma, cisto, fnh, outro, indeterminado}.
  ACERTO = resultado_hipotese POSITIVA E tipo_hipotese == tipo da coorte
  (hcc | metastase). NEGATIVA/INCONCLUSIVA em caso positivo, tipo ausente,
  fora do vocabulário ou trocado = ERRO. Falha técnica no denominador.
- Secundário: acurácia de detecção — sensibilidade = POSITIVA/(positivos)
  [MSD+TCIA], especificidade = NEGATIVA/(negativos) [CHAOS]. INCONCLUSIVA
  conta como ERRO no braço correspondente E é reportada separadamente.
- Secundário volumétrico (fase F do CT-01, mesmo passe, só CHAOS/MSD que
  têm máscara de referência): razão vol_pred/vol_ref, Dice, correlação do
  erro com carga tumoral + enriquecimento de tumor no volume perdido.
- LIMITE DECLARADO: não existe coorte pública de TC com subtipo BENIGNO
  rotulado; o vocabulário benigno existe no prompt para dar ao modelo a
  chance de errar honestamente, mas só hcc/metastase têm ground truth.

MÉTODO POR CASO: volume (CHAOS: série DICOM→NIfTI; MSD: NIfTI direto) →
TotalSegmentator task=total fast=False (args do stage3) →
dtwin.stages._refine_mask(opening,2,300) (refino DE PRODUÇÃO) → screening
CLI real (`python -m dtwin.medgemma_screening --volume ... --liver-mask
... --confirm-no-visible-phi`; dado público desidentificado) → parse do
medgemma_report.json. Alinhamento z do CHAOS: maior Dice entre as duas
ordens, reportado. Nada de RM/contratos congelados participa.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import SimpleITK as sitk

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.stages import _refine_mask  # noqa: E402

DADOS = Path(r"C:\datasets_ct")
SAIDA = RAIZ / ".fable/post_audit/evidence/CT01-F"
SAIDA.mkdir(parents=True, exist_ok=True)
TRABALHO = Path(r"C:\datasets_ct\_bench_work")
# WinError 32 intermitente nos temporários do nnU-Net sob %TEMP% do usuário
# (AV/indexador segurando handle): temp dedicado em NTFS menos vigiado.
_TMP_BENCH = TRABALHO / "_tmp"
_TMP_BENCH.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = os.environ["TEMP"] = str(_TMP_BENCH)
tempfile.tempdir = str(_TMP_BENCH)
PY = str(RAIZ / ".venv-win" / "Scripts" / "python.exe")
CONFIG_CT = "configs/medgemma_local_4b_ct_benchmark.yaml"
REFINO = {"opening": True, "radius": 2, "min_voxels": 300}
TIPOS_VALIDOS = {"hcc", "metastase", "hemangioma", "cisto", "fnh", "outro",
                 "indeterminado"}
RE_TIPO = re.compile(r"TIPO_HIPOTESE\s*:\s*([a-z_]+)", re.IGNORECASE)
FEITOS: set[tuple[str, str]] = set()  # casos ok do JSONL; skip ANTES do I/O pesado


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _parse_tipo(resumo: str) -> tuple[str | None, str | None]:
    """(tipo, via) — emenda v2 do protocolo (2026-08-28, declarada com
    apenas 1 caso do braço de tipo executado e ANULADO p/ reprocesso):
    1) via "prefixo": formato TIPO_HIPOTESE: <v> exigido pelo prompt;
    2) via "fallback": exatamente UM token do vocabulário presente no
       resumo sem acento ("outro" excluído por ambíguo). Ambíguo/ausente
       -> sem tipo (conta como erro no endpoint primário). A via fica
       registrada — aderência ao formato é métrica secundária."""
    m = RE_TIPO.search(resumo)
    if m:
        tipo = m.group(1).lower()
        return (tipo if tipo in TIPOS_VALIDOS else f"invalido:{tipo}", "prefixo")
    texto = _sem_acento(resumo)
    achados = {v for v in TIPOS_VALIDOS - {"outro"} if v in texto}
    if len(achados) == 1:
        return achados.pop(), "fallback"
    return None, None


def _dice(a, b) -> float:
    inter = float(np.logical_and(a, b).sum())
    s = float(a.sum() + b.sum())
    return (2.0 * inter / s) if s else 0.0


def _segmenta(volume_path: Path, seg_dir: Path):
    """TS em SUBPROCESSO por caso (mesmos args do stage3; ver
    ct01_ts_um_caso.py) — isola a memória: in-process, ~100 casos
    esgotavam o commit do Windows (WinError 1455 nos workers nnU-Net)."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [PY, str(Path(__file__).with_name("ct01_ts_um_caso.py")),
         str(volume_path), str(seg_dir)],
        cwd=RAIZ, capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"TS rc={proc.returncode}: {(proc.stderr or '')[-300:]}")
    liver = seg_dir / "liver.nii.gz"
    if not liver.is_file():
        return None, None
    img = sitk.ReadImage(str(liver))
    m = _refine_mask(sitk.GetArrayFromImage(img) > 0, **REFINO)
    return m, img


def _laudo(volume_path: Path, mask_path: Path, out_dir: Path,
           manifest_path: Path) -> dict | None:
    proc = subprocess.run(
        [PY, "-m", "dtwin.medgemma_screening",
         "--volume", str(volume_path), "--liver-mask", str(mask_path),
         "--case-manifest", str(manifest_path),
         "--medgemma-config", CONFIG_CT, "--output", str(out_dir),
         "--confirm-no-visible-phi"],
        cwd=RAIZ, capture_output=True, text=True, timeout=600,
    )
    candidatos = sorted(out_dir.rglob("medgemma_report.json")) if out_dir.is_dir() else []
    if not candidatos:
        cauda_out = (proc.stdout or "")[-500:]
        cauda_err = (proc.stderr or "")[-800:]
        return {"_erro": f"rc={proc.returncode} OUT..{cauda_out} ERR..{cauda_err}"}
    return json.loads(candidatos[-1].read_text(encoding="utf-8"))


def _um_caso(caso: str, braco: str, volume_path: Path, ref, tumor, voxel_ml,
             work: Path, tipo_esperado: str | None = None) -> dict:
    t0 = time.monotonic()
    registro: dict = {"braco": braco, "caso": caso,
                      "ground_truth": "NEGATIVA" if braco == "chaos_ct" else "POSITIVA"}
    if tipo_esperado:
        registro["tipo_esperado"] = tipo_esperado
    try:
        try:
            pred, img = _segmenta(volume_path, work / "seg")
        except (PermissionError, RuntimeError):  # WinError 32/1455: um retry
            time.sleep(10)
            pred, img = _segmenta(volume_path, work / "seg")
        if pred is None or not pred.any():
            registro.update(status="failed", motivo="sem_mascara_de_figado")
            return registro
        if ref is not None:
            if pred.shape != ref.shape:
                registro.update(status="failed",
                                motivo=f"shape pred{pred.shape}!=ref{ref.shape}")
                return registro
            d1, d2 = _dice(pred, ref), _dice(pred, ref[::-1])
            if d2 > d1:
                ref = ref[::-1]
                registro["ordem_z"] = "z_invertido"
            registro.update(
                dice=round(max(d1, d2), 4),
                vol_pred_ml=round(float(pred.sum()) * voxel_ml, 1),
                vol_ref_ml=round(float(ref.sum()) * voxel_ml, 1),
                razao=round(float(pred.sum()) / float(ref.sum()), 4) if ref.sum() else None,
            )
            if tumor is not None and tumor.any():
                perdido = np.logical_and(ref, ~pred)
                ft_ref = float(tumor.sum()) / float(ref.sum())
                ft_perd = (float(np.logical_and(perdido, tumor).sum()) / float(perdido.sum())
                           if perdido.sum() else 0.0)
                registro.update(
                    carga_tumoral=round(ft_ref, 4),
                    enriquecimento_tumor_no_perdido=round(ft_perd / ft_ref, 2) if ft_ref else None,
                )
        mask_path = work / "mask_organ.nii.gz"
        mask_img = sitk.GetImageFromArray(pred.astype(np.uint8))
        mask_img.CopyInformation(img)
        sitk.WriteImage(mask_img, str(mask_path))
        # Manifesto veraz do caso: dado público desidentificado de pesquisa.
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps({
            "case_id": f"anon-ct01f-{braco}-{caso}",
            "policy": "anonymize",
            "regulatory_state": "PESQUISA",
            "modality": "CT",
        }), encoding="utf-8")
        report = _laudo(volume_path, mask_path, work / "laudo", manifest_path)
        if not report or "_erro" in (report or {}):
            registro.update(status="failed",
                            motivo=f"laudo_indisponivel: {(report or {}).get('_erro','')[:900]}")
            return registro
        corpo = report.get("report") or report
        verdito = str(corpo.get("resultado_hipotese") or "AUSENTE").upper()
        resumo = str(corpo.get("resumo_do_achado") or "")
        tipo_hipotese, tipo_parse = _parse_tipo(resumo)
        registro.update(
            status="ok",
            resultado_hipotese=verdito,
            acerto_deteccao=bool(verdito == registro["ground_truth"]),
            tipo_hipotese=tipo_hipotese,
            tipo_parse=tipo_parse,
            resumo_do_achado=resumo[:200],
            confianca=corpo.get("confianca"),
            segundos=round(time.monotonic() - t0, 1),
        )
        if tipo_esperado:
            registro["acerto_tipo"] = bool(
                verdito == "POSITIVA" and tipo_hipotese == tipo_esperado
            )
    except Exception as exc:
        registro.update(status="failed", motivo=f"{type(exc).__name__}: {exc}"[:200])
    return registro


def casos_chaos():
    from PIL import Image

    base = DADOS / "CHAOS_CT" / "Train_Sets" / "CT"
    for caso_dir in sorted(base.iterdir(), key=lambda p: int(p.name)):
        if ("chaos_ct", caso_dir.name) in FEITOS:
            continue
        work = TRABALHO / f"chaos_{caso_dir.name}"
        work.mkdir(parents=True, exist_ok=True)
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(caso_dir / "DICOM_anon")))
        vol = reader.Execute()
        vol_path = work / "volume.nii.gz"
        sitk.WriteImage(vol, str(vol_path))
        ref = np.stack([
            np.array(Image.open(p)) > 0 for p in sorted((caso_dir / "Ground").glob("*.png"))
        ]).astype(bool)
        voxel_ml = float(np.prod(vol.GetSpacing())) / 1000.0
        yield caso_dir.name, "chaos_ct", vol_path, ref, None, voxel_ml, work, None


def casos_msd():
    base = DADOS / "Task03_Liver"
    for img_path in sorted((base / "imagesTr").glob("*.nii.gz")):
        caso = img_path.name.replace(".nii.gz", "")
        if ("msd_task03", caso) in FEITOS:
            continue
        work = TRABALHO / f"msd_{caso}"
        work.mkdir(parents=True, exist_ok=True)
        lbl = sitk.GetArrayFromImage(sitk.ReadImage(str(base / "labelsTr" / img_path.name)))
        img = sitk.ReadImage(str(img_path))
        voxel_ml = float(np.prod(img.GetSpacing())) / 1000.0
        yield caso, "msd_task03", img_path, lbl >= 1, lbl == 2, voxel_ml, work, None


def casos_tcia(pasta: str, braco: str, tipo: str):
    """Braços de TIPO: pacientes TCIA com diagnóstico conhecido por coorte.

    Cada subdiretório de <base>/<pasta> é um paciente contendo a série CT
    pré-selecionada (regra cega: maior ImageCount) já extraída. Destino
    final é o SSD externo D: (ordem do operador 2026-08-27), mas o D:
    desconectou; enquanto isso lê do staging C: — mover verificado quando
    o D: voltar.
    """
    base = Path(r"C:\datasets_ct") / pasta
    if not base.is_dir():
        return
    for pac_dir in sorted(base.iterdir()):
        if not pac_dir.is_dir() or (braco, pac_dir.name) in FEITOS:
            continue
        dcm = sorted(pac_dir.rglob("*.dcm"))
        if not dcm:
            continue
        work = TRABALHO / f"{braco}_{pac_dir.name}"
        work.mkdir(parents=True, exist_ok=True)
        reader = sitk.ImageSeriesReader()
        arquivos = reader.GetGDCMSeriesFileNames(str(dcm[0].parent))
        if not arquivos:
            continue
        reader.SetFileNames(arquivos)
        vol = reader.Execute()
        vol_path = work / "volume.nii.gz"
        sitk.WriteImage(vol, str(vol_path))
        voxel_ml = float(np.prod(vol.GetSpacing())) / 1000.0
        yield pac_dir.name, braco, vol_path, None, None, voxel_ml, work, tipo


def main() -> None:
    quais = sys.argv[1] if len(sys.argv) > 1 else "all"
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    jsonl = SAIDA / "ct01_laudo_resultados.jsonl"
    if jsonl.is_file():
        for ln in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if "anulado" in r:  # invalidação auditável; ok posterior re-vale
                FEITOS.discard(tuple(r["anulado"]))
            elif r.get("status") == "ok":
                FEITOS.add((r["braco"], r["caso"]))
    fontes = []
    if quais in ("all", "tipo", "hcc"):
        fontes.append(casos_tcia("TCIA_HCC", "tcia_hcc", "hcc"))
    if quais in ("all", "tipo", "crlm"):
        fontes.append(casos_tcia("TCIA_CRLM", "tcia_crlm", "metastase"))
    if quais in ("all", "chaos"):
        fontes.append(casos_chaos())
    if quais in ("all", "msd"):
        fontes.append(casos_msd())
    n = 0
    for fonte in fontes:
        for caso, braco, vol_path, ref, tumor, voxel_ml, work, tipo in fonte:
            if (braco, caso) in FEITOS:
                continue
            registro = _um_caso(caso, braco, vol_path, ref, tumor, voxel_ml, work,
                                tipo_esperado=tipo)
            with jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            print(json.dumps(registro, ensure_ascii=False), flush=True)
            if registro.get("status") == "ok":
                shutil.rmtree(work, ignore_errors=True)  # preserva work-dir em falha p/ debug
            n += 1
            if limite and n >= limite:
                print(f"LIMITE {limite} atingido", flush=True)
                return
    print("BENCHMARK_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
