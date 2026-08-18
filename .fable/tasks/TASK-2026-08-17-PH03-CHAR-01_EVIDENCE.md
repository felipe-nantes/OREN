# EVIDENCE PACKAGE — TASK-2026-08-17-PH03-CHAR-01

```yaml
TASK_ID: TASK-2026-08-17-PH03-CHAR-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: main em bd278b5 (código científico = 9683eaa); teste novo NÃO commitado
TASK_DESCRIPTION: >
  PHASE_03 wave 1 — characterization tests da P0 #1 (geometry equality):
  fixar o comportamento atual dos 3 comparadores de geometria, incluindo a
  divergência direction-blind do webapp. OBSERVED_BEHAVIOR; nenhum código de
  produção alterado.
ROUTE: [GEOMETRY (characterization), TESTS_BUILD_ENVIRONMENT]
MODULES: [CORE_IO_GEOMETRY, TEST_SUITE, WEBAPP_API_ORCHESTRATION, VOLUMETRY, SEGMENTATION_RUNTIME]
FILES_ANALYZED:
  - webapp/server.py:907-908 (comparador exato, sem direction), :984 (gate da união de fases), :970-994 (contexto da união em array space)
  - dtwin/segmentation_contract.py:109-122 (size exato; spacing/origin/direction atol=1e-5)
  - dtwin/volumetry.py:82-88 (idem)
FILES_CHANGED:
  - tests/test_characterization_geometry_equality.py (NOVO; 5 testes; phantoms sintéticos sitk; sem PHI/GPU)
RISK_LEVEL: LOW (somente teste novo; characterization permitida pelo TASK_PROTOCOL)
AUTHORITY_LEVEL: fase autorizada pelo humano em 2026-08-17
CONTRACTS_INVOLVED: [GEO-MASK-01, GEO-IMAGE-01 (leitura)]
SCIENTIFIC_CONTRACTS_INVOLVED: [nenhum editado]
BASELINE: suíte verde nos 2 backends (pós-CHG-01); os 5 testes novos não alteram nenhum existente
BUG_REPRODUCTION: >
  A divergência (webapp aceita direction divergente) é reproduzida
  deterministicamente pelo teste test_observed_server_ignora_direction_...
TESTS_BEFORE: [comparadores sem teste dedicado de igualdade geométrica cruzada]
TESTS_ADDED:
  - tests/test_characterization_geometry_equality.py::test_observed_server_ignora_direction_mas_contract_e_volumetry_nao
  - ::test_observed_server_rejeita_divergencia_de_size_spacing_origin
  - ::test_observed_server_usa_igualdade_exata_sem_tolerancia
  - ::test_observed_contract_e_volumetry_respeitam_atol_1e_5
  - ::test_observed_direction_dentro_da_tolerancia_e_aceita_pelos_estritos
TESTS_AFTER:
  - "host Windows (.venv-win): 5 passed, 0.48s"
  - "container POSIX (argos-runtime:local, worktree ro + tests/ do main como overlay): 5 passed, 1.82s"
STATIC_ANALYSIS: NOT_RUN (adiado por decisão)
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE (fase 07)
PROPERTY_TEST_RESULT: NOT_APPLICABLE (fase 04)
INTEGRATION_RESULT: NOT_APPLICABLE (característica de unidade; união end-to-end fica p/ fase 05)
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE (nenhuma mudança)
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE (somente proteção)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Characterization cobre os comparadores; o caminho completo da união de fases (subprocess+segmentação) não é exercitado (fase 05).
  - Comportamento fixado ≠ comportamento correto; decisão sobre unificar comparadores é HG-03 (fase 09).
UNRESOLVED_RISKS:
  - "CANDIDATA HG-03 (fase 09): unificar os comparadores — o gate da união de fases (server.py:984) aceita máscara com direction divergente e faz OR em array space; risco de união geometricamente inválida silenciosa. Agora protegido por characterization: qualquer mudança quebra o teste e força decisão explícita."
HUMAN_GATE: nenhum acionado; candidata HG-03 registrada
APPROVAL_STATUS: dentro do escopo autorizado da fase
DIFF_SUMMARY: 1 arquivo de teste novo (89 linhas); pack atualizado
ROLLBACK: deletar tests/test_characterization_geometry_equality.py
FINAL_STATUS: DONE (teste não commitado; commit quando solicitado)
```
