# Legado, duplicação e candidatos a código morto

Ausência de referência estática não prova morte. Antes de remover, verificar import direto/dinâmico, CLI, config, filesystem discovery, subprocess, framework convention, docs/runbooks, testes, experimentos e histórico Git.

| Candidate | Classification | Evidence | Required proof before removal |
|---|---|---|---|
| `webapp/server.py::_find_largest_compatible_series_legacy` | PROBABLY_DEAD | definição encontrada; nenhum uso estático fora dela no snapshot | Graphify/path, monkeypatch/tests/manual, coverage runtime, git history |
| `webapp/server.py::_legacy_completed_job_from_artifacts` | LEGACY_ACTIVE | chamado por restore de jobs | preservar ou migrar com fixture de restart |
| `dtwin/seg_worker.py` | LEGACY_ACTIVE / PRODUCTION_RUNTIME | copiado e invocado por `dtwin/segmentation_subprocess.py` | não remover; subprocess integration |
| `webapp/seg_worker.py` | UNKNOWN / BASELINE-PROTECTED | hash em baseline de segmentação e docs históricas; uso atual deve ser traçado | configs, launchers, tests, git history |
| `tools/medgemma_server_base.py` | LEGACY_ACTIVE | importado por `tools/medgemma_server_v14.py` | mapear launcher/config antes de consolidar |
| famílias `openswisshcc_v11`…`v27` | DUPLICATED_WITH_INTENT | protocolos/ablation versionados e testes próprios | ledger experimental e artifacts; não consolidar mecanicamente |
| múltiplos atomic writers/hash helpers | DUPLICATED_SUSPECTED | implementações locais repetidas | characterization + failure injection + compatibility |
| múltiplos geometry equality helpers | DUPLICATED_SUSPECTED | tolerâncias/semânticas locais | HG-03, exhaustive callers and regression |
| `dtwin/experiments/` | UNKNOWN | diretório sem arquivos rastreados no snapshot | packaging/history/dynamic discovery |
| documentos e scripts de versões descartadas | EXPERIMENTAL | resultados negativos preservados por método científico | nunca apagar sem retention/provenance decision |

## Classes permitidas

`CONFIRMED_DEAD`, `PROBABLY_DEAD`, `LEGACY_ACTIVE`, `EXPERIMENTAL`, `UNKNOWN`, `DUPLICATED_WITH_INTENT`, `DUPLICATED_SUSPECTED`.

No snapshot não há item classificado `CONFIRMED_DEAD`.


## Adendo 2026-08-17 (PHASE_01 wave 2 — TASK-2026-08-17-PH01-CARTO-02)

Censo estático completo de `tools/` em `TOOLS_STATUS.md` (evidência: `evidence/PH01/tools_status_9683eaa.csv`): 157 de 307 scripts são STATIC_ORPHAN (zero referências no repo), 87 só aparecem em docs, 23 só em outros tools. Nenhum foi executado ou removido; STATIC_ORPHAN ≠ morto. Achados correlatos: `webapp/seg_worker.py` estaticamente órfão (runtime copia `dtwin/seg_worker.py`, divergente) e o par `medgemma_server.py` (wired) vs `medgemma_server_v14.py` (só testes).
