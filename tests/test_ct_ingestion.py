"""Testes da ingestão de TC (CT-01) — perfil, gates, roteamento e fluxo.

Cobrem as decisões do plano CT-01: perfil por modalidade (D1/D2), série única
(D3), AUSÊNCIA de triagem visual em TC (D4 — teste negativo), aviso de
calibração com proveniência (D5) e flag de operador (D8). O fluxo de RM tem
que permanecer byte-idêntico — coberto pela bateria existente.
"""
from __future__ import annotations

from pathlib import Path

import pydicom
import pytest
import yaml
from fastapi.testclient import TestClient
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dtwin.core import PipelineError
from webapp import server

ROOT = Path(__file__).resolve().parents[1]


def _dicom_sintetico(path: Path, modality: str, series_uid: str) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = generate_uid()
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality = modality
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(str(path), ds)


# ---------------------------------------------------------------------------
# D1 — perfil
# ---------------------------------------------------------------------------

def test_perfil_ct_parseia_com_os_campos_do_plano():
    perfil = yaml.safe_load((ROOT / "profiles/figado_ct.yaml").read_text(encoding="utf-8"))
    assert perfil["modalidade"] == ["CT"]
    assert perfil["estado_regulatorio"] == "PESQUISA"
    assert perfil["validado"] is False, "so vira true apos benchmark LOCAL (CT-01-F)"
    assert perfil["segmentacao_orgao"]["motor_task"] == "total"
    assert perfil["segmentacao_orgao"]["rotulo_alvo"] == "liver"
    tarefas = perfil["segmentacao_anatomia"]["tarefas"]
    assert tarefas[0]["motor_task"] == "liver_segments"
    assert tarefas[0]["require_complete"] is True, "Couinaud CT degrada fail-closed"
    # D7: localizacao de candidato DESABILITADA (task CT sem nome confirmado)
    assert perfil["localizacao_candidata"]["habilitada"] is False


def test_perfil_mr_permanece_intocado_como_default():
    assert server.MODALITY_PROFILES["MR"] == server.PROFILE
    perfil = yaml.safe_load((ROOT / server.PROFILE).read_text(encoding="utf-8"))
    assert perfil["modalidade"] == ["MR", "MRI"]


# ---------------------------------------------------------------------------
# D2 — mapeamento de perfil
# ---------------------------------------------------------------------------

def test_profile_path_for_mapeia_e_recusa_desconhecida():
    assert server._profile_path_for("MR") == server.PROFILE
    assert server._profile_path_for("ct") == "profiles/figado_ct.yaml"
    with pytest.raises(PipelineError, match="não suportada"):
        server._profile_path_for("US")


# ---------------------------------------------------------------------------
# D5 — aviso de calibração
# ---------------------------------------------------------------------------

def test_aviso_volumetria_ct_tem_proveniencia_e_nunca_corrige():
    nota = server._aviso_volumetria_ct()
    assert nota["correcao_aplicada"] is False
    assert nota["replicada_neste_repositorio"] is False
    assert nota["origem"] == "volyrics_docs_249_250_n40"
    assert nota["research_only"] is True and nota["clinical_use_allowed"] is False
    assert "não replicada neste repositório" in nota["mensagem"]


# ---------------------------------------------------------------------------
# D8 — flag de operador + rota
# ---------------------------------------------------------------------------

def test_analyze_ct_sem_flag_e_recusado(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "CT_ENABLED", False)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"modality": "CT"},
    )
    assert resp.status_code == 409
    assert "WEBAPP_CT_ENABLED" in resp.json()["detail"]


def test_analyze_ct_despacha_worker_ct_e_nunca_o_de_rm(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "CT_ENABLED", True)
    chamados = {}
    monkeypatch.setattr(
        server, "process_ct_job", lambda job_id, raw: chamados.update(ct=job_id)
    )
    monkeypatch.setattr(
        server, "process_visual_job",
        lambda *a, **k: pytest.fail("worker de RM chamado para job de TC"),
    )
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"modality": "CT"},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["analysis_scenario"] == "ct_volumetric"
    assert corpo["modality"] == "CT"
    import time as _t
    for _ in range(50):
        if chamados.get("ct"):
            break
        _t.sleep(0.05)
    assert chamados.get("ct") == corpo["job_id"]


def test_analyze_ct_recusa_cenario_explicito_e_3d_aprimorado(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "CT_ENABLED", True)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"modality": "CT", "scenario": "hybrid_supervised"},
    )
    assert resp.status_code == 400
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"modality": "CT", "enhanced_3d": "1"},
    )
    assert resp.status_code == 400
    assert "RM" in resp.json()["detail"]


def test_analyze_sem_modalidade_segue_rm_como_sempre(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    chamados = {}
    monkeypatch.setattr(
        server, "process_visual_job", lambda job_id, raw: chamados.update(mr=job_id)
    )
    monkeypatch.setattr(
        server, "process_ct_job",
        lambda *a, **k: pytest.fail("worker de TC chamado sem seleção de TC"),
    )
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
    )
    assert resp.status_code == 200
    assert resp.json()["analysis_scenario"] == server.INDIVIDUAL_SCREENING_MODE
    assert resp.json()["modality"] == "MR"


