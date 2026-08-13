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
import hashlib
import io
import json
import logging
import math
import os
import platform
import shutil
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.request import urlopen

import numpy as np
import pydicom
import SimpleITK as sitk
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import FormData

from dtwin.benchmark.metrics import compute_benchmark_metrics
from dtwin.benchmark.subtype_metrics import (
    SUBTYPE_CLASSES,
    binary_label_for_subtype,
    compute_subtype_metrics,
)
from dtwin.benchmark.hashing import git_state
from dtwin.benchmark.reporting import write_run_outputs
from dtwin.benchmark.runner import classify_screening_failure
from dtwin.benchmark.dataset_audit import (
    describe_selected_series,
    select_best_mr_series,
    select_monophase_evidence_series,
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
from dtwin.candidate_subprocess import candidate_error, run_candidate_subprocess
from dtwin.learning.monophase_protocol import (
    build_hierarchical_screening_result,
    resolve_monophase_sequence_contract,
)

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
MONOPHASE_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_MONOPHASE_MEDGEMMA_CONFIG",
    "configs/medgemma_local_4b_monophase_rag.yaml",
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
MONOPHASE_DELAYED_VISUAL_BUNDLE = os.environ.get(
    "WEBAPP_MONOPHASE_DELAYED_VISUAL_BUNDLE",
    "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_production_bundle_v2",
)
# Promotion is deliberately fail-closed. The internal LLD gate passed, but the
# label-blind OpenSwiss evaluation failed sensitivity (25.40%). Keep the worker
# available for reproducible research without silently making it the product
# fallback. A future signed external gate may replace this environment switch.
MONOPHASE_DELAYED_VISUAL_AUTO_PROMOTED = (
    os.environ.get("WEBAPP_MONOPHASE_DELAYED_MEDSIGLIP_AUTO_PROMOTED", "0") == "1"
)
# The delayed head remains useful as an independent research signal even though
# it failed the external promotion gate.  In advisory mode it is never allowed
# to overwrite the MedGemma report; it only exposes agreement/disagreement for
# mandatory human review.  This is enabled by default because the primary
# decision remains unchanged and every limitation is persisted with the result.
MONOPHASE_DELAYED_ADVISORY_ENABLED = (
    os.environ.get("WEBAPP_MONOPHASE_DELAYED_MEDSIGLIP_ADVISORY", "1") == "1"
)
# Índice server-side autorizado para o benchmark interno. O navegador nunca
# envia esse caminho e o conteúdo privado nunca é encaminhado ao modelo.
VISUAL_AUTHORIZED_PHASE_AUDIT = os.environ.get(
    "WEBAPP_VISUAL_AUTHORIZED_PHASE_AUDIT",
    "ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1/private_reference/conversion_audit.json",
)
# O exame individual roda um único caminho: o classificador visual da Etapa C, de
# melhor acertividade medida (75,91%/76,11% agregado nested-OOF) e o único que
# identifica QUAL alteração há. Não há seleção de modo na interface nem na API --
# oferecer alternativas mais fracas convidaria a escolher a pior sem ter como
# saber disso.
INDIVIDUAL_SCREENING_MODE = "hybrid_supervised"
# Mantido para o benchmark e para uso por linha de comando, onde comparar
# configurações é justamente o objetivo. Não é alcançável pelo exame individual.
INDIVIDUAL_SCREENING_SCENARIOS = {
    "volumetric_rag": VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    "pathology_target": PATHOLOGY_TARGET_MEDGEMMA_CONFIG,
}
HEALTH_URL = os.environ.get("WEBAPP_MEDGEMMA_HEALTH", "http://127.0.0.1:8001/health")

# ---------------------------------------------------------------------------
# Backends MedGemma selecionáveis (27B / 4B).
#
# Um gateway carrega UM modelo. Para trocar sem reiniciar, sobe-se um gateway
# por modelo em portas distintas; cada config já carrega o próprio
# `endpoint_url`/`healthcheck_url`, então a troca é só escolher qual config o
# job usa.
#
# Isto NÃO muda o método de análise, e é importante não confundir com a seleção
# de cenário que foi deliberadamente removida da interface: o exame trifásico
# roda o classificador visual congelado e NÃO usa MedGemma. Este seletor afeta
# apenas onde o MedGemma é de fato usado -- fallback monofásico e benchmark.
#
# Formato: id=rótulo=config[=health_url], separados por ';'.
MEDGEMMA_BACKENDS_SPEC = os.environ.get("WEBAPP_MEDGEMMA_BACKENDS", "").strip()


def _parse_medgemma_backends(spec: str) -> dict[str, dict[str, str]]:
    """Lê o registro de backends declarado pelo launcher.

    Falha fechado por entrada: uma linha malformada é ignorada com aviso, em vez
    de derrubar o servidor ou -- pior -- criar um backend fantasma que a
    interface oferece e que não existe.
    """
    backends: dict[str, dict[str, str]] = {}
    for entry in spec.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        parts = [piece.strip() for piece in entry.split("=")]
        if len(parts) < 3 or not all(parts[:3]):
            log.warning("Backend MedGemma ignorado (formato inválido): %r", entry)
            continue
        identifier, label, config_path = parts[0], parts[1], parts[2]
        health = parts[3] if len(parts) > 3 and parts[3] else ""
        if not (REPO / config_path).is_file():
            log.warning("Backend MedGemma %r ignorado: config ausente (%s)", identifier, config_path)
            continue
        if not health:
            health = _health_url_from_config(config_path)
        backends[identifier] = {"id": identifier, "label": label, "config": config_path, "health": health}
    return backends


def _health_url_from_config(config_path: str) -> str:
    """Extrai o healthcheck declarado pelo próprio config do backend."""
    try:
        data = yaml.safe_load((REPO / config_path).read_text(encoding="utf-8")) or {}
        value = (
            ((data.get("medgemma_screening") or {}).get("medgemma") or {}).get("healthcheck_url")
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Não foi possível ler healthcheck de %s: %s", config_path, exc)
    return HEALTH_URL


MEDGEMMA_BACKENDS = _parse_medgemma_backends(MEDGEMMA_BACKENDS_SPEC)


def _medgemma_backend_config(backend_id: str | None, fallback: str) -> str:
    """Resolve o config do backend pedido, recusando id não registrado.

    Recusar em vez de cair no padrão é deliberado: se a interface pediu 27B e o
    servidor silenciosamente usasse 4B, o relatório sairia com o nome do modelo
    errado -- e o nome do modelo é parte do registro de proveniência.
    """
    if not backend_id:
        return fallback
    backend = MEDGEMMA_BACKENDS.get(str(backend_id))
    if backend is None:
        raise PipelineError(
            f"Backend MedGemma não autorizado: {backend_id!r}. "
            f"Disponíveis: {sorted(MEDGEMMA_BACKENDS) or 'nenhum'}."
        )
    return backend["config"]
MIN_SLICES = 3
PREP_TIMEOUT_GPU = int(os.environ.get("WEBAPP_PREP_TIMEOUT_GPU", "900"))
PREP_TIMEOUT_CPU = int(os.environ.get("WEBAPP_PREP_TIMEOUT_CPU", "2400"))
SCREEN_TIMEOUT = int(os.environ.get("WEBAPP_SCREEN_TIMEOUT", "600"))
MODEL_TIMEOUT = int(os.environ.get("WEBAPP_MODEL_TIMEOUT", "300"))
CANDIDATE_TIMEOUT = int(os.environ.get("WEBAPP_CANDIDATE_TIMEOUT", "95"))
# Tempo por fase extra (arterial, tardia) ao construir a máscara de
# visualização (docs/188 §9, docs/189). Roda depois da decisão congelada; uma
# fase que estoura o tempo é só excluída da união, nunca falha o exame.
UNION_PHASE_TIMEOUT = int(os.environ.get("WEBAPP_UNION_PHASE_TIMEOUT", "240"))
UNION_MASK_ENABLED = os.environ.get("WEBAPP_UNION_MASK_ENABLED", "1") == "1"
SEGMENTATION_VISUALIZATION_CONFIG = REPO / "configs/segmentation_visualization_v2.yaml"
try:
    _segmentation_visualization_config = yaml.safe_load(
        SEGMENTATION_VISUALIZATION_CONFIG.read_text(encoding="utf-8")
    ) or {}
except (OSError, yaml.YAMLError):
    _segmentation_visualization_config = {}
_authorized_segmentation_backends = {
    str(item.get("id"))
    for item in (_segmentation_visualization_config.get("candidate_backends") or [])
    if isinstance(item, dict) and item.get("enabled") is True
}
ENHANCED_3D_OPT_IN_ENABLED = bool(
    _segmentation_visualization_config.get("enabled")
    and ((_segmentation_visualization_config.get("webapp") or {}).get(
        "available_in_individual_exam"
    ))
    and "mrsegmentator" in _authorized_segmentation_backends
)
_mrsegmentator_environment = REPO / ".venv-mrseg"
_mrsegmentator_default = _mrsegmentator_environment / (
    "Scripts/mrsegmentator.exe" if os.name == "nt" else "bin/mrsegmentator"
)
# The Windows installation intentionally uses its isolated .venv-mrseg.  A
# container installs the same executable system-wide and declares its absolute
# path explicitly.  Browser input can never influence this value.
MRSEGMENTATOR_EXE = Path(
    os.environ.get("WEBAPP_MRSEGMENTATOR_EXE", str(_mrsegmentator_default))
).resolve()
ENHANCED_3D_TIMEOUT = int(os.environ.get("WEBAPP_ENHANCED_3D_TIMEOUT", "180"))
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
    completed_snapshot = None
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(**kw)
            if _jobs[job_id].get("state") == "done":
                completed_snapshot = dict(_jobs[job_id])
    if completed_snapshot is not None:
        try:
            _persist_completed_job_state(job_id, completed_snapshot)
        except Exception:  # noqa: BLE001
            log.exception("Job %s: falha ao persistir estado final", job_id)


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


# Motivos do gate anatômico, em português, para a tela.
_MOTIVOS_MASCARA = {
    "mask_missing": "a máscara do fígado não foi gerada",
    "geometry_mismatch": "a máscara não está na mesma grade do exame",
    "physical_volume_below_minimum": "o volume segmentado é pequeno demais para um fígado adulto",
    "axial_extent_below_minimum": "a altura do fígado segmentado é pequena demais",
    "inplane_extent_below_minimum": "a largura do fígado segmentado é pequena demais",
    "excessive_fragmentation": "a segmentação ficou fragmentada em várias partes",
}


def _mask_quality(case_dir: Path) -> dict:
    """Aplica ao webapp o MESMO gate de plausibilidade anatômica da pesquisa.

    Sem isso, o webapp reportava resultados que o pipeline de pesquisa contaria
    como falha técnica: um fígado segmentado pela metade produz painéis errados,
    e uma classificação a partir deles não é confiável, mesmo quando acerta.

    Caso real que motivou: um exame cujo fígado saiu com 283 mL e 69 mm de altura
    craniocaudal — menos da metade de um fígado adulto, sem tocar a borda do
    volume (ou seja, não era corte de campo de visão, era sub-segmentação).
    """
    from dtwin.benchmark.lld_mmri_v23_mask_quality import evaluate_liver_mask_quality

    import SimpleITK as sitk

    referencia = sitk.ReadImage(str(case_dir / "volume.nii.gz"))
    return evaluate_liver_mask_quality(case_dir / "mask_organ.nii.gz", referencia)


def _motivo_mascara(qualidade: dict) -> str:
    motivos = [
        _MOTIVOS_MASCARA.get(r, r) for r in qualidade.get("failure_reasons", [])
    ]
    return "; ".join(motivos) if motivos else "a máscara não passou na verificação"


def _segmentar_figado_com_gate(venous_dir: Path, destino: Path, rotulo: str) -> dict:
    """Segmenta o fígado e só entrega a máscara se ela for anatomicamente plausível.

    Ponto ÚNICO de decisão, usado pelo exame individual e pelo benchmark. Os dois
    já divergiram: o gate existia só no caminho individual, e o mesmo exame — os
    mesmos arquivos — era recusado numa página e contado como acerto na outra
    (docs/175). Enquanto houver uma função só, isso não volta.

    Falhar aqui é o comportamento correto, não um efeito colateral: os painéis são
    recortados desta máscara, então classificar sobre meio fígado é acertar por
    sorte. No benchmark a exceção vira falha técnica, que a política de métricas
    já conta como erro.
    """
    destino = Path(destino).resolve()
    proc = _segment(str(Path(venous_dir).resolve()), destino, "gpu", PREP_TIMEOUT_GPU, fast=False)
    if not _seg_done(destino):
        log.warning("%s: GPU falhou; tentando CPU", rotulo)
        shutil.rmtree(destino, ignore_errors=True)
        proc = _segment(str(Path(venous_dir).resolve()), destino, "cpu", PREP_TIMEOUT_CPU, fast=False)
        if not _seg_done(destino):
            raise PipelineError(_friendly_text(_cli_reason(proc)))
    qualidade = _mask_quality(destino)
    if not qualidade["gate_passed"]:
        log.warning("%s: máscara reprovada (%s)", rotulo, qualidade["failure_reasons"])
        raise PipelineError(
            "A segmentação do fígado não ficou anatomicamente plausível: "
            + _motivo_mascara(qualidade)
            + ". Um resultado calculado sobre ela não seria confiável."
        )
    return qualidade


# Faixa de plausibilidade do fígado adulto. O piso de 300 mL do gate pega só os
# desastres; entre 300 e 900 mL a segmentação passa mas quase certamente perdeu
# parte do órgão, e o usuário precisa saber disso ao olhar o modelo 3D.
#
# Medido nos 321 casos LLD do pipeline de pesquisa (docs/175): mediana 637 mL,
# p10 164 mL, e 76% abaixo de 900 mL. Não é uma cauda: na MAIORIA da coorte o
# volume segmentado fica abaixo do piso adulto. Por isso o aviso existe -- se
# fosse raro, bastaria a nota de rodapé.
#
# O limite inferior NÃO vira reprovação porque fígado pequeno existe de verdade:
# cirrose avançada, hepatectomia prévia, paciente pediátrico. Rejeitar seria
# trocar um erro silencioso por outro.
VOLUME_HEPATICO_TIPICO_ML = (900.0, 2400.0)


def _aviso_fragmentacao_figado(qualidade: dict | None) -> dict | None:
    """Avisa quando a segmentação saiu em pedaços e o modelo mostra só o maior.

    Sem isto o usuário vê um fígado limpo e não sabe que fragmentos foram
    retirados da cena. O gate anatômico já recusa o caso quando o componente
    principal fica abaixo de 90% do volume; entre 90% e 100% o exame passa, o
    visualizador isola o corpo principal (docs/188) e essa remoção precisa ser
    dita, não silenciada.
    """
    if not qualidade:
        return None
    componentes = qualidade.get("component_count")
    fracao = qualidade.get("largest_component_fraction")
    if not isinstance(componentes, int) or componentes <= 1:
        return None
    if not isinstance(fracao, (int, float)):
        return None
    descartado = max(0.0, (1.0 - float(fracao)) * 100.0)
    return {
        "nivel": "informacao" if descartado < 1.0 else "atencao",
        "componentes": int(componentes),
        "fracao_componente_principal": round(float(fracao), 4),
        "percentual_descartado": round(descartado, 2),
        "texto": (
            f"A segmentação saiu em {componentes} partes. O modelo 3D mostra o "
            f"corpo principal, que concentra {100 * float(fracao):.1f}% do volume; "
            f"os fragmentos restantes ({descartado:.1f}%) foram retirados da cena "
            "por serem quase sempre ruído de segmentação. Se o fígado deveria "
            "aparecer dividido neste exame, confira as imagens de referência."
        ),
    }


def _aviso_volume_figado(
    qualidade: dict | None, volume_uniao_ml: float | None = None
) -> dict | None:
    """Avisa quando o volume MOSTRADO NO MODELO 3D sai da faixa típica.

    Quando a máscara de união está disponível (docs/188 §9, docs/189), é ela
    que o modelo 3D de fato exibe -- então é o volume dela que precisa ser
    avaliado contra a faixa, não o da venosa isolada, que só alimentou a
    classificação. `volume_uniao_ml` é opcional e None em todo caller que não
    constrói união (por exemplo o benchmark em lote), preservando o
    comportamento anterior nesses casos.
    """
    if volume_uniao_ml is not None:
        volume = volume_uniao_ml
        origem = "a união das fases arterial, venosa e tardia"
    elif qualidade:
        candidato = qualidade.get("largest_component_volume_ml")
        volume = candidato if isinstance(candidato, (int, float)) else None
        origem = "a fase venosa"
    else:
        volume = None
        origem = "a fase venosa"
    if not isinstance(volume, (int, float)):
        return None
    baixo, alto = VOLUME_HEPATICO_TIPICO_ML
    if volume < baixo:
        return {
            "nivel": "atencao",
            "volume_ml": float(volume),
            "faixa_tipica_ml": [baixo, alto],
            "texto": (
                f"O fígado segmentado ({origem}) mede {volume:.0f} mL, abaixo da "
                f"faixa típica de um adulto ({baixo:.0f} a {alto:.0f} mL). A "
                "segmentação provavelmente perdeu parte do órgão, e o modelo 3D "
                "descreve só o que foi segmentado. Fígado pequeno também ocorre de "
                "verdade (cirrose avançada, hepatectomia prévia), então confira as "
                "imagens."
            ),
        }
    if volume > alto:
        return {
            "nivel": "atencao",
            "volume_ml": float(volume),
            "faixa_tipica_ml": [baixo, alto],
            "texto": (
                f"O fígado segmentado ({origem}) mede {volume:.0f} mL, acima da "
                f"faixa típica de um adulto ({baixo:.0f} a {alto:.0f} mL). Pode ser "
                "hepatomegalia real ou a máscara ter incorporado tecido vizinho."
            ),
        }
    return None


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
    input_assessment: dict[str, Any] | None = None,
    secondary_reader: dict[str, Any] | None = None,
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
        input_assessment=input_assessment,
        secondary_reader=secondary_reader,
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


def _viewer_assets(manifest: dict) -> dict[str, dict[str, str | None]]:
    """Lista fechada de artefatos que o manifesto autoriza o servidor a expor."""
    assets: dict[str, dict[str, str | None]] = {}
    for item in manifest.get("meshes", []):
        if not isinstance(item, dict):
            continue
        filename = item.get("stl")
        if not isinstance(filename, str) or Path(filename).name != filename:
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        assets[filename] = {
            "media_type": "model/stl",
            "sha256": metrics.get("mesh_sha256") if isinstance(metrics, dict) else None,
        }
        xr_asset = item.get("xr_asset")
        if isinstance(xr_asset, dict):
            xr_filename = xr_asset.get("stl")
            if (
                isinstance(xr_filename, str)
                and Path(xr_filename).name == xr_filename
                and xr_filename.lower().endswith(".stl")
            ):
                assets[xr_filename] = {
                    "media_type": "model/stl",
                    "sha256": xr_asset.get("sha256"),
                }
    views = (manifest.get("reference_images") or {}).get("views", {})
    if isinstance(views, dict):
        for view in views.values():
            if not isinstance(view, dict):
                continue
            for frame in view.get("frames", []):
                if not isinstance(frame, dict):
                    continue
                filename = frame.get("file")
                if (
                    isinstance(filename, str)
                    and Path(filename).name == filename
                    and filename.lower().endswith(".png")
                ):
                    assets[filename] = {
                        "media_type": "image/png",
                        "sha256": frame.get("sha256"),
                    }
    volumetry = manifest.get("volumetry")
    if isinstance(volumetry, dict):
        artifacts = volumetry.get("artifacts")
        if isinstance(artifacts, dict):
            json_name = artifacts.get("json")
            csv_name = artifacts.get("csv")
            if (
                isinstance(json_name, str)
                and Path(json_name).name == json_name
                and json_name.lower().endswith(".json")
            ):
                assets[json_name] = {
                    "media_type": "application/json",
                    "sha256": None,
                }
            if (
                isinstance(csv_name, str)
                and Path(csv_name).name == csv_name
                and csv_name.lower().endswith(".csv")
            ):
                assets[csv_name] = {
                    "media_type": "text/csv; charset=utf-8",
                    "sha256": artifacts.get("csv_sha256"),
                }
    return assets


def _model_done(case_dir: Path) -> bool:
    """Modelo publicável = manifesto válido, artefatos presentes e hashes íntegros."""
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        assets = _viewer_assets(manifest)
        mesh_names = {
            item.get("stl") for item in manifest.get("meshes", []) if isinstance(item, dict)
        }
        if not mesh_names or not mesh_names <= set(assets):
            return False
        volumetry = manifest.get("volumetry")
        if isinstance(volumetry, dict):
            artifacts = volumetry.get("artifacts") or {}
            json_name = artifacts.get("json")
            csv_name = artifacts.get("csv")
            if not all(
                isinstance(name, str) and Path(name).name == name
                for name in (json_name, csv_name)
            ):
                return False
            persisted_volumetry = json.loads(
                (manifest_path.parent / json_name).read_text(encoding="utf-8")
            )
            if persisted_volumetry != volumetry:
                return False
        for filename, spec in assets.items():
            path = manifest_path.parent / filename
            if not path.is_file():
                return False
            expected_hash = spec.get("sha256")
            if expected_hash and sha256_of(path) != expected_hash:
                return False
        return True
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


def _mesma_geometria_sitk(a: sitk.Image, b: sitk.Image) -> bool:
    return a.GetSize() == b.GetSize() and a.GetSpacing() == b.GetSpacing() and a.GetOrigin() == b.GetOrigin()


def _build_enhanced_visualization_shadow(
    case_dir: Path, phase_paths: dict[str, Path]
) -> dict[str, Any]:
    """Run the authorized visualization-only adapter; browser paths are never accepted."""

    from dtwin.segmentation_shadow import run_phase_aware_shadow

    return run_phase_aware_shadow(
        case_root=case_dir,
        phase_paths=phase_paths,
        reference_volume=case_dir / "volume.nii.gz",
        mrsegmentator_exe=MRSEGMENTATOR_EXE,
        timeout_seconds=ENHANCED_3D_TIMEOUT,
    )


def _build_union_liver_mask(case_dir: Path, phase_paths: dict[str, Path]) -> dict[str, Any]:
    """Segmenta arterial e tardia e funde com a venosa para o MODELO 3D.

    Roda só DEPOIS da decisão de triagem congelada: os painéis de classificação
    já foram construídos a partir de mask_organ.nii.gz (venosa) antes deste
    ponto, e permanecem exatamente como estavam -- esta função nunca escreve
    nele. O resultado vai para mask_organ_union.nii.gz, um arquivo NOVO que o
    estágio de malha (dtwin.stages._fonte_da_malha_do_orgao) prefere quando
    presente.

    Uma falha aqui NUNCA falha o exame: o pior caso é o modelo 3D continuar
    vindo só da venosa, como sempre foi. Cada fase extra tem seu próprio
    timeout e é simplesmente excluída da união se estourar, travar ou sair com
    geometria divergente.

    Por que isto é seguro fazer: validado contra referência humana (docs/189,
    CHAOS, n=20) que 82% dos voxels que a união ACRESCENTA sobre uma fase
    isolada são confirmados como fígado -- ela recupera órgão real, não invade
    tecido vizinho. E medido com as três fases de produção no LLD (n=19,
    experiments/three_phase_union_v1): recupera 23% de volume a mais que a
    venosa sozinha, na mediana.
    """
    from dtwin.benchmark.lld_mmri_v23_preparation import isolated_total_mr_liver_segmenter
    from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED

    venous_mask_path = case_dir / "mask_organ.nii.gz"
    if not venous_mask_path.is_file():
        return {"status": "venous_mask_missing", "phases_included": [], "phase_failures": {}}
    venous_image = sitk.ReadImage(str(venous_mask_path))
    venous = sitk.GetArrayFromImage(venous_image) > 0

    uniao = venous.copy()
    fases_incluidas = ["venous"]
    fases_falhas: dict[str, str] = {}
    # phase_paths vem de multiphase.phase_paths, cujas chaves são as constantes
    # de dtwin.learning.multiphase_ingest ("t1_arterial"/"t1_delayed"), não os
    # nomes curtos que este módulo usa para relatar fases -- importar em vez de
    # supor a string evita a mesma divergência silenciosa se o nome mudar lá.
    for fase, chave_real in (("arterial", ARTERIAL), ("delayed", DELAYED)):
        fonte = phase_paths.get(chave_real)
        if fonte is None or not Path(fonte).is_file():
            fases_falhas[fase] = "fase_ausente"
            continue
        destino = case_dir / f"mask_organ_{fase}.nii.gz"
        try:
            isolated_total_mr_liver_segmenter(
                Path(fonte), destino, device="gpu", fast=False,
                timeout_seconds=UNION_PHASE_TIMEOUT, python_executable=PY,
            )
        except Exception as exc:  # noqa: BLE001
            fases_falhas[fase] = type(exc).__name__
            continue
        try:
            imagem_fase = sitk.ReadImage(str(destino))
        except Exception:  # noqa: BLE001
            fases_falhas[fase] = "leitura_falhou"
            continue
        if not _mesma_geometria_sitk(imagem_fase, venous_image):
            fases_falhas[fase] = "geometria_divergente"
            continue
        uniao = uniao | (sitk.GetArrayFromImage(imagem_fase) > 0)
        fases_incluidas.append(fase)

    if len(fases_incluidas) == 1:
        # Nenhuma fase extra contribuiu -- não escreve um arquivo idêntico ao
        # venoso. dtwin.stages já cai para mask_organ.nii.gz sozinho.
        return {
            "status": "union_unavailable_venous_only",
            "phases_included": fases_incluidas,
            "phase_failures": fases_falhas,
        }

    saida = sitk.GetImageFromArray(uniao.astype(np.uint8))
    saida.CopyInformation(venous_image)
    destino_uniao = case_dir / "mask_organ_union.nii.gz"
    # O nome precisa terminar em ".nii.gz": o SimpleITK escolhe o formato de
    # escrita pela extensão, e ".tmp" sozinho não é reconhecido.
    temporario = case_dir / f".{destino_uniao.stem.removesuffix('.nii')}.partial.nii.gz"
    sitk.WriteImage(saida, str(temporario))
    temporario.replace(destino_uniao)

    espacamento = venous_image.GetSpacing()
    volume_venosa_ml = float(int(venous.sum()) * float(np.prod(espacamento)) / 1000.0)
    volume_uniao_ml = float(int(uniao.sum()) * float(np.prod(espacamento)) / 1000.0)
    return {
        "status": "union_built",
        "phases_included": fases_incluidas,
        "phase_failures": fases_falhas,
        "venous_volume_ml": round(volume_venosa_ml, 1),
        "union_volume_ml": round(volume_uniao_ml, 1),
        "classification_region_fraction_of_union": (
            round(volume_venosa_ml / volume_uniao_ml, 4) if volume_uniao_ml > 0 else None
        ),
    }


def _localize_candidate(case_dir: Path, decision: dict[str, Any]) -> dict[str, Any]:
    """Run the viewer-only localizer after the screening decision is frozen.

    A localization failure never changes the already computed prediction and
    never prevents publication of the liver model. It is reported explicitly.
    """
    subtype = decision.get("subtype") if isinstance(decision.get("subtype"), dict) else {}
    requested = decision.get("prediction") == "POSITIVE" or bool(subtype.get("determined"))
    if not requested:
        for name in (
            "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
            "mesh_candidate.vtp", "candidate_region.json", "candidate_request.json",
        ):
            (case_dir / name).unlink(missing_ok=True)
        return {
            "status": "not_requested_no_focal_finding",
            "candidate_present": False,
            "used_by_screening_inference": False,
            "requires_human_review": False,
        }
    request = {
        "schema": "argos-candidate-request-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "screening_decision_frozen": True,
        "prediction": str(decision.get("prediction")),
        "visual_score": float(decision.get("score", 0.0)),
        "visual_threshold": float(decision.get("threshold", 0.0)),
        "subtype_determined": bool(subtype.get("determined")),
        "subtype": str(subtype.get("subtype")) if subtype.get("determined") else None,
        "subtype_label": (
            SUBTYPE_LABELS_PT.get(str(subtype.get("subtype")), str(subtype.get("subtype")))
            if subtype.get("determined") else None
        ),
        "used_by_screening_inference": False,
        "ground_truth_included": False,
        "research_only": True,
    }
    request_path = case_dir / "candidate_request.json"
    temp = request_path.with_name(".candidate_request.json.tmp")
    temp.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(request_path)
    process = run_candidate_subprocess(
        case_dir=case_dir,
        request_path=request_path,
        device="gpu",
        timeout_seconds=CANDIDATE_TIMEOUT,
        python_executable=PY,
    )
    manifest_path = case_dir / "candidate_region.json"
    if process.returncode == 0 and manifest_path.is_file():
        try:
            result = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Manifesto do candidato automático inválido.") from exc
        if result.get("schema") != "argos-candidate-region-v1":
            raise PipelineError("Schema do candidato automático inválido.")
        return result
    # Remove any incomplete/stale candidate so finalize cannot publish it.
    for name in (
        "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
        "mesh_candidate.vtp", "candidate_region.json",
    ):
        (case_dir / name).unlink(missing_ok=True)
    return {
        "status": "localization_unavailable",
        "candidate_present": False,
        "used_by_screening_inference": False,
        "requires_human_review": True,
        "reason": candidate_error(process),
    }


def process_monophase_medsiglip_job(
    job_id: str,
    raw_dir: Path,
    *,
    input_assessment: dict[str, Any],
) -> None:
    """Classify an explicitly identified delayed single phase with MedSigLIP.

    The LLD nested-OOF gate applies only to the delayed representation.  A
    generic/arterial/venous series must never enter this worker.
    """
    from dtwin.learning.exam_to_panels import build_monophase_exam_panels
    from dtwin.learning.monophase_visual_inference import infer_monophase_case_from_panels
    from dtwin.learning.visual_inference import in_sample_status, load_production_bundle

    case_dir = (WORKSPACE / job_id / "case").resolve()
    started = time.monotonic()
    durations: dict[str, float] = {}
    try:
        _set(job_id, state="processing", step="ingestao_monofasica", progress=18)
        selection_started = time.monotonic()
        best_files, frames, selection = select_best_mr_series(raw_dir, min_slices=MIN_SLICES)
        selected = (selection or {}).get("selected") or {}
        sequence_contract = resolve_monophase_sequence_contract(selected)
        if not best_files or frames < MIN_SLICES:
            raise PipelineError("Nenhuma série DICOM de RM válida foi encontrada.")
        if selected.get("sequence_class") != "T1_DELAYED":
            raise PipelineError("O bundle MedSigLIP monofásico exige uma fase tardia identificada.")
        series_dir = WORKSPACE / job_id / "_series"
        series_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(best_files):
            shutil.copyfile(source, series_dir / f"{index:05d}_{Path(source).name}")
        durations["series_selection_and_copy"] = round(time.monotonic() - selection_started, 4)

        _set(job_id, step="segmentacao", progress=45)
        segment_started = time.monotonic()
        mask_quality = _segmentar_figado_com_gate(
            series_dir, case_dir, f"Job MedSigLIP monofásico {job_id}"
        )
        durations["preparation_and_segmentation"] = round(
            time.monotonic() - segment_started, 4
        )
        _persist_series_selection(case_dir, best_files)

        _set(job_id, step="paineis", progress=65)
        panel_started = time.monotonic()
        panels = build_monophase_exam_panels(
            case_id=job_id,
            volume_path=case_dir / "volume.nii.gz",
            coarse_liver_mask_path=case_dir / "mask_organ.nii.gz",
            output_dir=case_dir / "monophase_medsiglip_panels",
            panel_config_path=REPO / "configs/medsiglip_monophase_liver_enriched_v1.yaml",
        )
        durations["panels"] = round(time.monotonic() - panel_started, 4)

        _set(job_id, step="classificacao", progress=82)
        inference_started = time.monotonic()
        bundle_root = (REPO / MONOPHASE_DELAYED_VISUAL_BUNDLE).resolve()
        decision = infer_monophase_case_from_panels(
            bundle_root=bundle_root,
            panel_manifest_path=panels.manifest_path,
            panel_paths=panels.panel_paths,
            source_phase_key="t1_delayed",
            embedding_config_path=REPO / VISUAL_EMBEDDING_CONFIG,
        )
        durations["classification"] = round(time.monotonic() - inference_started, 4)

        _set(job_id, step="localizacao_candidata", progress=88)
        localization_started = time.monotonic()
        try:
            candidate_localization = _localize_candidate(case_dir, decision)
        except Exception as exc:  # localization never changes the frozen decision
            candidate_localization = {
                "status": "localization_unavailable",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
                "reason": type(exc).__name__,
            }
        durations["candidate_localization_after_inference"] = round(
            time.monotonic() - localization_started, 4
        )

        _set(job_id, step="modelo_3d", progress=94)
        model_started = time.monotonic()
        try:
            viewer_ready, viewer_error = _build_model(case_dir)
        except Exception as exc:  # noqa: BLE001
            viewer_ready, viewer_error = False, type(exc).__name__
        durations["model_3d"] = round(time.monotonic() - model_started, 4)
        durations["total"] = round(time.monotonic() - started, 4)

        bundle = load_production_bundle(bundle_root)
        status = in_sample_status(bundle, case_id=job_id)
        positive = decision["prediction"] == "POSITIVE"
        result = {
            "status": "concluido",
            "analysis_scenario": "monophase_medsiglip_delayed",
            "prediction": "POSITIVA" if positive else "NEGATIVA",
            "visual_score": decision["score"],
            "visual_threshold": decision["threshold"],
            "panel_count": decision["panel_count"],
            "panel_manifest_sha256": decision["panel_manifest_sha256"],
            "class_probabilities": decision["class_probabilities"],
            "source_phase_key": "t1_delayed",
            "selected_sequence_class": "T1_DELAYED",
            "monophase_sequence_contract": sequence_contract,
            "dynamic_enhancement_information_present": False,
            "validated_triphase_metrics_applicable": False,
            "monophase_reference_metrics": {
                "cohort": "LLD-MMRI nested patient-grouped OOF",
                "sensitivity": 0.7770700636942676,
                "specificity": 0.7584269662921348,
                "technical_failures_count_as_errors": True,
                "external_validation": False,
            },
            "input_assessment": input_assessment,
            "in_sample": status["in_sample"],
            "in_sample_verdict": status["verdict"],
            "durations_seconds": durations,
            "liver_mask_quality": mask_quality,
            "liver_volume_warning": _aviso_volume_figado(mask_quality),
            "liver_fragmentation_warning": _aviso_fragmentacao_figado(mask_quality),
            "candidate_localization": candidate_localization,
            "viewer_ready": bool(viewer_ready),
            "viewer_url": (
                f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
                if viewer_ready else None
            ),
            "viewer_error": viewer_error or None,
            "approval": {"status": "pending"} if viewer_ready else None,
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "disclaimer": DISCLAIMER,
        }
        result["hierarchical_assessment"] = build_hierarchical_screening_result(
            prediction=decision["prediction"],
            subtype=decision.get("subtype"),
            sequence_contract=sequence_contract,
        )
        result.update(_subtype_fields(decision["subtype"], positive))
        _set(job_id, state="done", step="concluido", progress=100, result=result)
    except subprocess.TimeoutExpired:
        _set(job_id, state="done", step="concluido", progress=100, result=_graceful(
            "O processamento excedeu o tempo limite.", "timeout"))
    except PipelineError as exc:
        _set(job_id, state="done", step="concluido", progress=100, result=_graceful(str(exc)))
    except Exception as exc:  # noqa: BLE001
        log.exception("Job MedSigLIP monofásico %s: falha inesperada", job_id)
        _set(job_id, state="done", step="concluido", progress=100, result=_graceful(
            "Não foi possível concluir a análise monofásica.", type(exc).__name__))


def process_visual_job(job_id: str, raw_dir: Path) -> None:
    """Exame individual pelo classificador visual da Etapa C.

    É o mesmo caminho do benchmark visual, caso a caso: fases em subpastas ->
    harmonização na grade venosa + segmentação hepática -> painéis
    liver-enriched -> embeddings MedSigLIP -> bundle congelado. Qualquer falha
    vira "não concluído"; nunca uma decisão fabricada.

    Exige as três fases dinâmicas em subpastas nomeadas, porque identificar a
    fase a partir de DICOM bruto é problema não resolvido (docs/123). Adivinhar
    aqui produziria um recorte na fase errada e uma resposta sem valor.
    """
    from dtwin.learning.exam_to_panels import build_exam_panels
    from dtwin.learning.multiphase_ingest import build_multiphase_case
    from dtwin.learning.raw_dicom_phase_resolver import RawPhaseResolutionError
    from dtwin.learning.visual_inference import (
        classify_embeddings,
        embed_panels,
        in_sample_status,
        load_production_bundle,
    )

    case_dir = (WORKSPACE / job_id / "case").resolve()
    with _lock:
        enhanced_3d_requested = bool((_jobs.get(job_id) or {}).get("enhanced_3d"))
    started = time.monotonic()
    duracoes: dict[str, float] = {}
    qualidade_mascara: dict | None = None
    try:
        _set(job_id, state="processing", step="ingestao_multifasica", progress=15)
        def segment_venous(venous_dir: Path, _work_dir: Path) -> Path:
            # Segmenta no PRÓPRIO diretório do job, e não numa subpasta: é de lá
            # que a rota /api/jobs/{id}/model serve a malha, então isso preserva o
            # modelo 3D de revisão que o fluxo anterior gerava.
            nonlocal qualidade_mascara
            qualidade_mascara = _segmentar_figado_com_gate(
                venous_dir, case_dir, f"Job visual {job_id}"
            )
            return case_dir

        t0 = time.monotonic()
        try:
            multiphase = build_multiphase_case(
                case_id=job_id,
                case_upload_dir=Path(raw_dir),
                output_dir=case_dir / "multiphase",
                segment_venous=segment_venous,
            )
        except RawPhaseResolutionError as exc:
            if exc.code != "insufficient_dynamic_phases":
                raise
            # Never make fake RGB phases. Use the best real series through a
            # dedicated single-phase reader and carry its limitations forward.
            _files, _frames, selection = select_best_mr_series(
                Path(raw_dir), min_slices=MIN_SLICES
            )
            _evidence_paths, evidence_selection = select_monophase_evidence_series(
                Path(raw_dir), min_slices=MIN_SLICES
            )
            selected_sequence_class = str(
                ((selection or {}).get("selected") or {}).get("sequence_class") or "UNKNOWN"
            )
            sequence_contract = resolve_monophase_sequence_contract(
                ((selection or {}).get("selected") or {})
            )
            delayed_medsiglip = (
                MONOPHASE_DELAYED_VISUAL_AUTO_PROMOTED
                and
                selected_sequence_class == "T1_DELAYED"
                and (REPO / MONOPHASE_DELAYED_VISUAL_BUNDLE / "bundle_manifest.json").is_file()
            )
            scenario = (
                "monophase_medsiglip_delayed" if delayed_medsiglip else "monophase_rag"
            )
            assessment = {
                "schema": "oren-input-assessment-v1",
                "mode": "single_phase",
                "dynamic_enhancement_information_present": False,
                "synthetic_phases_created": False,
                "validated_triphase_metrics_applicable": False,
                "fallback_reason_code": exc.code,
                "selected_sequence_class": selected_sequence_class,
                "monophase_sequence_contract": sequence_contract,
                "available_real_sequence_classes": (
                    list(evidence_selection.get("selected_sequence_classes") or [])
                    if evidence_selection else [selected_sequence_class]
                ),
                "complementary_real_sequence_classes": (
                    list(evidence_selection.get("complementary_sequence_classes") or [])
                    if evidence_selection else []
                ),
                "complementary_sequences_used_by_current_reader": False,
                "single_phase_reader": (
                    "MedSigLIP delayed frozen classifier"
                    if delayed_medsiglip
                    else (
                        "MedGemma 4B + RAG (primário) + MedSigLIP tardio (segundo leitor)"
                        if selected_sequence_class == "T1_DELAYED"
                        and MONOPHASE_DELAYED_ADVISORY_ENABLED
                        else "MedGemma 4B + RAG"
                    )
                ),
                "limitations": [
                    "Apenas uma série de RM foi usada.",
                    "O painel contém nove cortes sistematicamente amostrados e não representa cobertura axial integral.",
                    "Não é possível avaliar realce arterial, washout ou persistência entre fases.",
                    "Este resultado não deve ser comparado diretamente às métricas do protocolo trifásico.",
                ],
            }
            _set(
                job_id,
                analysis_scenario=scenario,
                input_assessment=assessment,
                step="ingestao_monofasica",
                progress=18,
            )
            if delayed_medsiglip:
                process_monophase_medsiglip_job(
                    job_id,
                    raw_dir,
                    input_assessment=assessment,
                )
                return
            with _lock:
                escolhido = (_jobs.get(job_id) or {}).get("monophase_medgemma_config")
            process_job(
                job_id,
                raw_dir,
                medgemma_config=escolhido or MONOPHASE_MEDGEMMA_CONFIG,
                analysis_scenario=scenario,
                input_assessment=assessment,
            )
            return
        duracoes["ingestao_e_segmentacao"] = round(time.monotonic() - t0, 4)

        # A single-phase fallback must not depend on the visual bundle.
        bundle = load_production_bundle(_visual_bundle_root("hybrid_supervised"))

        _set(job_id, state="processing", step="paineis", progress=55)
        t0 = time.monotonic()
        panels = build_exam_panels(
            case_id=job_id,
            phase_paths=multiphase.phase_paths,
            coarse_liver_mask_path=multiphase.coarse_liver_mask_path,
            output_dir=case_dir / "panels",
            panel_config_path=REPO / VISUAL_PANEL_CONFIG,
        )
        duracoes["paineis"] = round(time.monotonic() - t0, 4)

        _set(job_id, state="processing", step="classificacao", progress=80)
        t0 = time.monotonic()
        embeddings = embed_panels(REPO / VISUAL_EMBEDDING_CONFIG, panels.panel_paths)
        decision = classify_embeddings(bundle, embeddings)
        duracoes["classificacao"] = round(time.monotonic() - t0, 4)

        # A decisão já está congelada. Só agora a região candidata pode ser
        # localizada para o visualizador; ela jamais retorna ao classificador.
        _set(job_id, state="processing", step="localizacao_candidata", progress=88)
        t0 = time.monotonic()
        try:
            candidate_localization = _localize_candidate(case_dir, decision)
        except subprocess.TimeoutExpired:
            for name in (
                "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
                "mesh_candidate.vtp", "candidate_region.json",
            ):
                (case_dir / name).unlink(missing_ok=True)
            candidate_localization = {
                "status": "localization_timeout",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
            }
        except Exception as exc:  # noqa: BLE001
            candidate_localization = {
                "status": "localization_unavailable",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
                "reason": type(exc).__name__,
            }
        duracoes["localizacao_candidata_pos_inferencia"] = round(
            time.monotonic() - t0, 4
        )

        # Máscara de visualização pela união das três fases (docs/188 §9,
        # docs/189). A decisão já está congelada e os painéis já vieram só da
        # venosa -- isto só melhora o que o modelo 3D mostra, nunca o que foi
        # classificado. Roda antes de _build_model para que o estágio de malha
        # já encontre mask_organ_union.nii.gz, se ela existir.
        # A decisão e os painéis já estão congelados. Esta etapa escreve somente
        # os artefatos v2 de visualização e jamais altera mask_organ.nii.gz.
        visualizacao_shadow: dict[str, Any] = {"status": "not_requested"}
        if enhanced_3d_requested:
            _set(job_id, state="processing", step="segmentacao_3d_aprimorada", progress=91)
            t0 = time.monotonic()
            try:
                visualizacao_shadow = _build_enhanced_visualization_shadow(
                    case_dir, multiphase.phase_paths
                )
            except Exception as exc:  # noqa: BLE001
                visualizacao_shadow = {
                    "status": "failed",
                    "reason": type(exc).__name__,
                    "fallback": "existing_union_or_venous",
                    "production_files_written": False,
                }
                log.warning("Job visual %s: 3-D aprimorado indisponível (%s)", job_id, exc)
            duracoes["segmentacao_3d_aprimorada"] = round(time.monotonic() - t0, 4)

        shadow_approved = visualizacao_shadow.get("status") in {
            "APPROVED", "APPROVED_WITH_WARNING"
        }
        uniao_mascara: dict[str, Any] = {
            "status": "replaced_by_phase_aware_shadow" if shadow_approved else "union_disabled"
        }
        if UNION_MASK_ENABLED and not shadow_approved:
            _set(job_id, state="processing", step="mascara_uniao", progress=91)
            t0 = time.monotonic()
            try:
                uniao_mascara = _build_union_liver_mask(case_dir, multiphase.phase_paths)
            except Exception as exc:  # noqa: BLE001
                uniao_mascara = {
                    "status": "union_failed", "reason": type(exc).__name__,
                    "phases_included": ["venous"], "phase_failures": {},
                }
                log.warning("Job visual %s: união de fases falhou (%s)", job_id, exc)
            duracoes["mascara_uniao"] = round(time.monotonic() - t0, 4)

        # Modelo 3D do fígado para revisão. É acessório à decisão: se falhar, o
        # resultado sai do mesmo jeito, apenas sem o visualizador.
        _set(job_id, state="processing", step="modelo_3d", progress=94)
        t0 = time.monotonic()
        try:
            viewer_ready, motivo_modelo = _build_model(case_dir)
        except Exception as exc:  # noqa: BLE001
            viewer_ready, motivo_modelo = False, f"{type(exc).__name__}"
        duracoes["modelo_3d"] = round(time.monotonic() - t0, 4)
        if not viewer_ready:
            log.warning("Job visual %s: modelo 3D indisponível (%s)", job_id, motivo_modelo)

        positiva = decision["prediction"] == "POSITIVE"
        status = in_sample_status(bundle, case_id=job_id)
        resultado = {
            "status": "concluido",
            "analysis_scenario": "hybrid_supervised",
            "prediction": "POSITIVA" if positiva else "NEGATIVA",
            "visual_score": decision["score"],
            "visual_threshold": decision["threshold"],
            "panel_count": decision["panel_count"],
            "class_probabilities": decision["class_probabilities"],
            "phase_coverage": multiphase.coverage,
            "phase_resolution": multiphase.phase_resolution,
            "in_sample": status["in_sample"],
            "in_sample_verdict": status["verdict"],
            "durations_seconds": duracoes,
            "liver_mask_quality": qualidade_mascara,
            "liver_mask_union": uniao_mascara,
            "liver_visualization_shadow": visualizacao_shadow,
            "liver_volume_warning": _aviso_volume_figado(
                qualidade_mascara,
                (
                    ((visualizacao_shadow.get("mask") or {}).get("volume_ml"))
                    if shadow_approved
                    else (
                        uniao_mascara.get("union_volume_ml")
                        if uniao_mascara.get("status") == "union_built" else None
                    )
                ),
            ),
            "liver_fragmentation_warning": _aviso_fragmentacao_figado(qualidade_mascara),
            "candidate_localization": candidate_localization,
            "viewer_ready": bool(viewer_ready),
            "viewer_url": (
                f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
                if viewer_ready
                else None
            ),
            "approval": {"status": "pending"} if viewer_ready else None,
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "disclaimer": DISCLAIMER,
        }
        resultado.update(_subtype_fields(decision["subtype"], positiva))
        resultado["durations_seconds"]["total"] = round(time.monotonic() - started, 4)
        _set(job_id, state="done", step="concluido", progress=100, result=resultado)
    except subprocess.TimeoutExpired:
        _set(job_id, state="done", step="concluido", progress=100, result=_graceful(
            "O processamento excedeu o tempo limite.",
            "Exames muito grandes podem não caber no orçamento de tempo."))
    except PipelineError as exc:
        _set(job_id, state="done", step="concluido", progress=100,
             result=_graceful(str(exc)))
    except Exception as exc:  # noqa: BLE001
        log.exception("Job visual %s: falha inesperada", job_id)
        _set(job_id, state="done", step="concluido", progress=100, result=_graceful(
            "Não foi possível concluir a análise deste exame.",
            f"Falha inesperada: {type(exc).__name__}"))


def _case_dir_for_job(job_id: str) -> Path:
    if not job_id or any(ch not in "0123456789abcdef" for ch in job_id.lower()):
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    return (WORKSPACE / job_id / "case").resolve()


def _completed_job_state_path(job_id: str) -> Path:
    return _case_dir_for_job(job_id) / "outputs" / "webapp_job_state.json"


def _persist_completed_job_state(job_id: str, job: dict[str, Any]) -> Path:
    """Persist a completed webapp state atomically beside its artifacts."""
    if job.get("state") != "done":
        raise ValueError("only completed jobs may be persisted")
    allowed = {
        "state", "step", "progress", "analysis_scenario", "enhanced_3d",
        "result", "approval", "operational_timing", "operational_timing_artifact",
        "viewer_error",
    }
    payload = {key: job.get(key) for key in allowed if key in job}
    payload.update(
        schema="oren-webapp-completed-job-v1",
        job_id=job_id,
        persisted_at=datetime.now(timezone.utc).isoformat(),
    )
    path = _completed_job_state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _legacy_completed_job_from_artifacts(job_id: str) -> dict[str, Any] | None:
    """Migrate a pre-persistence completed job without fabricating analysis data."""
    case_dir = _case_dir_for_job(job_id)
    if not _model_done(case_dir):
        return None
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidate = manifest.get("candidate_region") or {}
    request = candidate.get("request") or {}
    raw_prediction = str(request.get("prediction") or "INCONCLUSIVE").upper()
    prediction = {
        "POSITIVE": "POSITIVA",
        "NEGATIVE": "NEGATIVA",
        "INCONCLUSIVE": "INCONCLUSIVA",
    }.get(raw_prediction, raw_prediction)
    approval_path = case_dir / "outputs" / "approval.json"
    approval: dict[str, Any] = {"status": "pending"}
    if approval_path.is_file():
        try:
            loaded = json.loads(approval_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                approval = loaded
        except (OSError, json.JSONDecodeError):
            pass
    result = {
        "status": "concluido",
        "analysis_scenario": "recovered_legacy_completed_job",
        "prediction": prediction,
        "visual_score": request.get("visual_score"),
        "visual_threshold": request.get("visual_threshold"),
        "panel_count": len(_rgb_panel_files(job_id)),
        "candidate_localization": candidate or None,
        "viewer_ready": True,
        "viewer_url": f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}",
        "approval": approval,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "disclaimer": DISCLAIMER,
        "restored_from_artifacts": True,
    }
    return {
        "state": "done",
        "step": "concluido",
        "progress": 100,
        "analysis_scenario": result["analysis_scenario"],
        "enhanced_3d": False,
        "result": result,
        "approval": approval,
    }


def _restore_completed_job(job_id: str) -> dict[str, Any] | None:
    path = _completed_job_state_path(job_id)
    restored: dict[str, Any] | None = None
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("schema") == "oren-webapp-completed-job-v1"
                and payload.get("job_id") == job_id
                and payload.get("state") == "done"
                and isinstance(payload.get("result"), dict)
            ):
                result = payload["result"]
                if not result.get("viewer_ready") or _model_done(_case_dir_for_job(job_id)):
                    restored = payload
        except (OSError, json.JSONDecodeError):
            restored = None
    if restored is None:
        restored = _legacy_completed_job_from_artifacts(job_id)
        if restored is not None:
            _persist_completed_job_state(job_id, restored)
    if restored is None:
        return None
    with _lock:
        existing = _jobs.get(job_id)
        if existing is None:
            _jobs[job_id] = restored
            existing = _jobs[job_id]
    return existing


def _xr_session_path(case_dir: Path, token: str) -> Path:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return case_dir / "outputs" / "xr_sessions" / f"{digest}.json"


def _read_xr_session(job_id: str, token: str) -> dict[str, Any]:
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Sessao XR invalida.")
    case_dir = _case_dir_for_job(job_id)
    path = _xr_session_path(case_dir, token)
    try:
        session = json.loads(path.read_text("utf-8"))
        expires_at = datetime.fromisoformat(str(session["expires_at"]))
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Sessao XR invalida.") from exc
    if session.get("job_id") != job_id or expires_at <= datetime.now(timezone.utc):
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=401, detail="Sessao XR expirada.")
    return session


