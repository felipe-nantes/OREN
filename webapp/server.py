#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Webapp de orquestração (modo Pesquisa/demo).

Fluxo, invisível para o usuário: recebe uma pasta DICOM de RM -> des-identifica ->
segmenta o fígado -> gera a montagem 2D -> chama o MedGemma -> devolve um relatório
simples. É "à prova de falhas": qualquer etapa que falhe produz um cartão gracioso
e honesto ("análise não concluída") — NUNCA um achado clínico fabricado.

Robustez: o pipeline pesado (TotalSegmentator com torch/CUDA, e a triagem MedGemma)
roda em SUBPROCESSOS isolados. Assim, mesmo um crash nativo (segfault, OOM de CUDA)
não derruba o servidor web — o subprocesso retorna erro e o job vira um cartão
gracioso. O servidor permanece sempre responsivo.

Aviso: para a experiência hands-off do demo, a confirmação humana de PHI queimada
nos pixels é auto-assumida. Isto é aceitável apenas em modo Pesquisa/demonstração;
o uso clínico exige a revisão humana real do painel.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.request import urlopen

import pydicom
import SimpleITK as sitk
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.datastructures import FormData

from dtwin.benchmark.metrics import compute_benchmark_metrics
from dtwin.benchmark.hashing import git_state
from dtwin.benchmark.reporting import write_run_outputs
from dtwin.benchmark.runner import classify_screening_failure
from dtwin.benchmark.dataset_audit import (
    describe_selected_series,
    select_best_mr_series,
)
from dtwin.benchmark.operational_timing import (
    DEFAULT_REPORT_BUDGET_SECONDS,
    build_operational_timing,
    persist_operational_timing,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import (
    OPTIONAL_REPORT_V2_FIELDS,
    effective_config_sha256,
    load_screening_config,
)
from dtwin.medgemma_volumetric import effective_screening_timeout
from dtwin.segmentation_subprocess import run_segmentation_subprocess

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("dtwin.webapp")

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STATIC = ROOT / "static"
VIEWER = REPO / "viewer"
WORKSPACE = Path("casos/webapp")
PROFILE = "profiles/figado.yaml"
MEDGEMMA_CONFIG = os.environ.get("WEBAPP_MEDGEMMA_CONFIG", "configs/medgemma_local_4b.yaml")
VOLUMETRIC_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_VOLUMETRIC_MEDGEMMA_CONFIG", "configs/medgemma_local_4b_volumetric.yaml"
)
RAG_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_RAG_MEDGEMMA_CONFIG", "configs/medgemma_local_4b_rag.yaml"
)
VOLUMETRIC_RAG_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_VOLUMETRIC_RAG_MEDGEMMA_CONFIG", "configs/medgemma_local_4b_volumetric_rag.yaml"
)
PATHOLOGY_TARGET_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_PATHOLOGY_TARGET_MEDGEMMA_CONFIG",
    "configs/medgemma_local_4b_volumetric_pathology_target.yaml",
)
FAST_PATHOLOGY_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_FAST_PATHOLOGY_MEDGEMMA_CONFIG",
    "configs/medgemma_local_4b_fast_pathology.yaml",
)
BENCHMARK_SCENARIOS = {
    "baseline": MEDGEMMA_CONFIG,
    "volumetric": VOLUMETRIC_MEDGEMMA_CONFIG,
    "rag": RAG_MEDGEMMA_CONFIG,
    "volumetric_rag": VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    "pathology_target": PATHOLOGY_TARGET_MEDGEMMA_CONFIG,
    "fast_pathology": FAST_PATHOLOGY_MEDGEMMA_CONFIG,
}
# Cenários que NÃO usam o MedGemma: classificador visual supervisionado da
# Etapa C (melhor resultado do projeto). Exige entrada MULTIFÁSICA — cada caso
# envia as fases identificadas em subpastas (arterial/venous/delayed), porque
# identificar a fase a partir de DICOM bruto é problema não resolvido (docs/123).
# É modo de PESQUISA: retrospectivo, não estável por dataset, não validado.
VISUAL_BENCHMARK_SCENARIOS = {
    "hybrid_supervised": os.environ.get(
        "WEBAPP_VISUAL_BUNDLE",
        "casos/qualification/hybrid_v1/medsiglip_multiclass_production_bundle_v1",
    ),
}
VISUAL_PANEL_CONFIG = os.environ.get(
    "WEBAPP_VISUAL_PANEL_CONFIG",
    "configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml",
)
VISUAL_EMBEDDING_CONFIG = os.environ.get(
    "WEBAPP_VISUAL_EMBEDDING_CONFIG", "configs/training/medsiglip_frozen_v1.yaml"
)
# Índice server-side autorizado para o benchmark interno. O navegador nunca
# envia esse caminho e o conteúdo privado nunca é encaminhado ao modelo.
VISUAL_AUTHORIZED_PHASE_AUDIT = os.environ.get(
    "WEBAPP_VISUAL_AUTHORIZED_PHASE_AUDIT",
    "ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1/private_reference/conversion_audit.json",
)
# A tela de exame individual só expõe modos que foram avaliados e versionados.
# O navegador envia apenas a chave; nunca um caminho de configuração.
INDIVIDUAL_SCREENING_SCENARIOS = {
    "volumetric_rag": VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    "pathology_target": PATHOLOGY_TARGET_MEDGEMMA_CONFIG,
}
HEALTH_URL = os.environ.get("WEBAPP_MEDGEMMA_HEALTH", "http://127.0.0.1:8001/health")
MIN_SLICES = 3
PREP_TIMEOUT_GPU = int(os.environ.get("WEBAPP_PREP_TIMEOUT_GPU", "900"))
PREP_TIMEOUT_CPU = int(os.environ.get("WEBAPP_PREP_TIMEOUT_CPU", "2400"))
SCREEN_TIMEOUT = int(os.environ.get("WEBAPP_SCREEN_TIMEOUT", "600"))
MODEL_TIMEOUT = int(os.environ.get("WEBAPP_MODEL_TIMEOUT", "300"))
# O Starlette limita uploads multipart a 1000 arquivos por padrão (proteção
# genérica contra DoS). Um dataset de benchmark real (muitos exames, cada um com
# centenas/milhares de fatias DICOM) estoura isso com facilidade. O servidor só
# escuta em loopback (uso local de pesquisa), então um teto bem mais alto — mas
# ainda explícito, nunca ilimitado — é seguro aqui.
MAX_UPLOAD_FILES = int(os.environ.get("WEBAPP_MAX_UPLOAD_FILES", "50000"))
DISCLAIMER = (
    "Uso em pesquisa. Não destinado à decisão clínica. Não é diagnóstico nem "
    "laudo médico. Revisão médica obrigatória."
)

PY = sys.executable
_jobs: dict[str, dict] = {}
_benchmarks: dict[str, dict] = {}
_lock = threading.Lock()
# O gateway MedGemma executa uma inferência por vez. Sem esta trava, dois jobs
# podem competir pelo mesmo gateway e o tempo de fila conta como timeout HTTP do
# segundo job. Segmentação e renderização continuam paralelas; só a triagem é
# serializada.
_medgemma_screening_lock = threading.Lock()


def _set(job_id: str, **kw) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(**kw)


def _set_benchmark(benchmark_id: str, **kw) -> None:
    with _lock:
        if benchmark_id in _benchmarks:
            _benchmarks[benchmark_id].update(**kw)


def _graceful(motivo: str, detalhe: str = "") -> dict:
    return {
        "status": "nao_concluido",
        "titulo": "Análise não concluída",
        "motivo": motivo,
        "detalhe": detalhe,
        "requires_human_review": True,
        "disclaimer": DISCLAIMER,
    }


