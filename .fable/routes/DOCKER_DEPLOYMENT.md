# DOCKER_DEPLOYMENT

TRIGGERS: Docker/Compose, portable Mac/ARM64, Windows launcher, Quest proxy/certificate, deploy/transfer.  
REAL_PATHS: `compose.yaml`, `compose.portable.yaml`, `docker/`, `INICIAR_OREN*.cmd`, `run_*.ps1`, `run_mac.sh`, `tools/initialize_argos_docker.ps1`.  
MODULES: DOCKER_LAUNCHERS, WEBAPP_API_ORCHESTRATION, MODEL_LOADING.  
MINIMUM_CONTEXT: DEPENDENCIES, SECURITY, REPRODUCIBILITY, target services/volumes.  
REFERENCES: Docker/NVIDIA/Apple/runtime official docs when task-specific.  
CONTRACTS: data/weights/state mounted outside image; secrets in env; health checks; platform capability explicit; portable image not assumed GPU.  
RISKS: MEDIUM; HIGH if backend/model/numerics change.  
AUTHORITY: inspect/build/test/propose; external network/secrets/model change gated.  
REQUIRED_TESTS: config validation, clean build, health, E2E smoke, volumes/read-only, Mac/Windows matrix, offline model, certificate/network.  
HUMAN_GATE: HG-09/11 as applicable.  
STOP_CONDITIONS: daemon unavailable for claimed validation, secret missing/exposed, unsupported architecture.  
EXPECTED_EVIDENCE: image/digest/platform, Compose resolution sanitized, health/E2E, transfer checksum and rollback.