def _quest_base_url(request: Request) -> str:
    configured = os.environ.get("OREN_QUEST_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    hostname = request.url.hostname or "127.0.0.1"
    request_port = request.url.port
    # Quando a sessão nasce no próprio atalho aberto pelo Quest, preservar a
    # origem que já provou estar acessível. Forçar HTTPS:8443 aqui fazia o
    # navegador abandonar o servidor HTTP:8082 funcional após a tela de loading.
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        default_port = 443 if request.url.scheme == "https" else 80
        port_suffix = f":{request_port}" if request_port and request_port != default_port else ""
        return f"{request.url.scheme}://{hostname}{port_suffix}"
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            hostname = str(probe.getsockname()[0])
        except OSError:
            hostname = "127.0.0.1"
        finally:
            probe.close()
    return f"https://{hostname}:{int(os.environ.get('OREN_QUEST_PORT', '8443'))}"


class ReviewChecklistPayload(BaseModel):
    inspected_3d_contour: bool = False
    compared_2d_reference: bool = False
    reviewed_candidate_against_mr: bool = False
    acknowledged_research_only: bool = False


class ClippingStatePayload(BaseModel):
    enabled: bool = False
    axis: Literal["x", "y", "z"] = "z"
    position_percent: float = 50.0
    inverted: bool = False


class ViewerSavedViewPayload(BaseModel):
    bookmark_id: str = Field(max_length=24, pattern=r"^view-[0-9]{3}$")
    label: str = Field(min_length=1, max_length=96)
    active_view: Literal[
        "padrao", "anterior", "superior", "direita", "focus", "anatomical", "saved"
    ] = "saved"
    active_preset: Literal[
        "custom", "default", "surface", "realistic", "anatomy", "triage", "segments"
    ] = "custom"
    active_anatomical_view: Literal[
        "none", "liver", "segments", "vascular", "candidate"
    ] = "none"
    material_profile: Literal["default", "anatomy", "triage", "segments"] = "default"
    selected_role: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")
    selection_isolated: bool = False
    camera_position_mm: list[float] = Field(min_length=3, max_length=3)
    camera_target_mm: list[float] = Field(min_length=3, max_length=3)
    reference_sync_enabled: bool = True
    reference_view: Literal["axial", "coronal", "sagittal"] = "axial"
    reference_frame_index: int = Field(default=0, ge=0)
    clipping: ClippingStatePayload = Field(default_factory=ClippingStatePayload)
    visible_roles: list[str] = Field(default_factory=list, max_length=64)
    opacity_by_role: dict[str, float] = Field(default_factory=dict)


class StructureDimensions3DPayload(BaseModel):
    role: str = Field(max_length=64, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=96)
    left_right_mm: float = Field(gt=0, le=5000)
    anterior_posterior_mm: float = Field(gt=0, le=5000)
    superior_inferior_mm: float = Field(gt=0, le=5000)
    method: Literal["axis_aligned_lps_bounding_box"] = "axis_aligned_lps_bounding_box"
    coordinate_system: Literal["LPS"] = "LPS"
    source: Literal["selected_segmentation_mesh"] = "selected_segmentation_mesh"
    approximate: Literal[True] = True


class ViewerStatePayload(BaseModel):
    active_view: Literal[
        "padrao", "anterior", "superior", "direita", "focus", "anatomical", "saved"
    ] = "padrao"
    active_preset: Literal[
        "custom", "default", "surface", "realistic", "anatomy", "triage", "segments"
    ] = "custom"
    active_anatomical_view: Literal[
        "none", "liver", "segments", "vascular", "candidate"
    ] = "none"
    wireframe_enabled: bool = False
    reference_sync_enabled: bool = True
    reference_view: Literal["axial", "coronal", "sagittal"] = "axial"
    reference_frame_index: int = Field(default=0, ge=0)
    selected_role: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")
    selection_isolated: bool = False
    saved_views: list[ViewerSavedViewPayload] = Field(default_factory=list, max_length=8)
    compared_saved_view_ids: list[str] = Field(default_factory=list, max_length=2)
    clipping: ClippingStatePayload | None = None
    measurements_mm: list[float] = Field(default_factory=list)
    structure_dimensions_3d: list[StructureDimensions3DPayload] = Field(
        default_factory=list, max_length=16
    )
    visible_roles: list[str] = Field(default_factory=list)


class ApprovalPayload(BaseModel):
    status: Literal["approved", "revision_requested"]
    checklist: ReviewChecklistPayload | None = None
    viewer_state: ViewerStatePayload | None = None
    candidate_review_decision: Literal[
        "accepted_as_region_of_interest", "rejected", "needs_correction"
    ] | None = None


class XRSessionRequest(BaseModel):
    role: Literal["patient", "clinician"] = "clinician"
    ttl_minutes: int = Field(default=30, ge=5, le=120)


class XRClientEventPayload(BaseModel):
    event: Literal[
        "viewer_ready", "entry_click", "session_requested", "session_started", "session_failed"
    ]
    mode: Literal["immersive-ar", "immersive-vr", "unknown"] = "unknown"
    error_name: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=300)