def _friendly_text(reason: str) -> str:
    s = (reason or "").lower()
    if any(t in s for t in ("backend not configured", "inacessível", "não está disponível", "não configurado")):
        return "O serviço de análise (MedGemma) não está ativo no momento."
    if "modalidade" in s:
        return "O exame enviado não parece ser uma RM compatível."
    if "poucas fatias" in s or "3d inviável" in s or "fatias axiais" in s:
        return "O exame enviado tem cortes insuficientes para a análise."
    if any(t in s for t in ("segmenta", "fígado", "liver", "totalsegmentator")):
        return "Não foi possível segmentar o fígado neste exame."
    if "diagnóstico definitivo" in s or "conduta" in s:
        return "A resposta do modelo não passou na verificação de segurança."
    if "phi" in s:
        return "O exame não passou na verificação de privacidade."
    return "Não foi possível concluir a análise deste exame."


def _friendly(err: Exception) -> str:  # conveniência p/ testes
    return _friendly_text(str(err))


def _expected_modalities() -> set[str]:
    """Modalidades aceitas pelo perfil ativo (ex.: {'MR','MRI'} para o fígado)."""
    try:
        prof = yaml.safe_load((REPO / PROFILE).read_text("utf-8")) or {}
        return {str(m).upper() for m in (prof.get("modalidade") or [])}
    except Exception:  # noqa: BLE001
        return {"MR", "MRI"}


def _modality_of(names: list[str]) -> str:
    """Lê a Modality (0008,0060) do primeiro arquivo legível da série."""
    for name in names[:5]:
        try:
            ds = pydicom.dcmread(name, stop_before_pixels=True, force=True)
        except Exception:  # noqa: BLE001
            continue
        modality = str(getattr(ds, "Modality", "") or "").upper()
        if modality:
            return modality
    return ""


def _modality_ok(names: list[str], expected: set[str]) -> bool:
    """Aceita se a modalidade bate com o perfil (ou é desconhecida — o gate do
    stage1 decide). REJEITA modalidade conhecida e incompatível (ex.: CT quando o
    perfil é MR), para não escolher a série errada num envio misto CT+MR."""
    modality = _modality_of(names)
    return not modality or not expected or modality in expected


def find_best_series(root: Path) -> tuple[list[str], int]:
    """Seleciona a série MR tecnicamente válida e mais informativa.

    A ordem é determinística e considera modalidade, geometria e classe provável
    da sequência. Labels e ground truth nunca participam da seleção.
    """
    files, frames, _metadata = select_best_mr_series(root, min_slices=MIN_SLICES)
    return files, frames


def _find_largest_compatible_series_legacy(root: Path) -> tuple[list[str], int]:
    """Acha a maior série DICOM COMPATÍVEL com o perfil, em qualquer estrutura:

    1) enumera TODAS as séries de cada diretório (uma pasta pode ter várias séries);
    2) filtra por modalidade (o perfil do fígado é MR): num envio misto CT+MR,
       ignora as séries CT em vez de escolher a maior e abortar no gate do stage1;
    3) se nenhuma série multi-arquivo servir, tenta um único DICOM **multi-frame**
       (um só `.dcm` que já é o volume 3D inteiro), medindo a profundidade real.

    Retorna (lista_de_arquivos_da_melhor_série, nº_de_cortes)."""
    reader = sitk.ImageSeriesReader()
    expected = _expected_modalities()
    best_files: list[str] = []
    for dirpath, _dirs, _files in os.walk(root):
        try:
            series_ids = list(reader.GetGDCMSeriesIDs(dirpath)) or [""]
        except Exception:  # noqa: BLE001
            series_ids = [""]
        for sid in series_ids:
            try:
                names = (reader.GetGDCMSeriesFileNames(dirpath, sid) if sid
                         else reader.GetGDCMSeriesFileNames(dirpath))
            except Exception:  # noqa: BLE001
                names = []
            if len(names) <= len(best_files):
                continue
            if not _modality_ok(list(names), expected):
                continue
            best_files = list(names)
    if len(best_files) >= MIN_SLICES:
        return best_files, len(best_files)

    # Fallback: DICOM multi-frame (um arquivo = volume inteiro) ou série de 1 arquivo.
    best_file, best_depth = None, 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                img = sitk.ReadImage(path)
            except Exception:  # noqa: BLE001
                continue
            depth = img.GetSize()[2] if img.GetDimension() >= 3 else 1
            if depth <= best_depth or not _modality_ok([path], expected):
                continue
            best_file, best_depth = path, depth
    if best_file and best_depth >= MIN_SLICES:
        return [best_file], best_depth
    return best_files, len(best_files)


def _persist_series_selection(case_dir: Path, files: list[str]) -> Path:
    """Persiste somente metadata sanitizada da série usada pela inferência."""
    output = case_dir / "outputs" / "series_selection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = describe_selected_series(files)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output)
    return output


def _run(cmd: list[str], timeout: int, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or str(REPO), capture_output=True, text=True, timeout=timeout)


def _segment(
    series_dir: str, case_dir: Path, device: str, timeout: int, *, fast: bool
) -> subprocess.CompletedProcess:
    """Roda a segmentação pelo launcher, a partir do %TEMP% (fora do OneDrive).

    `fast=False` (exame individual) usa full-res (~1.5mm) para uma máscara mais
    fiel; `fast=True` (benchmark) mantém 3mm por throughput."""
    return run_segmentation_subprocess(
        dicom_dir=Path(series_dir),
        case_dir=case_dir,
        profile_path=REPO / PROFILE,
        device=device,
        fast=fast,
        timeout_seconds=timeout,
        python_executable=PY,
    )


def _cli_reason(proc: subprocess.CompletedProcess) -> str:
    """Extrai a razão impressa ('[ABORTADO] ...' ou 'PREP_FAIL: ...'); senão o fim do log."""
    for line in (proc.stdout or "").splitlines() + (proc.stderr or "").splitlines():
        if "[ABORTADO]" in line:
            return line.split("[ABORTADO]", 1)[1].strip()
        if "PREP_FAIL:" in line:
            return line.split("PREP_FAIL:", 1)[1].strip()
    tail = (proc.stderr or proc.stdout or "").strip()
    return tail[-300:] if tail else f"código de saída {proc.returncode}"


def _safe_screening_log_text(value: str | None, case_dir: Path) -> str:
    """Conserva diagnóstico operacional sem expor caminhos locais do caso.

    A saída não é uma resposta do modelo e nunca é usada como achado clínico.
    Limitamos seu tamanho e removemos os dois caminhos conhecidos que poderiam
    revelar estrutura de arquivos de upload no artefato de benchmark.
    """
    text = str(value or "")[-12000:]
    for path, replacement in ((case_dir, "[CASE_DIR]"), (REPO, "[REPO]")):
        try:
            text = text.replace(str(path.resolve()), replacement)
        except OSError:
            text = text.replace(str(path), replacement)
    return text


