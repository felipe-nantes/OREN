# EVIDENCE — TASK-2026-08-20-PH09-HRR-03 (PHASE_09, wave 3: seg_worker.py órfão)

Data: 2026-08-20 · Executor: agente · Status: **DECISÃO RECEBIDA E APLICADA**
(ordem cronológica: prova → STOP → R1 aprovada → remoção).

## Prova de (in)alcançabilidade (OBSERVED)

Varredura integral do repo versionado (git grep, excluindo apenas
graphify-out/docs/.fable como não-executáveis):

1. **Zero imports** de `webapp.seg_worker` em qualquer .py.
2. **Zero invocações por string** ("seg_worker") em ps1/sh/yaml/CI/Docker.
   O launcher ATIVO é outro arquivo: `dtwin/seg_worker.py` (1018 bytes,
   worker mínimo), copiado em runtime por
   `dtwin/segmentation_subprocess.py:94-95`
   (`Path(__file__).with_name("seg_worker.py")` = o de dtwin/) e coberto por
   `tests/test_integration_segmentation_boundary.py:136`.
3. `webapp/seg_worker.py` (1957 bytes) é o PREDECESSOR legado: launcher
   spawn-safe da era do fluxo web v1 (docs/17: "criado dtwin/seg_worker.py,
   um worker mínimo e independente" — o sucessor). História git: criado em
   275a1f9, funcionalmente intocado desde 15a64a2 (o toque de daa878c foi só
   estilo mecânico da PHASE_08).
4. Referências restantes, TODAS não-runtime:
   - `tools/freeze_segmentation_visualization_baseline.py:14` — lista
     TRACKED_FILES hard-coded (ferramenta MANUAL de freeze/verify; nenhum
     invocador em código/CI; quebraria se re-executada após remoção).
   - `configs/baselines/segmentation_visualization_v1.json` — pina o SHA-256
     do arquivo. **OBSERVED: os 5 pins desse baseline estão STALE**
     (stages.py, figado.yaml, app.js, seg_worker.py, server.py — todos
     mudaram com aprovação ao longo das fases) e NENHUM código o verifica —
     é registro histórico congelado do snapshot v1, não um gate ativo.
   - docs/ (menções históricas).

Conclusão: **inalcançável em runtime**. Único worker vivo = dtwin/seg_worker.py.

## PROPOSTA

- **R1 (recomendada):** remover `webapp/seg_worker.py` e retirar a entrada de
  `TRACKED_FILES` do freeze tool (para um freeze manual futuro não quebrar).
  `configs/baselines/segmentation_visualization_v1.json` fica INTOCADO como
  registro histórico (já 100% stale por design das fases anteriores).
  Verificação: suíte completa + grep pós-remoção.
- R2: manter como legado documentado (nenhuma mudança).

Follow-up para PHASE_10 (fora desta decisão): decidir se o mecanismo de
baseline v1 vira um freeze v2 verificado ou é aposentado — hoje não é
verificado por ninguém.

## Classificação de evidência

- OBSERVED: varreduras git grep; hashes dos 5 pins recomputados; conteúdo dos
  dois workers lidos; história git.
- SOURCE_SUPPORTED: papel de sucessor do dtwin/seg_worker.py (docs/17 +
  segmentation_subprocess + teste de integração).
- INFERRED: nada material.

## STOP — aguardando decisão de remoção

---

## PÓS-GATE: decisão recebida e aplicada (2026-08-20)

**APROVADO R1** (Felipe Nantes, via AskUserQuestion; registro formal em
HUMAN_DECISIONS.md item 15).

### Aplicação

- `git rm webapp/seg_worker.py` (launcher legado).
- `tools/freeze_segmentation_visualization_baseline.py`: entrada removida de
  TRACKED_FILES com comentário citando a decisão; py_compile OK.
- Baseline histórico v1 intocado, conforme aprovado.

### Verificação (OBSERVED)

- grep pós-remoção: zero referências restantes fora de
  docs/.fable/configs (históricos) e do trio ativo
  (dtwin/seg_worker.py + segmentation_subprocess + teste de integração).
- Suíte completa (portão, 2m30s): **1769 passed / 4 skipped / 1 failed
  ambiental** (pré-existente) — zero regressões pós-remoção. Wave 3 DONE.