def _run_delayed_medsiglip_advisory(
    *,
    case_dir: Path,
    case_id: str,
    input_assessment: dict[str, Any],
    primary_prediction: str,
) -> dict[str, Any]:
    """Run the delayed MedSigLIP head strictly as a non-decisional reader.

    The head passed its internal LLD gate but did not generalize to OpenSwissHCC.
    Consequently this function deliberately has no way to change the primary
    MedGemma prediction.  Its signed, auditable output is useful to the human
    reviewer and to future paired validation, while remaining honest for an
    arbitrary DICOM upload whose source domain is unknown.
    """
    from dtwin.learning.exam_to_panels import build_monophase_exam_panels
    from dtwin.learning.monophase_visual_inference import infer_monophase_case_from_panels
    from dtwin.medgemma_screening import _write_json_atomic

    started = time.monotonic()
    contract = dict(input_assessment.get("monophase_sequence_contract") or {})
    output_path = case_dir / "outputs" / "second_reader" / "medsiglip_advisory.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base: dict[str, Any] = {
        "schema": "oren-monophase-second-reader-v1",
        "role": "advisory_second_reader",
        "affects_primary_decision": False,
        "primary_reader": "MedGemma 4B + RAG",
        "primary_prediction": str(primary_prediction).upper(),
        "source_phase_key": contract.get("source_phase_key"),
        "external_gate_passed": False,
        "auto_promotion_allowed": False,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    if not MONOPHASE_DELAYED_ADVISORY_ENABLED:
        result = {**base, "status": "disabled", "reason": "advisory_disabled_by_configuration"}
        _write_json_atomic(output_path, result)
        return result
    if (
        contract.get("source_phase_key") != "t1_delayed"
        or contract.get("sequence_specific_medsiglip_bundle_allowed") is not True
    ):
        result = {
            **base,
            "status": "not_eligible",
            "reason": "validated_head_requires_explicit_t1_delayed_series",
        }
        _write_json_atomic(output_path, result)
        return result

    bundle_root = (REPO / MONOPHASE_DELAYED_VISUAL_BUNDLE).resolve()
    if not (bundle_root / "bundle_manifest.json").is_file():
        result = {**base, "status": "unavailable", "reason": "signed_bundle_not_found"}
        _write_json_atomic(output_path, result)
        return result

    panels = build_monophase_exam_panels(
        case_id=case_id,
        volume_path=case_dir / "volume.nii.gz",
        coarse_liver_mask_path=case_dir / "mask_organ.nii.gz",
        output_dir=case_dir / "monophase_medsiglip_advisory_panels",
        panel_config_path=REPO / "configs/medsiglip_monophase_liver_enriched_v1.yaml",
    )
    decision = infer_monophase_case_from_panels(
        bundle_root=bundle_root,
        panel_manifest_path=panels.manifest_path,
        panel_paths=panels.panel_paths,
        source_phase_key="t1_delayed",
        embedding_config_path=REPO / VISUAL_EMBEDDING_CONFIG,
    )
    advisory_prediction = "POSITIVA" if decision["prediction"] == "POSITIVE" else "NEGATIVA"
    primary = str(primary_prediction).upper()
    comparable = primary in {"POSITIVA", "NEGATIVA"}
    result = {
        **base,
        "status": "completed",
        "prediction": advisory_prediction,
        "score": decision["score"],
        "threshold": decision["threshold"],
        "panel_count": decision["panel_count"],
        "panel_manifest_sha256": decision["panel_manifest_sha256"],
        "class_probabilities": decision["class_probabilities"],
        "agreement_with_primary": (
            advisory_prediction == primary if comparable else None
        ),
        "review_priority": (
            "standard" if comparable and advisory_prediction == primary else "elevated"
        ),
        "interpretation": (
            "Os dois leitores concordaram; a decisão continua sendo do MedGemma e exige revisão humana."
            if comparable and advisory_prediction == primary
            else "Os leitores discordaram ou o leitor principal foi inconclusivo; priorize a revisão humana."
        ),
        "known_limitations": [
            "O classificador foi desenvolvido no LLD-MMRI.",
            "A validação externa OpenSwissHCC não atingiu o gate de sensibilidade.",
            "O resultado não substitui nem altera o relatório MedGemma.",
        ],
        "latency_seconds": round(time.monotonic() - started, 4),
    }
    _write_json_atomic(output_path, result)
    return result


