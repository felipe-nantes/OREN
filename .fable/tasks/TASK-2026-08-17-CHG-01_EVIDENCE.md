# EVIDENCE PACKAGE — TASK-2026-08-17-CHG-01 (skipif de plataforma nos 2 testes Windows-only)

```yaml
TASK_ID: TASK-2026-08-17-CHG-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (mudança aplicada na árvore do repo principal, não commitada)
TASK_DESCRIPTION: >
  Aplicar @pytest.mark.skipif(os.name != "nt") nos 2 testes que assumem
  semântica Windows e falham em qualquer POSIX (baseline PHASE_00). Autorizado
  em HUMAN_DECISIONS.md item 6.
ROUTE: [TESTS_BUILD_ENVIRONMENT (rota alvo: SEGMENTATION/CACHE p/ teste 1, FRONTEND/ORCHESTRATION p/ teste 2 — nenhum código de produção tocado)]
MODULES: [TEST_SUITE]
FILES_ANALYZED:
  - tests/test_learning_monophase_slice_candidates.py
  - tests/test_operational_timing_relative_workspace.py
  - dtwin/learning/monophase_slice_candidates.py:81 (gate os.name — justificativa)
FILES_CHANGED:
  - tests/test_learning_monophase_slice_candidates.py (import os + skipif com reason)
  - tests/test_operational_timing_relative_workspace.py (imports os/pytest + skipif com reason)
RISK_LEVEL: LOW (somente marcadores de teste; nenhuma asserção alterada)
AUTHORITY_LEVEL: autorizado pelo humano (HUMAN_DECISIONS.md item 6)
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE:
  BEFORE_POSIX: "container PHASE_00 RUN2: os 2 testes FAILED (2f/1605p/3s na suíte global)"
  BEFORE_WINDOWS: "testes passavam (comportamento Windows nativo)"
BUG_REPRODUCTION: reproduzido na PHASE_00 (logs evidence/PH00/pytest_run2_writable_tree.log)
TESTS_BEFORE:
  - "POSIX: 2 FAILED (plataforma)"
  - "Windows: PASS"
TESTS_ADDED: []  # nenhum teste novo; 2 marcadores skipif
TESTS_AFTER:
  - "Windows host (.venv-win), 2 arquivos: 14 passed, 3 warnings, 0.67s — nada pulado"
  - "Container POSIX (argos-runtime:local, worktree ro + 2 arquivos patcheados via bind): 12 passed, 2 skipped, 1.53s — skips com as reasons corretas"
STATIC_ANALYSIS: NOT_RUN (ferramentas adiadas)
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: coberto pelos próprios arquivos de teste executados
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: >
  Suíte em POSIX passa de 2 failed → 0 failed (+2 skipped explícitos com
  reason). Cobertura no Windows inalterada. Nenhum código de produção tocado.
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - O comportamento de fallback Windows continua sem cobertura em POSIX (por construção); alternativa "corrigir o código" foi declinada nesta rodada (fase 08 candidata).
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum HG científico; autorização humana registrada (item 6)
APPROVAL_STATUS: aprovado por Felipe Nantes, 2026-08-17
DIFF_SUMMARY: 2 arquivos de teste; +import os/pytest; +2 decoradores skipif com reason técnica citando file:line
ROLLBACK: git checkout -- tests/test_learning_monophase_slice_candidates.py tests/test_operational_timing_relative_workspace.py
FINAL_STATUS: DONE (não commitado; commit separado quando solicitado)
```
