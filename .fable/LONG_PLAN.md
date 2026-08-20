# Plano cumulativo de longa duração

Estados persistentes: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `AWAITING_HUMAN`, `DONE`. Cada fase tem card em `plans/`; somente critérios de saída objetivos permitem avanço.

| Phase | Status | Objective | Exit summary |
|---|---|---|---|
| 00 Freeze | DONE (2026-08-17) | baseline reproduzível | suíte global executada em container (2f/1605p/3s, falhas explicadas); doctor OK; static/perf adiados por decisão humana; evidência em `tasks/TASK-2026-08-17-PH00-BASELINE-01_EVIDENCE.md` |
| 01 Cartography | DONE (2026-08-17) | mapa exaustivo | 8 entrypoints, 13 runtime edges, 20 edges estáticos, 18 constantes, 307 tools e 259 paths de cards verificados; zero drift de código; unknowns consolidados no exit review (CARTO-04 evidence) |
| 02 Contracts | DONE (2026-08-17) | contratos por módulo | científicos ratificados/congelados sem CONFLICTs (HUMAN_DECISIONS.md); 15 não científicos validados com evidência+testes (CONTRACTS.md); owner: Felipe Nantes; lacunas de teste → fases 03-04 |
| 03 Characterization | IN_PROGRESS (2026-08-18) | safety net legado | waves 1-4 DONE — **os 4 P0s caracterizados**: #1 geometry equality (5 testes; direction-blind, candidata HG-03), #2 nested splits (7 testes; fronteira interna + defaults SCI-003), #3 DICOM phase selection (7 testes; 3 ambiguidades candidatas HG-02), #4 mask→volumetry provenance (já coberto por 6 testes existentes + 1 novo; 3ª ocorrência direction-blind em stage5_refine, candidata HG-03) |
| 04 Invariants | DONE (2026-08-18) | specification/property | **11 contratos com invariante executável**, 61 testes novos, 8 mutantes dirigidos detectados, 2 auditorias estruturais AST; âncoras numéricas verificadas por reimplementação independente; exit review em INV-05 evidence |
| 05 Integration | DONE (2026-08-18) | fronteiras reais | 13 testes de integração em 3 arquivos: subprocess real (exit 2), runtime NUL reparado, corrupção fail-closed, uvicorn real, concorrência (achado TD-015), cadeia DICOM→harmonização com pixels reais; sucesso GPU-bound validado manualmente; blockers declarados; exit review em INT-03 evidence |
| 06 Scientific regression | DONE (2026-08-18) | datasets mínimos | reconciliação 451/16 FECHADA (ledger+OOF íntegros, cadeia assinada); tolerâncias por backend MEDIDAS (delta ZERO bitwise CPU) e RATIFICADAS (HUMAN_DECISIONS bloco 3); blockers declarados: fontes protegidas ausentes, GPU não sondada |
| 07 Adversarial | DONE (2026-08-19) | força dos gates | núcleo 82,6→89,5% branch; 15/15 mutantes KILLED (SCI-003/004/013, GEO-004, gates); 59 testes negativos; estático de defeito real triado (7×B023 benignos); S5/S6/G8/G9 justificados; exit review em TASK-2026-08-19-PH07-EXIT.md |
| 08 Low-risk refactor | DONE (2026-08-19) | pequenas melhorias | TD-015/TD-007 RESOLVED com testes; mypy robustness e 7×B023 zerados; 819 safe fixes mecânicos (731→2, residuais justificados); portões idênticos 1768/4/1-ambiental — zero regressões em ~830 mudanças; exit review em TASK-2026-08-19-PH08-EXIT.md |
| 09 High-risk review | DONE (2026-08-20) | propostas governadas | 3 mudanças semânticas, 3 decisões formais (HUMAN_DECISIONS 13-15): direction nos comparadores (HG-03), auditoria do manifesto DICOM (HG-02, TD-014 RESOLVED), remoção do seg_worker legado; ingest inocentado; 4/4 mutantes KILLED; portões idênticos; exit review em TASK-2026-08-20-PH09-EXIT.md |
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

