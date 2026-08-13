## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

### ARGOS runtime

Graphify is isolated from the project Python environment. On Windows, invoke it
through `tools/graphify_argos.ps1` instead of assuming `graphify` is on `PATH`:

- query: `powershell -ExecutionPolicy Bypass -File tools/graphify_argos.ps1 -Action Query -Question "..."`
- explain: `powershell -ExecutionPolicy Bypass -File tools/graphify_argos.ps1 -Action Explain -Question "..."`
- path: `powershell -ExecutionPolicy Bypass -File tools/graphify_argos.ps1 -Action Path -From "A" -To "B"`
- update: `powershell -ExecutionPolicy Bypass -File tools/graphify_argos.ps1 -Action Update`

The Graphify graph is engineering-only. Never add medical datasets, DICOM,
NIfTI, lesion masks, case outputs, or protected benchmark labels to it. It is
separate from the clinical metadata GraphRAG under `dtwin/graphrag`.
