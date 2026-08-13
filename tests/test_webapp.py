import hashlib
import shutil
from pathlib import Path
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from dtwin.core import PipelineError
from webapp import server


def test_graceful_payload_shape():
    g = server._graceful("motivo", "detalhe")
    assert g["status"] == "nao_concluido"
    assert g["requires_human_review"] is True
    assert "pesquisa" in g["disclaimer"].lower()
    # nunca contém um estado clínico fabricado
    assert "resultado_hipotese" not in g


def test_friendly_messages_are_human_and_nonclinical():
    assert "MedGemma" in server._friendly(PipelineError("MedGemma backend not configured. Aborting analysis."))
    assert "fígado" in server._friendly(PipelineError("Falha na segmentação automática (total_mr/liver): x"))
    assert "RM" in server._friendly(PipelineError("Modalidade do exame (CT) não bate com o perfil"))
    assert "segurança" in server._friendly(PipelineError("Resposta MedGemma contém diagnóstico definitivo"))
    # fallback genérico
    assert server._friendly(PipelineError("algo aleatório")) == "Não foi possível concluir a análise deste exame."


def test_find_best_series_empty_when_no_dicom(tmp_path):
    (tmp_path / "leia.txt").write_text("nao é dicom")
    files, n = server.find_best_series(tmp_path)
    assert files == [] and n == 0


def test_find_best_series_prefers_profile_modality(tmp_path):
    # Envio misto CT+MR (dataset CHAOS): a série CT é MAIOR, mas o perfil do fígado
    # é MR — find_best_series deve escolher a série MR, não a CT (regressão do bug
    # "Modalidade (CT) não bate" que dava ANÁLISE NÃO CONCLUÍDA).
    import numpy as np

    from tools.make_synthetic_case import write_dicom_series

    write_dicom_series(tmp_path / "ct", np.random.default_rng(0).integers(0, 200, (8, 16, 16)), modality="CT")
    write_dicom_series(tmp_path / "mr", np.random.default_rng(1).integers(0, 200, (5, 16, 16)), modality="MR")
    files, n = server.find_best_series(tmp_path)
    assert n == 5, f"deveria pegar a série MR (5 cortes), não a CT (8); pegou {n}"
    assert server._modality_of(files) == "MR"


def test_find_best_series_empty_when_only_incompatible_modality(tmp_path):
    # Só CT no envio, perfil é MR -> nenhuma série compatível -> vazio (mensagem
    # honesta "não encontramos série de RM", em vez de abortar fundo no stage1).
    import numpy as np

    from tools.make_synthetic_case import write_dicom_series

    write_dicom_series(tmp_path / "ct", np.random.default_rng(2).integers(0, 200, (6, 16, 16)), modality="CT")
    files, n = server.find_best_series(tmp_path)
    assert files == [] and n == 0


def test_series_selection_metadata_is_sanitized(tmp_path):
    import json
    import numpy as np

    from tools.make_synthetic_case import write_dicom_series

    source = tmp_path / "patient-secret" / "mr"
    write_dicom_series(
        source,
        np.random.default_rng(3).integers(0, 200, (5, 16, 16)),
        modality="MR",
    )
    files, _ = server.find_best_series(tmp_path)
    case_dir = tmp_path / "case"

    saved = server._persist_series_selection(case_dir, files)
    payload = json.loads(saved.read_text("utf-8"))
    serialized = saved.read_text("utf-8")

    assert payload["schema"] == "argos-series-selection-v1"
    assert payload["raw_paths_persisted"] is False
    assert payload["raw_uids_persisted"] is False
    assert "patient-secret" not in serialized
    assert str(tmp_path) not in serialized


def test_load_report_accepts_valid_report_regardless_of_returncode(tmp_path):
    # relatório válido no disco = sucesso, mesmo que o subprocesso tenha crashado no shutdown
    import json
    rp = tmp_path / "medgemma_report.json"
    rp.write_text(json.dumps({"report": {"resultado_hipotese": "NEGATIVA"}, "status": "pending_review"}), "utf-8")
    data = server._load_report(rp)
    assert data is not None and data["report"]["resultado_hipotese"] == "NEGATIVA"


