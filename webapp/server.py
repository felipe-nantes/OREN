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

import json
import logging
import math
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time  # noqa: F401 (superficie de patch: testes usam server.time.sleep)
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pydicom
import SimpleITK as sitk
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from dtwin.benchmark.dataset_audit import (
    describe_selected_series,
    select_best_mr_series,
)
from dtwin.benchmark.reporting import write_run_outputs as write_run_outputs
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import (
    load_screening_config as load_screening_config,  # patch-target da facade REF-03
)
from dtwin.segmentation_subprocess import run_segmentation_subprocess

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("dtwin.webapp")

# Entry legado `python -m webapp.server`: sob runpy este arquivo executa como
# o módulo __main__, e os submódulos da façade (REF-03) fazem
# `from webapp import server` — o que criaria uma SEGUNDA instância deste
# módulo e re-entraria o ciclo de import com os submódulos parcialmente
# inicializados. O auto-alias abaixo garante UMA instância única (mesma
# semântica do caminho de produção `uvicorn webapp.server:app`).
if __name__ == "__main__" and "webapp.server" not in sys.modules:
    _modulo_main = sys.modules.get(__name__)
    # Alias apenas quando o __main__ é ESTE arquivo (o caso `python -m`);
    # runpy.run_module de terceiros mantém __main__ alheio e fica de fora.
    if getattr(_modulo_main, "__file__", None) == __file__:
        sys.modules["webapp.server"] = _modulo_main

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STATIC = ROOT / "static"
VIEWER = REPO / "viewer"
WORKSPACE = Path("casos/webapp")
PROFILE = "profiles/figado.yaml"
# CT-01 (2026-08-25): perfil POR MODALIDADE (padrao portado do Volyrics).
# PROFILE permanece o default MR — todo o fluxo de RM e byte-identico ao
# anterior; CT so diverge quando o operador habilita e o cliente seleciona.
MODALITY_PROFILES = {"MR": PROFILE, "CT": "profiles/figado_ct.yaml"}
# TC atras de flag de operador ate a validacao volumetrica LOCAL (fase
# CT-01-F): os numeros citados no aviso sao medicao do Volyrics, nao deste
# repo (perfil figado_ct.yaml declara validado: false pela mesma razao).
CT_ENABLED = os.environ.get("WEBAPP_CT_ENABLED", "0") == "1"
# RIM-01 (2026-08-28, plano aprovado): eixo orgao x modalidade. MODALITY_
# PROFILES permanece como estava (alias figado-only; patch-points do REF-03
# e o teste _profile_path_for continuam validos byte-identicos). PROFILES e
# a tabela nova, usada apenas quando organ != "figado".
PROFILES = {
    ("figado", "MR"): PROFILE,
    ("figado", "CT"): "profiles/figado_ct.yaml",
    ("rins", "MR"): "profiles/rins.yaml",
    ("rins", "CT"): "profiles/rins_ct.yaml",
}
ORGANS_SUPORTADOS = frozenset(organ for organ, _ in PROFILES)
# Rim atras de flag de operador ate a validacao volumetrica LOCAL (fase F do
# plano RIM-01, benchmark contra CHAOS-MR/KiTS): perfis rins.yaml/rins_ct.yaml
# declaram validado: false pela mesma razao do padrao CT-01.
KIDNEY_ENABLED = os.environ.get("WEBAPP_KIDNEY_ENABLED", "0") == "1"
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
# CT-LAUDO (2026-08-28, ordem do operador — revoga o D4 do CT-01): laudo
# MedGemma zero-shot em TC usa a MESMA config do benchmark CT-01-F, para
# que os números de acurácia medidos descrevam exatamente o que roda aqui.
CT_MEDGEMMA_CONFIG = os.environ.get(
    "WEBAPP_MEDGEMMA_CONFIG_CT",
    "configs/medgemma_local_4b_ct_benchmark.yaml",
)
# CT-03 (2026-08-28, plano aprovado): detector de lesão TC (TS task
# liver_lesions/Dataset591) como candidato advisory. Fail-closed até o
# gate 75/75 do benchmark CT-03; timeout próprio (3d_fullres_high em TC
# de abdome não cabe nos 95s do candidato de RM).
CT_CANDIDATE_ENABLED = os.environ.get("WEBAPP_CT_CANDIDATE_ENABLED", "0") == "1"
CT_CANDIDATE_TIMEOUT = int(os.environ.get("WEBAPP_CT_CANDIDATE_TIMEOUT", "300"))
# Acurácia MEDIDA do laudo zero-shot em TC (CT01-F, 2026-08-28; evidência
# em .fable/post_audit/evidence/CT01-F/). Acompanha todo resultado de TC.
CT_SCREENING_VALIDATION = {
    "validado": False,
    "zero_shot": True,
    "benchmark": "CT01-F (2026-08-28)",
    "sensibilidade_pct": 16.2,
    "especificidade_pct": 60.0,
    "acerto_tipo_pct": 6.2,
    "nota": (
        "Laudo experimental: modelo de triagem visual portado de RM sem "
        "ajuste para TC. No benchmark local pré-registrado detectou apenas "
        "16,2% dos casos com tumor e classificou o tipo corretamente em "
        "6,2%. Uso em pesquisa; NUNCA substitui leitura radiológica."
    ),
}
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

