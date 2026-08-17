# LOGGING_AUDIT_PROVENANCE

TRIGGERS: log, manifest, audit, provenance, hash, protocol signature, human decision, report.  
REAL_PATHS: `dtwin/core.py`, `dtwin/learning/protocol.py`, `dtwin/benchmark/hashing.py`, `dtwin/benchmark/reporting.py`, `dtwin/benchmark/runner.py`, `dtwin/volumetry.py`, `webapp/server.py`.  
MODULES: ARTIFACT_PROVENANCE, BENCHMARK_METRICS_REPORTING, WEBAPP_API_ORCHESTRATION.  
MINIMUM_CONTEXT: CACHE_ARTIFACTS, PRIVACY_SECURITY, REPRODUCIBILITY.  
REFERENCES: reproducibility/security.  
CONTRACTS: complete source/config/model/code/data identity; atomic records; sanitized logs; hash≠cryptographic signature.  
RISKS: MEDIUM, HIGH if scientific ledger changes.  
AUTHORITY: improve nonsemantic logging after baseline; scientific provenance schema changes require impact review.  
REQUIRED_TESTS: atomicity/tamper, dirty Git, missing fields, clock/path portability, PHI/secret negative, approval linkage.  
HUMAN_GATE: HG-01/08/11 as relevant.  
STOP_CONDITIONS: provenance missing, “signed” ambiguous, secrets/PHI found.  
EXPECTED_EVIDENCE: manifest schema, sample sanitized record, independent verifier and retention policy.
