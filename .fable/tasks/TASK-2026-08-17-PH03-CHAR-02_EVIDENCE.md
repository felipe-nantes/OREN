# EVIDENCE PACKAGE — TASK-2026-08-17-PH03-CHAR-02

```yaml
TASK_ID: TASK-2026-08-17-PH03-CHAR-02
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: main em bd278b5 (código científico = 9683eaa); teste novo NÃO commitado
TASK_DESCRIPTION: PHASE_03 wave 2 — characterization do gerador de splits aninhados (P0 #2 leakage/CV), complementar aos testes existentes.
ROUTE: [CROSS_VALIDATION (characterization), TESTS_BUILD_ENVIRONMENT, METRICS_STATISTICS (transitiva)]
MODULES: [ML_CLASSIFIERS_SPLITS, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/learning/splits.py (integral: _group_cases, _assign_groups, build_nested_splits, validate_nested_splits)
  - dtwin/learning/schemas.py (ProtectedTrainingCase, LABELS, _token)
  - tests/test_learning_splits.py (cobertura existente, para não duplicar)
FILES_CHANGED:
  - tests/test_characterization_nested_splits.py (NOVO; 7 testes; fixtures 100% sintéticas, zero labels reais)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: fase autorizada pelo humano
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: [ARGOS-SCI-003 (protegido por teste de defaults; não alterado)]
BASELINE: suíte verde nos 2 backends; testes existentes de splits intactos
BUG_REPRODUCTION: N/A (nenhum bug; bordas fail-closed confirmadas como PipelineError)
TESTS_BEFORE:
  - "tests/test_learning_splits.py: 5 testes (determinismo, universo externo, fronteira externa por grupo, labels conflitantes, validação de leakage)"
TESTS_ADDED:
  - "::test_observed_grupo_de_paciente_nunca_cruza_fronteira_interna (lacuna central: fronteira INTERNA por grupo)"
  - "::test_observed_defaults_congelados_espelham_o_contrato_sci_003 (5/4/20260724 — mudança de default agora quebra teste)"
  - "::test_observed_menos_grupos_que_folds_aborta"
  - "::test_observed_classe_sem_grupo_por_fold_aborta"
  - "::test_observed_folds_menor_que_2_aborta"
  - "::test_observed_case_id_duplicado_aborta"
  - "::test_observed_seed_diferente_gera_atribuicao_diferente"
TESTS_AFTER:
  - "host Windows: 12 passed (7 novos + 5 existentes), 0.15s"
  - "container POSIX: 12 passed, 1.26s"
STATIC_ANALYSIS: NOT_RUN (adiado por decisão)
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE (fase 07)
PROPERTY_TEST_RESULT: NOT_APPLICABLE (fase 04 — candidato: property test de exclusividade de grupos com Hypothesis)
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Characterization do gerador; o CONSUMO dos splits pelo classificador (fit boundaries de scaler/tuning) fica para wave própria ou fase 05 — envolve pipeline sklearn pesado.
  - Balanceamento de folds não foi fixado numericamente (evitando snapshot frágil).
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: dentro do escopo autorizado
DIFF_SUMMARY: 1 arquivo de teste novo (~100 linhas)
ROLLBACK: deletar tests/test_characterization_nested_splits.py
FINAL_STATUS: DONE (não commitado; commit quando solicitado)
```