def test_load_report_rejects_missing_or_incomplete(tmp_path):
    import json
    assert server._load_report(tmp_path / "ausente.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"status": "x"}), "utf-8")  # sem report.resultado_hipotese
    assert server._load_report(bad) is None


def test_screening_diagnostics_are_sanitized_and_persisted(tmp_path):
    import json
    import subprocess

    case_dir = tmp_path / "case-001"
    proc = subprocess.CompletedProcess(
        args=["screening"], returncode=2,
        stdout=f"[ABORTADO] falha em {case_dir.resolve()}",
        stderr=f"trace em {server.REPO.resolve()}",
    )
    paths = server._persist_screening_diagnostics(case_dir, proc)
    output = case_dir / "outputs" / "medgemma"
    assert (case_dir / paths["stdout"]).is_file()
    assert (case_dir / paths["stderr"]).is_file()
    assert (case_dir / paths["metadata"]).is_file()
    assert str(case_dir.resolve()) not in (output / "screening_subprocess.stdout.log").read_text("utf-8")
    metadata = json.loads((output / "screening_subprocess.json").read_text("utf-8"))
    assert metadata["returncode"] == 2
    assert metadata["reason"].startswith("falha em [CASE_DIR]")


def test_success_status_overrides_report_envelope_status():
    # o envelope tem status='pending_review'; o frontend detecta sucesso por
    # status=='concluido', então o marcador de conclusão deve prevalecer.
    envelope = {"status": "pending_review", "report": {"resultado_hipotese": "NEGATIVA"},
                "model_version": "MedGemma 1.5 4B Instruction-Tuned", "disclaimer": "..."}
    result = server._success_result(envelope)
    assert result["status"] == "concluido"
    assert result["report"]["resultado_hipotese"] == "NEGATIVA"
    assert result["model_version"].startswith("MedGemma")


def test_viewer_result_exposes_review_url_only_when_model_is_ready():
    report = {"report": {"resultado_hipotese": "NEGATIVA"}}
    ready = server._viewer_result(report, "abc123", True)
    assert ready["viewer_ready"] is True
    assert ready["viewer_url"].endswith("&job=abc123")
    assert ready["approval"] == {"status": "pending"}
    unavailable = server._viewer_result(report, "abc123", False)
    assert unavailable["viewer_url"] is None


def test_model_endpoints_and_manual_approval(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "abc123"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    stl = outputs / "figado_orgao.stl"
    stl.write_bytes(b"solid liver\nendsolid liver\n")
    (outputs / "viewer_manifest.json").write_text(
        json.dumps({"meshes": [{"role": "orgao", "stl": stl.name, "color": "#ffffff"}]}),
        "utf-8",
    )
    server._jobs[job_id] = {
        "state": "done", "step": "concluido", "progress": 100,
        "result": {}, "approval": {"status": "pending"},
    }
    client = TestClient(server.app)
    assert client.get(f"/api/jobs/{job_id}/model/viewer_manifest.json").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/model/{stl.name}").content == stl.read_bytes()
    response = client.post(f"/api/jobs/{job_id}/approval", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    saved = json.loads((outputs / "approval.json").read_text("utf-8"))
    assert saved["review_type"] == "human_visual_review"


def test_rgb_panel_catalog_only_serves_authorized_case_panels(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "ab1234"
    case_dir = tmp_path / job_id / "case"
    panels = case_dir / "panels"
    outputs = case_dir / "outputs"
    panels.mkdir(parents=True)
    outputs.mkdir(parents=True)
    (outputs / "viewer_manifest.json").write_text(json.dumps({"meshes": []}), "utf-8")
    first = panels / "medgemma_liver_screening_panel_001_of_002.png"
    second = panels / "medgemma_liver_screening_panel_002_of_002.png"
    first.write_bytes(b"png-one")
    second.write_bytes(b"png-two")
    (panels / "private.png").write_bytes(b"not-authorized")

    client = TestClient(server.app)
    catalog = client.get(f"/api/jobs/{job_id}/rgb-panels")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["schema"] == "oren-rgb-panel-catalog-v1"
    assert payload["count"] == 2
    assert [item["filename"] for item in payload["panels"]] == [first.name, second.name]
    assert client.get(payload["panels"][0]["url"]).content == b"png-one"
    assert client.get(f"/api/jobs/{job_id}/rgb-panels/private.png").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/rgb-panels/../outputs/viewer_manifest.json").status_code == 404


def test_xr_session_is_short_lived_role_scoped_and_restart_resilient(monkeypatch, tmp_path):
    import json

    from dtwin.core import sha256_of

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "a1b2c3"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    stl = outputs / "figado_orgao.stl"
    stl.write_bytes(b"solid liver\nendsolid liver\n")
    manifest = {
        "meshes": [{
            "role": "orgao", "stl": stl.name, "color": "#ffffff",
            "metrics": {"mesh_sha256": sha256_of(stl)},
        }]
    }
    (outputs / "viewer_manifest.json").write_text(json.dumps(manifest), "utf-8")
    client = TestClient(server.app, base_url="http://192.168.15.8:8082")

    patient = client.post(
        f"/api/jobs/{job_id}/xr-session", json={"role": "patient", "ttl_minutes": 15}
    )
    assert patient.status_code == 200
    patient_url = patient.json()["viewer_url"]
    assert patient_url.startswith("http://192.168.15.8:8082/viewer/index.html?")
    patient_token = patient_url.split("#xr_token=", 1)[1]
    assert patient_token not in list((outputs / "xr_sessions").iterdir())[0].name
    assert client.get(f"/api/jobs/{job_id}/xr-session/{patient_token}").json()["role"] == "patient"
    assert client.post(
        f"/api/jobs/{job_id}/xr-session/{patient_token}/approval",
        json={"status": "revision_requested"},
    ).status_code == 403

    clinician = client.post(
        f"/api/jobs/{job_id}/xr-session", json={"role": "clinician"}
    )
    clinician_token = clinician.json()["viewer_url"].split("#xr_token=", 1)[1]
    server._jobs.pop(job_id, None)  # simula processo HTTPS reiniciado
    approved = client.post(
        f"/api/jobs/{job_id}/xr-session/{clinician_token}/approval",
        json={"status": "revision_requested"},
    )
    assert approved.status_code == 200
    assert approved.json()["xr_session"]["role"] == "clinician"
    saved = json.loads((outputs / "approval.json").read_text("utf-8"))
    assert saved["xr_session"]["schema"] == "oren-xr-session-v1"


def test_xr_client_event_accepts_only_bounded_diagnostic_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    case_dir = tmp_path / "ab12cd" / "case"
    case_dir.mkdir(parents=True)
    client = TestClient(server.app)

    accepted = client.post(
        "/api/jobs/ab12cd/xr-client-event",
        json={
            "event": "session_failed",
            "mode": "immersive-ar",
            "error_name": "InvalidStateError",
            "message": "XR session could not start",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"accepted": True}
    assert client.post(
        "/api/jobs/ab12cd/xr-client-event",
        json={"event": "arbitrary_event", "mode": "immersive-ar"},
    ).status_code == 422


def test_viewer_allowlist_includes_hash_protected_xr_lod(tmp_path):
    from dtwin.core import sha256_of

    source = tmp_path / "organ.stl"
    lod = tmp_path / "organ_xr_lod1.stl"
    source.write_bytes(b"source")
    lod.write_bytes(b"lod")
    manifest = {"meshes": [{
        "role": "orgao", "stl": source.name,
        "metrics": {"mesh_sha256": sha256_of(source)},
        "xr_asset": {"stl": lod.name, "sha256": sha256_of(lod)},
    }]}
    assets = server._viewer_assets(manifest)
    assert assets[lod.name]["sha256"] == sha256_of(lod)


def test_viewer_v2_checks_assets_and_requires_auditable_review(monkeypatch, tmp_path):
    import json

    from dtwin.core import sha256_of

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "def456"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    stl = outputs / "figado_orgao.stl"
    png = outputs / "mri_reference_axial_001_of_001.png"
    stl.write_bytes(b"solid liver\nendsolid liver\n")
    png.write_bytes(b"not-a-real-png-but-hash-protected")
    manifest = {
        "schema": "argos-viewer-manifest-v2",
        "meshes": [{
            "role": "orgao",
            "stl": stl.name,
            "color": "#ffffff",
            "metrics": {"mesh_sha256": sha256_of(stl)},
        }],
        "reference_images": {"views": {"axial": {"frames": [{
            "file": png.name,
            "sha256": sha256_of(png),
            "index": 0,
        }]}}},
        "review_requirements": {
            "inspect_3d_contour": True,
            "inspect_2d_reference": True,
            "acknowledge_research_only": True,
        },
    }
    (outputs / "viewer_manifest.json").write_text(json.dumps(manifest), "utf-8")
    server._jobs[job_id] = {
        "state": "done", "step": "concluido", "progress": 100,
        "result": {}, "approval": {"status": "pending"},
    }
    client = TestClient(server.app)

    assert server._model_done(tmp_path / job_id / "case") is True
    image_response = client.get(f"/api/jobs/{job_id}/model/{png.name}")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/png")
    assert client.post(
        f"/api/jobs/{job_id}/approval", json={"status": "approved"}
    ).status_code == 422

    response = client.post(
        f"/api/jobs/{job_id}/approval",
        json={
            "status": "approved",
            "checklist": {
                "inspected_3d_contour": True,
                "compared_2d_reference": True,
                "acknowledged_research_only": True,
            },
            "viewer_state": {
                "active_view": "anterior",
                "active_preset": "anatomy",
                "active_anatomical_view": "vascular",
                "wireframe_enabled": True,
                "reference_sync_enabled": True,
                "reference_view": "axial",
                "reference_frame_index": 7,
                "selected_role": "orgao",
                "selection_isolated": True,
                "saved_views": [{
                    "bookmark_id": "view-001",
                    "label": "Vista 1 · Fígado",
                    "active_view": "anatomical",
                    "active_preset": "default",
                    "active_anatomical_view": "liver",
                    "material_profile": "default",
                    "selected_role": "orgao",
                    "selection_isolated": False,
                    "camera_position_mm": [10.0, 20.0, 30.0],
                    "camera_target_mm": [0.0, 0.0, 0.0],
                    "reference_sync_enabled": True,
                    "reference_view": "axial",
                    "reference_frame_index": 7,
                    "clipping": {
                        "enabled": False, "axis": "z",
                        "position_percent": 50, "inverted": False,
                    },
                    "visible_roles": ["orgao"],
                    "opacity_by_role": {"orgao": 1.0},
                }],
                "compared_saved_view_ids": ["view-001"],
                "clipping": {
                    "enabled": True, "axis": "z",
                    "position_percent": 42, "inverted": False,
                },
                "measurements_mm": [12.5],
                "structure_dimensions_3d": [{
                    "role": "orgao",
                    "label": "Fígado",
                    "left_right_mm": 145.2,
                    "anterior_posterior_mm": 88.4,
                    "superior_inferior_mm": 120.1,
                    "method": "axis_aligned_lps_bounding_box",
                    "coordinate_system": "LPS",
                    "source": "selected_segmentation_mesh",
                    "approximate": True,
                }],
                "visible_roles": ["orgao"],
            },
        },
    )
    assert response.status_code == 200
    saved = json.loads((outputs / "approval.json").read_text("utf-8"))
    assert saved["review_protocol"] == "argos-viewer-review-v2"
    assert saved["checklist"]["compared_2d_reference"] is True
    assert saved["viewer_state"]["measurements_mm"] == [12.5]
    assert saved["viewer_state"]["structure_dimensions_3d"][0]["anterior_posterior_mm"] == 88.4
    assert saved["viewer_state"]["active_preset"] == "anatomy"
    assert saved["viewer_state"]["reference_sync_enabled"] is True
    assert saved["viewer_state"]["reference_view"] == "axial"
    assert saved["viewer_state"]["reference_frame_index"] == 7
    assert saved["viewer_state"]["selected_role"] == "orgao"
    assert saved["viewer_state"]["selection_isolated"] is True
    assert saved["viewer_state"]["active_anatomical_view"] == "vascular"
    assert saved["viewer_state"]["saved_views"][0]["bookmark_id"] == "view-001"
    assert saved["viewer_state"]["compared_saved_view_ids"] == ["view-001"]
    assert saved["viewer_manifest_sha256"] == sha256_of(outputs / "viewer_manifest.json")
    assert saved["artifact_hashes"][png.name] == sha256_of(png)

    png.write_bytes(b"tampered")
    assert server._model_done(tmp_path / job_id / "case") is False
    assert client.get(f"/api/jobs/{job_id}/model/{png.name}").status_code == 409


def test_candidate_review_requires_mr_comparison_and_explicit_roi_decision(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "cab123"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    stl = outputs / "figado_candidato.stl"
    stl.write_bytes(b"solid candidate\nendsolid candidate\n")
    manifest = {
        "meshes": [{"role": "candidato", "stl": stl.name, "color": "#ff8400"}],
        "candidate_region": {
            "schema": "argos-candidate-region-v1",
            "candidate_present": True,
            "candidate_is_diagnosis": False,
        },
        "review_requirements": {
            "inspect_candidate_against_mr": True,
            "acknowledge_research_only": True,
        },
    }
    (outputs / "viewer_manifest.json").write_text(json.dumps(manifest), "utf-8")
    server._jobs[job_id] = {"state": "done", "result": {}, "approval": {"status": "pending"}}
    client = TestClient(server.app)

    incomplete = client.post(
        f"/api/jobs/{job_id}/approval",
        json={
            "status": "approved",
            "checklist": {"acknowledged_research_only": True},
        },
    )
    assert incomplete.status_code == 422

    accepted = client.post(
        f"/api/jobs/{job_id}/approval",
        json={
            "status": "approved",
            "candidate_review_decision": "accepted_as_region_of_interest",
            "checklist": {
                "reviewed_candidate_against_mr": True,
                "acknowledged_research_only": True,
            },
        },
    )
    assert accepted.status_code == 200
    saved = json.loads((outputs / "approval.json").read_text("utf-8"))
    assert saved["candidate_review_decision"] == "accepted_as_region_of_interest"
    assert saved["candidate_review_scope"].endswith("not_diagnostic_confirmation")


def test_candidate_localizer_is_not_requested_without_focal_finding(tmp_path):
    result = server._localize_candidate(
        tmp_path,
        {"prediction": "NEGATIVE", "subtype": {"determined": False}},
    )
    assert result["status"] == "not_requested_no_focal_finding"
    assert result["used_by_screening_inference"] is False


def test_seg_done_requires_volume_and_mask(tmp_path):
    assert server._seg_done(tmp_path) is False
    (tmp_path / "volume.nii.gz").write_bytes(b"x")
    assert server._seg_done(tmp_path) is False
    (tmp_path / "mask_organ.nii.gz").write_bytes(b"x")
    assert server._seg_done(tmp_path) is True


def test_analyze_creates_job_and_status_is_queryable(monkeypatch, tmp_path):
    # não roda o pipeline real (GPU/MedGemma): substitui o worker por no-op
    monkeypatch.setattr(server, "process_job", lambda *a, **k: None)
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    resp = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0001.dcm", b"fake-dicom-bytes", "application/dicom"))],
        data={"relpaths": '["estudo/IMG-0001.dcm"]'},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    status = client.get(f"/api/status/{job_id}")
    assert status.status_code == 200
    assert status.json()["state"] in ("queued", "processing", "done")
    assert client.get("/api/status/inexistente").status_code == 404
    # o upload foi materializado preservando a subpasta
    assert (tmp_path / job_id / "_upload" / "estudo" / "IMG-0001.dcm").is_file()


def test_completed_job_state_survives_process_restart(monkeypatch, tmp_path):
    import json

    from dtwin.core import sha256_of

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "a0b1c2"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    mesh = outputs / "figado_orgao.stl"
    mesh.write_bytes(b"solid liver\nendsolid liver\n")
    manifest = {
        "schema": "argos-viewer-manifest-v2",
        "meshes": [{
            "role": "orgao",
            "stl": mesh.name,
            "metrics": {"mesh_sha256": sha256_of(mesh)},
        }],
    }
    (outputs / "viewer_manifest.json").write_text(json.dumps(manifest), "utf-8")
    server._jobs[job_id] = {
        "state": "processing",
        "step": "modelo_3d",
        "progress": 94,
        "analysis_scenario": "hybrid_supervised",
        "enhanced_3d": True,
        "result": None,
        "approval": {"status": "pending"},
    }
    server._set(
        job_id,
        state="done",
        step="concluido",
        progress=100,
        result={
            "status": "concluido",
            "viewer_ready": True,
            "viewer_url": f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}",
        },
    )
    assert (outputs / "webapp_job_state.json").is_file()

    server._jobs.pop(job_id)
    response = TestClient(server.app).get(f"/api/status/{job_id}")
    assert response.status_code == 200
    assert response.json()["state"] == "done"
    assert response.json()["enhanced_3d"] is True


def test_completed_job_restore_fails_closed_after_asset_tampering(monkeypatch, tmp_path):
    import json

    from dtwin.core import sha256_of

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    job_id = "d0e1f2"
    outputs = tmp_path / job_id / "case" / "outputs"
    outputs.mkdir(parents=True)
    mesh = outputs / "figado_orgao.stl"
    mesh.write_bytes(b"original")
    (outputs / "viewer_manifest.json").write_text(
        json.dumps({
            "schema": "argos-viewer-manifest-v2",
            "meshes": [{
                "role": "orgao",
                "stl": mesh.name,
                "metrics": {"mesh_sha256": sha256_of(mesh)},
            }],
        }),
        "utf-8",
    )
    server._jobs[job_id] = {"state": "processing", "result": None}
    server._set(
        job_id,
        state="done",
        step="concluido",
        progress=100,
        result={"status": "concluido", "viewer_ready": True},
    )
    server._jobs.pop(job_id)
    mesh.write_bytes(b"tampered")
    assert TestClient(server.app).get(f"/api/status/{job_id}").status_code == 404


def test_individual_screening_config_recusa_caminho_arbitrario():
    """A resolução de config segue existindo para benchmark e linha de comando,
    onde comparar configurações é o objetivo. Ela não é alcançável pelo exame
    individual, mas continua tendo que recusar caminho vindo de fora."""
    assert server._individual_screening_config("volumetric_rag") == server.VOLUMETRIC_RAG_MEDGEMMA_CONFIG
    with pytest.raises(PipelineError, match="não autorizado"):
        server._individual_screening_config("../../config-inseguro.yaml")


def test_analyze_roda_sempre_o_classificador_visual(monkeypatch, tmp_path):
    """O exame individual tem UM caminho, e ele não depende do que o cliente pede."""
    visto = {}
    monkeypatch.setattr(server, "process_visual_job",
                        lambda job_id, raw_dir: visto.update(visual=job_id))
    monkeypatch.setattr(server, "process_job",
                        lambda *a, **k: visto.update(medgemma=True))
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    response = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0001.dcm", b"fake-dicom-bytes", "application/dicom"))],
        data={"relpaths": '["estudo/IMG-0001.dcm"]'},
    )
    assert response.status_code == 200
    assert response.json()["analysis_scenario"] == "hybrid_supervised"
    # O worker é disparado em thread; um pequeno polling evita tornar o teste
    # dependente do scheduler.
    for _ in range(50):
        if visto:
            break
        time.sleep(0.01)
    assert "visual" in visto
    assert "medgemma" not in visto


def test_analyze_accepts_only_authorized_enhanced_3d_flag(monkeypatch, tmp_path):
    executable = tmp_path / "mrsegmentator.exe"
    executable.write_bytes(b"fake")
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "MRSEGMENTATOR_EXE", executable)
    monkeypatch.setattr(server, "ENHANCED_3D_OPT_IN_ENABLED", True)
    monkeypatch.setattr(server, "process_visual_job", lambda *a, **k: None)
    client = TestClient(server.app)
    accepted = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0001.dcm", b"fake", "application/dicom"))],
        data={"relpaths": '["estudo/IMG-0001.dcm"]', "enhanced_3d": "1"},
    )
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["enhanced_3d"] is True
    assert server._jobs[payload["job_id"]]["enhanced_3d"] is True

    rejected = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0002.dcm", b"fake", "application/dicom"))],
        data={"enhanced_3d": "../../modelo"},
    )
    assert rejected.status_code == 400


def test_enhanced_3d_requested_fails_before_processing_when_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "ENHANCED_3D_OPT_IN_ENABLED", True)
    monkeypatch.setattr(server, "MRSEGMENTATOR_EXE", tmp_path / "missing.exe")
    monkeypatch.setattr(server, "process_visual_job", lambda *a, **k: None)
    client = TestClient(server.app)
    response = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0001.dcm", b"fake", "application/dicom"))],
        data={"enhanced_3d": "1"},
    )
    assert response.status_code == 409
    assert "indisponível" in response.json()["detail"]


