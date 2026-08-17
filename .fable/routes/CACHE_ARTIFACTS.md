# CACHE_ARTIFACTS

TRIGGERS: cache, hash, artifact, manifest, checkpoint, resume, retry, partial, stale, corrupt.  
REAL_PATHS: `dtwin/learning/medsiglip_embeddings.py`, `dtwin/learning/protocol.py`, `dtwin/benchmark/reporting.py`, `dtwin/benchmark/runner.py`, `dtwin/medgemma_screening.py`, `dtwin/volumetry.py`, `webapp/server.py`.  
MODULES: ARTIFACT_PROVENANCE plus producer/consumer module.  
MINIMUM_CONTEXT: LOGGING_AUDIT_PROVENANCE, MODEL_LOADING for ML, CONCURRENCY for writers.  
REFERENCES: reproducibility/testing/security.  
CONTRACTS: identity includes input/model/revision/preprocessing/config/pipeline/artifact; atomic publish; partial never success; resume idempotent.  
RISKS: MEDIUM; HIGH if artifact affects scientific result.  
AUTHORITY: investigate/test/propose; cautious patch only with explicit scope and promotion check.  
REQUIRED_TESTS: corrupt/truncate/tamper, config/model/input change, crash between writes, concurrent writer, read-after-write, backup/prefix.  
HUMAN_GATE: HG-09/01 when scientific identity changes.  
STOP_CONDITIONS: validity key unknown, artifact provenance missing, incompatible reuse.  
EXPECTED_EVIDENCE: identity tuple, hash tree, state transitions, failure injection and recovery proof.
