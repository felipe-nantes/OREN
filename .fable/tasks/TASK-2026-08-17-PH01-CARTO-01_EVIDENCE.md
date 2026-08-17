# EVIDENCE PACKAGE — TASK-2026-08-17-PH01-CARTO-01

```yaml
TASK_ID: TASK-2026-08-17-PH01-CARTO-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (verificado no início e fim; worktree limpo)
TASK_DESCRIPTION: PHASE_01 wave 1 — refresh do grafo Graphify no commit congelado + verificação de entrypoints do SYSTEM_MAP.
ROUTE: [ARCHITECTURE (cartografia, report-only), DOCKER_DEPLOYMENT, TESTS_BUILD_ENVIRONMENT]
MODULES: [cross-cutting, DOCKER_LAUNCHERS, WEBAPP_API_ORCHESTRATION]
FILES_ANALYZED:
  - tools/graphify_argos.ps1 (invocação canônica)
  - docker/Dockerfile.graphify, compose.yaml (serviço graphify)
  - graphify-out/graph.json (seed versionado, apenas leitura)
  - pyproject.toml, digital_twin.py, dtwin/{engine,stages,core,volumetry}.py
  - webapp/server.py (import), webapp/static/*, viewer/*, INICIAR_OREN.cmd
  - dtwin/segmentation_subprocess.py, dtwin/seg_worker.py, webapp/seg_worker.py
FILES_CHANGED: []  # repositório intacto; apenas pack .fable/
RISK_LEVEL: LOW
AUTHORITY_LEVEL: investigação/report dentro da autoridade; fase autorizada pelo humano em 2026-08-17
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE: PHASE_00 vigente (container canônico; HEAD imutável durante a task)
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [baseline PHASE_00: 2f/1605p/3s no container]
TESTS_ADDED: []
TESTS_AFTER: [N/A — nenhuma mudança de código]
STATIC_ANALYSIS: >
  Graphify 0.9.42 (imagem argos-graphify:local), container --network none, mounts ro:
  RUN_A (mounts do serviço compose): 5.103 nós / 17.300 arestas / 224 comunidades (563 code files)
  RUN_B (raiz completa do worktree, CANÔNICO): 7.644 nós / 24.909 arestas / 308 comunidades (828 code files)
  Comando: docker run --rm --network none -w /workspace -v <worktree>:/workspace:ro
           -v <out>:/workspace/graphify-out argos-graphify:local extract . --code-only --max-workers 4
  graph.json sha256: 2ccaf65ab9b73f5c8a3f3742417cefc59329032353c58b0955b1cec06084b978 (evidence/PH01/graph_9683eaa.zip)
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: >
  Imports verificados em container runtime ro/offline: digital_twin.main callable;
  dtwin.{engine,stages,core,volumetry}; webapp.server.app é FastAPI;
  dtwin.learning.{raw_dicom_phase_resolver,multiphase_ingest} — todos IMPORTS_OK.
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - built_at_commit=None no grafo novo (o .git do worktree é ponteiro e não resolve no container); commit registrado aqui manualmente.
  - cluster-only/GRAPH_REPORT não regenerado (nomeação de comunidades pode requerer LLM/rede; política desta task era network none) — DEFERRED.
  - Reachability é estática (AST/imports); edges de runtime (subprocess/HTTP/artefatos) não são provados por esta wave.
UNRESOLVED_RISKS:
  - "POLÍTICA: o seed versionado graphify-out/graph.json contém 2.772 nós document (docs/, contexto/, READMEs), contrariando o comentário code-only de tools/graphify_argos.ps1:25-26. Decidir se o grafo versionado deve ser regenerado code-only (mudança LOW em artefato versionado — requer autorização)."
  - "LEGACY: webapp/seg_worker.py (42 linhas) não tem NENHUMA referência de entrada no código Python; o runtime copia dtwin/seg_worker.py (29 linhas, divergente) via dtwin/segmentation_subprocess.py:94-95. Candidato forte a LEGACY_AND_DEAD_CODE_CANDIDATES; remoção só em fase própria com prova de reachability runtime."
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: report-only dentro do escopo autorizado
DIFF_SUMMARY: >
  Repositório: nenhum. Pack: TASK_CARD + este evidence + evidence/PH01/
  (graph zip + sha256) + atualizações de CURRENT_STATE/LONG_PLAN/plan card/SYSTEM_MAP (anotação de verificação).
ROLLBACK: remover arquivos novos do pack e restaurar os editados pela versão anterior.
FINAL_STATUS: DONE
```

## Resultados de verificação (wave 1)

### Grafo: seed vs refresh

| Métrica | SEED @ fec93d77 | NOVO @ 9683eaa (canônico) | Explicação |
|---|---|---|---|
| Nós | 10.429 | 7.644 | seed inclui 2.772 nós `document` + 13 `concept` extras |
| Nós `code` | 6.757 | 6.757 | **idênticos** |
| Nós `rationale` | 855 | 855 | **idênticos** |
| Arestas | 27.519 | 24.909 | diferença atribuível aos nós de documento |
| Arquivos | 1.071 | 819 | 252 só no seed: docs/ (234), contexto/, READMEs, benchmarks |
| Arquivos só no NOVO | — | 0 | nenhum código novo/removido |

Conclusão: **zero drift de código** entre o seed e o commit congelado; o "stale" era só metadado/documentos. A base arquitetural do pack permanece válida.

### Entrypoints (SYSTEM_MAP → status)

| Entrypoint | Verificação | Status |
|---|---|---|
| CLI `digital-twin` | `[project.scripts]` → `digital_twin:main` callable | VERIFIED |
| Engine clássico | `dtwin/engine.py` + `dtwin/stages.py` importam | VERIFIED |
| FastAPI | `webapp.server.app` importa como FastAPI (container ro/offline) | VERIFIED |
| Frontend | index/benchmark.html, argos.css, oren-motion.js existem | VERIFIED |
| Viewer desktop | viewer/index.html, app.js, argos-viewer.css existem | VERIFIED |
| WebXR | viewer/xr.js + webapp/static/quest/ existem | VERIFIED |
| Docker | compose*.yaml, docker/, INICIAR_OREN.cmd → run_win.ps1 (existe) | VERIFIED |
| Research CLIs | tools/ = 325 arquivos, 307 code no grafo (18 não-código) | VERIFIED (status individual: wave futura) |

### Unknowns explícitos (exigência do exit criteria)

1. Status individual dos 307 scripts de `tools/` (ativo/experimental/morto) — wave dedicada.
2. Edges de runtime (subprocess launch, HTTP interno, escrita/leitura de artefatos) — prova estática não basta; requer characterization em fase 03/05.
3. `webapp/seg_worker.py` — reachability runtime não provada (estaticamente órfão).
4. Estado real do CI remoto neste commit (gh ausente no host).
5. GRAPH_REPORT/comunidades nomeadas — deferido (possível dependência de LLM/rede).
