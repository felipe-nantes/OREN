# DEPENDENCIES

TRIGGERS: package/version/lock, import, wheel, CVE, Python/CUDA compatibility.  
REAL_PATHS: `pyproject.toml`, `requirements.txt`, Dockerfiles/Compose, run scripts, `.github/workflows/tests.yml`.  
MODULES: DOCKER_LAUNCHERS, TEST_SUITE, affected model/runtime modules.  
MINIMUM_CONTEXT: TESTS_BUILD_ENVIRONMENT, SECURITY, REPRODUCIBILITY, MODEL_LOADING if relevant.  
REFERENCES: official package docs/releases/security advisories.  
CONTRACTS: compatible runtime and frozen model/numerical behavior; no silent package-driven scientific delta.  
RISKS: MEDIUM; HIGH for imaging/model/numerical packages.  
AUTHORITY: inventory/audit/propose; upgrade only with explicit scope and regressions.  
REQUIRED_TESTS: install clean, doctor, global, Docker build/E2E, geometry/scientific regressions, model load.  
HUMAN_GATE: HG-03/04/09 as applicable.  
STOP_CONDITIONS: upstream breaking semantics/security uncertainty/license issue/no rollback.  
EXPECTED_EVIDENCE: old/new resolved trees, advisories, platform matrix and full regression delta.

