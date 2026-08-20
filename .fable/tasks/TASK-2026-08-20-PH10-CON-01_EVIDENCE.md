# EVIDENCE — TASK-2026-08-20-PH10-CON-01 (PHASE_10: consolidação e encerramento do pack)

Data: 2026-08-20 · Executor: agente · Aprovador: Felipe Nantes

## RESUMO

**AUDITORIA COMPLETA: 10/10 fases DONE (2026-08-17 → 2026-08-20).** Esta wave
sincronizou os registros vivos com as fases 07-09, regenerou o mapa de código,
resolveu as 3 decisões de encerramento (HUMAN_DECISIONS itens 16-18) e
registrou o baseline final.

## Consolidação executada (OBSERVED)

1. **Registros vivos sincronizados**: SR-011 → RESOLVED (direction no stage5,
   item 13); LEGACY_AND_DEAD_CODE → webapp/seg_worker REMOVIDO (item 15);
   SYSTEM_MAP → componente removido anotado. Varredura por referências
   defasadas de seg_worker/direction: registros históricos e narrativas
   datadas preservados intactos (auditoria não reescreve história).
2. **Graphify regenerado** (incremental, code-only, sem rede): 12.195 nós /
   29.602 arestas / 782 comunidades (era 7.644/24.909/308 no snapshot
   9683eaa — o crescimento reflete os ~120 testes novos e as mudanças
   aprovadas das fases 04-09). Backup do grafo curado anterior preservado em
   `graphify-out/2026-08-20/`.
3. **Decisões de encerramento** (registro formal em HUMAN_DECISIONS bloco 6):
   - item 16: baseline v1 APOSENTADO como histórico (JSON e freeze tool
     anotados; nenhum freeze v2);
   - item 17: SAFETY_KERNEL.md RATIFICADO;
   - item 18: PHASE_03 formalmente DONE (waves opcionais declinadas).
4. **Baseline final da auditoria**: **1769 passed / 4 skipped / 1 failed
   ambiental** (test_environment_report_accepts_free_gpu, exige GPU livre) —
   idêntico aos 4 portões anteriores; log em scratchpad, sumário aqui.

## Balanço da auditoria (fases 00-10)

- **Suíte**: 1605 → 1769 testes passando (+164, incluindo 61 invariantes,
  13 integração real, 59 adversariais negativos, characterization e specs).
- **Núcleo científico**: 89,5% branch coverage; **19/19 mutantes dirigidos
  KILLED** ao longo das fases (8 PH04 + 15 PH07 + 4 PH09, com sondas
  hash-verificadas; contagem PH07 inclui os 15 e PH09 os 4 — total 27
  execuções contando confirmações).
- **Contratos**: SCI-001..013, GEO-001..004, DOM-001..002, SW-001 congelados;
  tolerâncias por backend ratificadas (GPU permanece EM ABERTO).
- **Decisões humanas**: 18 registradas em HUMAN_DECISIONS.md (blocos 1-6).
- **Débitos fechados**: TD-007 (vazamento), TD-014, TD-015; direction-blind
  (SR-011) resolvido; seg_worker legado removido; pip-audit limpo.
- **Aceitos/documentados**: BLE001 e estilo restante (baseline aceito),
  S5/S6/G8/G9 justificados, duplicação dos 56 helpers atomic (observação),
  flake único do Hypothesis (não reproduzido), 2×I001 em one-liners.
- **Blockers permanentes desta máquina** (inalterados): 3 fontes de labels
  protegidos ausentes; tolerâncias GPU não sondadas; reexecução completa
  impossível; lockfile integral por hardware ausente.
- **Pendências EXTERNAS ao repo**: correção editorial de "assinado" no
  manuscrito (SW-001); ambiguidades restantes de MANUSCRIPT_VS_CODE.

## Fronteira clínica (reafirmação final)

`research_only: true`, `clinical_use_allowed: false` — nada nesta auditoria
constitui validação clínica; o gate 0,75/0,75 é governança interna
(SCI-005); claims clínicos exigem HG-12 (fora da alçada de engenharia).

## Classificação de evidência

- OBSERVED: tudo nas seções acima (saídas salvas; decisões via AskUserQuestion).
- SOURCE_SUPPORTED: balanço numérico (evidence packages das fases).
- INFERRED: nada material.

## CONTEXT_EFFICIENCY

- Consolidação guiada por grep dirigido (3 varreduras) em vez de releitura
  do pack; graphify e suíte final em background paralelos às decisões
  humanas; registros históricos intocados por política (só linhas vivas).

## Proibições respeitadas

Nenhum código de produção alterado nesta fase (anotações em JSON de baseline
aposentado e docstring de ferramenta manual, ambas sem consumidores em
runtime); nenhum commit/push (aguarda solicitação).
