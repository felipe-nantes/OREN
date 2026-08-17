# ARCHITECTURE_REFACTOR

TRIGGERS: refactor, extract module/service, reorganize, reduce monolith/coupling.  
REAL_PATHS: often `webapp/server.py`, `dtwin/stages.py`, `dtwin/learning/`, `dtwin/benchmark/`, plus their callers in `configs/` and `tests/`.  
MODULES: all affected; use DEPENDENCY_MAP and Graphify.  
MINIMUM_CONTEXT: DEPENDENCIES, DEAD_CODE_DUPLICATION, TESTS, every semantic route crossed.  
REFERENCES: Python/testing/legacy/refactoring cards.  
CONTRACTS: public interfaces/artifact schemas/defaults/order/side effects preserved unless separately approved.  
RISKS: LOW/MEDIUM only if preservation proved; HIGH when scientific/geometry boundary moves.  
AUTHORITY: propose seams; small LOW extraction after safety net; high semantic refactor gated.  
REQUIRED_TESTS: characterization, contract, integration, global, static, mutation for moved critical logic, benchmark if hot path.  
HUMAN_GATE: highest semantic gate touched.  
STOP_CONDITIONS: unknown dynamic/runtime/data edge, mixed semantic+mechanical diff, no rollback.  
EXPECTED_EVIDENCE: before/after dependency graph, interface/artifact equivalence, tests and commit-sized diff.
