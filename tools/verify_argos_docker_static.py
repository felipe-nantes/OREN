"""Fail-closed static verification of the ARGOS container contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


REQUIRED_SERVICES = {"argos", "proxy", "neo4j", "medgemma", "graphify"}
FORBIDDEN_CONTEXT_NAMES = {
    ".git",
    ".local",
    ".medgemma",
    ".venv",
    ".venv-win",
    ".venv-mrseg",
    "artifacts",
    "casos",
    "data",
    "datasets",
    "dicom",
    "dicoms",
    "experiments",
    "rag",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def verify(root: Path) -> dict[str, object]:
    compose_path = root / "compose.yaml"
    compose = yaml.safe_load(_read(compose_path))
    services = compose.get("services") or {}
    missing = sorted(REQUIRED_SERVICES - set(services))
    if missing:
        raise ValueError(f"missing services: {missing}")

    argos = services["argos"]
    if argos.get("gpus") != "all":
        raise ValueError("ARGOS runtime must explicitly request the NVIDIA GPU")
    if "8000" not in set(argos.get("expose") or []):
        raise ValueError("ARGOS application port must remain internal")
    if argos.get("ports"):
        raise ValueError("ARGOS must be exposed only through the proxy")

    proxy_ports = set(services["proxy"].get("ports") or [])
    if "127.0.0.1:8080:8080" not in proxy_ports or "8443:8443" not in proxy_ports:
        raise ValueError("desktop loopback and Quest HTTPS ports are required")

    medgemma_profiles = set(services["medgemma"].get("profiles") or [])
    if "medgemma-container" not in medgemma_profiles:
        raise ValueError("container MedGemma must remain opt-in")
    graphify = services["graphify"]
    if graphify.get("network_mode") != "none":
        raise ValueError("Graphify container must not have network access")

    environment = compose.get("x-argos-environment") or {}
    if environment.get("HF_HUB_OFFLINE") != "1" or environment.get("TRANSFORMERS_OFFLINE") != "1":
        raise ValueError("model access must be local/offline at runtime")
    if "host.docker.internal" not in str(environment.get("WEBAPP_MEDGEMMA_HEALTH")):
        raise ValueError("default MedGemma gateway must use the host")

    dockerignore = {
        line.strip().rstrip("/")
        for line in _read(root / ".dockerignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    absent = sorted(FORBIDDEN_CONTEXT_NAMES - dockerignore)
    if absent:
        raise ValueError(f"sensitive/heavy build context paths not ignored: {absent}")

    dockerfile = _read(root / "docker" / "Dockerfile.argos")
    if re.search(r"COPY\s+(casos|data|datasets|artifacts|experiments)\b", dockerfile, re.I):
        raise ValueError("Docker image attempts to copy medical/generated data")
    if "USER argos" not in dockerfile:
        raise ValueError("ARGOS runtime must be non-root")

    nginx = _read(root / "docker" / "nginx.conf")
    for required in ("listen 8080", "listen 8443 ssl", "client_max_body_size 20g"):
        if required not in nginx:
            raise ValueError(f"missing proxy requirement: {required}")

    return {
        "valid": True,
        "services": sorted(services),
        "default_medgemma_mode": "host",
        "container_medgemma_opt_in": True,
        "medical_data_in_image": False,
        "graphify_network": "none",
        "quest_https": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
