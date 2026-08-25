# REF-03 — Design da decomposição de webapp/server.py (W-001/TD-001)

Data: 2026-08-25 · Executor: Fable 5 · Design: effort alto (mandato do
backlog) · Execução: por seam, portão completo entre cada um.

## Restrições que MANDAM no desenho (medidas, não supostas)

1. **10 consumidores externos** importam símbolos de `webapp.server`
   (5 testes + 5 tools). `webapp.server` PERMANECE como módulo público —
   nenhum importador muda nesta task.
2. **69 monkeypatches** em `tests/` sobre ~25 símbolos do server — inclusive
   constantes (`WORKSPACE` 27×, `REPO`, `MEDGEMMA_BACKENDS`,
   `MRSEGMENTATOR_EXE`, `ENHANCED_3D_OPT_IN_ENABLED`, bundles monophase) e
   funções de fluxo (`process_job`, `process_visual_job`,
   `process_benchmark`, `_segment`, `_mask_quality`, `find_best_series`,
   `_run`, `_load_report`, `_probe_backend`, `write_run_outputs`,
   `_run_benchmark_case`, `_run_visual_benchmark_case`,
   `_visual_model_info`).
   `monkeypatch.setattr(server, X, ...)` rebind a entrada no dict do MÓDULO
   server; qualquer código movido que resolva X pela própria global local
   IGNORA o patch → comportamento sob teste divergiria. Isso não é detalhe
   de teste: é o oráculo.

## As duas regras do corte

- **R1 — rotas, config e estado ficam em server.py.** As 19 rotas, as
  constantes env-driven, `JOBS`/`BENCHMARKS`/locks e o `app` FastAPI não se
  movem. Rotas chamam funções pelo namespace do próprio server (globals do
  módulo) → todo monkeypatch continua eficaz por construção.
- **R2 — late-binding obrigatório dentro dos módulos extraídos.** Código
  movido que precise de (a) qualquer constante de config, (b) estado
  (`JOBS`, `_set`, locks) ou (c) qualquer símbolo da lista de patch-targets
  acima resolve via `from webapp import server` (import do OBJETO módulo;
  ciclo seguro porque o atributo só é lido em tempo de chamada) e acessa
  `server.X` no ponto de uso. PROIBIDO copiar constante para o módulo novo
  ou chamar patch-target por global local. server.py re-importa os símbolos
  movidos (façade) para manter `server.X` público.

Verificação mecânica da R2: grep no módulo novo por qualquer nome da lista
de patch-targets/constantes usado sem o prefixo `server.`.

## Mapa de seams (ordem de execução, risco crescente)

| seam | conteúdo (linhas de origem aprox.) | patch-targets envolvidos | risco |
|---|---|---|---|
| S1 `webapp/payloads.py` + `webapp/xr_sessions.py` | modelos Pydantic (1800-1911); sessão XR, quest QR/base-url, persistência de job concluído (1561-1799) | nenhum | BAIXO |
| S2 `webapp/benchmarks.py` | subsistema benchmark inteiro (2249-3049): métricas, configs, model-info, proveniência, casos visual/clássico, worker, manifesto, CSV | `process_benchmark`, `_run_benchmark_case`, `_run_visual_benchmark_case`, `_visual_model_info`, `_is_visual_scenario` | MÉDIO |
| S3 `webapp/jobs.py` | workers de análise (1104-1560, 1912-2248): `process_job`, `process_visual_job`, monophase, advisory | `process_job`, `process_visual_job`, `_segment`, `_mask_quality`, `find_best_series`, `_run`, `write_run_outputs` | ALTO |
| S4 `webapp/phase_union.py` | união de fases + build do modelo + localização de candidato (848-1103) — DOWNSTREAM CIENTÍFICO | `_build_union_liver_mask` (importado por tool) | ALTO (byte-idêntico) |

Sobra em server.py: config/env, estado+locks, helpers de resultado/aviso
(322-847, patch-targets pesados — ficam), rotas (3050-3635). Estimativa
final ~1.600 linhas: monólito → 5 módulos coesos SEM mudança de API.

## Oráculos (por seam, nenhum commit sem todos verdes)

1. Guard novo `tests/test_server_route_inventory.py`: pina as 19 rotas
   (método+path) e os símbolos públicos monkeypatched — remoção acidental
   de rota ou de patch-point quebra ANTES do corte chegar ao runtime.
2. `test_webapp.py` (85) + `test_integration_webapp_boundary.py` +
   operational timing + viewer presets + visual subtype: intocados, verdes.
3. Suíte completa (baseline 1802/4/0) idêntica após cada seam.
4. S4 adicionalmente: specs de geometria dos comparadores (decisão 13)
   intactas; nenhuma tolerância tocada.

## Rollback

Qualquer rota/artefato/teste divergente ⇒ revert do seam inteiro (cada seam
é 1 commit) e reclassificação da causa antes de reter novamente.
