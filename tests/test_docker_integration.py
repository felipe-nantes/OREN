from pathlib import Path

import pytest

from tools.verify_argos_docker_static import verify


ROOT = Path(__file__).resolve().parents[1]


def test_docker_contract_is_safe_and_complete() -> None:
    result = verify(ROOT)
    assert result["valid"] is True
    assert result["default_medgemma_mode"] == "host"
    assert result["medical_data_in_image"] is False


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
    assert "--force-recreate --no-deps proxy" in start


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
