# PIPELINE

TRIGGERS: end-to-end, stage, prepare/finalize, exam/benchmark flow, “pipeline broke”.  
REAL_PATHS: `digital_twin.py`, `dtwin/engine.py`, `dtwin/stages.py`, `webapp/server.py`, `dtwin/benchmark/runner.py`.  
MODULES: PIPELINE_ENGINE_STAGES, WEBAPP_API_ORCHESTRATION, all selected stage modules.  
MINIMUM_CONTEXT: SYSTEM_MAP, DEPENDENCY_MAP, ORCHESTRATION and stage routes.  
REFERENCES: testing/reproducibility.  
CONTRACTS: fail closed; stage input/output/side effects; human review; artifact provenance; ground truth isolation.  
RISKS: maximum of involved stages, commonly HIGH.  
AUTHORITY: trace/reproduce/test; semantic change follows highest gate.  
REQUIRED_TESTS: real-boundary integration, stage fault injection, resume/idempotency, artifact verification, focused+global.  
HUMAN_GATE: composite.  
STOP_CONDITIONS: missing stage artifact, partial success treated final, unknown fallback or baseline.  
EXPECTED_EVIDENCE: timeline/data flow, commands, per-stage hashes/status/timing/failure and downstream results.