def test_segmentation_visualization_capability_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "ENHANCED_3D_OPT_IN_ENABLED", True)
    monkeypatch.setattr(server, "MRSEGMENTATOR_EXE", tmp_path / "missing.exe")
    payload = server.segmentation_visualization_capability()
    assert payload["available"] is False
    assert payload["selected_by_default"] is False
    assert payload["classification_immutable"] is True


def test_analyze_recusa_pedido_de_modo_mais_fraco(monkeypatch, tmp_path):
    """Recusar é melhor que rebaixar em silêncio: quem pediu outro modo precisa
    saber que não o recebeu, em vez de levar um resultado pior sem perceber."""
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    for pedido in ("pathology_target", "volumetric_rag", "baseline"):
        response = client.post(
            "/api/analyze",
            files=[("files", ("IMG-0001.dcm", b"fake-dicom-bytes", "application/dicom"))],
            data={"scenario": pedido},
        )
        assert response.status_code == 400, pedido
        assert "não autorizado" in response.json()["detail"]


def test_paginas_nao_oferecem_escolha_de_modo():
    """Nenhuma tela pode deixar o usuário escolher uma configuração pior: ele não
    tem como saber qual é a melhor, e oferecer a escolha transfere a ele um risco
    que é nosso."""
    for arquivo in ("webapp/static/index.html", "webapp/static/benchmark.html"):
        page = Path(arquivo).read_text(encoding="utf-8")
        assert "data-scenario=" not in page, f"{arquivo} ainda oferece seleção de modo"
    individual = Path("webapp/static/index.html").read_text(encoding="utf-8")
    assert "fd.append('scenario', 'hybrid_supervised')" in individual
    assert "id=\"enhanced3d\"" in individual
    assert "fd.append('enhanced_3d'" in individual
    assert "Não altera a classificação" in individual


def test_exame_individual_accepts_dicom_bruto_e_expoe_resolucao_de_fases():
    page = Path("webapp/static/index.html").read_text(encoding="utf-8")
    assert "pasta DICOM bruta" in page
    assert "modo monofásico experimental" in page
    assert "sem criar fases" in page
    assert "Ambiguidade entre várias séries" in page
    assert "ordered_axial_t1_postcontrast_series" in page
    assert "ordem temporal DICOM revisável" in page