def test_health_expoe_ct_enabled(monkeypatch):
    monkeypatch.setattr(server, "CT_ENABLED", True)
    client = TestClient(server.app)
    assert client.get("/api/health").json()["ct_enabled"] is True


def test_modalidade_desconhecida_e_recusada(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"modality": "US"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# D3 — seleção de série CT
# ---------------------------------------------------------------------------

def test_select_ct_series_pega_a_maior_serie_ct_e_ignora_rm(tmp_path):
    from webapp.jobs import _select_ct_series

    uid_a, uid_b, uid_mr = generate_uid(), generate_uid(), generate_uid()
    for i in range(3):
        _dicom_sintetico(tmp_path / f"ct_a_{i}.dcm", "CT", uid_a)
    for i in range(5):
        _dicom_sintetico(tmp_path / f"ct_b_{i}.dcm", "CT", uid_b)
    for i in range(9):
        _dicom_sintetico(tmp_path / f"mr_{i}.dcm", "MR", uid_mr)
    arquivos, n = _select_ct_series(tmp_path)
    assert n == 5
    assert all("ct_b_" in a for a in arquivos)


def test_select_ct_series_sem_ct_devolve_vazio(tmp_path):
    from webapp.jobs import _select_ct_series

    _dicom_sintetico(tmp_path / "mr_0.dcm", "MR", generate_uid())
    arquivos, n = _select_ct_series(tmp_path)
    assert (arquivos, n) == ([], 0)


# ---------------------------------------------------------------------------
# D4 — fluxo CT completo SEM triagem (teste negativo central do plano)
# ---------------------------------------------------------------------------

def _prepara_fluxo_ct(monkeypatch, tmp_path, job_id):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "MIN_SLICES", 1)
    perfis_usados = {}

    def fake_segment(series_dir, case_dir, device, timeout, *, fast, profile_rel=None):
        perfis_usados["segment"] = profile_rel
        Path(case_dir).mkdir(parents=True, exist_ok=True)
        import subprocess
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(server, "_segment", fake_segment)
    monkeypatch.setattr(server, "_seg_done", lambda case_dir: True)
    monkeypatch.setattr(server, "_persist_series_selection", lambda *a, **k: None)

    def fake_build_model(case_dir, profile_rel=None):
        perfis_usados["model"] = profile_rel
        return True, ""

    monkeypatch.setattr(server, "_build_model", fake_build_model)
    # Sentinelas: QUALQUER toque na superfície de triagem falha o teste.
    monkeypatch.setattr(
        server, "_run", lambda *a, **k: pytest.fail("subprocesso inesperado em job CT")
    )
    monkeypatch.setattr(
        server, "load_screening_config",
        lambda *a, **k: pytest.fail("config de triagem lida em job CT"),
    )
    monkeypatch.setattr(
        server, "process_job", lambda *a, **k: pytest.fail("process_job chamado em job CT")
    )
    monkeypatch.setattr(
        server, "process_monophase_medsiglip_job",
        lambda *a, **k: pytest.fail("monofasico chamado em job CT"),
    )
    monkeypatch.setattr(
        server, "_run_delayed_medsiglip_advisory",
        lambda *a, **k: pytest.fail("advisory chamado em job CT"),
    )
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5, "result": None,
        "analysis_scenario": "ct_volumetric", "modality": "CT",
    }
    return perfis_usados


def test_fluxo_ct_completo_sem_triagem_com_perfil_ct(monkeypatch, tmp_path):
    job_id = "c1000000000a"
    perfis = _prepara_fluxo_ct(monkeypatch, tmp_path, job_id)
    raw = tmp_path / job_id / "_upload"
    uid = generate_uid()
    for i in range(2):
        _dicom_sintetico(raw / f"ct_{i}.dcm", "CT", uid)

    server.process_ct_job(job_id, raw)

    job = server._jobs[job_id]
    assert job["state"] == "done"
    result = job["result"]
    assert result["status"] == "concluido"
    assert result["analysis_scenario"] == "ct_volumetric"
    assert result["screening_available"] is False
    assert result["prediction"] is None
    assert "RM" in result["screening_unavailable_reason"]
    assert result["viewer_ready"] is True
    assert result["requires_human_review"] is True
    assert result["volumetry_note"]["correcao_aplicada"] is False
    assert job["approval"] == {"status": "pending"}
    # o perfil CT viajou até a segmentação E até o finalize
    assert perfis["segment"] == "profiles/figado_ct.yaml"
    assert perfis["model"] == "profiles/figado_ct.yaml"


def test_fluxo_ct_com_upload_de_rm_falha_gracioso(monkeypatch, tmp_path):
    job_id = "c2000000000b"
    _prepara_fluxo_ct(monkeypatch, tmp_path, job_id)
    raw = tmp_path / job_id / "_upload"
    _dicom_sintetico(raw / "mr_0.dcm", "MR", generate_uid())

    server.process_ct_job(job_id, raw)

    job = server._jobs[job_id]
    assert job["state"] == "done"
    assert job["result"]["status"] == "nao_concluido"
    assert "TC" in job["result"]["motivo"]