# Constantes de dominio do benchmark (R1 do REF-03: config fica no server;
# benchmarks.py/jobs.py leem via server.<nome> em tempo de chamada)
SUBTYPE_LABELS_PT = {
    "fnh": "Hiperplasia nodular focal (HNF)",
    "hcc": "Carcinoma hepatocelular (CHC)",
    "hemangioma": "Hemangioma",
    "hepatic_cyst": "Cisto hepático simples",
}
# O alvo da triagem binária é o CHC. As demais entidades nomeadas são lesões
# reais, mas benignas -- um exame NEGATIVO pode perfeitamente conter uma delas.
SCREENING_TARGET_SUBTYPE = "hcc"
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
        except Exception:
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
    except Exception:
        return {"MR", "MRI"}


def _modality_of(names: list[str]) -> str:
    """Lê a Modality (0008,0060) do primeiro arquivo legível da série."""
    for name in names[:5]:
        try:
            ds = pydicom.dcmread(name, stop_before_pixels=True, force=True)
        except Exception:
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
        except Exception:
            series_ids = [""]
        for sid in series_ids:
            try:
                names = (reader.GetGDCMSeriesFileNames(dirpath, sid) if sid
                         else reader.GetGDCMSeriesFileNames(dirpath))
            except Exception:
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
            except Exception:
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


def _profile_path_for(modality: str) -> str:
    """Caminho (relativo ao repo) do perfil da modalidade selecionada.

    CT-01: seleção EXPLÍCITA pelo cliente; modalidade fora do mapa é recusada
    aqui — nunca rebaixada em silêncio para o perfil default."""
    perfil = MODALITY_PROFILES.get(str(modality or "").upper())
    if not perfil:
        raise PipelineError(f"Modalidade não suportada: {modality!r}.")
    return perfil


def _organ_profile_path_for(organ: str, modality: str) -> str:
    """Caminho do perfil para (órgão, modalidade) — RIM-01, análogo ao
    _profile_path_for de CT-01 mas cobrindo o eixo novo. Combinação fora
    da tabela é recusada aqui, nunca rebaixada em silêncio."""
    perfil = PROFILES.get((str(organ or "").lower(), str(modality or "").upper()))
    if not perfil:
        raise PipelineError(
            f"Combinação órgão/modalidade não suportada: {organ!r}/{modality!r}."
        )
    return perfil


