# Plano cumulativo de longa duração

Estados persistentes: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `AWAITING_HUMAN`, `DONE`. Cada fase tem card em `plans/`; somente critérios de saída objetivos permitem avanço.

| Phase | Status | Objective | Exit summary |
|---|---|---|---|
| 00 Freeze | DONE (2026-08-17) | baseline reproduzível | suíte global executada em container (2f/1605p/3s, falhas explicadas); doctor OK; static/perf adiados por decisão humana; evidência em `tasks/TASK-2026-08-17-PH00-BASELINE-01_EVIDENCE.md` |
| 01 Cartography | DONE (2026-08-17) | mapa exaustivo | 8 entrypoints, 13 runtime edges, 20 edges estáticos, 18 constantes, 307 tools e 259 paths de cards verificados; zero drift de código; unknowns consolidados no exit review (CARTO-04 evidence) |
| 02 Contracts | NOT_STARTED | contratos por módulo | observed vs approved separados |
| 03 Characterization | NOT_STARTED | safety net legado | comportamento incerto reproduzível |
| 04 Invariants | NOT_STARTED | specification/property | contratos discriminados por testes |
| 05 Integration | NOT_STARTED | fronteiras reais | pipelines e falhas/resume cobertos |
| 06 Scientific regression | NOT_STARTED | datasets mínimos | lógica e tolerância numérica separadas |
| 07 Adversarial | NOT_STARTED | força dos gates | branch/mutation/fault/static analisados |
| 08 Low-risk refactor | NOT_STARTED | pequenas melhorias | patch behavior-preserving comprovado |
| 09 High-risk review | NOT_STARTED | propostas governadas | decisão humana por mudança semântica |
| 10 Consolidation | NOT_STARTED | baseline final | mapas/contratos/evidências atualizados |

## Fila inicial recomendada — não executar automaticamente

Prioridade = impacto × risco de falha silenciosa × importância científica × alcance downstream × lacuna de cobertura, ponderada por testabilidade.

1. **P0 geometry equality/resampling**: `webapp/server.py`, `dtwin/stages.py`, `multiphase_ingest.py`; há caminhos que não comparam direction. HIGH, HG-03/04.
2. **P0 patient leakage/nested CV**: splits/classifiers/protocols/OOF. HIGH, HG-06/07/08.
3. **P0 DICOM selection/deidentification**: raw resolver, CLI `read_dicom_series`, retained raw upload. HIGH, HG-02/11.
4. **P0 mask→volumetry provenance**: shadow/union/refine source, gates and approval. HIGH, HG-05/10.
5. **P1 artifact/cache identity/atomicity**: embeddings, reports, resume/checkpoints. MEDIUM→HIGH.
6. **P1 Etapa C reproduction**: exact 467 ledger, OOF, metrics/CI/config. HIGH, HG-01/06/07/08/09.
7. **P1 viewer quantitative correctness**: mask vs mesh, units, LOD/clipping. HIGH, HG-03/10.
8. **P1 job concurrency/backpressure/restart**: webapp threads/uploads/state. MEDIUM.
9. **P2 architecture seams**: separate runtime from research namespaces and monoliths. LOW/MEDIUM only after contracts.
10. **P2 legacy/dead candidates**: prove reachability before removal.

## Definition of Done de qualquer task

`ROUTE_COMPLETED`; `RISK_CLASSIFIED`; `CONTRACTS_IDENTIFIED`; `BASELINE_CAPTURED`; testes apropriados presentes; autoridade respeitada; pós-testes passam; invariantes, regressões científicas/geométricas, static/mutation/benchmark aplicáveis satisfeitos; aprovação registrada; evidence package completo; `CURRENT_STATE` atualizado.