def test_visual_job_falls_back_only_for_insufficient_dynamic_phases(monkeypatch, tmp_path):
    from dtwin.learning import multiphase_ingest
    from dtwin.learning.raw_dicom_phase_resolver import RawPhaseResolutionError

    job_id = "mono00000001"
    raw = tmp_path / "upload"
    raw.mkdir()
    monkeypatch.setattr(server, "WORKSPACE", tmp_path / "workspace")
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5,
        "result": None, "analysis_scenario": "hybrid_supervised",
    }

    def insufficient(**_kwargs):
        raise RawPhaseResolutionError(
            "fases insuficientes", code="insufficient_dynamic_phases"
        )

    captured = {}

    def single_phase_worker(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(multiphase_ingest, "build_multiphase_case", insufficient)
    monkeypatch.setattr(server, "process_job", single_phase_worker)

    server.process_visual_job(job_id, raw)

    assert captured["args"] == (job_id, raw)
    assert captured["kwargs"]["medgemma_config"] == server.MONOPHASE_MEDGEMMA_CONFIG
    assert captured["kwargs"]["analysis_scenario"] == "monophase_rag"
    assessment = captured["kwargs"]["input_assessment"]
    assert assessment["dynamic_enhancement_information_present"] is False
    assert assessment["synthetic_phases_created"] is False
    assert assessment["validated_triphase_metrics_applicable"] is False
    assert assessment["monophase_sequence_contract"]["selected_sequence_class"] == "UNKNOWN"
    assert assessment["monophase_sequence_contract"]["cross_phase_claims_allowed"] is False
    assert server._jobs[job_id]["analysis_scenario"] == "monophase_rag"


def test_visual_job_routes_explicit_delayed_monophase_to_medsiglip(monkeypatch, tmp_path):
    from dtwin.learning import multiphase_ingest
    from dtwin.learning.raw_dicom_phase_resolver import RawPhaseResolutionError

    job_id = "monodelay001"
    raw = tmp_path / "upload"
    raw.mkdir()
    workspace = tmp_path / "workspace"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "WORKSPACE", workspace)
    monkeypatch.setattr(server, "REPO", tmp_path)
    monkeypatch.setattr(server, "MONOPHASE_DELAYED_VISUAL_BUNDLE", "bundle")
    monkeypatch.setattr(server, "MONOPHASE_DELAYED_VISUAL_AUTO_PROMOTED", True)
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5,
        "result": None, "analysis_scenario": "hybrid_supervised",
    }

    def insufficient(**_kwargs):
        raise RawPhaseResolutionError(
            "fases insuficientes", code="insufficient_dynamic_phases"
        )

    captured = {}
    monkeypatch.setattr(multiphase_ingest, "build_multiphase_case", insufficient)
    monkeypatch.setattr(
        server,
        "select_best_mr_series",
        lambda *_a, **_k: (
            [str(raw / "one.dcm")], 30,
            {"selected": {"sequence_class": "T1_DELAYED"}},
        ),
    )
    monkeypatch.setattr(
        server,
        "process_monophase_medsiglip_job",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs),
    )
    monkeypatch.setattr(
        server, "process_job", lambda *_a, **_k: pytest.fail("4B fallback was called")
    )

    server.process_visual_job(job_id, raw)

    assert captured["args"] == (job_id, raw)
    assessment = captured["kwargs"]["input_assessment"]
    assert assessment["selected_sequence_class"] == "T1_DELAYED"
    assert assessment["monophase_sequence_contract"]["source_phase_key"] == "t1_delayed"
    assert assessment["monophase_sequence_contract"]["washout_claim_allowed"] is False
    assert assessment["single_phase_reader"].startswith("MedSigLIP")
    assert server._jobs[job_id]["analysis_scenario"] == "monophase_medsiglip_delayed"


def test_visual_job_keeps_ambiguous_raw_study_fail_closed(monkeypatch, tmp_path):
    from dtwin.learning import multiphase_ingest
    from dtwin.learning.raw_dicom_phase_resolver import RawPhaseResolutionError

    job_id = "ambig0000001"
    raw = tmp_path / "upload"
    raw.mkdir()
    monkeypatch.setattr(server, "WORKSPACE", tmp_path / "workspace")
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5,
        "result": None, "analysis_scenario": "hybrid_supervised",
    }

    def ambiguous(**_kwargs):
        raise RawPhaseResolutionError(
            "mais de um estudo elegível",
            code="ambiguous_explicit_multiphase_studies",
        )

    fallback_called = []
    monkeypatch.setattr(multiphase_ingest, "build_multiphase_case", ambiguous)
    monkeypatch.setattr(server, "process_job", lambda *_a, **_k: fallback_called.append(True))

    server.process_visual_job(job_id, raw)

    assert fallback_called == []
    assert server._jobs[job_id]["result"]["status"] == "nao_concluido"
    assert "mais de um estudo" in server._jobs[job_id]["result"]["motivo"]


def test_monophase_config_is_low_latency_rag_and_forbids_dynamic_claims():
    from dtwin.medgemma_client import load_screening_config

    config = load_screening_config(server.REPO / server.MONOPHASE_MEDGEMMA_CONFIG)
    prompt = config["prompt"]["template"]

    assert config["panel"]["strategy"] == "uniform_9"
    assert config["rag"]["enabled"] is True
    assert "entrada é monofásica" in prompt
    assert "Nenhuma fase foi sintetizada" in prompt
    assert "não afirme realce arterial, washout" in prompt
    assert '"alvo_da_triagem"' in prompt


def test_monophase_viewer_result_preserves_input_assessment():
    assessment = {
        "mode": "single_phase",
        "dynamic_enhancement_information_present": False,
        "synthetic_phases_created": False,
        "validated_triphase_metrics_applicable": False,
    }
    result = server._viewer_result(
        {"report": {"resultado_hipotese": "INCONCLUSIVA"}},
        "abc123",
        False,
        analysis_scenario="monophase_rag",
        input_assessment=assessment,
    )

    assert result["analysis_scenario"] == "monophase_rag"
    assert result["input_assessment"] == assessment
    assert result["status"] == "concluido"


def test_delayed_medsiglip_runs_only_as_persisted_advisory(monkeypatch, tmp_path):
    from dtwin.learning import exam_to_panels, monophase_visual_inference

    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "volume.nii.gz").write_bytes(b"volume")
    (case_dir / "mask_organ.nii.gz").write_bytes(b"mask")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle_manifest.json").write_text("{}", encoding="utf-8")
    panel = tmp_path / "panel.png"
    panel.write_bytes(b"panel")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(server, "REPO", tmp_path)
    monkeypatch.setattr(server, "MONOPHASE_DELAYED_VISUAL_BUNDLE", "bundle")
    monkeypatch.setattr(server, "MONOPHASE_DELAYED_ADVISORY_ENABLED", True)
    monkeypatch.setattr(
        exam_to_panels,
        "build_monophase_exam_panels",
        lambda **_kwargs: SimpleNamespace(
            panel_paths=[panel], panel_count=1, manifest_path=manifest
        ),
    )
    monkeypatch.setattr(
        monophase_visual_inference,
        "infer_monophase_case_from_panels",
        lambda **_kwargs: {
            "prediction": "NEGATIVE",
            "score": 0.21,
            "threshold": 0.59,
            "panel_count": 1,
            "panel_manifest_sha256": "a" * 64,
            "class_probabilities": {"negative_unspecified": 0.79, "positive_unspecified": 0.21},
        },
    )
    assessment = {
        "mode": "single_phase",
        "monophase_sequence_contract": {
            "source_phase_key": "t1_delayed",
            "sequence_specific_medsiglip_bundle_allowed": True,
        },
    }

    result = server._run_delayed_medsiglip_advisory(
        case_dir=case_dir,
        case_id="case123",
        input_assessment=assessment,
        primary_prediction="POSITIVA",
    )

    assert result["status"] == "completed"
    assert result["prediction"] == "NEGATIVA"
    assert result["agreement_with_primary"] is False
    assert result["review_priority"] == "elevated"
    assert result["affects_primary_decision"] is False
    persisted = case_dir / "outputs" / "second_reader" / "medsiglip_advisory.json"
    assert persisted.is_file()
    assert '"affects_primary_decision": false' in persisted.read_text(encoding="utf-8")


def test_medsiglip_advisory_rejects_non_delayed_sequence_without_inference(
    monkeypatch, tmp_path
):
    from dtwin.learning import exam_to_panels

    monkeypatch.setattr(server, "MONOPHASE_DELAYED_ADVISORY_ENABLED", True)
    monkeypatch.setattr(
        exam_to_panels,
        "build_monophase_exam_panels",
        lambda **_kwargs: pytest.fail("painéis não devem ser gerados para fase inelegível"),
    )
    result = server._run_delayed_medsiglip_advisory(
        case_dir=tmp_path,
        case_id="case123",
        input_assessment={
            "mode": "single_phase",
            "monophase_sequence_contract": {
                "source_phase_key": "t2",
                "sequence_specific_medsiglip_bundle_allowed": False,
            },
        },
        primary_prediction="NEGATIVA",
    )

    assert result["status"] == "not_eligible"
    assert result["affects_primary_decision"] is False


def test_monophase_viewer_result_exposes_secondary_reader_without_changing_report():
    second = {
        "status": "completed",
        "prediction": "NEGATIVA",
        "affects_primary_decision": False,
    }
    result = server._viewer_result(
        {"report": {"resultado_hipotese": "POSITIVA"}},
        "abc123",
        False,
        analysis_scenario="monophase_rag",
        input_assessment={"mode": "single_phase"},
        secondary_reader=second,
    )

    assert result["report"]["resultado_hipotese"] == "POSITIVA"
    assert result["secondary_reader"] == second


def test_benchmark_metrics_keep_failures_and_inconclusives_visible():
    results = [
        {"truth": "positive", "prediction": "POSITIVA", "status": "decisive"},
        {"truth": "positive", "prediction": "NEGATIVA", "status": "decisive"},
        {"truth": "negative", "prediction": "NEGATIVA", "status": "decisive"},
        {"truth": "negative", "prediction": "POSITIVA", "status": "decisive"},
        {"truth": "positive", "prediction": "INCONCLUSIVA", "status": "inconclusive"},
        {"truth": "negative", "prediction": None, "status": "failed"},
    ]
    metrics = server.calculate_benchmark_metrics(results)
    assert metrics["confusion_matrix"] == {"tp": 1, "tn": 1, "fp": 2, "fn": 2}
    assert metrics["accuracy"] == 0.3333
    assert metrics["sensitivity"] == 0.3333
    assert metrics["specificity"] == 0.3333
    assert metrics["precision"] == 0.3333
    assert metrics["f1_score"] == 0.3333
    assert metrics["coverage_rate"] == 0.6667
    assert metrics["completion_rate"] == 0.8333
    assert metrics["inconclusive_cases"] == 1
    assert metrics["failed_cases"] == 1
    assert metrics["scoring_policy"] == "inconclusive_and_failed_count_as_errors"
    assert metrics["target"]["met"] is False
    assert metrics["decisive_only"]["confusion_matrix"] == {
        "tp": 1, "tn": 1, "fp": 1, "fn": 1,
    }


