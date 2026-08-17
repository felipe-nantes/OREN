# PERFORMANCE

TRIGGERS: slow, optimize, timeout, FPS, VRAM/RAM, latency, batch, cold/warm cache.  
REAL_PATHS: target module plus `webapp/server.py`, subprocess wrappers, model configs, `viewer/xr.js`, operational timing modules.  
MODULES: target, WEBAPP_API_ORCHESTRATION, WEBXR_QUEST.  
MINIMUM_CONTEXT: MEMORY_CONCURRENCY, REPRODUCIBILITY and semantic route whose output may change.  
REFERENCES: Python/PyTorch/testing/reproducibility.  
CONTRACTS: optimization must not change pixels/masks/scores/geometry unless approved; benchmark controls hardware/cache/rounds.  
RISKS: MEDIUM; HIGH if approximation/batching/order/precision alters output.  
AUTHORITY: profile and propose; behavior-preserving patch only with equivalence evidence.  
REQUIRED_TESTS: before/after same hardware, warm/cold, peak RAM/VRAM, output hashes/tolerances, long-run/leak, failure pressure.  
HUMAN_GATE: relevant HG-04/05/07/09/10 if semantics.  
STOP_CONDITIONS: baseline environment differs, speed claim without rounds, output drift unexplained.  
EXPECTED_EVIDENCE: profiler/command/hardware, distributions not single timing, resource peaks and correctness deltas.

