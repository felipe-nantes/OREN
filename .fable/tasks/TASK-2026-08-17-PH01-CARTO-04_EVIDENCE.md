# EVIDENCE PACKAGE — TASK-2026-08-17-PH01-CARTO-04

```yaml
TASK_ID: TASK-2026-08-17-PH01-CARTO-04
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (worktree limpo)
TASK_DESCRIPTION: PHASE_01 wave 4 (final) — verificação de DEPENDENCY_MAP.md e module cards; exit review da fase.
ROUTE: [ARCHITECTURE (cartografia, report-only), DEPENDENCIES (leitura)]
MODULES: [cross-cutting; todos os 24 module cards superficialmente]
FILES_ANALYZED:
  - .fable/DEPENDENCY_MAP.md (integral)
  - .fable/modules/*.md (24 cards, extração programática de paths; VOLUMETRY.md lido integralmente como amostra)
  - importadores citados pelos edges (digital_twin.py, dtwin/{__init__,engine,stages,core}.py, webapp/server.py, dtwin/learning/*, via regex dirigida)
FILES_CHANGED: []  # repositório intacto; pack anotado
RISK_LEVEL: LOW
AUTHORITY_LEVEL: report-only; encerramento de fase por critérios objetivos (permitido pelo LONG_PLAN); avanço para PHASE_02 permanece com o humano
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE: PHASE_00 vigente
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A]
STATIC_ANALYSIS: >
  (a) 20 edges estáticos do DEPENDENCY_MAP verificados por regex de import nos
  arquivos importadores: 20/20 VERIFIED (script evidence/PH01/ph01_depmap_check.py).
  (b) Module cards: 259 paths extraídos dos 24 cards; 259/259 existem no
  worktree (script evidence/PH01/ph01_cards_check.py). Único token não
  encontrado ("benchmarks/fallback", MEDGEMMA_INFERENCE.md:24) é prosa, não path.
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Cards verificados por existência de paths + amostra de leitura; o conteúdo semântico integral dos 24 cards não foi re-auditado linha a linha.
  - Toda a cartografia é estática/fiação; prova de execução com dados fica para as fases 03/05 (como o próprio plan card enquadra).
UNRESOLVED_RISKS: [herdados das waves 1-3; nenhum novo]
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: report-only dentro do escopo autorizado
DIFF_SUMMARY: >
  Pack: anotação de verificação no DEPENDENCY_MAP.md; scripts arquivados em
  evidence/PH01/; exit review no plan card PHASE_01; estado/plano/handoff atualizados.
ROLLBACK: remover anotações/arquivos novos do pack.
FINAL_STATUS: DONE
```

## EXIT REVIEW — PHASE_01_CARTOGRAPHY

EXIT_CRITERIA: "todos os paths críticos e edges runtime/data/scientific verificados; unknowns explicitados."

| Critério | Cobertura | Evidência |
|---|---|---|
| Entrypoints confirmados | 8/8 VERIFIED | wave 1 (CARTO-01) |
| Grafo/módulos no commit congelado | regenerado, zero drift de código vs seed | wave 1; evidence/PH01/graph_9683eaa.zip |
| Status dos 307 tools | censo completo em TOOLS_STATUS.md | wave 2 (CARTO-02) |
| Runtime edges (subprocess/HTTP/data) | 13 VERIFIED com file:line (1 parcial: WebXR não exercitado) | wave 3; RUNTIME_EDGES.md |
| Constantes/cadeias científicas | 18 verificações: 15 MATCH, 1 MATCH_TRANSITIVE, 2 CONFLICTs pré-existentes confirmados | wave 3 |
| Dependency map (STATIC) | 20/20 edges VERIFIED | wave 4 |
| Module cards | 259/259 paths existem | wave 4 |
| Legacy/duplication candidates | seg_worker órfão, medgemma_server_v14, 157 tools órfãos, graph doc-nodes | waves 1-2; LEGACY adendo |
| Unknowns explicitados | sim — consolidados abaixo | todas as waves |

### Unknowns consolidados da fase (permanecem abertos, por design)

1. Prova de EXECUÇÃO dos edges com dados reais (fases 03/05).
2. Sessão WebXR/Quest real não exercitada.
3. Reachability runtime dos 157 tools órfãos e do webapp/seg_worker.py.
4. Estado do CI remoto no commit (gh ausente).
5. GRAPH_REPORT/comunidades nomeadas (possível dependência LLM/rede).
6. CONFLICTs GEO-002/SW-001/DOM-002 e reconciliação 451/16 — decisões humanas pendentes.
7. Dimensão 1152 (SCI-009) sem assert direto — candidata a spec test na fase 04.

VEREDITO: EXIT_CRITERIA satisfeitos no escopo estático/fiação que a fase define. **PHASE_01 = DONE.**
