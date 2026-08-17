# EVIDENCE PACKAGE — TASK-2026-08-17-PH01-CARTO-03

```yaml
TASK_ID: TASK-2026-08-17-PH01-CARTO-03
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (worktree limpo)
TASK_DESCRIPTION: PHASE_01 wave 3 — runtime edges do SYSTEM_MAP provados por leitura dirigida; constantes científicas cruzadas com SCIENTIFIC_CONTRACTS.yaml. Report-only.
ROUTE: [PIPELINE (leitura), ORCHESTRATION (leitura), CONFIG_PROFILES (leitura), LOGGING_AUDIT_PROVENANCE (leitura)]
MODULES: [WEBAPP_API_ORCHESTRATION, SEGMENTATION_RUNTIME, CANDIDATE_LOCALIZATION, MEDGEMMA_INFERENCE, VOLUMETRY, VIEWER_ARTIFACTS_3D, CONFIG_PROFILES, ML_CLASSIFIERS_SPLITS, MEDSIGLIP_EMBEDDINGS]
FILES_ANALYZED:
  - webapp/server.py (trechos dirigidos), digital_twin.py, dtwin/engine.py
  - dtwin/segmentation_subprocess.py, dtwin/candidate_subprocess.py, dtwin/medgemma_client.py
  - dtwin/stages.py:43-51,155-210; dtwin/volumetry.py:151-178
  - dtwin/learning/{multiphase_ingest,visual_inference,medsiglip_embeddings}.py (trechos citados pelos contratos)
  - dtwin/benchmark/openswisshcc_alignment.py:60-92,432-457
  - profiles/figado.yaml; configs/training/{hybrid_v1_protocol.yaml,hybrid_v1_protocol.lock.json,medsiglip_frozen_v1.yaml,medsiglip_multiclass_v1.yaml}
  - viewer/app.js (consumo de manifesto)
  - .fable/SCIENTIFIC_CONTRACTS.yaml (integral, leitura)
FILES_CHANGED: []  # repositório intacto; pack ganhou RUNTIME_EDGES.md
RISK_LEVEL: LOW (report-only)
AUTHORITY_LEVEL: inspecionar e reportar; nenhum conflito arbitrado
CONTRACTS_INVOLVED: [ARGOS-SW-001 (leitura)]
SCIENTIFIC_CONTRACTS_INVOLVED: [SCI-001..013, GEO-001..004, DOM-001..002 — leitura; nenhum alterado]
BASELINE: PHASE_00 vigente; nenhuma execução com dados
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A]
STATIC_ANALYSIS: leitura dirigida com evidência file:line; resultados consolidados em RUNTIME_EDGES.md
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: NOT_APPLICABLE (prova estática; characterization fica p/ fases 03/05)
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Fiação provada estaticamente; nenhum edge exercitado com dados.
  - WebXR não exercitado em sessão real.
UNRESOLVED_RISKS:
  - "SCI-009: dimensão 1152 não é assertada em código/config — derivada do modelo e congelada só transitivamente (model_id+revision+manifests). Candidato a specification test na fase 04."
  - "GEO-002: 0.80 é default de parâmetro de função (2 call-site defaults), não constante de config — sensível a call sites; CONFLICT do contrato permanece aguardando decisão humana."
  - "SW-001 e DOM-002: CONFLICTs pré-existentes confirmados como descritos; nenhuma resolução tentada."
HUMAN_GATE: nenhum acionado; nenhum valor/semântica tocado
APPROVAL_STATUS: report-only dentro do escopo autorizado
DIFF_SUMMARY: >
  Pack: novo RUNTIME_EDGES.md (edges + tabela de constantes); TASK_CARD + este
  evidence; atualizações de estado/plano/handoff.
ROLLBACK: remover arquivos novos do pack e restaurar editados.
FINAL_STATUS: DONE
```

## Sumário dos resultados

- 13 runtime edges verificados (11 do fluxo web + 2 do CLI); 1 parcial (WebXR: fiação existe, sessão não exercitada).
- 18 verificações de constantes: 15 MATCH, 1 MATCH_TRANSITIVE (SCI-009 dim), 2 VERIFIED_AS_DESCRIBED (GEO-002, SW-001 — CONFLICTs pré-existentes confirmados, não resolvidos).
- Nenhuma divergência NOVA contrato-vs-código encontrada nas porções verificáveis.