def process_job(
    job_id: str,
    raw_dir: Path,
    medgemma_config: str = VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    analysis_scenario: str = "volumetric_rag",
    input_assessment: dict[str, Any] | None = None,
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
    secondary_reader: dict[str, Any] | None = None
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

        # A delayed MedSigLIP head is useful as a second opinion, but its failed
        # external gate forbids automatic promotion.  Run it only after a valid
        # primary report exists and never let an advisory failure invalidate the
        # MedGemma result.
        if input_assessment and input_assessment.get("mode") == "single_phase":
            advisory_started = time.monotonic()
            _set(job_id, step="segundo_leitor", progress=88)
            try:
                secondary_reader = _run_delayed_medsiglip_advisory(
                    case_dir=case_dir,
                    case_id=job_id,
                    input_assessment=input_assessment,
                    primary_prediction=str(
                        (report.get("report") or {}).get("resultado_hipotese") or "INCONCLUSIVA"
                    ),
                )
            except Exception as exc:  # advisory evidence must not erase a valid report
                log.exception("Job %s: segundo leitor MedSigLIP indisponível", job_id)
                secondary_reader = {
                    "schema": "oren-monophase-second-reader-v1",
                    "role": "advisory_second_reader",
                    "status": "unavailable",
                    "reason": type(exc).__name__,
                    "affects_primary_decision": False,
                    "external_gate_passed": False,
                    "requires_human_review": True,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
            durations_seconds["medsiglip_advisory"] = round(
                time.monotonic() - advisory_started, 4
            )

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
                input_assessment=input_assessment,
                secondary_reader=secondary_reader,
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


SUBTYPE_LABELS_PT = {
    "fnh": "Hiperplasia nodular focal (HNF)",
    "hcc": "Carcinoma hepatocelular (CHC)",
    "hemangioma": "Hemangioma",
    "hepatic_cyst": "Cisto hepático simples",
}


# O alvo da triagem binária é o CHC. As demais entidades nomeadas são lesões
# reais, mas benignas -- um exame NEGATIVO pode perfeitamente conter uma delas.
SCREENING_TARGET_SUBTYPE = "hcc"


def _subtype_fields(subtype: dict, positiva: bool) -> dict:
    """Campos de subtipo para a resposta, sem afirmar o que não se sabe.

    Duas coisas distintas que a interface não pode confundir:

    * **Triagem negativa não significa fígado sem lesão.** Só o CHC é positivo
      neste endpoint; HNF, hemangioma e cisto são negativos e continuam sendo
      alterações. Dizer "não há alteração" num negativo seria falso, e descartaria
      uma identificação que o modelo fez com confiança alta.
    * **Nomear exige base.** Se a massa de probabilidade foi para as classes sem
      subtipo documentado (docs/161), o subtipo fica indeterminado -- escolher o
      maior de quatro números quase nulos seria inventá-lo.
    """
    determinado = bool(subtype.get("determined"))
    campos = {
        "subtype_determined": determinado,
        "subtype": None,
        "subtype_label": None,
        "subtype_confidence": None,
        "subtype_named_lesion_mass": subtype.get("named_lesion_mass"),
        "subtype_is_screening_target": None,
        "subtype_unavailable_reason": None,
    }
    if not determinado:
        campos["subtype_unavailable_reason"] = subtype.get("reason")
        return campos
    nome = str(subtype["subtype"])
    campos.update(
        subtype=nome,
        subtype_label=SUBTYPE_LABELS_PT.get(nome, nome),
        subtype_confidence=subtype.get("subtype_confidence"),
        subtype_is_screening_target=(nome == SCREENING_TARGET_SUBTYPE),
    )
    if not positiva and nome == SCREENING_TARGET_SUBTYPE:
        # Triagem negativa mas a classe mais provável é o próprio alvo: as duas
        # leituras discordam e nenhuma deve ser apresentada como conclusão.
        campos["subtype_unavailable_reason"] = (
            "A triagem ficou abaixo do limiar, mas a classe mais provável é o "
            "próprio alvo. As duas leituras discordam e o caso exige revisão."
        )
    return campos


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
            # Mesmo gate anatômico do exame individual. Sem ele, o benchmark
            # contava como acerto exames que a página individual recusava.
            work_dir = Path(work_dir).resolve()
            base["liver_mask_quality"] = _segmentar_figado_com_gate(
                venous_dir, work_dir, f"Benchmark visual {benchmark_id}/{item['id']}"
            )
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
        positiva = decision["prediction"] == "POSITIVE"
        base.update(
            prediction="POSITIVA" if positiva else "NEGATIVA",
            confidence=None,
            status="decisive",
            visual_score=decision["score"],
            visual_threshold=decision["threshold"],
            panel_count=decision["panel_count"],
            in_sample=status["in_sample"],
            in_sample_verdict=status["verdict"],
            class_probabilities=decision["class_probabilities"],
        )
        base.update(_subtype_fields(decision["subtype"], positiva))
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


def _evaluate_benchmark_result(
    inference_result: dict,
    label: str,
    truth_subtype: str | None = None,
) -> dict:
    """Anexa ground truths binário e multiclasse somente após a inferência."""
    started = time.monotonic()
    result = dict(inference_result)
    expected = "POSITIVA" if label == "positive" else "NEGATIVA"
    prediction = result.get("prediction")
    result.update(
        truth=label,
        truth_subtype=truth_subtype,
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
            results.append(
                _evaluate_benchmark_result(
                    inference_result,
                    item["label"],
                    item.get("truth_subtype"),
                )
            )
            _set_benchmark(benchmark_id, processed=index, progress=5 + int(index / len(cases) * 90))

        completed_at = datetime.now(timezone.utc).isoformat()
        model_info = (
            _visual_model_info(scenario) if visual else _benchmark_model_info(medgemma_config)
        )
        metrics = calculate_benchmark_metrics(results)
        subtype_metrics = (
            compute_subtype_metrics(results)
            if manifest.get("evaluation_mode") == "pathology_and_subtype"
            else None
        )
        combined_target = {
            "requires_binary_and_subtype_targets": bool(subtype_metrics),
            "binary_met": metrics["target"]["met"],
            "subtype_met": subtype_metrics["target"]["met"] if subtype_metrics else None,
            "met": bool(
                metrics["target"]["met"]
                and (subtype_metrics is None or subtype_metrics["target"]["met"])
            ),
        }
        report = {
            "schema_version": 1,
            "benchmark_id": benchmark_id,
            "dataset_name": manifest["dataset_name"],
            "dataset_kind": manifest["dataset_kind"],
            "evaluation_mode": manifest.get("evaluation_mode", "binary"),
            "scenario": manifest.get("scenario", "baseline"),
            "started_at": started_at,
            "completed_at": completed_at,
            "model": model_info,
            "metrics": metrics,
            "subtype_metrics": subtype_metrics,
            "combined_target": combined_target,
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
            "evaluation_mode": manifest.get("evaluation_mode", "binary"),
            "subtype_reference_vocabulary": (
                list(SUBTYPE_CLASSES)
                if manifest.get("evaluation_mode") == "pathology_and_subtype"
                else None
            ),
        }
        write_run_outputs(benchmark_root, run_manifest, results, metrics)
        if subtype_metrics is not None:
            subtype_path = benchmark_root / "metrics_subtype.json"
            subtype_temp = benchmark_root / ".metrics_subtype.json.tmp"
            subtype_temp.write_text(
                json.dumps(subtype_metrics, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            subtype_temp.replace(subtype_path)
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
    evaluation_mode = str(manifest.get("evaluation_mode") or "binary")
    scenario = str(manifest.get("scenario") or "baseline")
    cases = manifest.get("cases")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="Informe o nome do dataset.")
    if dataset_kind not in {"positive", "negative", "mixed"}:
        raise HTTPException(status_code=400, detail="Tipo de dataset inválido.")
    if evaluation_mode not in {"binary", "pathology_and_subtype"}:
        raise HTTPException(status_code=400, detail="Modo de avaliação inválido.")
    if evaluation_mode == "pathology_and_subtype" and dataset_kind != "mixed":
        raise HTTPException(
            status_code=400,
            detail="O benchmark de patologia e variação exige dataset misto.",
        )
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
        truth_subtype = case.get("truth_subtype")
        if truth_subtype is not None:
            truth_subtype = str(truth_subtype).strip()
        if evaluation_mode == "pathology_and_subtype":
            if truth_subtype not in SUBTYPE_CLASSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Subtipo de referência inválido no exame {case_id}.",
                )
            expected_label = binary_label_for_subtype(truth_subtype)
            if label != expected_label:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Rótulo binário incompatível com o subtipo no exame {case_id}."
                    ),
                )
        elif truth_subtype:
            raise HTTPException(
                status_code=400,
                detail="Subtipo protegido só é aceito no modo patologia e variação.",
            )
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
        normalized.append({
            "id": case_id,
            "label": label,
            "truth_subtype": truth_subtype if evaluation_mode == "pathology_and_subtype" else None,
            "file_indices": clean_indices,
        })
    if seen_files != set(range(file_count)):
        raise HTTPException(status_code=400, detail="Todos os arquivos devem pertencer a um exame.")
    return {
        "dataset_name": dataset_name, "dataset_kind": dataset_kind,
        "evaluation_mode": evaluation_mode,
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
        "truth_subtype", "predicted_subtype_for_scoring", "subtype_correct",
        # Identificação da alteração (modo visual). `subtype_determined` falso num
        # caso POSITIVA não é dado faltante: é o modelo declarando que não tem base
        # para nomear o subtipo neste exame (docs/161).
        "subtype_determined", "subtype", "subtype_confidence",
        "subtype_named_lesion_mass", "subtype_unavailable_reason",
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
            _csv_cell(item.get("truth_subtype")),
            _csv_cell(item.get("predicted_subtype_for_scoring")),
            _csv_cell(item.get("subtype_correct")),
            _csv_cell(item.get("subtype_determined")),
            _csv_cell(item.get("subtype")),
            _csv_cell(item.get("subtype_confidence")),
            _csv_cell(item.get("subtype_named_lesion_mass")),
            _csv_cell(item.get("subtype_unavailable_reason")),
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


def _probe_backend(health_url: str) -> str:
    try:
        with urlopen(health_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return "desligado"
    return "pronto" if data.get("status") == "ready" else "carregando"


@app.get("/api/medgemma-backends")
def medgemma_backends() -> dict:
    """Backends MedGemma registrados, com o estado REAL de cada gateway.

    A interface só oferece o que respondeu no healthcheck. Oferecer um modelo
    que não está no ar produziria uma falha no meio da análise, depois do
    usuário já ter esperado a segmentação -- e a mensagem de erro não diria que
    a causa foi um gateway ausente.
    """
    itens = [
        {
            "id": backend["id"],
            "label": backend["label"],
            "config": backend["config"],
            "estado": _probe_backend(backend["health"]),
        }
        for backend in MEDGEMMA_BACKENDS.values()
    ]
    itens.sort(key=lambda row: row["label"])
    return {
        "backends": itens,
        "prontos": [row["id"] for row in itens if row["estado"] == "pronto"],
        # Dito de forma explícita para a interface não sugerir que a escolha
        # muda a acertividade do exame trifásico: ela não muda.
        "afeta": "fallback monofásico e benchmark; o exame trifásico usa o "
                 "classificador visual congelado e não passa pelo MedGemma",
    }


@app.get("/api/segmentation-visualization")
def segmentation_visualization_capability() -> dict:
    available = bool(ENHANCED_3D_OPT_IN_ENABLED and MRSEGMENTATOR_EXE.is_file())
    webapp_config = _segmentation_visualization_config.get("webapp") or {}
    return {
        "available": available,
        "mode": "quality_triggered_secondary_protected_fusion_v1",
        "selected_by_default": bool(
            available and webapp_config.get("selected_by_default") is True
        ),
        "scope": "visualization_only",
        "classification_immutable": True,
        "research_only": True,
    }


@app.post("/api/analyze")
async def analyze(request: Request) -> dict:
    form = await _upload_form(request)
    files = [v for v in form.getlist("files") if not isinstance(v, str)]
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    # O exame individual roda EXCLUSIVAMENTE o classificador visual da Etapa C,
    # que é o de melhor acertividade medida. O cliente não escolhe: um pedido que
    # mande outro cenário é recusado em vez de silenciosamente rebaixado, para
    # que ninguém receba um resultado pior achando que pediu outra coisa.
    pedido = form.get("scenario")
    if pedido is not None and str(pedido) != INDIVIDUAL_SCREENING_MODE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Modo de exame individual não autorizado: {str(pedido)!r}. "
                f"A análise individual usa apenas {INDIVIDUAL_SCREENING_MODE!r}."
            ),
        )
    scenario = INDIVIDUAL_SCREENING_MODE
    enhanced_raw = form.get("enhanced_3d")
    if enhanced_raw is not None and str(enhanced_raw) not in {"0", "1"}:
        raise HTTPException(status_code=400, detail="Opção de 3-D aprimorado inválida.")
    enhanced_3d = str(enhanced_raw or "0") == "1"
    if enhanced_3d and not (
        ENHANCED_3D_OPT_IN_ENABLED and MRSEGMENTATOR_EXE.is_file()
    ):
        raise HTTPException(
            status_code=409,
            detail="Segmentação 3-D aprimorada indisponível neste ambiente.",
        )
    # A escolha de backend MedGemma NÃO é escolha de cenário: ela só tem efeito
    # se o exame cair no fallback monofásico. Um id não registrado é recusado
    # aqui, antes de gastar segmentação, em vez de rebaixado em silêncio.
    backend_pedido = form.get("medgemma_backend")
    try:
        monophase_config = _medgemma_backend_config(
            str(backend_pedido) if backend_pedido else None, MONOPHASE_MEDGEMMA_CONFIG
        )
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
            "monophase_medgemma_config": monophase_config,
            "enhanced_3d": enhanced_3d,
        }
    threading.Thread(
        target=process_visual_job, args=(job_id, raw_dir), daemon=True
    ).start()
    return {
        "job_id": job_id,
        "analysis_scenario": scenario,
        "enhanced_3d": enhanced_3d,
    }


