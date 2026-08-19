# PHASE 04 — Specification / invariants

STATUS: DONE (2026-08-18 — waves 1-5, TASK-2026-08-18-PH04-INV-01..05)

EXIT_RESULT (2026-08-18): 11 contratos com invariante executável (GEO-CONVERT-01,
GEO-LABEL-01, SW-ATOMIC-01, SW-ARTIFACT-01, SW-FAIL-CLOSED-01, SW-HTTP-01,
SW-XR-01, POL-PHI-01, ARGOS-SCI-003/008, ARGOS-SCI-013, ARGOS-SCI-004);
61 testes novos em 6 arquivos test_property_*; 8 mutantes dirigidos detectados
(CopyInformation removido, resample linear em label, escrita não-atômica,
agrupamento por exame, Wald por Wilson, exclusão de falhas do denominador,
aceita-qualquer-contrato); 2 auditorias estruturais AST vigiam call sites
novos. Exit review completo em tasks/TASK-2026-08-18-PH04-INV-05_EVIDENCE.md.

OBJECTIVE: encode approved contracts and general properties.  
INPUTS: ratified contracts, standards, characterization findings.  
TASKS: contract, negative, edge and Hypothesis-style property tests for geometry, DICOM, cache, splits, metrics and artifacts.  
OUTPUTS: tests citing contract IDs and discriminating relevant mutations.  
ENTRY_CRITERIA: contract authority known.  
EXIT_CRITERIA: critical invariants fail under known counterexamples/mutations.  
BLOCKERS: unknown scientific contract or unavailable fixtures/tooling.  
EVIDENCE: before/after failure demonstrations.  

