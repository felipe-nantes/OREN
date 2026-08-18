"""Distribuição portátil ARM64 (Mac, sem ambiente de dev) — preservada.

Extraído de tests/test_docker_integration.py durante a migração para runtime
nativo (TASK-2026-08-18-MIGR-01). Decisão humana (2026-08-18, PH-02): esta
capacidade — rodar via container pronto para quem não tem Python/CUDA/deps
instalados — não tem equivalente nativo por definição e fica FORA do escopo
"sem Docker". Ver .fable/MIGRATION_DOCKER_TO_NATIVE.md.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
