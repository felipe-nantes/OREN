"""Integração — fronteira real do webapp (PHASE_05, wave 2).

Complementa tests/test_webapp.py (que usa TestClient/ASGI em processo) com as
fronteiras que só existem fora do processo:

- **uvicorn de verdade**: o servidor sobe num subprocess real, atende
  `/api/health` por HTTP de socket, recusa uma segunda instância na mesma
  porta (o mecanismo em que `run_win.ps1` confia) e libera a porta ao morrer.
- **concorrência de jobs** (LONG_PLAN P1 #8): atualizações concorrentes de
  `_set` não se perdem, e o estado persistido ao concluir é JSON íntegro
  mesmo sob corrida — a janela persist-fora-do-lock não pode corromper.

TASK-2026-08-18-PH05-INT-02.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(("127.0.0.1", 0))
        return sonda.getsockname()[1]


def test_uvicorn_real_atende_recusa_segunda_instancia_e_libera_a_porta():
    """E2E nativo mínimo: o mesmo comando que o launcher usa, num subprocess
    real. Cobre o que o TestClient não alcança: bind de socket, porta ocupada
    e liberação no encerramento."""
    porta = _porta_livre()
    comando = [
        sys.executable, "-m", "uvicorn", "webapp.server:app",
        "--host", "127.0.0.1", "--port", str(porta),
    ]
    servidor = subprocess.Popen(
        comando, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        # 1) servidor real responde /api/health por HTTP de socket
        prazo = time.monotonic() + 120
        saude = None
        while time.monotonic() < prazo:
            if servidor.poll() is not None:
                saida = servidor.stdout.read() if servidor.stdout else ""
                pytest.fail(f"uvicorn morreu durante o boot:\n{saida[-1500:]}")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{porta}/api/health", timeout=3
                ) as resposta:
                    saude = json.loads(resposta.read().decode("utf-8"))
                break
            except OSError:
                time.sleep(1.0)
        assert saude is not None, "health não respondeu em 120s"
        assert "backend" in saude

        # 2) segunda instância na MESMA porta falha rápido (fronteira do launcher)
        segunda = subprocess.run(
            comando, cwd=str(ROOT),
            capture_output=True, text=True, timeout=120,
        )
        assert segunda.returncode != 0, "segunda instância deveria falhar: porta ocupada"

        # 3) a primeira continua saudável depois do conflito
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/api/health", timeout=5
        ) as resposta:
            assert resposta.status == 200
    finally:
        servidor.terminate()
        try:
            servidor.wait(timeout=30)
        except subprocess.TimeoutExpired:
            servidor.kill()
            servidor.wait(timeout=15)

    # 4) porta liberada após o encerramento
    prazo = time.monotonic() + 30
    liberada = False
    while time.monotonic() < prazo:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
                sonda.bind(("127.0.0.1", porta))
            liberada = True
            break
        except OSError:
            time.sleep(1.0)
    assert liberada, "porta não foi liberada após o encerramento do servidor"


def test_atualizacoes_concorrentes_de_job_nao_se_perdem(monkeypatch, tmp_path):
    """LONG_PLAN P1 #8: 16 threads batendo em `_set` no mesmo job — nenhuma
    atualização pode se perder (o lock cobre o update) e o estado persistido
    na conclusão tem de ser JSON íntegro apesar do persist fora do lock."""
    from webapp import server

    job_id = "ab7700000001"
    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    with server._lock:
        server._jobs[job_id] = {"state": "running"}

    threads = 16
    chaves_por_thread = 50

    def martela(indice: int) -> None:
        for n in range(chaves_por_thread):
            server._set(job_id, **{f"t{indice}_k{n}": n})

    grupo = [threading.Thread(target=martela, args=(i,)) for i in range(threads)]
    for t in grupo:
        t.start()
    for t in grupo:
        t.join()

    with server._lock:
        atual = dict(server._jobs[job_id])
    esperadas = {f"t{i}_k{n}" for i in range(threads) for n in range(chaves_por_thread)}
    presentes = esperadas & set(atual)
    assert presentes == esperadas, (
        f"{len(esperadas) - len(presentes)} atualizações perdidas sob concorrência"
    )

    # corrida na conclusão: várias threads marcando done ao mesmo tempo
    def conclui(indice: int) -> None:
        server._set(job_id, state="done", quem_concluiu=indice)

    finalizadores = [threading.Thread(target=conclui, args=(i,)) for i in range(8)]
    for t in finalizadores:
        t.start()
    for t in finalizadores:
        t.join()

    persistido_path = server._completed_job_state_path(job_id)
    assert persistido_path.is_file(), "estado final não foi persistido"
    persistido = json.loads(persistido_path.read_text(encoding="utf-8"))
    # O persist usa uma ALLOWLIST sanitizada por design (state/step/progress/
    # result/...), não o dict inteiro — chaves internas arbitrárias ficam de
    # fora de propósito. O contrato observável: arquivo íntegro, schema
    # correto, estado done.
    assert persistido["schema"] == "oren-webapp-completed-job-v1"
    assert persistido["state"] == "done"
    assert persistido["job_id"] == job_id

    # TD-015 CORRIGIDO (PHASE_08): o persist agora reexecuta o replace sob
    # PermissionError (contenção WinError 5) e limpa o temporário em
    # try/finally. Sob contenção nenhum temporário pode sobrar.
    temporarios_vazados = list(persistido_path.parent.glob(".webapp_job_state.json.*.tmp"))
    assert temporarios_vazados == [], (
        f"temporários vazados sob contenção: {temporarios_vazados}"
    )

    with server._lock:
        server._jobs.pop(job_id, None)


def test_persist_reexecuta_replace_sob_permission_error_e_limpa_tmp(monkeypatch, tmp_path):
    """TD-015: falhas transitórias de replace (WinError 5) são reexecutadas e o
    temporário nunca sobra no disco."""
    from webapp import server

    job_id = "ab7700000004"
    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    original_replace = Path.replace
    falhas = {"restantes": 2}

    def replace_intermitente(self, target):
        if self.name.startswith(".webapp_job_state.json.") and falhas["restantes"] > 0:
            falhas["restantes"] -= 1
            raise PermissionError(13, "acesso negado (simulado)")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace_intermitente)
    caminho = server._persist_completed_job_state(job_id, {"state": "done"})
    assert json.loads(caminho.read_text(encoding="utf-8"))["state"] == "done"
    assert falhas["restantes"] == 0, "o retry não foi exercitado"
    assert list(caminho.parent.glob(".webapp_job_state.json.*.tmp")) == []


def test_persist_estoura_apos_esgotar_retries_sem_vazar_tmp(monkeypatch, tmp_path):
    """TD-015: contenção permanente continua estourando para o chamador (que
    loga), mas sem deixar temporário para trás."""
    from webapp import server

    job_id = "ab7700000005"
    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    monkeypatch.setattr(server.time, "sleep", lambda _s: None)
    original_replace = Path.replace

    def replace_sempre_nega(self, target):
        if self.name.startswith(".webapp_job_state.json."):
            raise PermissionError(13, "acesso negado (simulado)")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace_sempre_nega)
    with pytest.raises(PermissionError):
        server._persist_completed_job_state(job_id, {"state": "done"})
    destino = server._completed_job_state_path(job_id)
    assert list(destino.parent.glob(".webapp_job_state.json.*.tmp")) == []


def test_persistencia_do_estado_final_e_atomica_no_disco(monkeypatch, tmp_path):
    """A conclusão do job grava o snapshot em disco; o arquivo nunca pode ser
    lido pela metade — leitura repetida durante escritas sucessivas devolve
    sempre JSON completo e válido."""
    from webapp import server

    job_id = "ab7700000002"
    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    caminho = server._completed_job_state_path(job_id)

    parar = threading.Event()
    leituras_invalidas: list[str] = []

    def escreve() -> None:
        for rodada in range(200):
            with server._lock:
                server._jobs[job_id] = {"state": "running", "rodada": rodada}
            server._set(job_id, state="done", rodada=rodada)
        parar.set()

    def le() -> None:
        while not parar.is_set():
            if caminho.is_file():
                try:
                    json.loads(caminho.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    # conteúdo PARCIAL é violação do contrato de atomicidade
                    leituras_invalidas.append(f"{type(exc).__name__}: {exc}")
                except OSError:
                    # sharing violation transitória do Windows durante o
                    # os.replace: o arquivo não está corrompido, apenas
                    # momentaneamente indisponível — realidade da plataforma,
                    # não violação do contrato
                    continue

    escritor = threading.Thread(target=escreve)
    leitor = threading.Thread(target=le)
    leitor.start()
    escritor.start()
    escritor.join()
    leitor.join()

    assert not leituras_invalidas, (
        f"leitor observou estado parcial/corrompido: {leituras_invalidas[:3]}"
    )
    with server._lock:
        server._jobs.pop(job_id, None)
