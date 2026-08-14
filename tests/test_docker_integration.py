from pathlib import Path

import pytest

from tools.verify_argos_docker_static import verify


ROOT = Path(__file__).resolve().parents[1]


def test_docker_contract_is_safe_and_complete() -> None:
    result = verify(ROOT)
    assert result["valid"] is True
    assert result["default_medgemma_mode"] == "host"
    assert result["medical_data_in_image"] is False
    assert result["portable_arm64_runtime"] is True
    assert result["portable_container_acceleration"] == "cpu"


def test_portable_runtime_is_native_arm64_capable_and_has_no_gpu_reservation() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.argos-portable").read_text(encoding="utf-8")
    override = (ROOT / "compose.portable.yaml").read_text(encoding="utf-8")
    config = (ROOT / "configs/training/medsiglip_frozen_cpu_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "FROM python:3.11-slim-bookworm" in dockerfile
    assert '"torch==2.10.0"' in dockerfile
    assert '"torchvision==0.25.0"' in dockerfile
    assert '"TotalSegmentator==2.18.0"' in dockerfile
    assert "gpus: !reset []" in override
    assert "WEBAPP_MEDGEMMA_CONFIG: configs/medgemma_ollama_27b.yaml" in override
    assert "WEBAPP_VOLUMETRIC_RAG_MEDGEMMA_CONFIG: configs/medgemma_ollama_27b_volumetric_rag.yaml" in override
    assert "ARGOS_DOCKER_PLATFORM" in override
    assert "device: cpu" in config and "dtype: float32" in config


def test_portable_transfer_is_fail_closed_for_medical_data_and_secrets() -> None:
    exporter = (ROOT / "tools/export_argos_portable.ps1").read_text(encoding="utf-8")
    importer = (ROOT / "tools/import_argos_portable.sh").read_text(encoding="utf-8")
    initializer = (ROOT / "tools/initialize_argos_docker.sh").read_text(encoding="utf-8")
    for forbidden in ("casos", "data", ".env.docker", ".safetensors", ".dcm"):
        assert forbidden in exporter
    assert "checksums.sha256" in exporter and "shasum -a 256 -c" in importer
    assert "openssl rand" in initializer
    assert "oren-quest-key.pem" in initializer


def test_container_path_override_preserves_windows_default(monkeypatch: pytest.MonkeyPatch) -> None:
    source = (ROOT / "webapp" / "server.py").read_text(encoding="utf-8")
    assert 'os.environ.get("WEBAPP_MRSEGMENTATOR_EXE"' in source
    assert '"Scripts/mrsegmentator.exe" if os.name == "nt" else "bin/mrsegmentator"' in source


def test_docker_secrets_and_local_paths_are_not_versioned() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env.docker" in ignored
    example = (ROOT / "docker" / ".env.example").read_text(encoding="utf-8")
    assert "SUBSTITUA_POR_UMA_SENHA_FORTE" in example
    assert "profurg" not in example.lower()


def test_medgemma_container_remains_optional() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert 'profiles: ["medgemma-container"]' in compose
    assert "host.docker.internal:8001" in compose
    medgemma = compose.split("  medgemma:", 1)[1].split("  graphify:", 1)[0]
    assert '127.0.0.1:8001:8001' not in medgemma
    assert '      - "8001"' in medgemma


def test_launchers_switch_medgemma_modes_without_gpu_or_port_conflicts() -> None:
    start = (ROOT / "tools" / "start_argos_docker.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "tools" / "stop_argos_docker.ps1").read_text(encoding="utf-8")
    assert "stop_medgemma_gateway_win.ps1" in start
    assert "stop medgemma" in start
    assert "stop_medgemma_gateway_win.ps1" in stop
    assert '$health.backend -eq "pronto"' in start
    assert '$SkipMedGemmaStart -and $health.backend -eq "desligado"' in start
    assert "--force-recreate --no-deps proxy" in start
    assert "ensure_docker_desktop.ps1" in start


def test_container_medgemma_has_private_bind_opt_in_only() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    server = (ROOT / "tools" / "medgemma_server_v14.py").read_text(encoding="utf-8")
    assert 'ARGOS_CONTAINER: "1"' in compose
    assert 'os.environ.get("ARGOS_CONTAINER") == "1"' in server
    assert 'allowed_hosts.add("0.0.0.0")' in server
    verifier = (ROOT / "tools" / "verify_medgemma_container.ps1").read_text(
        encoding="utf-8"
    )
    assert "finally" in verifier
    assert "start_medgemma_gateway_win.ps1" in verifier
    assert 'host_port_exposed = $false' in verifier


def test_graphify_container_has_no_network() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    graphify = compose.split("  graphify:", 1)[1].split("\nnetworks:", 1)[0]
    assert "network_mode: none" in graphify


def test_e2e_smoke_requires_real_result_and_viewer() -> None:
    smoke = (ROOT / "tools" / "smoke_test_argos_docker_e2e.py").read_text(
        encoding="utf-8"
    )
    assert 'result.get("status") != "concluido"' in smoke
    assert 'result.get("viewer_ready")' in smoke
    assert 'manifest_payload.get("meshes")' in smoke


def test_independent_job_verifier_covers_durable_artifacts_and_xr() -> None:
    verifier = (ROOT / "tools" / "verify_argos_docker_job.py").read_text(
        encoding="utf-8"
    )
    for requirement in (
        "reconstruction_quality_gate_passed",
        "whole_liver_volume_ml",
        "ground_truth_lesion_mask_used",
        "used_by_screening_inference",
        "xr_https_role_separation",
        "path_traversal_rejected",
    ):
        assert requirement in verifier


def test_e2e_smoke_can_explicitly_request_enhanced_3d() -> None:
    smoke = (ROOT / "tools" / "smoke_test_argos_docker_e2e.py").read_text(
        encoding="utf-8"
    )
    assert 'parser.add_argument("--enhanced-3d", action="store_true")' in smoke
    assert '"1" if enhanced_3d else "0"' in smoke