def _persist_screening_diagnostics(
    case_dir: Path, process: subprocess.CompletedProcess
) -> dict[str, str]:
    """Persiste stdout/stderr sanitizados quando a triagem não gera relatório."""
    output_dir = case_dir / "outputs" / "medgemma"
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "screening_subprocess.stdout.log"
    stderr_path = output_dir / "screening_subprocess.stderr.log"
    stdout_path.write_text(_safe_screening_log_text(process.stdout, case_dir), encoding="utf-8")
    stderr_path.write_text(_safe_screening_log_text(process.stderr, case_dir), encoding="utf-8")
    metadata_path = output_dir / "screening_subprocess.json"
    metadata_path.write_text(json.dumps({
        "schema": "argos-screening-subprocess-diagnostics-v1",
        "returncode": process.returncode,
        "reason": _safe_screening_log_text(_cli_reason(process), case_dir),
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    relative = output_dir.relative_to(case_dir)
    return {
        "stdout": str(relative / stdout_path.name),
        "stderr": str(relative / stderr_path.name),
        "metadata": str(relative / metadata_path.name),
    }


def _seg_done(case_dir: Path) -> bool:
    """Segmentação concluída = volume + máscara existem (o returncode é ignorado:
    libs nativas podem crashar no shutdown no Windows APÓS gravar os artefatos)."""
    return (case_dir / "mask_organ.nii.gz").is_file() and (case_dir / "volume.nii.gz").is_file()


def _success_result(report: dict) -> dict:
    """Monta o resultado de sucesso para o frontend.

    IMPORTANTE: o envelope do relatório tem sua própria chave 'status'
    ('pending_review'); ela NÃO pode sobrescrever o marcador de conclusão que o
    frontend usa. Por isso 'status'='concluido' é aplicado por ÚLTIMO."""
    return {**report, "status": "concluido"}


def _viewer_result(
    report: dict,
    job_id: str,
    viewer_ready: bool,
    *,
    analysis_scenario: str = "volumetric_rag",
) -> dict:
    """Acrescenta a visualizacao sem alterar o contrato do relatorio MedGemma."""
    result = _success_result(report)
    result.update(
        viewer_ready=bool(viewer_ready),
        viewer_url=(
            f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
            if viewer_ready
            else None
        ),
        approval={"status": "pending"} if viewer_ready else None,
        analysis_scenario=analysis_scenario,
    )
    return result


def _load_report(path: Path) -> dict | None:
    """Relatório válido = sucesso, independentemente do returncode do subprocesso.
    run_screening grava o JSON atomicamente só após validá-lo, então a existência de
    um relatório com 'resultado_hipotese' significa que a triagem concluiu de fato."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    report = data.get("report")
    if not isinstance(report, dict) or not report.get("resultado_hipotese"):
        return None
    return data


def _model_done(case_dir: Path) -> bool:
    """Modelo publicavel = manifesto valido e todos os STLs presentes."""
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        meshes = manifest.get("meshes", [])
        return bool(meshes) and all(
            isinstance(item, dict)
            and Path(str(item.get("stl", ""))).name == item.get("stl")
            and (manifest_path.parent / item["stl"]).is_file()
            for item in meshes
        )
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return False


def _build_model(case_dir: Path) -> tuple[bool, str]:
    """Gera a malha do figado em subprocesso, sem inventar uma lesao."""
    proc = _run(
        [
            PY,
            "digital_twin.py",
            "finalize",
            str(case_dir),
            "--profile",
            PROFILE,
            "--no-lesion",
        ],
        timeout=MODEL_TIMEOUT,
    )
    if _model_done(case_dir):
        return True, ""
    return False, _cli_reason(proc)


def _case_dir_for_job(job_id: str) -> Path:
    if not job_id or any(ch not in "0123456789abcdef" for ch in job_id.lower()):
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    return (WORKSPACE / job_id / "case").resolve()


class ApprovalPayload(BaseModel):
    status: Literal["approved", "revision_requested"]


def process_job(
    job_id: str,
    raw_dir: Path,
    medgemma_config: str = VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    analysis_scenario: str = "volumetric_rag",
) -> None:
    # case_dir e raw_dir (_upload) são IRMÃOS sob WORKSPACE/job_id; nunca aninhados,
    # senão limpar o case_dir apagaria o DICOM enviado (necessário no fallback CPU).
    case_dir = (WORKSPACE / job_id / "case").resolve()
    worker_started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    durations_seconds: dict[str, float] = {}
    outcome = "failed"
    failure_stage: str | None = "series_selection_and_copy"
    segmentation_device: str | None = None
    report_available = False
    viewer_ready = False
    try:
        _set(job_id, state="processing", step="ingestao", progress=15)
        series_started = time.monotonic()
        best_files, n = find_best_series(raw_dir)
        if not best_files or n < MIN_SLICES:
            durations_seconds["series_selection_and_copy"] = round(
                time.monotonic() - series_started, 4
            )
            outcome = "not_completed"
            _set(job_id, state="done", result=_graceful(
                "Não encontramos uma série DICOM de RM válida no envio.",
                "Envie a pasta de um exame de RM (DICOM) com múltiplos cortes — "
                "ou um único arquivo DICOM multi-frame."))
            return

        # Copia a série escolhida para um diretório limpo: isola de estruturas
        # bagunçadas / múltiplas séries e garante que o prepare veja só esta série.
        series_dir_path = WORKSPACE / job_id / "_series"
        series_dir_path.mkdir(parents=True, exist_ok=True)
        for i, source in enumerate(best_files):
            shutil.copyfile(source, series_dir_path / f"{i:05d}_{os.path.basename(source)}")
        series_dir = str(series_dir_path.resolve())
        durations_seconds["series_selection_and_copy"] = round(
            time.monotonic() - series_started, 4
        )

        # Fase 1: ingestão + des-identificação + segmentação (launcher isolado).
        failure_stage = "preparation_and_segmentation"
        segmentation_started = time.monotonic()
        try:
            _set(job_id, step="segmentacao", progress=45)
            segmentation_device = "gpu"
            prep = _segment(series_dir, case_dir, "gpu", PREP_TIMEOUT_GPU, fast=False)
            if not _seg_done(case_dir):
                reason = _cli_reason(prep)
                log.warning("Segmentação na GPU falhou (%s); tentando CPU...", reason[:100])
                shutil.rmtree(case_dir, ignore_errors=True)
                _set(job_id, step="segmentacao", progress=55)
                segmentation_device = "cpu_fallback"
                prep = _segment(series_dir, case_dir, "cpu", PREP_TIMEOUT_CPU, fast=False)
                if not _seg_done(case_dir):
                    reason = _cli_reason(prep)
                    outcome = "not_completed"
                    _set(job_id, state="done", result=_graceful(_friendly_text(reason), reason))
                    return
        finally:
            durations_seconds["preparation_and_segmentation"] = round(
                time.monotonic() - segmentation_started, 4
            )

        # Fase 2: montagem 2D + MedGemma (subprocesso isolado).
        _persist_series_selection(case_dir, best_files)
        failure_stage = "medgemma_screening"
        _set(job_id, step="medgemma", progress=80)
        screening_started = time.monotonic()
        try:
            screening_config = load_screening_config(REPO / medgemma_config)
            screening_timeout, _panel_count = effective_screening_timeout(
                sitk.GetArrayFromImage(
                    sitk.ReadImage(str(case_dir / "mask_organ.nii.gz"))
                ) > 0,
                screening_config,
                SCREEN_TIMEOUT,
            )
            with _medgemma_screening_lock:
                scr = _run(
                    [
                        PY,
                        "-m",
                        "dtwin.medgemma_screening",
                        "--case-dir",
                        str(case_dir),
                        "--medgemma-config",
                        medgemma_config,
                        "--confirm-no-visible-phi",
                    ],
                    timeout=screening_timeout,
                )
        finally:
            durations_seconds["screening_subprocess"] = round(
                time.monotonic() - screening_started, 4
            )

        report = _load_report(case_dir / "outputs" / "medgemma" / "medgemma_report.json")
        if report is None:
            reason = _cli_reason(scr)
            outcome = "not_completed"
            _set(job_id, state="done", result=_graceful(_friendly_text(reason), reason))
            return

        report_available = True
        outcome = "report_completed"
        durations_seconds.update({
            str(key): float(value)
            for key, value in (report.get("durations_seconds") or {}).items()
            if isinstance(value, (int, float)) and float(value) >= 0
        })
        durations_seconds["time_to_report"] = round(time.monotonic() - worker_started, 4)

        # Fase 3: máscara hepática -> malha/STL para revisão humana.
        failure_stage = "model_3d"
        _set(job_id, step="modelo_3d", progress=92)
        model_started = time.monotonic()
        try:
            viewer_ready, viewer_error = _build_model(case_dir)
        finally:
            durations_seconds["model_3d"] = round(time.monotonic() - model_started, 4)

        if not viewer_ready:
            log.warning(
                "Job %s: relatório concluído, mas modelo 3D falhou: %s",
                job_id,
                viewer_error,
            )
            outcome = "report_completed_viewer_failed"
        else:
            outcome = "completed"
            failure_stage = None

        _set(
            job_id,
            state="done",
            step="concluido",
            progress=100,
            viewer_error=viewer_error or None,
            approval={"status": "pending"} if viewer_ready else None,
            result=_viewer_result(
                report,
                job_id,
                viewer_ready,
                analysis_scenario=analysis_scenario,
            ),
        )
    except subprocess.TimeoutExpired:
        outcome = "timeout"
        _set(job_id, state="done", result=_graceful(
            "O processamento excedeu o tempo limite.", "timeout"))
    except Exception as exc:  # noqa: BLE001
        outcome = "failed"
        log.exception("Job %s: falha inesperada", job_id)
        _set(job_id, state="done", result=_graceful(
            "Ocorreu um erro inesperado no processamento.", type(exc).__name__))
    finally:
        durations_seconds["total_with_3d"] = round(time.monotonic() - worker_started, 4)
        try:
            config_path = REPO / medgemma_config
            config_sha256 = sha256_of(config_path) if config_path.is_file() else "unavailable"
            timing = build_operational_timing(
                job_id=job_id,
                analysis_scenario=analysis_scenario,
                medgemma_config=medgemma_config,
                medgemma_config_sha256=config_sha256,
                started_at_utc=started_at_utc,
                finished_at_utc=datetime.now(timezone.utc).isoformat(),
                durations_seconds=durations_seconds,
                outcome=outcome,
                report_available=report_available,
                viewer_ready=viewer_ready,
                failure_stage=failure_stage,
                segmentation_device=segmentation_device,
                report_budget_seconds=DEFAULT_REPORT_BUDGET_SECONDS,
            )
            timing_path = persist_operational_timing(case_dir, timing)
            _set(
                job_id,
                operational_timing=timing,
                operational_timing_artifact=str(
                    timing_path.relative_to((WORKSPACE / job_id).resolve())
                ),
            )
        except Exception:  # noqa: BLE001
            log.exception("Job %s: não foi possível persistir a auditoria de tempo", job_id)
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(WORKSPACE / job_id / "_series", ignore_errors=True)

def calculate_benchmark_metrics(results: list[dict]) -> dict:
    """Adaptador retrocompatível para o núcleo compartilhado do benchmark."""
    metrics = compute_benchmark_metrics(results)
    metrics["scoring_policy"] = "inconclusive_and_failed_count_as_errors"
    return metrics


def _benchmark_config(scenario: str) -> str:
    if scenario not in BENCHMARK_SCENARIOS:
        raise PipelineError(f"Cenário de benchmark não autorizado: {scenario!r}")
    configured = BENCHMARK_SCENARIOS[scenario]
    resolved = (REPO / configured).resolve()
    configs_root = (REPO / "configs").resolve()
    if resolved.parent != configs_root or not resolved.is_file():
        raise PipelineError(f"Configuração autorizada não encontrada: {configured}")
    return configured


def _individual_screening_config(scenario: str) -> str:
    """Resolve um modo autorizado da tela de exame individual."""
    if scenario not in INDIVIDUAL_SCREENING_SCENARIOS:
        raise PipelineError(f"Modo de exame individual não autorizado: {scenario!r}")
    configured = INDIVIDUAL_SCREENING_SCENARIOS[scenario]
    resolved = (REPO / configured).resolve()
    configs_root = (REPO / "configs").resolve()
    if resolved.parent != configs_root or not resolved.is_file():
        raise PipelineError(f"Configuração autorizada não encontrada: {configured}")
    return configured


def _benchmark_model_info(config_path: str | None = None) -> dict:
    config_path = config_path or MEDGEMMA_CONFIG
    try:
        screening = load_screening_config(REPO / config_path)
        model = screening.get("medgemma", {})
        return {
            "model_id": model.get("model_id"),
            "model_version": model.get("model_version"),
            "model_parameter_scale": model.get("model_parameter_scale"),
            "runtime": model.get("runtime", "transformers"),
            "experimental_strategy": str(
                screening.get("panel", {}).get("strategy", "uniform_9")
            ),
            "config": config_path,
        }
    except Exception:  # noqa: BLE001
        return {"model_id": None, "model_version": None, "config": config_path}


def _is_visual_scenario(scenario: str) -> bool:
    return scenario in VISUAL_BENCHMARK_SCENARIOS


def _visual_bundle_root(scenario: str) -> Path:
    """Resolve o bundle do classificador visual, sem aceitar caminho do navegador."""
    if scenario not in VISUAL_BENCHMARK_SCENARIOS:
        raise PipelineError(f"Cenário visual não autorizado: {scenario!r}")
    root = (REPO / VISUAL_BENCHMARK_SCENARIOS[scenario]).resolve()
    if not (root / "bundle_manifest.json").is_file():
        raise PipelineError(
            "Bundle do classificador visual não encontrado. Gere-o com: "
            "python -m tools.train_medsiglip_multiclass train-production"
        )
    return root


def _provenance_summary(results: list[dict]) -> dict:
    """Resume a procedência dos casos e diz se as métricas são interpretáveis.

    Sem isto, a tela apresenta acurácia/sensibilidade com o mesmo destaque de um
    resultado limpo mesmo quando todos os casos podem ter sido vistos no treino
    — que é exatamente como um número inflado vira conclusão. O veredito por
    caso vem do guard de três estados (`in_sample_verdict`).
    """
    counts = {"in_sample": 0, "out_of_sample": 0, "unknown": 0}
    for row in results:
        verdict = str(row.get("in_sample_verdict") or "unknown")
        counts[verdict if verdict in counts else "unknown"] += 1
    total = sum(counts.values())
    messages = []
    if counts["in_sample"]:
        messages.append(
            f"{counts['in_sample']} de {total} caso(s) foram vistos no treino do modelo: "
            "as métricas incluem desempenho in-sample, que é inflado."
        )
    if counts["unknown"]:
        messages.append(
            f"{counts['unknown']} de {total} caso(s) têm procedência NÃO verificável "
            "contra o conjunto de treino (identificadores de nomenclatura distinta). "
            "Eles podem ser in-sample."
        )
    clean = counts["out_of_sample"] == total and total > 0
    if not clean:
        messages.append(
            "Portanto estas métricas NÃO são estimativa de generalização. "
            "A estimativa honesta do modelo é o nested-OOF da Etapa C "
            "(75,91% sens. / 76,11% esp., docs/121)."
        )
    return {
        "counts": counts,
        "metrics_are_generalization_estimate": clean,
        "warning": " ".join(messages) or None,
    }


def _visual_model_info(scenario: str) -> dict:
    """Identidade do classificador visual, com o enquadramento honesto embutido."""
    try:
        manifest = json.loads((_visual_bundle_root(scenario) / "bundle_manifest.json").read_text("utf-8"))
    except (PipelineError, OSError, json.JSONDecodeError):
        return {"model_id": "medsiglip_multiclass", "model_version": "indisponível"}
    return {
        "model_id": "medsiglip_multiclass_production_bundle",
        "model_version": str(manifest.get("candidate_id") or "hybrid_v1"),
        "bundle_signature": manifest.get("bundle_signature"),
        "decision_threshold": manifest.get("decision_threshold"),
        "generalization_estimate_source": manifest.get("generalization_estimate_source"),
        "oof_reference": "Etapa C nested-OOF 75,91%/76,11% (docs/121)",
        "gate_75_75_stable_by_dataset": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def _authorized_visual_phase_resolution(case_id: str, raw_case_dir: Path):
    """Resolve séries opacas apenas para IDs do benchmark cego autorizado.

    Casos comuns continuam usando as subpastas arterial/venous/delayed. O
    caminho do índice vem exclusivamente da configuração do servidor.
    """
    from dtwin.learning.internal_blind_phase_adapter import (
        BLIND_CASE_PATTERN,
        resolve_authorized_blind_phase_folders,
    )

    if not BLIND_CASE_PATTERN.fullmatch(str(case_id)):
        return None
    configured = Path(VISUAL_AUTHORIZED_PHASE_AUDIT)
    audit_path = configured if configured.is_absolute() else REPO / configured
    return resolve_authorized_blind_phase_folders(
        case_id=str(case_id),
        case_dir=Path(raw_case_dir),
        audit_path=audit_path.resolve(),
    )


def _run_visual_benchmark_case(
    benchmark_id: str, index: int, item: dict, raw_case_dir: Path, scenario: str
) -> dict:
    """Executa o fluxo visual da Etapa C para UM exame multifásico.

    fases (subpastas) -> harmonização na grade venosa + segmentação hepática ->
    painéis liver-enriched -> embeddings MedSigLIP -> bundle de produção.
    Qualquer falha vira falha técnica (conta como erro), nunca decisão fabricada.
    """
    from dtwin.learning.exam_to_panels import build_exam_panels
    from dtwin.learning.multiphase_ingest import build_multiphase_case
    from dtwin.learning.visual_inference import (
        classify_embeddings,
        embed_panels,
        in_sample_status,
        load_production_bundle,
    )

    benchmark_root = WORKSPACE / "benchmarks" / benchmark_id
    case_dir = (benchmark_root / "cases" / f"{index:04d}").resolve()
    started = time.monotonic()
    base = {
        "case_id": item["id"],
        "dataset": item.get("dataset", "web_upload"),
        "input_format": "DICOM_MULTIPHASE",
        "prediction": None,
        "confidence": None,
        "status": "failed",
        "error": None,
        "input_hashes": {},
        "durations_seconds": {},
    }
    try:
        bundle = load_production_bundle(_visual_bundle_root(scenario))
        authorized_resolution = _authorized_visual_phase_resolution(
            str(item["id"]), Path(raw_case_dir)
        )
        if authorized_resolution is not None:
            base["input_format"] = "DICOM_MULTIPHASE_AUTHORIZED_INDEX"
            base["phase_resolution"] = authorized_resolution.safe_manifest()

        def segment_venous(venous_dir: Path, work_dir: Path) -> Path:
            work_dir = Path(work_dir).resolve()
            prep = _segment(str(Path(venous_dir).resolve()), work_dir, "gpu", PREP_TIMEOUT_GPU, fast=False)
            if not _seg_done(work_dir):
                log.warning("Benchmark visual %s/%s: GPU falhou; tentando CPU", benchmark_id, item["id"])
                shutil.rmtree(work_dir, ignore_errors=True)
                prep = _segment(str(Path(venous_dir).resolve()), work_dir, "cpu", PREP_TIMEOUT_CPU, fast=False)
                if not _seg_done(work_dir):
                    raise PipelineError(_friendly_text(_cli_reason(prep)))
            return work_dir

        ingest_started = time.monotonic()
        multiphase = build_multiphase_case(
            case_id=str(item["id"]),
            case_upload_dir=Path(raw_case_dir),
            output_dir=case_dir / "multiphase",
            segment_venous=segment_venous,
            phase_dirs=(
                authorized_resolution.phase_dirs
                if authorized_resolution is not None
                else None
            ),
        )
        base["durations_seconds"]["multiphase_ingest_and_segmentation"] = round(
            time.monotonic() - ingest_started, 4
        )
        base["phase_coverage"] = multiphase.coverage

        panel_started = time.monotonic()
        panels = build_exam_panels(
            case_id=str(item["id"]),
            phase_paths=multiphase.phase_paths,
            coarse_liver_mask_path=multiphase.coarse_liver_mask_path,
            output_dir=case_dir / "panels",
            panel_config_path=REPO / VISUAL_PANEL_CONFIG,
        )
        base["durations_seconds"]["panel_generation"] = round(time.monotonic() - panel_started, 4)

        inference_started = time.monotonic()
        embeddings = embed_panels(REPO / VISUAL_EMBEDDING_CONFIG, panels.panel_paths)
        decision = classify_embeddings(bundle, embeddings)
        base["durations_seconds"]["visual_inference"] = round(time.monotonic() - inference_started, 4)

        # Sem mapa de proveniência, um identificador de coorte com nomenclatura
        # própria (ex.: benchmark cego) cai em 'unknown' — que NÃO é o mesmo que
        # out-of-sample e não deve ser lido como tal.
        status = in_sample_status(bundle, case_id=str(item["id"]))
        base.update(
            prediction="POSITIVA" if decision["prediction"] == "POSITIVE" else "NEGATIVA",
            confidence=None,
            status="decisive",
            visual_score=decision["score"],
            visual_threshold=decision["threshold"],
            panel_count=decision["panel_count"],
            in_sample=status["in_sample"],
            in_sample_verdict=status["verdict"],
        )
        return base
    except subprocess.TimeoutExpired:
        base["error"] = "O processamento excedeu o tempo limite."
        base["status"] = "timeout"
        return base
    except PipelineError as exc:
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        log.exception("Benchmark visual %s/%s: falha inesperada", benchmark_id, item["id"])
        base["error"] = f"Falha inesperada: {type(exc).__name__}"
        return base
    finally:
        base["duration_seconds"] = round(time.monotonic() - started, 2)
        base["durations_seconds"]["total"] = round(time.monotonic() - started, 4)


def _run_benchmark_case(
    benchmark_id: str,
    index: int,
    item: dict,
    raw_case_dir: Path,
    medgemma_config: str | None = None,
) -> dict:
    """Executa segmentação + triagem para um exame, sem gerar a malha 3D."""
    benchmark_root = WORKSPACE / "benchmarks" / benchmark_id
    # case_dir PRECISA ser absoluto: a segmentação roda por um launcher com
    # cwd=%TEMP% (workaround do nnU-Net no Windows). Se for relativo, a saída cai
    # sob %TEMP% e _seg_done() — avaliado a partir da raiz do repo — nunca a
    # encontra, marcando TODO exame como falha (e forçando o fallback lento p/ CPU).
    # O fluxo de exame individual (process_job) já resolve por isso; espelhamos aqui.
    case_dir = (benchmark_root / "cases" / f"{index:04d}").resolve()
    series_dir = benchmark_root / "_series" / f"{index:04d}"
    started = time.monotonic()
    base = {
        "case_id": item["id"],
        "dataset": item.get("dataset", "web_upload"),
        "input_format": "DICOM",
        "prediction": None,
        "confidence": None,
        "status": "failed",
        "error": None,
        "input_hashes": {},
        "durations_seconds": {},
    }
    medgemma_config = medgemma_config or MEDGEMMA_CONFIG
    try:
        import_started = time.monotonic()
        best_files, n = find_best_series(raw_case_dir)
        if not best_files or n < MIN_SLICES:
            base["error"] = "Nenhuma série DICOM de RM válida foi encontrada."
            return base

        series_dir.mkdir(parents=True, exist_ok=True)
        for file_index, source in enumerate(best_files):
            shutil.copyfile(source, series_dir / f"{file_index:05d}_{os.path.basename(source)}")
        base["durations_seconds"]["import"] = round(time.monotonic() - import_started, 4)

        preparation_started = time.monotonic()
        prep = _segment(str(series_dir.resolve()), case_dir, "gpu", PREP_TIMEOUT_GPU, fast=True)
        if not _seg_done(case_dir):
            reason = _cli_reason(prep)
            log.warning("Benchmark %s/%s: GPU falhou (%s); tentando CPU", benchmark_id, item["id"], reason[:100])
            shutil.rmtree(case_dir, ignore_errors=True)
            prep = _segment(str(series_dir.resolve()), case_dir, "cpu", PREP_TIMEOUT_CPU, fast=True)
            if not _seg_done(case_dir):
                base["error"] = _friendly_text(_cli_reason(prep))
                return base
        _persist_series_selection(case_dir, best_files)
        base["durations_seconds"]["preparation_and_segmentation"] = round(
            time.monotonic() - preparation_started, 4
        )

        screening_started = time.monotonic()
        screening_config = load_screening_config(REPO / medgemma_config)
        effective_timeout, expected_panel_count = effective_screening_timeout(
            sitk.GetArrayFromImage(sitk.ReadImage(str(case_dir / "mask_organ.nii.gz"))) > 0,
            screening_config,
            SCREEN_TIMEOUT,
        )
        with _medgemma_screening_lock:
            screening = _run(
                [
                    PY,
                    "-m",
                    "dtwin.medgemma_screening",
                    "--case-dir",
                    str(case_dir),
                    "--medgemma-config",
                    medgemma_config,
                    "--confirm-no-visible-phi",
                ],
                timeout=effective_timeout,
            )
        envelope = _load_report(case_dir / "outputs" / "medgemma" / "medgemma_report.json")
        if envelope is None:
            reason = _cli_reason(screening)
            base["error"] = _friendly_text(reason)
            base["status"] = classify_screening_failure(reason).value
            base["screening_diagnostics"] = _persist_screening_diagnostics(case_dir, screening)
            failure_path = case_dir / "outputs" / "medgemma" / "medgemma_failure.json"
            if failure_path.is_file():
                base["failure_artifact"] = str(failure_path.relative_to(case_dir))
            return base

        report = envelope["report"]
        base["durations_seconds"].update(envelope.get("durations_seconds") or {})
        base["durations_seconds"]["screening_subprocess"] = round(
            time.monotonic() - screening_started, 4
        )
        base["input_hashes"] = {
            "volume": envelope.get("input_volume_sha256"),
            "mask_organ": envelope.get("input_liver_mask_sha256"),
            "panel": envelope.get("input_panel_sha256"),
            "screening_config": envelope.get("screening_config_sha256"),
            "panels": {
                item["image"]: item["sha256"] for item in envelope.get("input_panels", [])
            },
        }
        prediction = str(report.get("resultado_hipotese", "")).upper()
        if prediction not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}:
            base["error"] = "O relatório retornou uma classificação inválida."
            base["status"] = "invalid_response"
            return base
        base.update(
            prediction=prediction,
            confidence=report.get("confianca"),
            status="inconclusive" if prediction == "INCONCLUSIVA" else "decisive",
            report_summary=report.get("resumo_do_achado"),
            # Campos v2 (schema pathology-target) só existem quando o modelo os
            # emite; preservados aqui para estratificar o benchmark e o CSV.
            report_v2={
                key: report[key] for key in OPTIONAL_REPORT_V2_FIELDS if key in report
            },
            report_path=str(
                Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / "medgemma_report.json"
            ),
            panel_path=str(
                Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / str(envelope.get("input_panel") or "")
            ),
            panel_paths=[
                str(Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / item["image"])
                for item in envelope.get("input_panels", [])
            ],
            panel_strategy=screening_config.get("panel", {}).get("strategy", "uniform_9"),
            expected_panel_count=expected_panel_count,
            effective_screening_timeout_seconds=effective_timeout,
        )
        return base
    except subprocess.TimeoutExpired:
        base["error"] = "O processamento excedeu o tempo limite."
        base["status"] = "timeout"
        return base
    except Exception as exc:  # noqa: BLE001
        log.exception("Benchmark %s/%s: falha inesperada", benchmark_id, item["id"])
        base["error"] = f"Falha inesperada: {type(exc).__name__}"
        return base
    finally:
        base["duration_seconds"] = round(time.monotonic() - started, 2)
        base["durations_seconds"]["total"] = round(time.monotonic() - started, 4)
        shutil.rmtree(series_dir, ignore_errors=True)


def _evaluate_benchmark_result(inference_result: dict, label: str) -> dict:
    """Anexa o ground truth somente após a inferência ter encerrado."""
    started = time.monotonic()
    result = dict(inference_result)
    expected = "POSITIVA" if label == "positive" else "NEGATIVA"
    prediction = result.get("prediction")
    result.update(
        truth=label,
        correct=(prediction == expected) if prediction in {"POSITIVA", "NEGATIVA"} else None,
        protected_ground_truth_hashes={"lesion_mask": None, "annotation_manifest": None},
    )
    durations = dict(result.get("durations_seconds") or {})
    durations["evaluation"] = round(time.monotonic() - started, 4)
    result["durations_seconds"] = durations
    return result


def process_benchmark(benchmark_id: str, manifest: dict, raw_dir: Path) -> None:
    benchmark_root = WORKSPACE / "benchmarks" / benchmark_id
    cases = manifest["cases"]
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []
    try:
        scenario = manifest.get("scenario", "baseline")
        visual = _is_visual_scenario(scenario)
        medgemma_config = None if visual else _benchmark_config(scenario)
        _set_benchmark(benchmark_id, state="processing", started_at=started_at)
        for index, item in enumerate(cases, start=1):
            progress = 5 + int(((index - 1) / max(len(cases), 1)) * 90)
            _set_benchmark(
                benchmark_id,
                current_case=item["id"],
                processed=index - 1,
                progress=progress,
            )
            case_item = {"id": item["id"], "dataset": manifest["dataset_name"]}
            if visual:
                inference_result = _run_visual_benchmark_case(
                    benchmark_id, index, case_item, raw_dir / f"{index:04d}", scenario
                )
            else:
                inference_result = _run_benchmark_case(
                    benchmark_id, index, case_item, raw_dir / f"{index:04d}", medgemma_config
                )
            results.append(_evaluate_benchmark_result(inference_result, item["label"]))
            _set_benchmark(benchmark_id, processed=index, progress=5 + int(index / len(cases) * 90))

        completed_at = datetime.now(timezone.utc).isoformat()
        model_info = (
            _visual_model_info(scenario) if visual else _benchmark_model_info(medgemma_config)
        )
        metrics = calculate_benchmark_metrics(results)
        report = {
            "schema_version": 1,
            "benchmark_id": benchmark_id,
            "dataset_name": manifest["dataset_name"],
            "dataset_kind": manifest["dataset_kind"],
            "scenario": manifest.get("scenario", "baseline"),
            "started_at": started_at,
            "completed_at": completed_at,
            "model": model_info,
            "metrics": metrics,
            "provenance": _provenance_summary(results) if visual else None,
            "cases": results,
            "disclaimer": DISCLAIMER,
        }
        benchmark_root.mkdir(parents=True, exist_ok=True)
        report_path = benchmark_root / "benchmark_report.json"
        temp = benchmark_root / ".benchmark_report.json.tmp"
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(report_path)
        config_path = (
            None
            if visual
            else (REPO / str(medgemma_config)).resolve()
        )
        run_manifest = {
            "schema_version": 1,
            "run_id": benchmark_id,
            "created_at": started_at,
            **git_state(REPO),
            "model_family": "MedSigLIP" if visual else "MedGemma",
            **model_info,
            "medgemma_config_path": medgemma_config,
            "medgemma_config_hash": (
                effective_config_sha256(load_screening_config(config_path))
                if config_path is not None and config_path.is_file()
                else None
            ),
            "visual_panel_config_path": VISUAL_PANEL_CONFIG if visual else None,
            "visual_embedding_config_path": VISUAL_EMBEDDING_CONFIG if visual else None,
            "visual_panel_config_sha256": (
                sha256_of((REPO / VISUAL_PANEL_CONFIG).resolve())
                if visual and (REPO / VISUAL_PANEL_CONFIG).is_file()
                else None
            ),
            "visual_embedding_config_sha256": (
                sha256_of((REPO / VISUAL_EMBEDDING_CONFIG).resolve())
                if visual and (REPO / VISUAL_EMBEDDING_CONFIG).is_file()
                else None
            ),
            "dataset_names": [manifest["dataset_name"]],
            "num_cases_total": len(cases),
            "num_cases_positive": sum(item["label"] == "positive" for item in cases),
            "num_cases_negative": sum(item["label"] == "negative" for item in cases),
            "started_at": started_at,
            "finished_at": completed_at,
            "duration_seconds_total": round(
                sum(float(item.get("duration_seconds") or 0) for item in results), 4
            ),
            "environment": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            "research_only": True,
        }
        write_run_outputs(benchmark_root, run_manifest, results, metrics)
        _set_benchmark(
            benchmark_id,
            state="done",
            current_case=None,
            processed=len(cases),
            progress=100,
            report=report,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Benchmark %s: falha inesperada", benchmark_id)
        _set_benchmark(
            benchmark_id,
            state="failed",
            progress=100,
            error=f"Não foi possível concluir o benchmark: {type(exc).__name__}",
        )
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)


def _parse_benchmark_manifest(raw: str, file_count: int) -> dict:
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Manifesto do benchmark inválido.") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="Manifesto do benchmark inválido.")
    dataset_name = str(manifest.get("dataset_name") or "").strip()[:120]
    dataset_kind = manifest.get("dataset_kind")
    scenario = str(manifest.get("scenario") or "baseline")
    cases = manifest.get("cases")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="Informe o nome do dataset.")
    if dataset_kind not in {"positive", "negative", "mixed"}:
        raise HTTPException(status_code=400, detail="Tipo de dataset inválido.")
    if scenario not in BENCHMARK_SCENARIOS and scenario not in VISUAL_BENCHMARK_SCENARIOS:
        raise HTTPException(status_code=400, detail="Cenário de benchmark inválido.")
    if not isinstance(cases, list) or not cases:
        raise HTTPException(status_code=400, detail="Nenhum exame foi identificado no dataset.")

    seen_ids: set[str] = set()
    seen_files: set[int] = set()
    normalized = []
    for case in cases:
        if not isinstance(case, dict):
            raise HTTPException(status_code=400, detail="Definição de exame inválida.")
        case_id = str(case.get("id") or "").strip()[:120]
        label = case.get("label")
        indices = case.get("file_indices")
        if not case_id or case_id in seen_ids:
            raise HTTPException(status_code=400, detail="Os exames precisam de identificadores únicos.")
        if label not in {"positive", "negative"}:
            raise HTTPException(status_code=400, detail=f"Rótulo inválido no exame {case_id}.")
        if dataset_kind in {"positive", "negative"} and label != dataset_kind:
            raise HTTPException(
                status_code=400,
                detail=f"O rótulo do exame {case_id} não corresponde ao tipo do dataset.",
            )
        if not isinstance(indices, list) or not indices:
            raise HTTPException(status_code=400, detail=f"O exame {case_id} não contém arquivos.")
        clean_indices = []
        for value in indices:
            if not isinstance(value, int) or value < 0 or value >= file_count or value in seen_files:
                raise HTTPException(status_code=400, detail="Mapeamento de arquivos do benchmark inválido.")
            seen_files.add(value)
            clean_indices.append(value)
        seen_ids.add(case_id)
        normalized.append({"id": case_id, "label": label, "file_indices": clean_indices})
    if seen_files != set(range(file_count)):
        raise HTTPException(status_code=400, detail="Todos os arquivos devem pertencer a um exame.")
    return {
        "dataset_name": dataset_name, "dataset_kind": dataset_kind,
        "scenario": scenario, "cases": normalized,
    }


def _csv_cell(value: Any) -> Any:
    """Serializa valores compostos/booleanos de forma estável para o CSV."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    return value


def _benchmark_csv(report: dict) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "case_id", "truth", "prediction", "status", "correct", "confidence",
        "duration_seconds", "error",
        # Taxonomia protegida (preenchida quando o manifesto a declara).
        "target_condition", "negative_subtype", "positive_subtype", "phenotype_tags",
        # Schema v2 do relatório MedGemma (cenário pathology-target).
        "ha_lesao_focal_suspeita", "ha_variante_anatomica_benigna",
        "ha_pseudolesao_ou_artefato", "tipo_alteracao_nao_alvo",
    ])
    for item in report.get("cases", []):
        v2 = item.get("report_v2") or {}
        writer.writerow([
            item.get("case_id"), item.get("truth"), item.get("prediction"),
            item.get("status"), item.get("correct"), item.get("confidence"),
            item.get("duration_seconds"), _csv_cell(item.get("error")),
            _csv_cell(item.get("target_condition")),
            _csv_cell(item.get("negative_subtype")),
            _csv_cell(item.get("positive_subtype")),
            _csv_cell(item.get("phenotype_tags")),
            _csv_cell(v2.get("ha_lesao_focal_suspeita")),
            _csv_cell(v2.get("ha_variante_anatomica_benigna")),
            _csv_cell(v2.get("ha_pseudolesao_ou_artefato")),
            _csv_cell(v2.get("tipo_alteracao_nao_alvo")),
        ])
    return stream.getvalue()


async def _upload_form(request: Request) -> FormData:
    """Analisa o multipart com o teto de arquivos elevado (MAX_UPLOAD_FILES).

    FastAPI não expõe max_files/max_fields do parser do Starlette através de
    File(...)/Form(...); por isso o form é lido manualmente aqui, nos dois
    endpoints que recebem upload de exames. Sem `async with`: os UploadFile
    precisam continuar abertos até serem lidos no corpo do endpoint; o
    encerramento/limpeza é feito pelo próprio Starlette ao fim da requisição."""
    return await request.form(max_files=MAX_UPLOAD_FILES, max_fields=MAX_UPLOAD_FILES)


app = FastAPI(title="Digital Twin — Triagem MedGemma (demo, modo Pesquisa)")


@app.get("/api/health")
def health() -> dict:
    backend = "desligado"
    try:
        with urlopen(HEALTH_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        backend = "pronto" if data.get("status") == "ready" else "carregando"
    except Exception:  # noqa: BLE001
        backend = "desligado"
    return {"backend": backend}


@app.post("/api/analyze")
async def analyze(request: Request) -> dict:
    form = await _upload_form(request)
    files = [v for v in form.getlist("files") if not isinstance(v, str)]
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    scenario = str(form.get("scenario") or "volumetric_rag")
    try:
        medgemma_config = _individual_screening_config(scenario)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    relpaths = form.get("relpaths")
    job_id = uuid.uuid4().hex[:12]
    raw_dir = WORKSPACE / job_id / "_upload"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        paths = json.loads(relpaths) if isinstance(relpaths, str) else []
        if not isinstance(paths, list):
            paths = []
    except Exception:  # noqa: BLE001
        paths = []
    for i, uf in enumerate(files):
        rel = (paths[i] if i < len(paths) and paths[i] else uf.filename) or f"file_{i}"
        parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", "..", ".")]
        dest = raw_dir.joinpath(*parts) if parts else raw_dir / f"file_{i}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await uf.read())
    with _lock:
        _jobs[job_id] = {
            "state": "queued", "step": "recebendo", "progress": 5, "result": None,
            "analysis_scenario": scenario,
        }
    threading.Thread(
        target=process_job,
        args=(job_id, raw_dir, medgemma_config, scenario),
        daemon=True,
    ).start()
    return {"job_id": job_id, "analysis_scenario": scenario}


@app.get("/api/status/{job_id}")
def status(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return {
        "state": job["state"],
        "step": job["step"],
        "progress": job["progress"],
        "analysis_scenario": job.get("analysis_scenario"),
        "result": job["result"] if job["state"] == "done" else None,
        "approval": job.get("approval"),
        "operational_timing": job.get("operational_timing"),
        "operational_timing_artifact": job.get("operational_timing_artifact"),
    }


@app.post("/api/benchmarks")
async def create_benchmark(request: Request) -> dict:
    form = await _upload_form(request)
    files = [v for v in form.getlist("files") if not isinstance(v, str)]
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    manifest = form.get("manifest")
    if not isinstance(manifest, str):
        raise HTTPException(status_code=400, detail="Manifesto do benchmark ausente.")
    parsed = _parse_benchmark_manifest(manifest, len(files))
    benchmark_id = uuid.uuid4().hex[:12]
    raw_dir = WORKSPACE / "benchmarks" / benchmark_id / "_upload"
    # O cenário visual precisa saber de QUAL subpasta cada arquivo veio (a fase),
    # então a estrutura relativa é preservada em vez de achatada. Os cenários
    # MedGemma continuam achatando: eles escolhem uma única série por caso e a
    # estrutura é irrelevante para eles.
    preserve_structure = _is_visual_scenario(parsed["scenario"])
    relpaths_raw = form.get("relpaths")
    try:
        relpaths = json.loads(relpaths_raw) if isinstance(relpaths_raw, str) else []
        if not isinstance(relpaths, list):
            relpaths = []
    except json.JSONDecodeError:
        relpaths = []
    if preserve_structure and not relpaths:
        raise HTTPException(
            status_code=400,
            detail=(
                "O cenário visual exige as fases em subpastas (arterial/venous/delayed). "
                "Reenvie selecionando a pasta do dataset."
            ),
        )
    try:
        for case_index, item in enumerate(parsed["cases"], start=1):
            case_upload = raw_dir / f"{case_index:04d}"
            case_upload.mkdir(parents=True, exist_ok=True)
            for local_index, file_index in enumerate(item["file_indices"]):
                upload = files[file_index]
                original_name = Path(upload.filename or f"file_{file_index}").name
                if preserve_structure:
                    relative = relpaths[file_index] if file_index < len(relpaths) else ""
                    parts = [
                        part
                        for part in str(relative or "").replace("\\", "/").split("/")
                        if part not in ("", ".", "..")
                    ]
                    # descarta o primeiro nível (pasta do caso): a fase é o resto
                    destination = case_upload.joinpath(*parts[1:]) if len(parts) > 1 else (
                        case_upload / f"{local_index:06d}_{original_name}"
                    )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(await upload.read())
                    continue
                destination = case_upload / f"{local_index:06d}_{original_name}"
                destination.write_bytes(await upload.read())
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(raw_dir.parent, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Falha ao receber os arquivos do dataset.") from exc

    with _lock:
        _benchmarks[benchmark_id] = {
            "state": "queued",
            "progress": 2,
            "processed": 0,
            "total": len(parsed["cases"]),
            "current_case": None,
            "report": None,
            "error": None,
        }
    threading.Thread(
        target=process_benchmark,
        args=(benchmark_id, parsed, raw_dir),
        daemon=True,
    ).start()
    return {"benchmark_id": benchmark_id, "total_cases": len(parsed["cases"])}


@app.get("/api/benchmarks/{benchmark_id}")
def benchmark_status(benchmark_id: str) -> dict:
    with _lock:
        benchmark = _benchmarks.get(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark não encontrado.")
    return {
        "state": benchmark["state"],
        "progress": benchmark["progress"],
        "processed": benchmark["processed"],
        "total": benchmark["total"],
        "current_case": benchmark.get("current_case"),
        "report": benchmark.get("report") if benchmark["state"] == "done" else None,
        "error": benchmark.get("error"),
    }


@app.get("/api/benchmarks/{benchmark_id}/report.json")
def benchmark_report_json(benchmark_id: str):
    if not benchmark_id or any(ch not in "0123456789abcdef" for ch in benchmark_id.lower()):
        raise HTTPException(status_code=404, detail="Benchmark não encontrado.")
    path = WORKSPACE / "benchmarks" / benchmark_id / "benchmark_report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Relatório ainda não disponível.")
    return FileResponse(path, media_type="application/json", filename=f"benchmark-{benchmark_id}.json")


@app.get("/api/benchmarks/{benchmark_id}/report.csv")
def benchmark_report_csv(benchmark_id: str):
    if not benchmark_id or any(ch not in "0123456789abcdef" for ch in benchmark_id.lower()):
        raise HTTPException(status_code=404, detail="Benchmark não encontrado.")
    path = WORKSPACE / "benchmarks" / benchmark_id / "benchmark_report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Relatório ainda não disponível.")
    try:
        report = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Relatório inválido.") from exc
    return Response(
        content=_benchmark_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="benchmark-{benchmark_id}.csv"'},
    )


@app.get("/api/jobs/{job_id}/model/viewer_manifest.json")
def model_manifest(job_id: str):
    path = _case_dir_for_job(job_id) / "outputs" / "viewer_manifest.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Modelo 3D nao disponivel.")
    return FileResponse(path, media_type="application/json")


@app.get("/api/jobs/{job_id}/model/{filename}")
def model_file(job_id: str, filename: str):
    case_dir = _case_dir_for_job(job_id)
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    if Path(filename).name != filename or not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        allowed = {item.get("stl") for item in manifest.get("meshes", []) if isinstance(item, dict)}
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Manifesto do modelo invalido.")
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    path = manifest_path.parent / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    return FileResponse(path, media_type="model/stl", filename=filename)


@app.post("/api/jobs/{job_id}/approval")
def approve_model(job_id: str, payload: ApprovalPayload) -> dict:
    case_dir = _case_dir_for_job(job_id)
    if not _model_done(case_dir):
        raise HTTPException(status_code=409, detail="Modelo 3D ainda nao esta disponivel.")
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    approval = {
        "status": payload.status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_type": "human_visual_review",
    }
    path = case_dir / "outputs" / "approval.json"
    temp = path.with_name(".approval.json.tmp")
    temp.write_text(json.dumps(approval, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    _set(job_id, approval=approval)
    return approval


STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/viewer", StaticFiles(directory=str(VIEWER), html=True), name="viewer")
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")


def main() -> int:
    import uvicorn

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("WEBAPP_PORT", "8000")), log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
