# EVIDENCE PACKAGE — TASK-2026-08-17-PH02-CONTRACTS-01

```yaml
TASK_ID: TASK-2026-08-17-PH02-CONTRACTS-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: >
  código = 9683eaa + skipif (0ba6f01) + graphify (bd278b5); pack em 7efa2dc+.
  Verificações feitas no worktree congelado 9683eaa (código Python idêntico).
TASK_DESCRIPTION: PHASE_02 wave 1 — validação dos 15 contratos não científicos do CONTRACTS.md com evidência file:line, teste protetor e status; owner designado.
ROUTE: [contratos cross-cutting; leitura em CORE/VOLUMETRY/SEGMENTATION/PROVENANCE/MEDGEMMA/WEBXR]
MODULES: [CORE_IO_GEOMETRY, VOLUMETRY, SEGMENTATION_RUNTIME, ARTIFACT_PROVENANCE, MEDGEMMA_INFERENCE, WEBXR_QUEST, BENCHMARK_METRICS_REPORTING]
FILES_ANALYZED:
  - dtwin/benchmark/reporting.py, dtwin/learning/protocol.py (atomicidade)
  - dtwin/medgemma_client.py (contrato HTTP), webapp/server.py (XR/allowlist/research_only)
  - dtwin/core.py, dtwin/segmentation_contract.py, dtwin/volumetry.py (geometria)
  - dtwin/learning/visual_inference.py, .gitignore, profiles/figado.yaml (políticas)
FILES_CHANGED: []  # repositório intacto; CONTRACTS.md do pack anotado
RISK_LEVEL: LOW (report-only)
AUTHORITY_LEVEL: inspecionar e reportar
CONTRACTS_INVOLVED: [SW-ATOMIC-01, SW-FAIL-CLOSED-01, SW-ARTIFACT-01, SW-HTTP-01, SW-XR-01, GEO-IMAGE-01, GEO-CONVERT-01, GEO-MASK-01, GEO-LABEL-01, GEO-MESH-01, POL-RESEARCH-01, POL-PHI-01, POL-ENDPOINT-01, POL-VOLUME-01, POL-FAILURE-01]
SCIENTIFIC_CONTRACTS_INVOLVED: [referências cruzadas aos ratificados (SCI-004/011, GEO-004); nenhum editado]
BASELINE: PHASE_00 vigente; suíte verde nos dois backends após CHG-01
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A]
STATIC_ANALYSIS: greps dirigidos + leitura; resultados na tabela de verificação do CONTRACTS.md
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE (lacunas anotadas para fase 04)
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Verificação de mecanismo, não prova exaustiva de execução (fase 03/05).
  - GEO-LABEL-01: auditoria de TODOS os call sites de resample fica para fase 04.
UNRESOLVED_RISKS:
  - "Lacunas de teste anotadas: SW-ATOMIC parcial-exposto; GEO-CONVERT round-trip property; GEO-LABEL auditoria exaustiva — insumos diretos das fases 03-04."
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: report-only dentro do escopo
DIFF_SUMMARY: pack — tabela de verificação adicionada ao CONTRACTS.md; owner designado (Felipe Nantes)
ROLLBACK: restaurar CONTRACTS.md anterior
FINAL_STATUS: DONE
```

## Resultado

15/15 contratos com evidência localizada e teste protetor identificado: 11 VERIFIED, 3 VERIFIED_OBSERVED (fail-closed, PHI, label-resampling — mecanismo presente, exaustividade pendente), 1 VERIFIED_BY_COMPOSITION (GEO-IMAGE-01). Nenhuma divergência contrato-vs-código encontrada.
