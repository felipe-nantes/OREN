# ORCHESTRATION

TRIGGERS: job, queue, thread, subprocess, timeout, retry, fallback, restart, health.  
REAL_PATHS: `webapp/server.py`, `dtwin/segmentation_subprocess.py`, `dtwin/candidate_subprocess.py`, `dtwin/engine.py`, `digital_twin.py`, `compose.yaml`, `compose.portable.yaml`.  
MODULES: WEBAPP_API_ORCHESTRATION, SEGMENTATION_RUNTIME, DOCKER_LAUNCHERS.  
MINIMUM_CONTEXT: PIPELINE, MEMORY_CONCURRENCY, CACHE_ARTIFACTS, target subprocess contract.  
REFERENCES: Python/testing/security/reproducibility.  
CONTRACTS: one owner per job/artifact; bounded timeout/retry; child failure isolated; no silent fallback; durable completion only after verification.  
RISKS: MEDIUM; HIGH when ordering/failure affects endpoint.  
AUTHORITY: diagnose/fault-test/propose; promote before behavior change.  
REQUIRED_TESTS: timeout/crash/OOM, concurrent jobs/writers, restart restore, partial cleanup, health mismatch, absolute/relative workspace.  
HUMAN_GATE: target semantic gate if stage behavior changes.  
STOP_CONDITIONS: duplicate live worker, ambiguous ownership, recovery would overwrite user artifacts.  
EXPECTED_EVIDENCE: process tree/state machine, timing, checkpoint/hash, retry count and recovery proof.
