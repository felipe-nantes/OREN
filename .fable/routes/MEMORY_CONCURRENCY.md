# MEMORY_CONCURRENCY

TRIGGERS: OOM, memory leak, thread, race, lock, backpressure, concurrent writer/process.  
REAL_PATHS: `webapp/server.py`, segmentation/candidate subprocess modules, batch inference/embedding modules, launchers.  
MODULES: WEBAPP_API_ORCHESTRATION, SEGMENTATION_RUNTIME, MEDSIGLIP_EMBEDDINGS.  
MINIMUM_CONTEXT: ORCHESTRATION, CACHE_ARTIFACTS, PERFORMANCE.  
REFERENCES: Python/PyTorch/testing.  
CONTRACTS: bounded resources; no shared artifact race; one live job owner; cleanup after crash; deterministic ordering where scientific.  
RISKS: MEDIUM; HIGH if missing/reordered cases alter denominator.  
AUTHORITY: reproduce/stress/fault-test/propose; carefully scoped infra patch.  
REQUIRED_TESTS: simultaneous jobs, duplicate worker, low memory, timeout tree kill, atomic writer, queue saturation, restart.  
HUMAN_GATE: HG-08 if failures/denominator behavior changes.  
STOP_CONDITIONS: risk of data overwrite, uncontrolled live processes, unreliable resource measurement.  
EXPECTED_EVIDENCE: process/thread state, memory curve, artifact integrity, failure accounting and recovery.

