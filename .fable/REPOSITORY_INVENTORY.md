# Inventário do repositório

## Snapshot versionado

1.267 paths. Distribuição principal: `tools` 307, `tests` 258, `dtwin` 251, `docs` 247, `configs` 121, `viewer` 16, `webapp` 12, `contexto` 12.

| Path | Classificação | Conteúdo / observação |
|---|---|---|
| `digital_twin.py` | PRODUCTION | CLI fina |
| `dtwin/core.py`, `engine.py`, `stages.py` | PRODUCTION research-only | motor clássico |
| `dtwin/segmentation_*`, `seg_worker.py` | PRODUCTION + EXPERIMENTAL_INTEGRATED | subprocess/gates/shadow |
| `dtwin/volumetry.py`, `viewer_artifacts.py`, `viewer_xr.py` | PRODUCTION research-only | volume/3D/XR |
| `dtwin/learning/` | MIXED PRODUCTION/EXPERIMENTAL | ingest runtime + ML/training |
| `dtwin/benchmark/` | MIXED SUPPORT/EXPERIMENTAL/LEGACY | metrics/runtime support + many protocols históricos |
| `dtwin/datasets/` | RESEARCH_SUPPORT | registry/ingest público |
| `dtwin/rag/` | EXPERIMENTAL_INTEGRATED | BM25/text RAG |
| `dtwin/graphrag/` | EXPERIMENTAL | Neo4j metadata graph |
| `webapp/server.py` | PRODUCTION research-only | FastAPI/orchestration monolith |
| `webapp/static/` | PRODUCTION | web UI |
| `viewer/` | PRODUCTION | offline Three.js/WebXR |
| `profiles/figado.yaml` | CONFIG HIGH_RISK | organ, segmentation, refino, mesh, export |
| `configs/` | CONFIG MIXED | model/benchmark/training/runtime |
| `tools/` | SCRIPT MIXED | operation, benchmark, freeze, audit, verify |
| `tests/` | TEST | 1.610 collected |
| `.github/workflows/tests.yml` | BUILD_ENVIRONMENT | CI minimal |
| `docker/`, `compose*.yaml`, launchers | BUILD_ENVIRONMENT/PRODUCTION | Windows/Mac/Quest/container |
| `docs/`, `contexto/`, README/runbooks | DOCUMENTATION MIXED | current + historical |
| `graphify-out/` | GENERATED | engineering graph; snapshot stale by two commits |
| `casos/`, `data/`, `artifacts/`, `experiments/`, `flywheel/`, `rag/` | DATA/ARTIFACT GENERATED/PRIVATE | ignored; never pack/Git |
| `.venv*`, `.tmp*`, `.local`, `.medgemma` | GENERATED LOCAL | environments/cache/runtime |

## Root entrypoints/scripts

`INICIAR_OREN.cmd`, `INICIAR_OREN_QUEST*.cmd`, `run_win.ps1`, `run_mac.sh`, `run_quest*.ps1`, certificate scripts and `ABRIR_GRAPHIFY.cmd` are manual/runtime entrypoints even without imports.

## Unknowns

File-level production/legacy status for all 307 tools and historical benchmarks requires runtime/config/docs/git-history tracing. They must not be bulk-deleted. See `LEGACY_AND_DEAD_CODE_CANDIDATES.md`.