@app.get("/api/status/{job_id}")
def status(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        job = _restore_completed_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return {
        "state": job["state"],
        "step": job["step"],
        "progress": job["progress"],
        "analysis_scenario": job.get("analysis_scenario"),
        "enhanced_3d": bool(job.get("enhanced_3d")),
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


@app.post("/api/jobs/{job_id}/xr-session")
def create_xr_session(job_id: str, payload: XRSessionRequest, request: Request) -> dict:
    """Issue a short-lived, revocable link for a Quest session.

    The random secret is kept in the URL fragment, so it is not sent while the
    viewer shell and model assets load.  Only its SHA-256 is persisted locally.
    """
    case_dir = _case_dir_for_job(job_id)
    if not _model_done(case_dir):
        raise HTTPException(status_code=409, detail="Modelo 3D ainda nao esta disponivel.")
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session = {
        "schema": "oren-xr-session-v1",
        "job_id": job_id,
        "role": payload.role,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=payload.ttl_minutes)).isoformat(),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    path = _xr_session_path(case_dir, token)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    base = _quest_base_url(request)
    viewer_url = (
        f"{base}/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
        f"&xr=1&xr_role={payload.role}&xr_build=20260812-44#xr_token={token}"
    )
    return {**session, "viewer_url": viewer_url}


@app.get("/api/jobs/{job_id}/xr-session/{token}")
def get_xr_session(job_id: str, token: str) -> dict:
    return _read_xr_session(job_id, token)


@app.post("/api/jobs/{job_id}/xr-client-event")
def record_xr_client_event(job_id: str, payload: XRClientEventPayload) -> dict:
    _case_dir_for_job(job_id)  # valida o identificador sem ler dados clínicos
    log.info(
        "XR client %s: event=%s mode=%s error=%s message=%s",
        job_id, payload.event, payload.mode, payload.error_name or "-", payload.message or "-",
    )
    return {"accepted": True}


@app.post("/api/jobs/{job_id}/xr-session/{token}/approval")
def approve_model_from_xr(job_id: str, token: str, payload: ApprovalPayload) -> dict:
    session = _read_xr_session(job_id, token)
    if session.get("role") != "clinician":
        raise HTTPException(
            status_code=403,
            detail="O perfil de paciente nao pode registrar aprovacao tecnica.",
        )
    result = approve_model(job_id, payload)
    result["xr_session"] = {
        "schema": session["schema"],
        "role": session["role"],
        "created_at": session["created_at"],
    }
    approval_path = _case_dir_for_job(job_id) / "outputs" / "approval.json"
    temp = approval_path.with_name(".approval.json.xr.tmp")
    temp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(approval_path)
    _set(job_id, approval=result)
    return result


@app.get("/api/jobs/{job_id}/model/viewer_manifest.json")
def model_manifest(job_id: str):
    path = _case_dir_for_job(job_id) / "outputs" / "viewer_manifest.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Modelo 3D nao disponivel.")
    return FileResponse(path, media_type="application/json")


