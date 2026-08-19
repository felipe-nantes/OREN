"""Integração — fronteira do subprocess de segmentação (PHASE_05, wave 1).

Exercita fronteiras REAIS sem GPU nem pesos verdadeiros:

- reparo do runtime isolado do TotalSegmentator (`prepare_totalsegmentator_environment`):
  o comentário do módulo descreve config.json global zerado com NUL por
  desligamento abrupto do Windows — o MESMO modo de falha observado no Docker
  Desktop desta máquina em 2026-08-18. Aqui esse reparo é exercitado de fato.
- crash real do worker em subprocess (`run_segmentation_subprocess` spawna um
  Python de verdade) → fail-closed com código de saída e extração de erro.
- corrupção de artefato entre estágios → `PipelineError`, nada fabricado
  (SW-FAIL-CLOSED-01 / SW-ARTIFACT-01 na fronteira de integração).

TASK-2026-08-18-PH05-INT-01.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.segmentation_subprocess import (
    prepare_totalsegmentator_environment,
    run_segmentation_subprocess,
    segmentation_error,
)

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Reparo do runtime TotalSegmentator
# --------------------------------------------------------------------------- #
def _pesos_falsos(tmp_path: Path) -> Path:
    weights = tmp_path / "pesos" / "nnunet" / "results"
    weights.mkdir(parents=True)
    return weights


def test_runtime_repara_config_zerada_com_nul_e_preserva_backup(tmp_path):
    """O cenário do comentário do módulo, exercitado de verdade: config.json
    do runtime preenchida com bytes NUL (desligamento abrupto) é substituída
    por uma config válida E o arquivo corrompido vira backup auditável."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    config = runtime / "config.json"
    config.write_bytes(b"\x00" * 64)

    environment = prepare_totalsegmentator_environment(
        runtime_root=runtime,
        base_environment={"TOTALSEG_WEIGHTS_PATH": str(_pesos_falsos(tmp_path))},
    )

    reparada = json.loads(config.read_text(encoding="utf-8"))
    assert reparada["send_usage_stats"] is False
    assert reparada["prediction_counter"] == 0
    backups = list(runtime.glob("config.invalid.*.bin"))
    assert len(backups) == 1, "o arquivo corrompido deveria ter virado backup"
    assert backups[0].read_bytes() == b"\x00" * 64
    assert environment["TOTALSEG_HOME_DIR"] == str(runtime)


