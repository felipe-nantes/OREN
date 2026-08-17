# EVIDENCE PACKAGE — TASK-2026-08-17-CHG-02 (regeneração code-only do graphify-out versionado)

```yaml
TASK_ID: TASK-2026-08-17-CHG-02
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141 (mudança aplicada na árvore do repo principal, não commitada)
TASK_DESCRIPTION: >
  Substituir o graphify-out/ versionado (construído sem --code-only, com 2.772
  nós de documento, violando a política de tools/graphify_argos.ps1:25-26) pela
  extração code-only reproduzível do snapshot congelado. Autorizado em
  HUMAN_DECISIONS.md item 5.
ROUTE: [DOCKER_DEPLOYMENT (execução), LOGGING_AUDIT_PROVENANCE (artefato derivado)]
MODULES: [cross-cutting]
FILES_ANALYZED: [tools/graphify_argos.ps1, docker/Dockerfile.graphify, graphify-out/* (seed)]
FILES_CHANGED:
  - graphify-out/graph.json (7.644 nós/24.909 arestas/311 comunidades; code-only)
  - graphify-out/graph.html (regenerado com GRAPHIFY_VIZ_NODE_LIMIT=12000)
  - graphify-out/GRAPH_REPORT.md (regenerado; nomes de comunidade por hub/placeholder — sem LLM)
  - graphify-out/manifest.json (cache de hashes da extração nova)
  - graphify-out/GRAPH_TREE.html (REMOVIDO — derivado do grafo antigo com nós de documento; ABRIR_GRAPHIFY.cmd tem fallback para graph.html)
RISK_LEVEL: LOW (artefato derivado; nenhum código executável)
AUTHORITY_LEVEL: autorizado pelo humano (HUMAN_DECISIONS.md item 5)
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE:
  SEED: "10.429 nós/27.519 arestas/597 comunidades @ fec93d77 (inclui 2.772 nós document)"
  NOVO: "código idêntico ao seed (6.757 code + 855 rationale); zero drift comprovado na wave 1"
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A — artefato derivado; verificação = contagens e sha256]
STATIC_ANALYSIS: >
  Comandos (containers argos-graphify:local, --network none, mounts ro):
  1) extract . --code-only --max-workers 4  → graph.json 7.644/24.909
  2) cluster-only /workspace                → GRAPH_REPORT.md (aviso: sem LLM backend, nomes placeholder/hub)
  3) cluster-only com GRAPHIFY_VIZ_NODE_LIMIT=12000 → graph.html regenerado
  sha256 do graph.json de extração registrado em evidence/PH01/graph_9683eaa_sha256.txt
  (2ccaf65ab9b73f5c8a3f3742417cefc59329032353c58b0955b1cec06084b978; o graph.json
  final difere por conter clustering/labels do passo 2-3).
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: >
  Nenhum runtime afetado. O grafo versionado passa a cumprir a política
  code-only (zero nós de documento). GRAPH_TREE.html deixa de existir até nova
  geração (launcher usa graph.html).
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Nomes de comunidade são placeholder/hub (sem LLM, por política de rede); "graphify label" com backend LLM pode renomeá-los no futuro, sob decisão.
  - built_at_commit ausente no grafo (worktree .git é ponteiro); commit registrado aqui.
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum HG científico; autorização humana registrada (item 5)
APPROVAL_STATUS: aprovado por Felipe Nantes, 2026-08-17
DIFF_SUMMARY: 4 arquivos substituídos + 1 removido em graphify-out/
ROLLBACK: git checkout -- graphify-out  (restaura o seed antigo)
FINAL_STATUS: DONE (não commitado; commit separado quando solicitado)
```