def _rgb_panel_files(job_id: str) -> list[Path]:
    panel_dir = _case_dir_for_job(job_id) / "panels"
    if not panel_dir.is_dir():
        return []
    return sorted(
        path for path in panel_dir.glob("medgemma_liver_screening_panel_???_of_???.png")
        if path.is_file() and path.name == Path(path.name).name
    )


@app.get("/api/jobs/{job_id}/rgb-panels")
def rgb_panel_catalog(job_id: str) -> dict:
    panels = _rgb_panel_files(job_id)
    return {
        "schema": "oren-rgb-panel-catalog-v1",
        "job_id": job_id,
        "count": len(panels),
        "panels": [
            {
                "index": index,
                "filename": panel.name,
                "url": f"/api/jobs/{job_id}/rgb-panels/{panel.name}",
                "sha256": sha256_of(panel),
            }
            for index, panel in enumerate(panels, start=1)
        ],
    }


@app.get("/api/jobs/{job_id}/rgb-panels/{filename}")
def rgb_panel_file(job_id: str, filename: str):
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Painel RGB nao encontrado.")
    authorized = {path.name: path for path in _rgb_panel_files(job_id)}
    path = authorized.get(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Painel RGB nao encontrado.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/model/{filename}")
def model_file(job_id: str, filename: str):
    case_dir = _case_dir_for_job(job_id)
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    if Path(filename).name != filename or not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        assets = _viewer_assets(manifest)
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Manifesto do modelo invalido.")
    if filename not in assets:
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    path = manifest_path.parent / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do modelo nao encontrado.")
    expected_hash = assets[filename].get("sha256")
    if expected_hash and sha256_of(path) != expected_hash:
        raise HTTPException(status_code=409, detail="Integridade do artefato do modelo falhou.")
    return FileResponse(path, media_type=str(assets[filename]["media_type"]))


@app.post("/api/jobs/{job_id}/approval")
def approve_model(job_id: str, payload: ApprovalPayload) -> dict:
    case_dir = _case_dir_for_job(job_id)
    if not _model_done(case_dir):
        raise HTTPException(status_code=409, detail="Modelo 3D ainda nao esta disponivel.")
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        # O servidor HTTPS do Quest pode ser iniciado depois do processamento.
        # Reconstruir somente o estado mínimo evita perder a revisão após restart.
        with _lock:
            _jobs[job_id] = {
                "state": "done", "step": "concluido", "progress": 100,
                "result": {}, "approval": {"status": "pending"},
            }
            job = _jobs[job_id]
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="Manifesto do modelo invalido.") from exc

    checklist = payload.checklist or ReviewChecklistPayload()
    requirements = manifest.get("review_requirements", {})
    if payload.status == "approved" and isinstance(requirements, dict):
        missing: list[str] = []
        if requirements.get("inspect_3d_contour") and not checklist.inspected_3d_contour:
            missing.append("inspecao_3d")
        if requirements.get("inspect_2d_reference") and not checklist.compared_2d_reference:
            missing.append("comparacao_2d")
        if requirements.get("acknowledge_research_only") and not checklist.acknowledged_research_only:
            missing.append("ciencia_uso_pesquisa")
        if requirements.get("inspect_candidate_against_mr"):
            if not checklist.reviewed_candidate_against_mr:
                missing.append("comparacao_candidato_rm")
            if payload.candidate_review_decision not in {
                "accepted_as_region_of_interest", "rejected"
            }:
                missing.append("decisao_sobre_candidato")
        if missing:
            raise HTTPException(
                status_code=422,
                detail="Checklist de revisao incompleto: " + ", ".join(missing),
            )

    state = payload.viewer_state or ViewerStatePayload()
    allowed_roles = {
        item.get("role") for item in manifest.get("meshes", []) if isinstance(item, dict)
    }
    if len(state.visible_roles) > 64 or any(role not in allowed_roles for role in state.visible_roles):
        raise HTTPException(status_code=422, detail="Estado do visualizador contem estrutura invalida.")
    bookmark_ids: set[str] = set()
    for saved_view in state.saved_views:
        if saved_view.bookmark_id in bookmark_ids:
            raise HTTPException(status_code=422, detail="Marcador de vista duplicado.")
        bookmark_ids.add(saved_view.bookmark_id)
        saved_roles = set(saved_view.visible_roles)
        opacity_roles = set(saved_view.opacity_by_role)
        if (
            not saved_roles.issubset(allowed_roles)
            or not opacity_roles.issubset(allowed_roles)
            or (saved_view.selected_role is not None and saved_view.selected_role not in allowed_roles)
        ):
            raise HTTPException(status_code=422, detail="Marcador de vista contem estrutura invalida.")
        camera_values = saved_view.camera_position_mm + saved_view.camera_target_mm
        if any(not math.isfinite(value) or abs(value) > 100_000 for value in camera_values):
            raise HTTPException(status_code=422, detail="Camera do marcador de vista invalida.")
        if any(
            not math.isfinite(opacity) or not 0 <= opacity <= 1
            for opacity in saved_view.opacity_by_role.values()
        ):
            raise HTTPException(status_code=422, detail="Opacidade do marcador de vista invalida.")
    if (
        len(set(state.compared_saved_view_ids)) != len(state.compared_saved_view_ids)
        or any(bookmark_id not in bookmark_ids for bookmark_id in state.compared_saved_view_ids)
    ):
        raise HTTPException(status_code=422, detail="Comparacao de vistas contem marcador invalido.")
    if len(state.measurements_mm) > 20 or any(
        not math.isfinite(value) or value < 0 or value > 5000
        for value in state.measurements_mm
    ):
        raise HTTPException(status_code=422, detail="Medicoes do visualizador invalidas.")
    measured_roles: set[str] = set()
    for dimensions in state.structure_dimensions_3d:
        if dimensions.role not in allowed_roles or dimensions.role in measured_roles:
            raise HTTPException(status_code=422, detail="Medicao tridimensional contem estrutura invalida.")
        measured_roles.add(dimensions.role)
        values = (
            dimensions.left_right_mm,
            dimensions.anterior_posterior_mm,
            dimensions.superior_inferior_mm,
        )
        if any(not math.isfinite(value) or not 0 < value <= 5000 for value in values):
            raise HTTPException(status_code=422, detail="Dimensoes tridimensionais invalidas.")
    clipping = state.clipping or ClippingStatePayload()
    if not math.isfinite(clipping.position_percent) or not 0 <= clipping.position_percent <= 100:
        raise HTTPException(status_code=422, detail="Plano de corte invalido.")

    artifact_hashes = {
        filename: spec.get("sha256") or sha256_of(manifest_path.parent / filename)
        for filename, spec in _viewer_assets(manifest).items()
    }
    approval = {
        "status": payload.status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_type": "human_visual_review",
        "review_protocol": "argos-viewer-review-v2",
        "checklist": checklist.model_dump(),
        "viewer_state": state.model_dump(),
        "candidate_review_decision": payload.candidate_review_decision,
        "candidate_review_scope": (
            "technical_region_of_interest_only_not_diagnostic_confirmation"
            if manifest.get("candidate_region")
            else None
        ),
        "viewer_manifest_sha256": sha256_of(manifest_path),
        "artifact_hashes": artifact_hashes,
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