def test_runtime_preserva_contador_de_predicoes_de_config_valida(tmp_path):
    """Reexecução idempotente: uma config válida existente não é zerada — o
    prediction_counter sobrevive ao reparo."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "config.json").write_text(
        json.dumps({"totalseg_id": "x", "send_usage_stats": True, "prediction_counter": 17}),
        encoding="utf-8",
    )

    prepare_totalsegmentator_environment(
        runtime_root=runtime,
        base_environment={"TOTALSEG_WEIGHTS_PATH": str(_pesos_falsos(tmp_path))},
    )

    reparada = json.loads((runtime / "config.json").read_text(encoding="utf-8"))
    assert reparada["prediction_counter"] == 17
    assert reparada["send_usage_stats"] is False  # política local reforçada
    assert not list(runtime.glob("config.invalid.*")), "config válida não gera backup"


def test_runtime_sem_pesos_falha_fechado_antes_de_qualquer_subprocess(tmp_path):
    """SW-FAIL-CLOSED-01: pesos ausentes abortam ANTES de spawnar qualquer
    worker — nunca uma segmentação fabricada ou um erro tardio confuso."""
    with pytest.raises(RuntimeError, match="Pesos do TotalSegmentator"):
        prepare_totalsegmentator_environment(
            runtime_root=tmp_path / "runtime",
            base_environment={"TOTALSEG_WEIGHTS_PATH": str(tmp_path / "nao_existe")},
        )


# --------------------------------------------------------------------------- #
# Crash real do worker em subprocess
# --------------------------------------------------------------------------- #
def test_worker_real_crasha_fechado_com_prep_fail_extraivel(tmp_path, monkeypatch):
    """Fronteira real: spawna o seg_worker num Python de verdade com um
    diretório DICOM inexistente. O worker importa o motor, falha com
    PipelineError, imprime PREP_FAIL e sai com código 2 — e
    `segmentation_error` extrai a mensagem para o operador."""
    monkeypatch.setenv("TOTALSEG_WEIGHTS_PATH", str(_pesos_falsos(tmp_path)))
    monkeypatch.setenv("ARGOS_TOTALSEG_RUNTIME_DIR", str(tmp_path / "runtime"))

    processo = run_segmentation_subprocess(
        dicom_dir=tmp_path / "dicom_que_nao_existe",
        case_dir=tmp_path / "caso",
        profile_path=ROOT / "profiles" / "figado.yaml",
        device="cpu",
        fast=True,
        timeout_seconds=300,
        python_executable=sys.executable,
    )

    # Exit 2 é especificamente o caminho PipelineError do motor (verificado
    # em 2026-08-18): o worker importou dtwin com sucesso (não é o exit 65 de
    # import quebrado) e falhou fechado na validação do input.
    assert processo.returncode == 2, (
        f"esperado exit 2 (PipelineError); veio {processo.returncode}: "
        f"{(processo.stdout or '')[:200]}"
    )
    assert "PREP_OK" not in (processo.stdout or "")
    erro = segmentation_error(processo)
    assert "Pasta DICOM inexistente" in erro, "mensagem acionável esperada"
    assert "PREP_FAIL" not in erro, "a extração deve remover o marcador"


def test_worker_com_argumentos_invalidos_sai_com_codigo_proprio(tmp_path):
    """O contrato de argumentos do worker é fail-closed: argc errado → exit 64
    com PREP_FAIL, sem tocar em nada."""
    worker = ROOT / "dtwin" / "seg_worker.py"
    processo = subprocess.run(
        [sys.executable, str(worker), "so_um_argumento"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert processo.returncode == 64
    assert "PREP_FAIL" in processo.stdout


def test_extracao_de_erro_prioriza_marcador_e_trunca_ruido():
    """`segmentation_error` é a única janela do operador para o crash: o
    marcador PREP_FAIL vence qualquer ruído; sem marcador, cauda truncada;
    sem saída nenhuma, o código de saída."""
    prep_fail = subprocess.CompletedProcess(
        args=[], returncode=2,
        stdout="lixo antes\nPREP_FAIL: mensagem acionável\nlixo depois",
        stderr="traceback gigante",
    )
    assert segmentation_error(prep_fail) == "mensagem acionável"

    sem_marcador = subprocess.CompletedProcess(
        args=[], returncode=3, stdout="", stderr="x" * 5000
    )
    assert len(segmentation_error(sem_marcador)) <= 1000

    silencioso = subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="")
    assert "7" in segmentation_error(silencioso)


# --------------------------------------------------------------------------- #
# Corrupção de artefato entre estágios
# --------------------------------------------------------------------------- #
def test_mascara_corrompida_entre_prepare_e_finalize_aborta_sem_fabricar(synthetic_case):
    """SW-FAIL-CLOSED-01 na integração: a máscara do órgão corrompida DEPOIS
    do prepare e ANTES do finalize derruba o finalize com PipelineError — o
    pipeline não fabrica malha nem manifesto a partir de lixo."""
    from dtwin.engine import Engine

    case = synthetic_case
    mtime_antes = {
        p.name: p.stat().st_mtime for p in case.root.rglob("*.stl")
    }
    case.mask_organ.write_bytes(b"isto nao e um nifti \x00\x01\x02")

    with pytest.raises(PipelineError):
        Engine(str(ROOT / "profiles" / "figado.yaml")).finalize(
            str(case.root), no_lesion=True
        )

    mtime_depois = {p.name: p.stat().st_mtime for p in case.root.rglob("*.stl")}
    assert mtime_antes == mtime_depois, (
        "finalize sobre máscara corrompida não pode publicar/reescrever STL"
    )
