# EVIDENCE PACKAGE — TASK-2026-08-18-PH04-INV-04

```yaml
TASK_ID: TASK-2026-08-18-PH04-INV-04
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em dfb36b5; testes novos NÃO commitados
TASK_DESCRIPTION: >
  PHASE_04 wave 4 — contratos de splits e métricas como invariantes
  executáveis: isolamento por paciente/grupo (ARGOS-SCI-003, ARGOS-SCI-008) e
  estatística de proporções (ARGOS-SCI-013), com denominadores (ARGOS-SCI-004).
ROUTE: [CROSS_VALIDATION, METRICS_STATISTICS, TESTS_BUILD_ENVIRONMENT]
MODULES: [ML_CLASSIFIERS_SPLITS, BENCHMARK_METRICS_REPORTING, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/learning/splits.py (integral)
  - dtwin/benchmark/metrics.py:11-66 (wilson_interval, _ratio, _terminal_counts, _undefined_reasons)
  - tests/test_learning_splits.py + tests/test_characterization_nested_splits.py (cobertura prévia, coortes fixas)
FILES_CHANGED:
  - tests/test_property_splits_isolation.py (NOVO; 7 testes)
  - tests/test_property_metrics_invariants.py (NOVO; 15 testes)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: PHASE_04 autorizada; nenhum código de produção alterado
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED:
  - ARGOS-SCI-003 (nested patient-grouped CV) — protegido, não alterado
  - ARGOS-SCI-008 (isolamento de ground truth) — protegido, não alterado
  - ARGOS-SCI-013 (Wilson 95%) — protegido, não alterado
  - ARGOS-SCI-004 (denominadores) — parcialmente protegido (recusa de denominador vazio)
BASELINE: 1645 passed / 0 failed / 4 skipped
BUG_REPRODUCTION: N/A — os invariantes valem no código atual
TESTS_ADDED:
  - "splits: nenhum grupo cruza QUALQUER fronteira (externa e interna) — Hypothesis, 120 exemplos"
  - "splits: cada exame aparece exatamente uma vez no teste externo"
  - "splits: folds internos particionam exatamente o treino externo (fit_scope)"
  - "splits: artefato não carrega nenhum label (anti-gaming)"
  - "splits: determinismo para a mesma seed"
  - "splits: validador aceita o que o gerador produz"
  - "splits: validador REJEITA leakage injetado manualmente"
  - "métricas: Wilson sempre em [0,1] e ordenado — 300 exemplos"
  - "métricas: Wilson não degenera em p=0 e p=1 (a razão de não ser Wald)"
  - "métricas: intervalo contém a proporção observada"
  - "métricas: mais amostras não alargam o intervalo"
  - "métricas: nível de confiança maior produz intervalo maior"
  - "métricas: denominador vazio devolve None em vez de inventar intervalo"
  - "métricas: nível de confiança inválido é rejeitado"
  - "métricas: 5 âncoras numéricas contra cálculo independente"
TESTS_AFTER:
  - "splits isolado: 7 passed, 2.73s"
  - "métricas isolado: 15 passed, 0.82s"
  - "suíte completa: ver seção final"
MUTATION_RESULT: >
  Dois mutantes dirigidos, ambos detectados (EXIT_CRITERIA da fase):
  (1) `splits.py` agrupando por `case_id` em vez de `patient_group_id` — o
      leakage clássico por múltiplos exames do mesmo paciente. O invariante
      falha e NOMEIA o paciente vazado ('pos_paciente_002').
  (2) `metrics.py` com Wald no lugar de Wilson — 5 testes falham, incluindo
      o de degeneração nos extremos, que é precisamente a propriedade pela
      qual o contrato exige Wilson.
  Ambos revertidos; `splits.py` e `metrics.py` confirmados idênticos ao HEAD
  por `git diff --exit-code`.
PROPERTY_TEST_RESULT: PASSED
BEHAVIOR_CHANGE: NONE (nenhum código de produção alterado)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - As coortes geradas usam folds pequenos (outer 2-4, inner 2-3) para manter o Hypothesis rápido; os defaults congelados 5/4 continuam cobertos pelo teste de characterization da PHASE_03.
  - ARGOS-SCI-004 foi coberto apenas na borda "denominador vazio não vira intervalo"; a política completa de contagem de falhas (`_terminal_counts`, `compute_benchmark_metrics`) permanece com a cobertura prévia de tests/test_benchmark_metrics.py e não ganhou property test nesta wave.
  - Bootstrap agrupado por paciente (2000 reamostragens, ARGOS-SCI-013) não foi coberto — vive em learning/robustness.py, candidato à próxima wave.
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: dentro do escopo autorizado
DIFF_SUMMARY: 2 arquivos de teste novos (~300 linhas somadas)
ROLLBACK: deletar os 2 arquivos de teste
FINAL_STATUS: DONE (não commitado)
```

## Nota de método — âncora numérica corrigida antes de virar teste

A primeira versão da âncora de Wilson usava valores que eu havia citado de
memória (`[0.2523, 0.3648]` para 81/263) e **falhou** contra a implementação,
que devolvia `[0.2553, 0.3662]`.

Em vez de ajustar o teste ao código — o que transformaria a âncora numa
tautologia inútil — a fórmula foi reimplementada de forma independente e
comparada em 5 pontos, incluindo os extremos:

| k/n | reimplementação independente | produção |
|---|---|---|
| 81/263 | (0.255289, 0.366210) | (0.2553, 0.3662) |
| 0/50 | (0.000000, 0.071348) | (0.0, 0.0713) |
| 50/50 | (0.928652, 1.000000) | (0.9287, 1.0) |
| 1/10 | (0.017876, 0.404150) | (0.0179, 0.4042) |
| 500/1000 | (0.469070, 0.530930) | (0.4691, 0.5309) |

**A implementação de produção está correta; o valor lembrado é que estava
errado.** As 5 âncoras verificadas viraram o teste parametrizado.
