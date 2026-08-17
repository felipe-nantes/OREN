# Schema do pacote de evidências

Todo patch futuro deve produzir um documento versionável com os campos abaixo. `N/A` exige justificativa; campo vazio não é aceito.

```yaml
TASK_ID:
DATE:
BASE_COMMIT:
TASK_DESCRIPTION:
ROUTE: []
MODULES: []
FILES_ANALYZED: []
FILES_CHANGED: []
RISK_LEVEL:
AUTHORITY_LEVEL:
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE:
BUG_REPRODUCTION:
TESTS_BEFORE: []
TESTS_ADDED: []
TESTS_AFTER: []
STATIC_ANALYSIS:
BRANCH_COVERAGE:
MUTATION_RESULT:
PROPERTY_TEST_RESULT:
INTEGRATION_RESULT:
SCIENTIFIC_REGRESSION_RESULT:
GEOMETRIC_REGRESSION_RESULT:
BENCHMARK_BEFORE:
BENCHMARK_AFTER:
BEHAVIOR_CHANGE:
SCIENTIFIC_BEHAVIOR_CHANGE:
GEOMETRIC_BEHAVIOR_CHANGE:
KNOWN_LIMITATIONS: []
UNRESOLVED_RISKS: []
HUMAN_GATE:
APPROVAL_STATUS:
DIFF_SUMMARY:
ROLLBACK:
FINAL_STATUS:
```

## Regras

- Uma mudança semântica por pacote; não misture refatoração, atualização de dependência e mudança científica.
- Inclua comandos completos, exit codes, ambiente, hashes e denominadores.
- Distingua `NOT_RUN`, `NOT_AVAILABLE`, `NOT_APPLICABLE`, `FAILED` e `PASSED`.
- Resultados numéricos devem carregar unidade, tolerância, população e fonte.
- Approval deve citar gate, aprovador, data, escopo e contrato exato; “aprovado” genérico não cobre mudanças futuras.
- O pacote não pode conter PHI, credenciais, labels protegidos ou dumps de ambiente secretos.

