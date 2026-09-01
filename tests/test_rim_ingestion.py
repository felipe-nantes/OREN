"""Testes do multi-órgão RIM-01 — perfis, roteamento órgão×modalidade, o
worker genérico process_organ_job (fase B) e o candidato de cisto renal
por união de lados (fase D).

Escopo v1 coberto: perfis rins.yaml/rins_ct.yaml parseiam e resolvem via a
tabela PROFILES; /api/analyze aceita organ=rins atrás de flag e recusa
campos figado-específicos (scenario, medgemma_backend, enhanced_3d, AUTO);
process_organ_job roda volumetria+3D SEM triagem/laudo/candidato — igual ao
D4 do CT-01, agora generalizado. O fluxo organ=figado (default) permanece
byte-idêntico — coberto pela bateria existente e por test_ct_ingestion.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydicom.uid import generate_uid

from dtwin.core import PipelineError, load_profile
from webapp import server

from .test_ct_ingestion import _dicom_sintetico

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Perfis + tabela órgão×modalidade
# ---------------------------------------------------------------------------

def test_perfis_rim_parseiam_com_uniao_de_dois_rotulos():
    for caminho, modalidades_esperadas, task, candidato_habilitado in (
        ("profiles/rins.yaml", ["MR", "MRI"], "total_mr", False),
        # fase D: TS tem kidney_cysts em CT (Dataset789); MR nao tem
        # equivalente, entao o candidato de RM segue desabilitado.
        ("profiles/rins_ct.yaml", ["CT"], "total", True),
    ):
        perfil = yaml.safe_load((ROOT / caminho).read_text(encoding="utf-8"))
        assert perfil["modalidade"] == modalidades_esperadas
        assert perfil["validado"] is False, "so vira true apos benchmark LOCAL (fase F)"
        assert perfil["segmentacao_orgao"]["rotulo_alvo"] == ["kidney_left", "kidney_right"]
        assert perfil["segmentacao_orgao"]["motor_task"] == task
        assert perfil["localizacao_candidata"]["habilitada"] is candidato_habilitado
        if candidato_habilitado:
            assert perfil["localizacao_candidata"]["motor_task"] == "kidney_cysts"
        # cada lado vira estrutura propria (volumetria por lado)
        estruturas = perfil["segmentacao_anatomia"]["tarefas"][0]["estruturas"]
        papeis = {e["papel"] for e in estruturas}
        assert papeis == {"rim_esquerdo", "rim_direito"}
    # load_profile (parser real, valida chaves obrigatorias) tambem aceita
    load_profile(ROOT / "profiles/rins.yaml")
    load_profile(ROOT / "profiles/rins_ct.yaml")


def test_profiles_table_cobre_os_quatro_pares_organo_modalidade():
    assert server.PROFILES[("figado", "MR")] == server.PROFILE
    assert server.PROFILES[("figado", "CT")] == "profiles/figado_ct.yaml"
    assert server.PROFILES[("rins", "MR")] == "profiles/rins.yaml"
    assert server.PROFILES[("rins", "CT")] == "profiles/rins_ct.yaml"
    assert server.ORGANS_SUPORTADOS == {"figado", "rins"}


def test_organ_profile_path_for_mapeia_e_recusa_desconhecida():
    assert server._organ_profile_path_for("rins", "mr") == "profiles/rins.yaml"
    assert server._organ_profile_path_for("RINS", "CT") == "profiles/rins_ct.yaml"
    assert server._organ_profile_path_for("figado", "MR") == server.PROFILE
    with pytest.raises(PipelineError, match="não suportada"):
        server._organ_profile_path_for("pulmao", "MR")
    with pytest.raises(PipelineError, match="não suportada"):
        server._organ_profile_path_for("rins", "US")


def test_profile_path_for_figado_permanece_intocado():
    """_profile_path_for (CT-01) segue byte-idêntico — RIM-01 não o reusa."""
    assert server._profile_path_for("MR") == server.PROFILE
    assert server._profile_path_for("ct") == "profiles/figado_ct.yaml"


# ---------------------------------------------------------------------------
# /api/analyze — roteamento por órgão
# ---------------------------------------------------------------------------

def test_analyze_organ_rins_sem_flag_e_recusado(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "KIDNEY_ENABLED", False)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"organ": "rins", "modality": "MR"},
    )
    assert resp.status_code == 409
    assert "rins" in resp.json()["detail"]


def test_analyze_organ_desconhecido_e_recusado(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
        data={"organ": "pulmao"},
    )
    assert resp.status_code == 400


def test_analyze_organ_rins_despacha_worker_dedicado_e_nunca_os_de_figado(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "KIDNEY_ENABLED", True)
    monkeypatch.setattr(server, "CT_ENABLED", True)
    chamados = {}
    monkeypatch.setattr(
        server, "process_organ_job", lambda job_id, raw: chamados.update(rim=job_id)
    )
    monkeypatch.setattr(
        server, "process_ct_job",
        lambda *a, **k: pytest.fail("worker de TC de fígado chamado para job de rim"),
    )
    monkeypatch.setattr(
        server, "process_visual_job",
        lambda *a, **k: pytest.fail("worker de RM de fígado chamado para job de rim"),
    )
    client = TestClient(server.app)
    for modalidade in ("MR", "CT"):
        resp = client.post(
            "/api/analyze",
            files=[("files", ("a.dcm", b"x", "application/dicom"))],
            data={"organ": "rins", "modality": modalidade},
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["organ"] == "rins"
        assert corpo["analysis_scenario"] == "organ_volumetric"
        import time as _t
        for _ in range(50):
            if chamados.get("rim") == corpo["job_id"]:
                break
            _t.sleep(0.05)
        assert chamados.get("rim") == corpo["job_id"]
        chamados.clear()


def test_analyze_organ_rins_recusa_campos_exclusivos_de_figado(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "KIDNEY_ENABLED", True)
    client = TestClient(server.app)
    base = {"organ": "rins", "modality": "MR"}
    casos = (
        {**base, "scenario": "hybrid_supervised"},
        {**base, "medgemma_backend": "algum"},
        {**base, "enhanced_3d": "1"},
        {"organ": "rins", "modality": "AUTO"},
    )
    for dados in casos:
        resp = client.post(
            "/api/analyze",
            files=[("files", ("a.dcm", b"x", "application/dicom"))],
            data=dados,
        )
        assert resp.status_code == 400, dados


def test_analyze_organ_default_figado_preserva_dispatch_legado(monkeypatch, tmp_path):
    """Sem o campo organ, o comportamento é EXATAMENTE o de antes do RIM-01."""
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    chamados = {}
    monkeypatch.setattr(
        server, "process_visual_job", lambda job_id, raw: chamados.update(mr=job_id)
    )
    monkeypatch.setattr(
        server, "process_organ_job",
        lambda *a, **k: pytest.fail("worker de rim chamado sem organ=rins"),
    )
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("a.dcm", b"x", "application/dicom"))],
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["organ"] == "figado"
    assert corpo["analysis_scenario"] == server.INDIVIDUAL_SCREENING_MODE


# ---------------------------------------------------------------------------
# process_organ_job — worker (mock do TotalSegmentator/finalize; sem GPU)
# ---------------------------------------------------------------------------

def _prepara_fluxo_organ(monkeypatch, tmp_path, job_id, organ, modality):
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
    if modality == "MR":
        monkeypatch.setattr(
            server, "find_best_series",
            lambda raw_dir: (["a.dcm", "b.dcm"], 2),
        )
    # Sentinelas: nenhum classificador/triagem/laudo/candidato roda p/ rim.
    monkeypatch.setattr(
        server, "_run", lambda *a, **k: pytest.fail("subprocesso inesperado em job de orgao")
    )
    monkeypatch.setattr(
        server, "load_screening_config",
        lambda *a, **k: pytest.fail("config de triagem lida em job de orgao"),
    )
    monkeypatch.setattr(
        server, "process_job", lambda *a, **k: pytest.fail("process_job chamado em job de orgao")
    )
    monkeypatch.setattr(
        server, "process_monophase_medsiglip_job",
        lambda *a, **k: pytest.fail("monofasico chamado em job de orgao"),
    )
    monkeypatch.setattr(
        server, "_run_delayed_medsiglip_advisory",
        lambda *a, **k: pytest.fail("advisory chamado em job de orgao"),
    )
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5, "result": None,
        "analysis_scenario": "organ_volumetric", "modality": modality, "organ": organ,
    }
    return perfis_usados


def test_process_organ_job_rins_mr_sem_triagem_com_perfil_correto(monkeypatch, tmp_path):
    job_id = "r1000000000a"
    raw = tmp_path / job_id / "_upload"
    raw.mkdir(parents=True)
    arquivos_mr = [raw / "a.dcm", raw / "b.dcm"]
    for arquivo in arquivos_mr:
        arquivo.write_bytes(b"x")
    perfis = _prepara_fluxo_organ(monkeypatch, tmp_path, job_id, "rins", "MR")
    monkeypatch.setattr(
        server, "find_best_series",
        lambda raw_dir: ([str(p) for p in arquivos_mr], 2),
    )

    server.process_organ_job(job_id, raw)

    job = server._jobs[job_id]
    assert job["state"] == "done", job.get("result")
    result = job["result"]
    assert result["status"] == "concluido"
    assert result["analysis_scenario"] == "organ_volumetric"
    assert result["organ"] == "rins"
    assert result["modality"] == "MR"
    assert result["screening_available"] is False
    assert result["prediction"] is None
    assert result["candidate_localization"] is None
    assert result["viewer_ready"] is True
    assert result["requires_human_review"] is True
    assert job["approval"] == {"status": "pending"}
    assert perfis["segment"] == "profiles/rins.yaml"
    assert perfis["model"] == "profiles/rins.yaml"


def test_process_organ_job_rins_ct_usa_perfil_ct_e_chama_candidato_de_cisto(
    monkeypatch, tmp_path
):
    """rins_ct.yaml tem localizacao_candidata.habilitada=true desde a fase
    D — process_organ_job precisa chamar _localize_candidate_ct (mesma
    função organ-agnóstica do CT-01/CT-03) e anexar o resultado ao payload."""
    from webapp import jobs as jobs_mod

    job_id = "r2000000000b"
    perfis = _prepara_fluxo_organ(monkeypatch, tmp_path, job_id, "rins", "CT")
    chamadas = {}

    def fake_localize(case_dir, profile_rel):
        chamadas["profile"] = profile_rel
        return {"schema": "argos-candidate-region-v1", "status": "pending_human_review",
                "candidate_present": True, "task": "kidney_cysts",
                "total_candidate_volume_mm3": 456.7,
                "used_by_screening_inference": False, "requires_human_review": True}

    monkeypatch.setattr(jobs_mod, "_localize_candidate_ct", fake_localize)
    raw = tmp_path / job_id / "_upload"
    uid = generate_uid()
    for i in range(2):
        _dicom_sintetico(raw / f"ct_{i}.dcm", "CT", uid)

    server.process_organ_job(job_id, raw)

    job = server._jobs[job_id]
    assert job["state"] == "done", job.get("result")
    result = job["result"]
    assert result["modality"] == "CT"
    assert result["organ"] == "rins"
    assert result["candidate_localization"]["candidate_present"] is True
    assert result["candidate_localization"]["task"] == "kidney_cysts"
    assert chamadas["profile"] == "profiles/rins_ct.yaml"
    assert perfis["segment"] == "profiles/rins_ct.yaml"
    assert perfis["model"] == "profiles/rins_ct.yaml"


def test_process_organ_job_serie_ausente_falha_graciosamente(monkeypatch, tmp_path):
    job_id = "r3000000000c"
    _prepara_fluxo_organ(monkeypatch, tmp_path, job_id, "rins", "CT")
    raw = tmp_path / job_id / "_upload"
    raw.mkdir(parents=True)  # sem nenhum DICOM de TC

    server.process_organ_job(job_id, raw)

    result = server._jobs[job_id]["result"]
    assert result["status"] != "concluido"
    assert "requer" not in result  # sanity: shape gracioso, não exceção crua


# ---------------------------------------------------------------------------
# Fase D — candidato de cisto renal: união dos dois lados (kidney_cysts)
# ---------------------------------------------------------------------------

def test_generate_candidate_region_kidney_cysts_uniao_dos_dois_lados(
    synthetic_case, tmp_path, monkeypatch
):
    """kidney_cysts produz DOIS arquivos (um por lado); generate_candidate_region
    precisa unir os dois antes de validar — mesmo contrato do fígado (uma
    máscara), mas construído a partir de duas saídas do TotalSegmentator."""
    import numpy as np
    import SimpleITK as sitk

    from dtwin.candidate_region import generate_candidate_region
    from dtwin.core import array_to_image, read_image, save_image
    from tests.conftest import make_sphere_mask

    ref = read_image(synthetic_case.volume)
    shape = sitk.GetArrayFromImage(ref).shape
    # órgão sintético = esfera raio 12 em (20,20,20) (fixture synthetic_case);
    # as duas "lesões" precisam caber DENTRO do órgão para isolar a união do
    # clipe (que já é testado à parte) — deslocadas só no eixo Z, disjuntas.
    left = make_sphere_mask(shape, (20, 20, 14), 3)
    right = make_sphere_mask(shape, (20, 20, 26), 3)
    assert not (left & right).any()  # esferas disjuntas: prova a união real

    def fake_totalsegmentator(*, input, output, task, **kwargs):
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        save_image(array_to_image(left.astype(np.uint8), ref, np.uint8),
                  out / "kidney_cyst_left.nii.gz")
        save_image(array_to_image(right.astype(np.uint8), ref, np.uint8),
                  out / "kidney_cyst_right.nii.gz")

    monkeypatch.setattr(
        "totalsegmentator.python_api.totalsegmentator", fake_totalsegmentator
    )
    request_path = synthetic_case.root / "candidate_request.json"
    request_path.write_text(json.dumps({
        "schema": "argos-candidate-request-v1", "task": "kidney_cysts",
    }), encoding="utf-8")

    resultado = generate_candidate_region(
        synthetic_case.root, device="cpu", request_path=request_path
    )

    assert resultado["task"] == "kidney_cysts"
    assert resultado["candidate_present"] is True
    assert resultado["component_count"] == 2  # um componente por lado
    esperado_voxels = int(left.sum() + right.sum())
    # clip na máscara do órgão (esfera maior, cobre as duas): nada é cortado
    assert resultado["candidate_voxels_inside_liver"] == esperado_voxels


def test_generate_candidate_region_kidney_cysts_falta_um_lado_aborta(
    synthetic_case, tmp_path, monkeypatch
):
    import numpy as np
    import SimpleITK as sitk

    from dtwin.candidate_region import generate_candidate_region
    from dtwin.core import PipelineError, array_to_image, read_image, save_image
    from tests.conftest import make_sphere_mask

    ref = read_image(synthetic_case.volume)
    shape = sitk.GetArrayFromImage(ref).shape
    left = make_sphere_mask(shape, (12, 12, 12), 3)

    def fake_totalsegmentator(*, input, output, task, **kwargs):
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        save_image(array_to_image(left.astype(np.uint8), ref, np.uint8),
                  out / "kidney_cyst_left.nii.gz")
        # kidney_cyst_right.nii.gz deliberadamente não escrito

    monkeypatch.setattr(
        "totalsegmentator.python_api.totalsegmentator", fake_totalsegmentator
    )
    request_path = synthetic_case.root / "candidate_request.json"
    request_path.write_text(json.dumps({
        "schema": "argos-candidate-request-v1", "task": "kidney_cysts",
    }), encoding="utf-8")

    with pytest.raises(PipelineError, match="kidney_cyst_right"):
        generate_candidate_region(
            synthetic_case.root, device="cpu", request_path=request_path
        )