def test_benchmark_target_requires_both_classes_at_75_percent():
    results = [
        *[{"truth": "positive", "prediction": "POSITIVA", "status": "decisive"}] * 3,
        {"truth": "positive", "prediction": "INCONCLUSIVA", "status": "inconclusive"},
        *[{"truth": "negative", "prediction": "NEGATIVA", "status": "decisive"}] * 3,
        {"truth": "negative", "prediction": None, "status": "failed"},
    ]
    metrics = server.calculate_benchmark_metrics(results)
    assert metrics["sensitivity"] == 0.75
    assert metrics["specificity"] == 0.75
    assert metrics["target"]["met"] is True
    assert metrics["confidence_intervals_95"]["sensitivity"] is not None


def test_benchmark_metrics_return_none_when_class_is_absent():
    metrics = server.calculate_benchmark_metrics([
        {"truth": "negative", "prediction": "NEGATIVA", "status": "decisive"},
    ])
    assert metrics["accuracy"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["sensitivity"] is None
    assert metrics["precision"] is None
    assert metrics["f1_score"] is None
    assert metrics["target"]["met"] is False


def test_benchmark_upload_maps_files_to_cases(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "process_benchmark", lambda *a, **k: None)
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    manifest = {
        "dataset_name": "Coorte teste",
        "dataset_kind": "mixed",
        "cases": [
            {"id": "caso-a", "label": "positive", "file_indices": [0, 1]},
            {"id": "caso-b", "label": "negative", "file_indices": [2]},
        ],
    }
    response = client.post(
        "/api/benchmarks",
        files=[
            ("files", ("a1.dcm", b"a1", "application/dicom")),
            ("files", ("a2.dcm", b"a2", "application/dicom")),
            ("files", ("b1.dcm", b"b1", "application/dicom")),
        ],
        data={"manifest": json.dumps(manifest)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cases"] == 2
    benchmark_id = payload["benchmark_id"]
    status = client.get(f"/api/benchmarks/{benchmark_id}")
    assert status.status_code == 200
    assert status.json()["total"] == 2
    root = tmp_path / "benchmarks" / benchmark_id / "_upload"
    assert len(list((root / "0001").iterdir())) == 2
    assert len(list((root / "0002").iterdir())) == 1


def test_benchmark_manifest_accepts_authorized_rag_scenarios():
    import json

    for scenario in (
        "baseline", "volumetric", "rag", "volumetric_rag", "pathology_target",
        "fast_pathology",
    ):
        parsed = server._parse_benchmark_manifest(
            json.dumps({
                "dataset_name": "Coorte",
                "dataset_kind": "positive",
                "scenario": scenario,
                "cases": [{"id": "c1", "label": "positive", "file_indices": [0]}],
            }),
            file_count=1,
        )
        assert parsed["scenario"] == scenario


def test_benchmark_manifest_accepts_visual_scenario():
    import json

    parsed = server._parse_benchmark_manifest(
        json.dumps({
            "dataset_name": "Coorte multifásica",
            "dataset_kind": "mixed",
            "scenario": "hybrid_supervised",
            "cases": [{"id": "c1", "label": "positive", "file_indices": [0]}],
        }),
        file_count=1,
    )
    assert parsed["scenario"] == "hybrid_supervised"
    assert server._is_visual_scenario("hybrid_supervised") is True
    # cenários MedGemma continuam não-visuais
    assert server._is_visual_scenario("pathology_target") is False


def test_benchmark_manifest_accepts_pathology_and_subtype_and_derives_consistency():
    import json

    parsed = server._parse_benchmark_manifest(
        json.dumps({
            "dataset_name": "Coorte de variações",
            "dataset_kind": "mixed",
            "evaluation_mode": "pathology_and_subtype",
            "scenario": "hybrid_supervised",
            "cases": [
                {"id": "hcc-1", "label": "positive", "truth_subtype": "hcc", "file_indices": [0]},
                {"id": "fnh-1", "label": "negative", "truth_subtype": "fnh", "file_indices": [1]},
                {"id": "hem-1", "label": "negative", "truth_subtype": "hemangioma", "file_indices": [2]},
                {"id": "cyst-1", "label": "negative", "truth_subtype": "hepatic_cyst", "file_indices": [3]},
            ],
        }),
        file_count=4,
    )
    assert parsed["evaluation_mode"] == "pathology_and_subtype"
    assert [case["label"] for case in parsed["cases"]] == [
        "positive", "negative", "negative", "negative",
    ]


def test_benchmark_manifest_rejects_inconsistent_or_unprotected_subtype():
    import json

    base = {
        "dataset_name": "Coorte",
        "dataset_kind": "mixed",
        "evaluation_mode": "pathology_and_subtype",
        "scenario": "hybrid_supervised",
        "cases": [{
            "id": "caso-1", "label": "positive", "truth_subtype": "fnh", "file_indices": [0],
        }],
    }
    with pytest.raises(Exception, match="incompatível"):
        server._parse_benchmark_manifest(json.dumps(base), file_count=1)

    base["evaluation_mode"] = "binary"
    with pytest.raises(Exception, match="só é aceito"):
        server._parse_benchmark_manifest(json.dumps(base), file_count=1)


def test_ground_truth_subtype_is_attached_only_after_inference():
    inference = {
        "case_id": "caso-1",
        "prediction": "NEGATIVA",
        "status": "decisive",
        "subtype_determined": True,
        "subtype": "fnh",
    }
    assert "truth_subtype" not in inference
    evaluated = server._evaluate_benchmark_result(inference, "negative", "fnh")
    assert evaluated["truth_subtype"] == "fnh"
    assert evaluated["correct"] is True
    assert "truth_subtype" not in inference


def test_benchmark_frontend_exposes_dual_metrics_without_removing_binary_mode():
    page = Path("webapp/static/benchmark.html").read_text(encoding="utf-8")
    assert 'value="binary" checked' in page
    assert 'value="pathology_and_subtype"' in page
    assert "Acurácia balanceada" in page
    assert "Matriz de confusão multiclasse" in page
    assert "HCC é positivo para a patologia-alvo" in page
    assert "A referência de subtipo somente é anexada depois da inferência" in page


def test_provenance_summary_flags_unknown_and_in_sample():
    # unknown NAO pode ser lido como limpo: o caso pode ter sido visto no treino.
    only_unknown = server._provenance_summary([
        {"in_sample_verdict": "unknown"}, {"in_sample_verdict": "unknown"},
    ])
    assert only_unknown["counts"]["unknown"] == 2
    assert only_unknown["metrics_are_generalization_estimate"] is False
    lowered = only_unknown["warning"].lower()
    assert "procedência não verificável" in lowered
    assert "não são estimativa de generalização" in lowered

    seen = server._provenance_summary([
        {"in_sample_verdict": "in_sample"}, {"in_sample_verdict": "out_of_sample"},
    ])
    assert seen["counts"]["in_sample"] == 1
    assert seen["metrics_are_generalization_estimate"] is False
    assert "vistos no treino" in seen["warning"]


def test_provenance_summary_clean_only_when_all_out_of_sample():
    clean = server._provenance_summary([
        {"in_sample_verdict": "out_of_sample"}, {"in_sample_verdict": "out_of_sample"},
    ])
    assert clean["metrics_are_generalization_estimate"] is True
    assert clean["warning"] is None


def test_provenance_summary_treats_missing_verdict_as_unknown():
    # Caso legado, sem o campo: nunca assumir que e limpo.
    legacy = server._provenance_summary([{"case_id": "x"}])
    assert legacy["counts"]["unknown"] == 1
    assert legacy["metrics_are_generalization_estimate"] is False


def test_visual_scenario_rejects_unauthorized_key():
    from dtwin.core import PipelineError

    with pytest.raises(PipelineError, match="não autorizado"):
        server._visual_bundle_root("../etc/passwd")


def test_visual_scenario_requires_trained_bundle(monkeypatch, tmp_path):
    from dtwin.core import PipelineError

    # aponta para um diretório sem bundle_manifest.json
    monkeypatch.setattr(server, "REPO", tmp_path)
    monkeypatch.setattr(
        server, "VISUAL_BENCHMARK_SCENARIOS", {"hybrid_supervised": "sem_bundle"}
    )
    with pytest.raises(PipelineError, match="train-production"):
        server._visual_bundle_root("hybrid_supervised")


def test_authorized_visual_phase_resolution_ignores_regular_case(tmp_path):
    assert server._authorized_visual_phase_resolution("caso-comum", tmp_path) is None


def test_authorized_visual_phase_resolution_uses_only_server_config(
    monkeypatch, tmp_path
):
    import hashlib
    import json

    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

    case_id = "ARGOS-BLIND-0001"
    upload = tmp_path / "uploaded"
    rows = []
    for number, role in (
        (1, "t1_arterial"),
        (2, "t1_venous"),
        (3, "t1_delayed"),
    ):
        path = upload / f"series_{number:03d}" / "volume.dcm"
        path.parent.mkdir(parents=True)
        file_meta = FileMetaDataset()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.MediaStorageSOPClassUID = MRImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.SOPClassUID = MRImageStorage
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.PatientID = case_id
        ds.Modality = "MR"
        ds.SeriesNumber = number
        ds.save_as(str(path), enforce_file_format=True)
        rows.append(
            {
                "blind_case_id": case_id,
                "series_number": number,
                "role_private": role,
                "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    audit = tmp_path / "authorized" / "conversion_audit.json"
    audit.parent.mkdir()
    audit.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(server, "REPO", tmp_path)
    monkeypatch.setattr(
        server,
        "VISUAL_AUTHORIZED_PHASE_AUDIT",
        "authorized/conversion_audit.json",
    )

    resolved = server._authorized_visual_phase_resolution(case_id, upload)
    assert resolved is not None
    assert resolved.safe_manifest()["private_paths_persisted"] is False


def test_visual_benchmark_finalization_does_not_require_medgemma_config(
    monkeypatch, tmp_path
):
    captured = {}
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(server, "WORKSPACE", tmp_path / "workspace")
    monkeypatch.setattr(
        server,
        "_run_visual_benchmark_case",
        lambda *_args, **_kwargs: {
            "case_id": "caso-visual",
            "prediction": "NEGATIVA",
            "status": "decisive",
            "duration_seconds": 1.0,
            "durations_seconds": {"total": 1.0},
        },
    )
    monkeypatch.setattr(
        server,
        "_visual_model_info",
        lambda _scenario: {
            "model_id": "medsiglip_multiclass_production_bundle",
            "model_version": "test",
        },
    )
    monkeypatch.setattr(
        server,
        "write_run_outputs",
        lambda _root, run_manifest, _results, _metrics: captured.update(
            run_manifest=run_manifest
        ),
    )
    server._benchmarks["visual-run"] = {
        "state": "queued",
        "progress": 0,
        "processed": 0,
        "total": 1,
        "current_case": None,
        "report": None,
        "error": None,
    }
    server.process_benchmark(
        "visual-run",
        {
            "dataset_name": "visual",
            "dataset_kind": "negative",
            "scenario": "hybrid_supervised",
            "cases": [
                {
                    "id": "caso-visual",
                    "label": "negative",
                    "file_indices": [0],
                }
            ],
        },
        raw,
    )
    assert server._benchmarks["visual-run"]["state"] == "done"
    assert captured["run_manifest"]["model_family"] == "MedSigLIP"
    assert captured["run_manifest"]["medgemma_config_path"] is None
    assert captured["run_manifest"]["medgemma_config_hash"] is None
    assert captured["run_manifest"]["visual_panel_config_sha256"] is not None
    assert captured["run_manifest"]["visual_embedding_config_sha256"] is not None


def test_visual_upload_preserves_opaque_series_tree_for_authorized_adapter(
    monkeypatch, tmp_path
):
    import json

    monkeypatch.setattr(server, "process_benchmark", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    case_id = "ARGOS-BLIND-0001"
    manifest = {
        "dataset_name": "ARGOS internal blind",
        "dataset_kind": "negative",
        "scenario": "hybrid_supervised",
        "cases": [
            {
                "id": case_id,
                "label": "negative",
                "file_indices": [0, 1, 2],
            }
        ],
    }
    relpaths = [
        f"webapp_input/{case_id}/series_001/volume.dcm",
        f"webapp_input/{case_id}/series_002/volume.dcm",
        f"webapp_input/{case_id}/series_003/volume.dcm",
    ]
    response = client.post(
        "/api/benchmarks",
        files=[
            ("files", ("volume.dcm", b"one", "application/dicom")),
            ("files", ("volume.dcm", b"two", "application/dicom")),
            ("files", ("volume.dcm", b"three", "application/dicom")),
        ],
        data={
            "manifest": json.dumps(manifest),
            "relpaths": json.dumps(relpaths),
        },
    )
    assert response.status_code == 200
    benchmark_id = response.json()["benchmark_id"]
    uploaded_case = (
        tmp_path
        / "benchmarks"
        / benchmark_id
        / "_upload"
        / "0001"
        / case_id
    )
    assert (uploaded_case / "series_001" / "volume.dcm").read_bytes() == b"one"
    assert (uploaded_case / "series_002" / "volume.dcm").read_bytes() == b"two"
    assert (uploaded_case / "series_003" / "volume.dcm").read_bytes() == b"three"


def test_benchmark_upload_accepts_more_than_default_starlette_file_cap(monkeypatch, tmp_path):
    """Starlette limita multipart a max_files=1000 por padrão; um dataset de
    benchmark real (muitos exames x muitas fatias) estoura isso facilmente.
    O endpoint precisa aceitar mais, via MAX_UPLOAD_FILES (ver webapp/server.py)."""
    import json

    monkeypatch.setattr(server, "process_benchmark", lambda *a, **k: None)
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    n = 1200  # acima do max_files=1000 default do Starlette; abaixo de MAX_UPLOAD_FILES
    manifest = {
        "dataset_name": "Dataset grande",
        "dataset_kind": "positive",
        "cases": [{"id": "caso-a", "label": "positive", "file_indices": list(range(n))}],
    }
    response = client.post(
        "/api/benchmarks",
        files=[("files", (f"slice_{i:05d}.dcm", b"x", "application/dicom")) for i in range(n)],
        data={"manifest": json.dumps(manifest)},
    )
    assert response.status_code == 200
    assert response.json()["total_cases"] == 1


def test_benchmark_case_uses_absolute_case_dir_and_scores(monkeypatch, tmp_path):
    """Regressão: a segmentação do benchmark roda por um launcher com cwd=%TEMP%.
    Se o case_dir for relativo, a saída cai fora do repo e _seg_done() nunca a
    encontra, marcando TODO exame como falha. O case_dir precisa ser absoluto."""
    import subprocess

    import numpy as np
    import SimpleITK as sitk

    # Reproduz produção: WORKSPACE é RELATIVO ("casos/webapp"). Sem .resolve() no
    # código, o case_dir sairia relativo — é exatamente isso que o teste captura.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "WORKSPACE", Path("casos/webapp"))
    seen = {}

    def fake_segment(series_dir, case_dir, device, timeout, *, fast):
        # o bug real era o case_dir chegar relativo aqui
        seen["absolute"] = Path(case_dir).is_absolute()
        seen["fast"] = fast  # benchmark deve segmentar em modo rápido
        # simula uma segmentação bem-sucedida gravando os artefatos esperados. A
        # máscara é um NIfTI REAL: o webapp a lê para calcular o timeout efetivo.
        Path(case_dir).mkdir(parents=True, exist_ok=True)
        volume = sitk.GetImageFromArray(np.ones((4, 5, 6), dtype=np.float32))
        mask = sitk.GetImageFromArray(np.ones((4, 5, 6), dtype=np.uint8))
        sitk.WriteImage(volume, str(Path(case_dir) / "volume.nii.gz"))
        sitk.WriteImage(mask, str(Path(case_dir) / "mask_organ.nii.gz"))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def fake_run(cmd, timeout, cwd=None):  # a triagem MedGemma (subprocesso)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    def fake_load_report(path):
        return {"report": {"resultado_hipotese": "POSITIVA", "confianca": "alta",
                           "resumo_do_achado": "x"}}

    monkeypatch.setattr(server, "_segment", fake_segment)
    monkeypatch.setattr(server, "_run", fake_run)
    monkeypatch.setattr(server, "_load_report", fake_load_report)

    raw_case = tmp_path / "raw" / "0001"
    raw_case.mkdir(parents=True)
    dcm_files = []
    for i in range(3):
        f = raw_case / f"IMG-{i}.dcm"
        f.write_bytes(b"fake-dicom")
        dcm_files.append(str(f))
    monkeypatch.setattr(server, "find_best_series", lambda d: (dcm_files, 3))

    inference_result = server._run_benchmark_case("bench01", 1, {"id": "c1"}, raw_case)
    result = server._evaluate_benchmark_result(inference_result, "positive")

    assert seen["absolute"] is True, "case_dir passado à segmentação deve ser absoluto"
    assert seen["fast"] is True, "benchmark deve segmentar em modo rápido (throughput)"
    assert result["status"] == "decisive"
    assert result["prediction"] == "POSITIVA"
    assert result["correct"] is True


def test_benchmark_upload_rejects_unmapped_file(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    client = TestClient(server.app)
    manifest = {
        "dataset_name": "Inválido",
        "dataset_kind": "positive",
        "cases": [{"id": "caso-a", "label": "positive", "file_indices": [0]}],
    }
    response = client.post(
        "/api/benchmarks",
        files=[
            ("files", ("a.dcm", b"a", "application/dicom")),
            ("files", ("b.dcm", b"b", "application/dicom")),
        ],
        data={"manifest": json.dumps(manifest)},
    )
    assert response.status_code == 400
    assert "Todos os arquivos" in response.json()["detail"]


def test_benchmark_report_downloads_json_and_csv(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    benchmark_id = "abc123"
    root = tmp_path / "benchmarks" / benchmark_id
    root.mkdir(parents=True)
    report = {
        "benchmark_id": benchmark_id,
        "cases": [{
            "case_id": "caso-a", "truth": "positive", "prediction": "POSITIVA",
            "status": "decisive", "correct": True, "confidence": "alta",
            "duration_seconds": 12.5, "error": None,
            "positive_subtype": "hcc_suspicious",
            "phenotype_tags": ["arterial_hyperenhancement", "washout_suspicion"],
            "report_v2": {
                "ha_lesao_focal_suspeita": True,
                "ha_variante_anatomica_benigna": False,
                "tipo_alteracao_nao_alvo": "none",
            },
        }],
    }
    (root / "benchmark_report.json").write_text(json.dumps(report), "utf-8")
    client = TestClient(server.app)
    assert client.get(f"/api/benchmarks/{benchmark_id}/report.json").status_code == 200
    csv_response = client.get(f"/api/benchmarks/{benchmark_id}/report.csv")
    assert csv_response.status_code == 200
    header, first_row = csv_response.text.splitlines()[:2]
    assert "case_id,truth,prediction" in header
    # Colunas estratificadas (taxonomia + schema v2) presentes e preenchidas.
    for column in (
        "truth_subtype", "predicted_subtype_for_scoring", "subtype_correct",
        "target_condition", "negative_subtype", "positive_subtype", "phenotype_tags",
        "ha_lesao_focal_suspeita", "tipo_alteracao_nao_alvo",
    ):
        assert column in header
    assert "caso-a,positive,POSITIVA" in first_row
    assert "hcc_suspicious" in first_row
    assert "arterial_hyperenhancement;washout_suspicion" in first_row
    assert "true" in first_row  # ha_lesao_focal_suspeita booleano serializado


def test_web_benchmark_persists_auditable_run_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    def fake_inference(*args, **kwargs):
        assert "label" not in args[2]
        return {
            "case_id": "caso-a", "dataset": "coorte", "input_format": "DICOM",
            "prediction": "POSITIVA", "status": "decisive",
            "confidence": "alta", "duration_seconds": 1.25, "error": None,
        }

    monkeypatch.setattr(server, "_run_benchmark_case", fake_inference)
    benchmark_id = "abc999"
    raw = tmp_path / "benchmarks" / benchmark_id / "_upload"
    raw.mkdir(parents=True)
    with server._lock:
        server._benchmarks[benchmark_id] = {
            "state": "queued", "progress": 0, "processed": 0, "total": 1,
            "current_case": None, "report": None, "error": None,
        }
    server.process_benchmark(benchmark_id, {
        "dataset_name": "coorte", "dataset_kind": "positive",
        "cases": [{"id": "caso-a", "label": "positive", "file_indices": [0]}],
    }, raw)
    root = tmp_path / "benchmarks" / benchmark_id
    for name in (
        "run_manifest.json", "cases.jsonl", "metrics_primary.json",
        "metrics_decisions_only.json", "confusion_matrices.json", "summary.md",
    ):
        assert (root / name).is_file(), name
    assert server._benchmarks[benchmark_id]["state"] == "done"


def test_web_benchmark_builds_dual_report_without_leaking_subtype_to_inference(
    monkeypatch, tmp_path
):
    import json

    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    truth = {
        "hcc-1": "hcc",
        "fnh-1": "fnh",
        "hem-1": "hemangioma",
        "cyst-1": "hepatic_cyst",
    }

    def fake_visual(_benchmark_id, _index, case_item, _raw_dir, _scenario):
        assert set(case_item) == {"id", "dataset"}
        assert "truth_subtype" not in case_item
        subtype = truth[case_item["id"]]
        return {
            "case_id": case_item["id"],
            "prediction": "POSITIVA" if subtype == "hcc" else "NEGATIVA",
            "status": "decisive",
            "confidence": 0.9,
            "duration_seconds": 1.0,
            "subtype_determined": True,
            "subtype": subtype,
            "in_sample_verdict": "out_of_sample",
        }

    monkeypatch.setattr(server, "_run_visual_benchmark_case", fake_visual)
    monkeypatch.setattr(server, "_visual_model_info", lambda _scenario: {"model_id": "test"})
    monkeypatch.setattr(server, "write_run_outputs", lambda *_args, **_kwargs: None)
    benchmark_id = "dual001"
    raw = tmp_path / "benchmarks" / benchmark_id / "_upload"
    raw.mkdir(parents=True)
    server._benchmarks[benchmark_id] = {
        "state": "queued", "progress": 0, "processed": 0, "total": 4,
        "current_case": None, "report": None, "error": None,
    }
    cases = [
        {
            "id": case_id,
            "label": "positive" if subtype == "hcc" else "negative",
            "truth_subtype": subtype,
            "file_indices": [index],
        }
        for index, (case_id, subtype) in enumerate(truth.items())
    ]
    server.process_benchmark(benchmark_id, {
        "dataset_name": "quatro classes",
        "dataset_kind": "mixed",
        "evaluation_mode": "pathology_and_subtype",
        "scenario": "hybrid_supervised",
        "cases": cases,
    }, raw)

    report = server._benchmarks[benchmark_id]["report"]
    assert server._benchmarks[benchmark_id]["state"] == "done"
    assert report["metrics"]["sensitivity"] == 1.0
    assert report["metrics"]["specificity"] == 1.0
    assert report["subtype_metrics"]["balanced_accuracy"] == 1.0
    assert report["subtype_metrics"]["class_coverage_complete"] is True
    assert report["combined_target"]["met"] is True
    assert all(row["subtype_correct"] is True for row in report["cases"])
    subtype_artifact = tmp_path / "benchmarks" / benchmark_id / "metrics_subtype.json"
    assert subtype_artifact.is_file()
    assert json.loads(subtype_artifact.read_text("utf-8"))["balanced_accuracy"] == 1.0


def _mascara_de_teste(destino: Path, gate_passa: bool) -> None:
    """Cria os arquivos que _seg_done exige. O gate é decidido pelo stub."""
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "volume.nii.gz").write_bytes(b"x")
    (destino / "mask_organ.nii.gz").write_bytes(b"x")


def test_gate_anatomico_recusa_mascara_implausivel(monkeypatch, tmp_path):
    """Uma máscara reprovada não pode virar resultado: os painéis saem dela."""
    monkeypatch.setattr(server, "_segment",
                        lambda *a, **k: _mascara_de_teste(Path(a[1]), True))
    monkeypatch.setattr(server, "_mask_quality", lambda _d: {
        "gate_passed": False,
        "failure_reasons": ["physical_volume_below_minimum"],
    })
    with pytest.raises(PipelineError, match="anatomicamente plausível"):
        server._segmentar_figado_com_gate(tmp_path / "venosa", tmp_path / "saida", "teste")


def test_gate_anatomico_devolve_qualidade_quando_aprova(monkeypatch, tmp_path):
    qualidade = {"gate_passed": True, "largest_component_volume_ml": 1500.0}
    monkeypatch.setattr(server, "_segment",
                        lambda *a, **k: _mascara_de_teste(Path(a[1]), True))
    monkeypatch.setattr(server, "_mask_quality", lambda _d: qualidade)
    assert server._segmentar_figado_com_gate(
        tmp_path / "venosa", tmp_path / "saida", "teste") == qualidade


def test_os_dois_caminhos_usam_o_mesmo_gate():
    """Regressão de docs/175.

    O gate existia só no exame individual, e o MESMO exame era recusado numa
    página e contado como acerto na outra. Este teste falha se alguém voltar a
    chamar _segment direto de dentro de um dos fluxos visuais, contornando o
    ponto único de decisão.
    """
    import inspect

    for fluxo in (server.process_visual_job, server._run_visual_benchmark_case):
        fonte = inspect.getsource(fluxo)
        assert "_segmentar_figado_com_gate" in fonte, (
            f"{fluxo.__name__} não usa o gate unificado"
        )
        assert "_segment(" not in fonte, (
            f"{fluxo.__name__} chama _segment direto e escapa do gate anatômico"
        )


def test_registro_de_backends_ignora_entrada_invalida_sem_derrubar():
    """Uma linha malformada não pode criar backend fantasma nem quebrar o boot."""
    spec = (
        "27b=MedGemma 27B=configs/medgemma_ollama_27b.yaml;"
        "quebrado=sem_config;"
        "inexistente=X=configs/nao_existe_mesmo.yaml;"
        "   ;"
        "4b=MedGemma 1.5 4B=configs/medgemma_local_4b_mps.yaml"
    )
    backends = server._parse_medgemma_backends(spec)
    assert set(backends) == {"27b", "4b"}
    assert backends["27b"]["label"] == "MedGemma 27B"
    # O healthcheck sai do próprio config quando não é declarado no spec.
    assert backends["27b"]["health"].endswith("/health")


def test_backend_nao_registrado_e_recusado_em_vez_de_rebaixado(monkeypatch):
    """Rebaixar em silêncio faria o relatório nomear o modelo errado."""
    monkeypatch.setattr(server, "MEDGEMMA_BACKENDS", {
        "27b": {"id": "27b", "label": "27B", "config": "configs/medgemma_ollama_27b.yaml", "health": "h"},
    })
    assert server._medgemma_backend_config(None, "padrao.yaml") == "padrao.yaml"
    assert server._medgemma_backend_config("27b", "padrao.yaml") == "configs/medgemma_ollama_27b.yaml"
    with pytest.raises(PipelineError, match="não autorizado"):
        server._medgemma_backend_config("4b", "padrao.yaml")


def test_endpoint_de_backends_so_reporta_o_que_respondeu(monkeypatch):
    monkeypatch.setattr(server, "MEDGEMMA_BACKENDS", {
        "27b": {"id": "27b", "label": "MedGemma 27B", "config": "c27.yaml", "health": "http://x/27"},
        "4b": {"id": "4b", "label": "MedGemma 1.5 4B", "config": "c4.yaml", "health": "http://x/4"},
    })
    monkeypatch.setattr(server, "_probe_backend",
                        lambda url: "pronto" if url.endswith("/27") else "desligado")
    payload = server.medgemma_backends()
    assert payload["prontos"] == ["27b"]
    estados = {row["id"]: row["estado"] for row in payload["backends"]}
    assert estados == {"27b": "pronto", "4b": "desligado"}


def test_analyze_recusa_backend_desconhecido(monkeypatch, tmp_path):
    """A recusa vem ANTES de gastar segmentação, não no meio da análise."""
    monkeypatch.setattr(server, "process_visual_job", lambda *a, **k: None)
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "MEDGEMMA_BACKENDS", {})
    client = TestClient(server.app)
    response = client.post(
        "/api/analyze",
        files=[("files", ("IMG-0001.dcm", b"fake", "application/dicom"))],
        data={"relpaths": '["estudo/IMG-0001.dcm"]', "medgemma_backend": "27b"},
    )
    assert response.status_code == 400
    assert "não autorizado" in response.json()["detail"]


def test_config_de_embedding_mps_so_difere_em_execucao():
    """Trocar device/dtype é aceitável; trocar a representação invalidaria o bundle."""
    import yaml as _yaml
    cuda = _yaml.safe_load(Path("configs/training/medsiglip_frozen_v1.yaml").read_text(encoding="utf-8"))
    mps = _yaml.safe_load(Path("configs/training/medsiglip_frozen_mps_v1.yaml").read_text(encoding="utf-8"))
    assert mps["device"] == "mps"
    for chave in ("schema", "model_id", "revision", "image_size", "pooling",
                  "l2_normalize", "output_dtype", "local_files_only"):
        assert mps[chave] == cuda[chave], f"{chave} divergiu entre CUDA e MPS"


def test_aviso_de_fragmentacao_so_aparece_quando_ha_fragmento():
    """Máscara íntegra não deve gerar aviso — ruído treina o revisor a ignorar."""
    assert server._aviso_fragmentacao_figado(None) is None
    assert server._aviso_fragmentacao_figado(
        {"component_count": 1, "largest_component_fraction": 1.0}
    ) is None


def test_aviso_de_fragmentacao_declara_quanto_saiu_da_cena():
    aviso = server._aviso_fragmentacao_figado(
        {"component_count": 4, "largest_component_fraction": 0.93}
    )
    assert aviso is not None
    assert aviso["componentes"] == 4
    assert aviso["percentual_descartado"] == 7.0
    assert aviso["nivel"] == "atencao"
    assert "4 partes" in aviso["texto"]


def test_aviso_de_fragmentacao_e_informativo_quando_o_descarte_e_irrelevante():
    aviso = server._aviso_fragmentacao_figado(
        {"component_count": 2, "largest_component_fraction": 0.9995}
    )
    assert aviso is not None and aviso["nivel"] == "informacao"


def test_uniao_de_fases_nunca_toca_a_mascara_de_classificacao(tmp_path, monkeypatch):
    """A garantia central de docs/188/189: mask_organ.nii.gz (o que os painéis
    de classificação já leram) precisa sair intacto -- byte a byte."""
    import numpy as np
    import SimpleITK as sitk

    case_dir = tmp_path
    venosa = np.zeros((10, 10, 10), dtype=np.uint8)
    venosa[3:7, 3:7, 3:7] = 1
    img = sitk.GetImageFromArray(venosa)
    caminho_venosa = case_dir / "mask_organ.nii.gz"
    sitk.WriteImage(img, str(caminho_venosa))
    hash_antes = hashlib.sha256(caminho_venosa.read_bytes()).hexdigest()

    arterial = case_dir / "arterial.nii.gz"
    delayed = case_dir / "delayed.nii.gz"
    ampliada = np.zeros((10, 10, 10), dtype=np.uint8)
    ampliada[2:8, 2:8, 2:8] = 1
    for caminho in (arterial, delayed):
        extra = sitk.GetImageFromArray(ampliada)
        extra.CopyInformation(img)
        sitk.WriteImage(extra, str(caminho))

    def fake_segmenter(source, output, **kwargs):
        # simula a segmentação: copia a imagem "ampliada" correspondente
        shutil.copyfile(source, output)
        return {}

    monkeypatch.setattr(
        "dtwin.benchmark.lld_mmri_v23_preparation.isolated_total_mr_liver_segmenter",
        fake_segmenter,
    )
    resultado = server._build_union_liver_mask(
        case_dir, {"t1_arterial": arterial, "t1_delayed": delayed}
    )

    assert hashlib.sha256(caminho_venosa.read_bytes()).hexdigest() == hash_antes, (
        "a máscara de classificação foi alterada -- isso não pode acontecer"
    )
    assert resultado["status"] == "union_built"
    assert set(resultado["phases_included"]) == {"venous", "arterial", "delayed"}
    assert resultado["union_volume_ml"] > resultado["venous_volume_ml"]
    assert (case_dir / "mask_organ_union.nii.gz").is_file()


def test_uniao_de_fases_degrada_para_venosa_quando_tudo_falha(tmp_path, monkeypatch):
    """Nenhuma fase extra disponível -> nenhum arquivo novo, exame não falha."""
    import numpy as np
    import SimpleITK as sitk

    case_dir = tmp_path
    venosa = np.zeros((6, 6, 6), dtype=np.uint8)
    venosa[1:4, 1:4, 1:4] = 1
    sitk.WriteImage(sitk.GetImageFromArray(venosa), str(case_dir / "mask_organ.nii.gz"))

    def falha(source, output, **kwargs):
        raise RuntimeError("segmentação indisponível nesta simulação")

    monkeypatch.setattr(
        "dtwin.benchmark.lld_mmri_v23_preparation.isolated_total_mr_liver_segmenter", falha
    )
    resultado = server._build_union_liver_mask(case_dir, {"t1_arterial": Path("nao-existe.nii.gz")})

    assert resultado["status"] == "union_unavailable_venous_only"
    assert not (case_dir / "mask_organ_union.nii.gz").is_file()


def test_uniao_de_fases_descarta_fase_com_geometria_divergente(tmp_path, monkeypatch):
    import numpy as np
    import SimpleITK as sitk

    case_dir = tmp_path
    venosa_arr = np.zeros((8, 8, 8), dtype=np.uint8)
    venosa_arr[2:6, 2:6, 2:6] = 1
    img_venosa = sitk.GetImageFromArray(venosa_arr)
    sitk.WriteImage(img_venosa, str(case_dir / "mask_organ.nii.gz"))

    arterial = case_dir / "arterial.nii.gz"
    sitk.WriteImage(sitk.GetImageFromArray(venosa_arr), str(arterial))  # fonte só precisa existir

    def segmenta_com_geometria_errada(source, output, **kwargs):
        imagem = sitk.GetImageFromArray(venosa_arr)
        imagem.SetSpacing((5.0, 5.0, 5.0))  # geometria deliberadamente diferente
        sitk.WriteImage(imagem, str(output))
        return {}

    monkeypatch.setattr(
        "dtwin.benchmark.lld_mmri_v23_preparation.isolated_total_mr_liver_segmenter",
        segmenta_com_geometria_errada,
    )
    resultado = server._build_union_liver_mask(case_dir, {"t1_arterial": arterial})

    assert resultado["status"] == "union_unavailable_venous_only"
    assert resultado["phase_failures"]["arterial"] == "geometria_divergente"


def test_aviso_de_volume_usa_a_uniao_quando_disponivel():
    aviso = server._aviso_volume_figado(
        {"largest_component_volume_ml": 480.0}, volume_uniao_ml=200.0
    )
    assert aviso is not None
    assert aviso["volume_ml"] == 200.0
    assert "união" in aviso["texto"]


def test_aviso_de_volume_sem_uniao_mantem_comportamento_anterior():
    """Chamada de 1 argumento (o caminho do benchmark) continua igual."""
    aviso = server._aviso_volume_figado({"largest_component_volume_ml": 200.0})
    assert aviso is not None
    assert aviso["volume_ml"] == 200.0
    assert "venosa" in aviso["texto"]


def test_mascara_uniao_e_construida_depois_da_classificacao_no_codigo():
    """Regressão estrutural: garante, no texto-fonte, que a chamada de união
    vem DEPOIS de classify_embeddings -- nunca antes."""
    import inspect

    fonte = inspect.getsource(server.process_visual_job)
    pos_classificacao = fonte.index("classify_embeddings(")
    pos_uniao = fonte.index("_build_union_liver_mask(")
    assert pos_uniao > pos_classificacao, (
        "a união de fases precisa ser construída depois da decisão congelada"
    )


def test_shadow_3d_roda_depois_da_classificacao_e_antes_da_malha():
    import inspect

    fonte = inspect.getsource(server.process_visual_job)
    pos_classificacao = fonte.index("classify_embeddings(")
    pos_shadow = fonte.index("_build_enhanced_visualization_shadow(")
    pos_modelo = fonte.index("_build_model(")
    assert pos_classificacao < pos_shadow < pos_modelo
    assert "if UNION_MASK_ENABLED and not shadow_approved" in fonte


def test_uniao_de_fases_usa_as_chaves_reais_do_multiphase_ingest(tmp_path, monkeypatch):
    """Regressão: a primeira versão buscava phase_paths["arterial"], mas as
    chaves reais de multiphase.phase_paths são as constantes de
    dtwin.learning.multiphase_ingest ("t1_arterial"/"t1_delayed"). Um teste
    cego a esse detalhe passaria mesmo com a busca errada -- pego só num
    exame real pelo front. Este teste usa as constantes importadas, não uma
    string reescrita à mão, para nunca mais divergir em silêncio."""
    import numpy as np
    import SimpleITK as sitk
    from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED, VENOUS

    venosa = np.zeros((6, 6, 6), dtype=np.uint8)
    venosa[1:4, 1:4, 1:4] = 1
    img = sitk.GetImageFromArray(venosa)
    sitk.WriteImage(img, str(tmp_path / "mask_organ.nii.gz"))

    fonte_arterial = tmp_path / f"{ARTERIAL}.nii.gz"
    fonte_delayed = tmp_path / f"{DELAYED}.nii.gz"
    sitk.WriteImage(img, str(fonte_arterial))
    sitk.WriteImage(img, str(fonte_delayed))

    def fake_segmenter(source, output, **kwargs):
        shutil.copyfile(source, output)
        return {}

    monkeypatch.setattr(
        "dtwin.benchmark.lld_mmri_v23_preparation.isolated_total_mr_liver_segmenter",
        fake_segmenter,
    )
    # phase_paths no formato REAL que build_multiphase_case produz.
    phase_paths_real = {VENOUS: tmp_path / "mask_organ.nii.gz",
                        ARTERIAL: fonte_arterial, DELAYED: fonte_delayed}
    resultado = server._build_union_liver_mask(tmp_path, phase_paths_real)

    assert resultado["status"] == "union_built", (
        f"as fases não foram encontradas com as chaves reais: {resultado}"
    )
    assert resultado["phase_failures"] == {}
