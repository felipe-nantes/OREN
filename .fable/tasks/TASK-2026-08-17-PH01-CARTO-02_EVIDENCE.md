# EVIDENCE PACKAGE — TASK-2026-08-17-PH01-CARTO-02

```yaml
TASK_ID: TASK-2026-08-17-PH01-CARTO-02
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (worktree limpo durante toda a task)
TASK_DESCRIPTION: PHASE_01 wave 2 — status estático dos 307 scripts de tools/ por referências cruzadas; nenhum script executado.
ROUTE: [DEAD_CODE_DUPLICATION (mapeamento, sem remoção), TESTS_BUILD_ENVIRONMENT]
MODULES: [cross-cutting, TEST_SUITE, DOCKER_LAUNCHERS]
FILES_ANALYZED: [tools/ (307 code), corpus de 1.239 arquivos-texto do worktree (py/ps1/cmd/sh/yaml/toml/json/md/html/js/css)]
FILES_CHANGED: []  # repositório intacto; pack ganhou TOOLS_STATUS.md
RISK_LEVEL: LOW
AUTHORITY_LEVEL: report-only dentro da autoridade
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE: PHASE_00 vigente; nenhum código tocado
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A]
STATIC_ANALYSIS: >
  Script auxiliar (host Python 3.13, stdlib): para cada tool, contagem de
  referências por caminho completo (tools/<x>, caminhos normalizados), import
  (tools.<x>) e basename com fronteira de palavra, categorizada por origem
  (RUNTIME dtwin/webapp/viewer/digital_twin.py; LAUNCH docker/CI/configs/
  launchers; TESTS; TOOLS; DOCS). Corpus exclui .git e graphify-out (o grafo
  contém todos os nomes e geraria falso positivo).
  Resultado: 13 RUNTIME_OR_LAUNCH_WIRED, 27 TEST_REFERENCED_ONLY,
  23 TOOLCHAIN_ONLY, 87 DOC_REFERENCED_ONLY, 157 STATIC_ORPHAN (total 307).
  Confiança: 147 STRONG, 3 WEAK (build_lld_mmri_v23_enhancement_panels.py,
  download_http_ranges.py, smoke_test_argos_docker_e2e.py), 157 NONE (órfãos).
  Validação: sanity dos wired (medgemma_server←compose, graphify_argos←ABRIR_GRAPHIFY.cmd,
  quest_network/serve_quest_certificate←launchers Quest); amostragem de órfãos com
  grep amplo = zero refs; nenhum padrão subprocess/importlib→tools no runtime.
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: NOT_APPLICABLE (nenhum script executado, por regra da task)
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Invocação dinâmica por string construída não é detectável estaticamente (mitigado por amostragem).
  - Referências fora do repo (shells de operador, notebooks externos, histórico git) não contam.
  - STATIC_ORPHAN ≠ morto: tools são CLIs de operador; ausência de referência não prova inutilidade.
UNRESOLVED_RISKS:
  - "157 órfãos estáticos (51% de tools/) — superfície grande de possível legacy; qualquer remoção exige prova de reachability runtime, fase própria (LONG_PLAN item 10) e autorização."
  - "medgemma_server_v14.py é TEST_REFERENCED_ONLY enquanto medgemma_server.py é o wired — par de versões a revisar em dead-code phase."
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: report-only dentro do escopo autorizado
DIFF_SUMMARY: >
  Pack: novo mapa versionado TOOLS_STATUS.md; evidence/PH01/tools_status_9683eaa.csv
  + ph01_tools_status.py (gerador); TASK_CARD + este evidence; atualização de
  estado/plano/handoff; nota em LEGACY_AND_DEAD_CODE_CANDIDATES.md.
ROLLBACK: remover os arquivos novos e restaurar os editados.
FINAL_STATUS: DONE
```
