# TESTS_BUILD_ENVIRONMENT

TRIGGERS: pytest, CI, lint, typing, coverage, Hypothesis, mutation, benchmark, build environment.  
REAL_PATHS: `tests/`, `pyproject.toml`, `.github/workflows/tests.yml`, Dockerfiles, test utilities.  
MODULES: TEST_SUITE plus target module.  
MINIMUM_CONTEXT: TEST_STRATEGY, TOOLING, target semantic route/contract.  
REFERENCES: pytest/Hypothesis/coverage/mutation/Ruff/mypy/pip-audit cards.  
CONTRACTS: test type explicit; characterization ≠ specification; branch coverage/ mutation strength over raw count.  
RISKS: LOW/MEDIUM; HIGH if expected outputs/fixtures encode scientific change.  
AUTHORITY: add mechanical/contract tests within known authority; scientific expectations need gate.  
REQUIRED_TESTS: meta-test that counterexample/mutation fails; collect/run portable; CI parity.  
HUMAN_GATE: target semantic gate.  
STOP_CONDITIONS: expected behavior not authoritative, tool installation would change locked environment without scope.  
EXPECTED_EVIDENCE: tool versions, commands/results, coverage/mutation gaps and test taxonomy/contract IDs.

