# TASK_CARD — TASK-2026-08-17-PH02-CONTRACTS-01

```yaml
TASK_ID: TASK-2026-08-17-PH02-CONTRACTS-01
TASK_DESCRIPTION: >
  PHASE_02 wave 1 — validar os 15 contratos não científicos do CONTRACTS.md
  (SW-ATOMIC/FAIL-CLOSED/ARTIFACT/HTTP/XR, GEO-IMAGE/CONVERT/MASK/LABEL/MESH,
  POL-RESEARCH/PHI/ENDPOINT/VOLUME/FAILURE) contra o código: evidência
  file:line, teste protetor localizado, status e lacunas. Report-only; os
  contratos científicos já foram ratificados/resolvidos em GOV-01.
TASK_TYPE: investigation / contract validation (report-only)
REQUESTED_OUTCOME: >
  CONTRACTS.md anotado com status VERIFIED/PARTIAL/GAP por contrato, testes
  protetores citados, lacunas de teste explícitas (insumo das fases 03-04),
  e owner designado.
FILES_DIRECTLY_MENTIONED: [.fable/CONTRACTS.md]
FILES_SUSPECTED: [dtwin/{core,volumetry,segmentation_contract,viewer_artifacts,medgemma_client,stages}.py, dtwin/benchmark/{reporting,runner}.py, dtwin/learning/{protocol,medsiglip_embeddings}.py, webapp/server.py, tests/]
PRIMARY_MODULE: cross-cutting (contratos)
SECONDARY_MODULES: [CORE_IO_GEOMETRY, VOLUMETRY, SEGMENTATION_RUNTIME, ARTIFACT_PROVENANCE, MEDGEMMA_INFERENCE, WEBXR_QUEST]
UPSTREAM_DEPENDENCIES: [PHASE_01 (mapas verificados), GOV-01 (científicos ratificados)]
DOWNSTREAM_DEPENDENCIES: [fases 03 (characterization) e 04 (invariants) usam as lacunas]
SCIENTIFIC_IMPACT: NONE_DIRECT (leitura; científicos não são tocados)
GEOMETRIC_IMPACT: NONE_DIRECT (leitura)
STATISTICAL_IMPACT: NONE_DIRECT
PRIVACY_IMPACT: LOW (código versionado)
SECURITY_IMPACT: NONE_DIRECT (leitura de contratos de segurança)
PERFORMANCE_IMPACT: NONE
RISK_LEVEL: LOW
AUTHORITY_LEVEL: inspecionar e reportar
REQUIRED_CONTEXT: [base obrigatória, CONTRACTS.md, RUNTIME_EDGES.md, SCIENTIFIC_CONTRACTS.yaml (ratificado)]
REQUIRED_REFERENCES: [TEST_STRATEGY.md se necessário]
REQUIRED_CONTRACTS: [os 15 não científicos — objeto da task]
REQUIRED_SCIENTIFIC_CONTRACTS: [nenhum editável; leitura de POL-* que apontam para o YAML]
BASELINE_REQUIRED: true (HEAD do snapshot; repo principal agora em bd278b5 com código idêntico a 9683eaa exceto skipif de 2 testes)
CHARACTERIZATION_REQUIRED: false
CONTRACT_TESTS_REQUIRED: false  # localizar testes existentes; criar testes é fase 03/04
PROPERTY_TESTS_REQUIRED: false
INTEGRATION_TESTS_REQUIRED: false
SCIENTIFIC_REGRESSION_REQUIRED: false
MUTATION_TESTING_REQUIRED: false
BENCHMARK_REQUIRED: false
ALLOWED_ACTIONS: [leitura dirigida/grep; anotar CONTRACTS.md; escrita em .fable/ e scratchpad]
FORBIDDEN_ACTIONS: [alterar código/configs; editar valores de contratos científicos; commit/push sem pedido]
HUMAN_GATE: nenhum (report-only)
STOP_CONDITIONS: [divergência grave contrato-vs-código que exija decisão científica]
EXPECTED_EVIDENCE_PACKAGE: CONTRACTS.md anotado + evidence package + estado/handoff
```

STATUS: DONE (2026-08-17) — 15/15 contratos validados (11 VERIFIED, 3 VERIFIED_OBSERVED, 1 by-composition); nenhuma divergência; lacunas de teste anotadas p/ fases 03-04. PHASE_02 encerrada junto (GOV-01 já cobrira ratificação/conflitos).
