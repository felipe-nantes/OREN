# EVIDENCE PACKAGE — TASK-2026-08-18-PH04-INV-01

```yaml
TASK_ID: TASK-2026-08-18-PH04-INV-01
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em dfb36b5; teste novo NÃO commitado
TASK_DESCRIPTION: PHASE_04 wave 1 — GEO-CONVERT-01 como property test de round-trip, gerado via Hypothesis.
ROUTE: [GEOMETRY (invariant test), TESTS_BUILD_ENVIRONMENT]
MODULES: [CORE_IO_GEOMETRY, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/core.py:80-91 (array_from, array_to_image, CopyInformation)
  - tests/test_core_geometry.py (2 testes existentes, geometria fixa)
  - .fable/CONTRACTS.md (GEO-CONVERT-01, gap pré-flagged)
FILES_CHANGED:
  - tests/test_property_geometry_roundtrip.py (NOVO; 2 property tests via Hypothesis)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: PHASE_04 autorizada; instalação do Hypothesis autorizada explicitamente pelo humano
CONTRACTS_INVOLVED: [GEO-CONVERT-01]
SCIENTIFIC_CONTRACTS_INVOLVED: [nenhum editado]
BASELINE: suíte pré-instalação: 1 failed (ambiental) / 1626 passed / 4 skipped
BUG_REPRODUCTION: N/A (nenhum bug; invariante confirmado válido no código atual)
TESTS_BEFORE: ["tests/test_core_geometry.py: 2 testes com geometria fixa (identidade, oblíqua)"]
TESTS_ADDED:
  - "test_property_array_roundtrip_preserva_geometria_e_dados — @given spacing/origin/direction/voxels, 200 exemplos"
  - "test_property_array_to_image_ignora_geometria_do_array_de_entrada — idem, caso adversarial (array com geometria implícita divergente)"
TESTS_AFTER:
  - "arquivo isolado: 2 passed, 603 warnings, 0.90s (400 exemplos Hypothesis no total)"
  - "suíte completa: 1628 passed, 1 failed (pré-existente, ambiental), 4 skipped, 97.81s"
STATIC_ANALYSIS: NOT_APPLICABLE
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: >
  Mutação manual dirigida (não mutmut): array_to_image sem CopyInformation.
  Resultado: 2/2 testes FALHAM; Hypothesis reduz automaticamente ao
  contraexemplo mínimo (array de zeros 4x5x6, spacing (1,1,1) default).
  Prova o EXIT_CRITERIA da fase ("invariantes falham sob contraexemplos/
  mutações conhecidas"). Mutante não aplicado ao código real — só verificado
  em processo isolado e revertido.
PROPERTY_TEST_RESULT: PASSED (código real); FAILED sob mutação (esperado)
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE (nenhum código de produção alterado; ambiente ganhou 1 dependência de teste — hypothesis 6.165.10 + sortedcontainers 2.4.0)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Direções testadas via conjunto curado de 5 matrizes ortonormais (identidade, flips, permutação, rotação 30°), não geração aleatória de matrizes ortonormais arbitrárias — decisão deliberada para evitar reinventar geração de matrizes de rotação válidas; cobre os casos de aquisição reais do domínio (axial/coronal/sagital/flip/gantry tilt).
  - Shape fixo (4,5,6) para manter os testes rápidos; não testa arrays muito grandes ou 2D/4D.
UNRESOLVED_RISKS: []
HUMAN_GATE: >
  Instalação do Hypothesis no .venv-win autorizada explicitamente em 2026-08-18,
  revertendo o adiamento de ferramentas de 2026-08-17 especificamente para esta
  biblioteca (ferramenta de teste, não de análise estática).
APPROVAL_STATUS: dentro do escopo autorizado
DIFF_SUMMARY: 1 arquivo de teste novo (~85 linhas); ambiente com 2 pacotes novos (hypothesis, sortedcontainers)
ROLLBACK: deletar tests/test_property_geometry_roundtrip.py; pip uninstall hypothesis sortedcontainers (opcional, não requerido)
FINAL_STATUS: DONE (não commitado; commit quando solicitado)
```