def _aviso_volumetria_ct() -> dict:
    """Nota consultiva de calibração para volumetria de TC (CT-01, D5).

    É medição registrada, não configuração: benchmark do VOLYRICS (docs/249 +
    docs/250 daquele repo; CHAOS-CT n=20 razão 0,991; 3D-IRCADb-01 n=20 razão
    0,997; combinado mediana 0,99; Spearman rho 0,035 p=0,88 — erro NÃO
    escala com carga tumoral, ao contrário da RM). NÃO replicada neste
    repositório — por isso o perfil CT segue `validado: false` e a nota nunca
    vira correção automática: o volume publicado é sempre o da máscara
    aprovada na revisão humana."""
    return {
        "tipo": "calibracao_volumetria_ct",
        "mensagem": (
            "Contexto de calibração (TC): em benchmark externo contra referência "
            "humana (n=40; CHAOS-CT e 3D-IRCADb-01), a razão mediana "
            "volume-predito/referência foi 0,99, sem subestimação sistemática "
            "detectável e sem escalonamento do erro com carga tumoral. "
            "MEDIÇÃO DE ORIGEM EXTERNA (Volyrics, docs/249-250 daquele projeto), "
            "não replicada neste repositório. Viés de mediana populacional não "
            "prevê o erro deste caso individual."
        ),
        "razao_mediana_externa": 0.99,
        "origem": "volyrics_docs_249_250_n40",
        "replicada_neste_repositorio": False,
        "correcao_aplicada": False,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def _segment(
    series_dir: str,
    case_dir: Path,
    device: str,
    timeout: int,
    *,
    fast: bool,
    profile_rel: str | None = None,
) -> subprocess.CompletedProcess:
    """Roda a segmentação pelo launcher, a partir do %TEMP% (fora do OneDrive).

    `fast=False` (exame individual) usa full-res (~1.5mm) para uma máscara mais
    fiel; `fast=True` (benchmark) mantém 3mm por throughput. `profile_rel`
    (CT-01) escolhe o perfil por job; None preserva o default MR — nenhum
    caller de RM mudou."""
    return run_segmentation_subprocess(
        dicom_dir=Path(series_dir),
        case_dir=case_dir,
        profile_path=REPO / (profile_rel or PROFILE),
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
    import SimpleITK as sitk

    from dtwin.benchmark.lld_mmri_v23_mask_quality import evaluate_liver_mask_quality

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


# --- REF-03 seam 4: uniao de fases e modelo 3D extraidos p/ webapp/phase_union.py ---
# DOWNSTREAM CIENTIFICO (decisao 13). Facade R1/R2 identica aos seams 1-3.
# --- REF-03 seam 3: workers de analise extraidos p/ webapp/jobs.py ---
# Facade (regras R1/R2): simbolos publicos preservados; jobs.py resolve
# config/estado/patch-targets via server.<nome> em tempo de chamada.
# --- REF-03 seam 2: subsistema de benchmark extraido p/ webapp/benchmarks.py ---
# Facade (regra R2): simbolos continuam publicos em webapp.server; modulos
# extraidos resolvem config/estado/patch-targets via server.<nome>.
from webapp.benchmarks import (
    _authorized_visual_phase_resolution as _authorized_visual_phase_resolution,
)
from webapp.benchmarks import (
    _benchmark_config as _benchmark_config,
)
from webapp.benchmarks import (
    _benchmark_csv as _benchmark_csv,
)
from webapp.benchmarks import (
    _benchmark_model_info as _benchmark_model_info,
)
from webapp.benchmarks import (
    _csv_cell as _csv_cell,
)
from webapp.benchmarks import (
    _evaluate_benchmark_result as _evaluate_benchmark_result,
)
from webapp.benchmarks import (
    _individual_screening_config as _individual_screening_config,
)
from webapp.benchmarks import (
    _is_visual_scenario as _is_visual_scenario,
)
from webapp.benchmarks import (
    _parse_benchmark_manifest as _parse_benchmark_manifest,
)
from webapp.benchmarks import (
    _provenance_summary as _provenance_summary,
)
from webapp.benchmarks import (
    _run_benchmark_case as _run_benchmark_case,
)
from webapp.benchmarks import (
    _run_visual_benchmark_case as _run_visual_benchmark_case,
)
from webapp.benchmarks import (
    _subtype_fields as _subtype_fields,
)
from webapp.benchmarks import (
    _upload_form as _upload_form,
)
from webapp.benchmarks import (
    _visual_bundle_root as _visual_bundle_root,
)
from webapp.benchmarks import (
    _visual_model_info as _visual_model_info,
)
from webapp.benchmarks import (
    calculate_benchmark_metrics as calculate_benchmark_metrics,
)
from webapp.benchmarks import (
    process_benchmark as process_benchmark,
)

# --- REF-03 seam 1: persistencia de job, sessoes XR e payloads extraidos ---
# Facade: os simbolos continuam publicos em webapp.server (testes e tools
# monkeypatcham/importam por aqui). Os modulos novos resolvem config/estado
# via server.<nome> em tempo de chamada (regra R2 do design), entao
# monkeypatch.setattr(server, ...) segue valendo.
# (re-exports intencionais: noqa F401 — remover quebraria patch-points/tools)
from webapp.job_persistence import (
    _case_dir_for_job as _case_dir_for_job,
)
from webapp.job_persistence import (
    _completed_job_state_path as _completed_job_state_path,
)
from webapp.job_persistence import (
    _legacy_completed_job_from_artifacts as _legacy_completed_job_from_artifacts,
)
from webapp.job_persistence import (
    _persist_completed_job_state as _persist_completed_job_state,
)
from webapp.job_persistence import (
    _restore_completed_job as _restore_completed_job,
)
from webapp.jobs import (
    _run_delayed_medsiglip_advisory as _run_delayed_medsiglip_advisory,
)
from webapp.jobs import (
    process_ct_job as process_ct_job,
)
from webapp.jobs import (
    process_job as process_job,
)
from webapp.jobs import (
    process_monophase_medsiglip_job as process_monophase_medsiglip_job,
)
from webapp.jobs import (
    process_organ_job as process_organ_job,
)
from webapp.jobs import (
    process_visual_job as process_visual_job,
)
from webapp.payloads import (
    ApprovalPayload as ApprovalPayload,
)
from webapp.payloads import (
    ClippingStatePayload as ClippingStatePayload,
)
from webapp.payloads import (
    ReviewChecklistPayload as ReviewChecklistPayload,
)
from webapp.payloads import (
    StructureDimensions3DPayload as StructureDimensions3DPayload,
)
from webapp.payloads import (
    ViewerSavedViewPayload as ViewerSavedViewPayload,
)
from webapp.payloads import (
    ViewerStatePayload as ViewerStatePayload,
)
from webapp.payloads import (
    XRClientEventPayload as XRClientEventPayload,
)
from webapp.payloads import (
    XRSessionRequest as XRSessionRequest,
)
from webapp.phase_union import (
    _build_enhanced_visualization_shadow as _build_enhanced_visualization_shadow,
)
from webapp.phase_union import (
    _build_model as _build_model,
)
from webapp.phase_union import (
    _build_union_liver_mask as _build_union_liver_mask,
)
from webapp.phase_union import (
    _localize_candidate as _localize_candidate,
)
from webapp.phase_union import (
    _mesma_geometria_sitk as _mesma_geometria_sitk,
)
from webapp.phase_union import (
    _model_done as _model_done,
)
from webapp.xr_sessions import (
    _quest_base_url as _quest_base_url,
)
from webapp.xr_sessions import (
    _quest_qr_data_url as _quest_qr_data_url,
)
from webapp.xr_sessions import (
    _read_xr_session as _read_xr_session,
)
from webapp.xr_sessions import (
    _recent_quest_jobs as _recent_quest_jobs,
)
from webapp.xr_sessions import (
    _xr_session_path as _xr_session_path,
)

app = FastAPI(title="Digital Twin — Triagem MedGemma (demo, modo Pesquisa)")


@app.get("/api/health")
def health() -> dict:
    backend = "desligado"
    try:
        with urlopen(HEALTH_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        backend = "pronto" if data.get("status") == "ready" else "carregando"
    except Exception:
        backend = "desligado"
    # CT-01: a UI só mostra o seletor de modalidade quando o operador
    # habilitou TC (flag WEBAPP_CT_ENABLED; perfil CT ainda validado:false).
    return {"backend": backend, "ct_enabled": CT_ENABLED, "kidney_enabled": KIDNEY_ENABLED}


def _probe_backend(health_url: str) -> str:
    try:
        with urlopen(health_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
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


def _detect_upload_modality(raw_dir: Path, max_files: int = 200) -> set[str]:
    """Modalidades DICOM presentes no envio (amostra de headers, sem pixels).

    AUTO-modalidade (2026-08-28, ordem do operador: "a página de laudos deve
    funcionar tanto na RM quanto na CT"): a tag Modality decide o worker;
    MRI normaliza para MR. Arquivos ilegíveis são ignorados.
    """
    presentes: set[str] = set()
    lidos = 0
    for path in sorted(Path(raw_dir).rglob("*")):
        if not path.is_file() or lidos >= max_files:
            continue
        lidos += 1
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        except Exception:
            continue
        tag = str(getattr(ds, "Modality", "") or "").upper()
        if tag == "MRI":
            tag = "MR"
        if tag in MODALITY_PROFILES:
            presentes.add(tag)
        if presentes == set(MODALITY_PROFILES):
            break
    return presentes


@app.post("/api/analyze")
async def analyze(request: Request) -> dict:
    form = await _upload_form(request)
    files = [v for v in form.getlist("files") if not isinstance(v, str)]
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    # RIM-01 (2026-08-28): orgao e SELECAO EXPLICITA do cliente, mesmo padrao
    # de honestidade da modalidade em CT-01. Default "figado" preserva
    # compatibilidade total com clientes existentes.
    organ = str(form.get("organ") or "figado").lower()
    if organ not in ORGANS_SUPORTADOS:
        raise HTTPException(status_code=400, detail=f"Órgão não suportado: {organ!r}.")
    if organ == "rins" and not KIDNEY_ENABLED:
        # Perfis rins.yaml/rins_ct.yaml declaram validado:false (benchmark
        # local pendente, fase F do plano RIM-01); sem a flag o caminho nem
        # existe — mesmo padrão do CT_ENABLED.
        raise HTTPException(
            status_code=409,
            detail=(
                "Análise de rins indisponível neste ambiente (validação local "
                "pendente; habilite com WEBAPP_KIDNEY_ENABLED=1)."
            ),
        )
    # CT-01: modalidade e SELECAO EXPLICITA do cliente (decisao do operador,
    # 2026-08-25); a tag DICOM vira validacao no worker. Default "MR" preserva
    # compatibilidade total com clientes existentes. AUTO (2026-08-28)
    # resolve pela tag DICOM apos o upload — ver _detect_upload_modality.
    modality = str(form.get("modality") or "MR").upper()
    if organ == "rins" and modality == "AUTO":
        # Detecção automática de modalidade é figado-específica (o ramo AUTO
        # abaixo dispara process_ct_job direto); rim exige seleção explícita
        # de RM/TC nesta fase — escopo declarado, não rebaixamento silencioso.
        raise HTTPException(
            status_code=400,
            detail="Análise de rins exige modalidade explícita (RM ou TC); AUTO não é suportado.",
        )
    modalidade_auto = modality == "AUTO"
    if modalidade_auto:
        modality = "MR"  # provisório; resolvido após salvar os arquivos
    if modality not in MODALITY_PROFILES:
        raise HTTPException(
            status_code=400, detail=f"Modalidade não suportada: {modality!r}."
        )
    if organ == "figado":
        if modality == "CT" and not CT_ENABLED:
            # Perfil CT declara validado:false (benchmark local pendente, fase
            # CT-01-F); sem a flag de operador o caminho nem existe.
            raise HTTPException(
                status_code=409,
                detail=(
                    "Análise de TC indisponível neste ambiente (validação local "
                    "pendente; habilite com WEBAPP_CT_ENABLED=1)."
                ),
            )
        # O exame individual roda EXCLUSIVAMENTE o classificador visual da Etapa C,
        # que é o de melhor acertividade medida. O cliente não escolhe: um pedido que
        # mande outro cenário é recusado em vez de silenciosamente rebaixado, para
        # que ninguém receba um resultado pior achando que pediu outra coisa.
        pedido = form.get("scenario")
        if modality == "CT" and pedido is not None:
            # O cenário de TC é implicado pela modalidade (ct_volumetric, sem
            # triagem); um pedido explícito seria ignorado — recusar é honesto.
            raise HTTPException(
                status_code=400,
                detail="Exame de TC não aceita seleção de cenário (é sempre ct_volumetric).",
            )
        if pedido is not None and str(pedido) != INDIVIDUAL_SCREENING_MODE:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Modo de exame individual não autorizado: {str(pedido)!r}. "
                    f"A análise individual usa apenas {INDIVIDUAL_SCREENING_MODE!r}."
                ),
            )
        scenario = "ct_volumetric" if modality == "CT" else INDIVIDUAL_SCREENING_MODE
        enhanced_raw = form.get("enhanced_3d")
        if enhanced_raw is not None and str(enhanced_raw) not in {"0", "1"}:
            raise HTTPException(status_code=400, detail="Opção de 3-D aprimorado inválida.")
        enhanced_3d = str(enhanced_raw or "0") == "1"
        if enhanced_3d and modality == "CT":
            # O 3-D aprimorado usa o MRSegmentator — RM por definição; recusar
            # explícito em vez de rebaixar em silêncio.
            raise HTTPException(
                status_code=400,
                detail="Segmentação 3-D aprimorada é exclusiva de RM.",
            )
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
    else:
        # RIM-01: escopo v1 e SOMENTE volumetria + 3D -- sem triagem/laudo,
        # sem cenario configuravel, sem 3-D aprimorado (MRSegmentator e
        # figado-especifico), sem backend MedGemma. Qualquer um desses
        # campos vindo no envio e recusado explicito, nunca ignorado em
        # silencio.
        for campo, valor in (
            ("scenario", form.get("scenario")),
            ("medgemma_backend", form.get("medgemma_backend")),
        ):
            if valor is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Analise de rins nao aceita o campo {campo!r}.",
                )
        enhanced_raw = form.get("enhanced_3d")
        if enhanced_raw is not None and str(enhanced_raw) not in {"0", "1"}:
            raise HTTPException(status_code=400, detail="Opcao de 3-D aprimorada invalida.")
        if str(enhanced_raw or "0") == "1":
            raise HTTPException(
                status_code=400,
                detail="Segmentacao 3-D aprimorada e exclusiva de figado/RM.",
            )
        scenario = "organ_volumetric"
        enhanced_3d = False
        monophase_config = MONOPHASE_MEDGEMMA_CONFIG  # nao usado por process_organ_job
    relpaths = form.get("relpaths")
    job_id = uuid.uuid4().hex[:12]
    raw_dir = WORKSPACE / job_id / "_upload"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        paths = json.loads(relpaths) if isinstance(relpaths, str) else []
        if not isinstance(paths, list):
            paths = []
    except Exception:
        paths = []
    for i, uf in enumerate(files):
        rel = (paths[i] if i < len(paths) and paths[i] else uf.filename) or f"file_{i}"
        parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", "..", ".")]
        dest = raw_dir.joinpath(*parts) if parts else raw_dir / f"file_{i}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await uf.read())
    if modalidade_auto:
        presentes = _detect_upload_modality(raw_dir)
        if presentes == {"MR", "CT"}:
            shutil.rmtree(WORKSPACE / job_id, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=(
                    "O envio mistura séries de RM e de TC; selecione a "
                    "modalidade explicitamente para este exame."
                ),
            )
        if presentes == {"CT"}:
            if not CT_ENABLED:
                shutil.rmtree(WORKSPACE / job_id, ignore_errors=True)
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "O envio é de TC, mas a análise de TC está indisponível "
                        "neste ambiente (habilite com WEBAPP_CT_ENABLED=1)."
                    ),
                )
            # Campos RM enviados por default do cliente (cenário, 3-D
            # aprimorado, backend) são ignorados: o usuário pediu AUTO,
            # não os pediu para TC.
            modality = "CT"
            scenario = "ct_volumetric"
            enhanced_3d = False
        # vazio ou só MR: segue o caminho de RM (o gracioso existente cobre
        # envio sem série válida)
    with _lock:
        _jobs[job_id] = {
            "state": "queued", "step": "recebendo", "progress": 5, "result": None,
            "analysis_scenario": scenario,
            "modality": modality,
            "organ": organ,
            "monophase_medgemma_config": monophase_config,
            "enhanced_3d": enhanced_3d,
        }
    # CT-01 (D3/D4): TC despacha para o worker dedicado (série única, sem
    # triagem, perfil figado_ct); RM segue o caminho atual byte-idêntico.
    # RIM-01: qualquer modalidade de rim despacha para o worker genérico de
    # órgão (volumetria + 3D, sem triagem — nenhum classificador renal existe).
    if organ == "rins":
        worker = process_organ_job
    elif modality == "CT":
        worker = process_ct_job
    else:
        worker = process_visual_job
    threading.Thread(
        target=worker, args=(job_id, raw_dir), daemon=True
    ).start()
    return {
        "job_id": job_id,
        "analysis_scenario": scenario,
        "modality": modality,
        "organ": organ,
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
    except Exception as exc:
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
        f"&xr=1&xr_role={payload.role}&xr_build=20260814-anatomic-v1-3#xr_token={token}"
    )
    return {
        **session,
        "viewer_url": viewer_url,
        "quest_short_url": f"{base}/quest/",
        "qr_code_data_url": _quest_qr_data_url(viewer_url),
    }


@app.get("/api/quest/recent-jobs")
def recent_quest_jobs(limit: int = 8) -> dict:
    bounded_limit = max(1, min(int(limit), 20))
    jobs = _recent_quest_jobs(limit=bounded_limit)
    return {
        "schema": "oren-quest-ready-jobs-v1",
        "count": len(jobs),
        "jobs": jobs,
        "research_only": True,
        "clinical_use_allowed": False,
    }


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
