# PHASE 01 — Cartography

STATUS: DONE (2026-08-17 — waves 1-4: TASK-2026-08-17-PH01-CARTO-01..04)

OBJECTIVE: provar arquitetura, data/artifact flows e reachability.  
INPUTS: Graphify, imports, CLIs, configs, subprocesses, docs, tests, history.  
TASKS: confirmar cada entrypoint; module/file dependency; scientific constants; runtime edges; legacy/duplication candidates.  
OUTPUTS: inventory/system/dependency/module maps versionados.  
ENTRY_CRITERIA: Phase 00 baseline sufficient.  
EXIT_CRITERIA: todos os paths críticos e edges runtime/data/scientific verificados; unknowns explicitados.  
EXIT_RESULT (2026-08-17): 8 entrypoints VERIFIED; grafo regenerado em 9683eaa com zero drift de código vs seed (evidence/PH01/graph_9683eaa.zip); 307 tools censados (`TOOLS_STATUS.md`); 13 runtime edges + 18 constantes científicas verificados (`RUNTIME_EDGES.md`; 15 MATCH, 2 CONFLICTs pré-existentes confirmados sem resolução); 20 edges estáticos do `DEPENDENCY_MAP.md` VERIFIED; 259/259 paths dos module cards existem. Unknowns consolidados no exit review (`tasks/TASK-2026-08-17-PH01-CARTO-04_EVIDENCE.md`): prova de execução com dados, WebXR real, reachability runtime dos órfãos, CI remoto, GRAPH_REPORT, CONFLICTs pendentes de decisão humana, spec test da dim 1152.  
BLOCKERS: ~~graph snapshot stale~~ (resolvido w1); ~~307 tools require status tracing~~ (resolvido w2).  
EVIDENCE: `CURRENT_STATE.md`; `tasks/TASK-2026-08-17-PH01-CARTO-0{1..4}_EVIDENCE.md`; `evidence/PH01/`; `TOOLS_STATUS.md`; `RUNTIME_EDGES.md`.
