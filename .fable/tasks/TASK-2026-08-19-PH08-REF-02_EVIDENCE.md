# EVIDENCE — TASK-2026-08-19-PH08-REF-02 (PHASE_08, wave 2: safe fixes mecânicos)

Data: 2026-08-19 · Executor: agente · Autorização: Felipe Nantes ("siga para a
wave 2"). Baseline: suíte do portão da wave 1 (1768/4/1-ambiental).

## RESUMO

Baseline ruff mecânico reduzido de **731 → 2** achados usando SOMENTE fixes
seguros do próprio ruff (sem `--unsafe-fixes`), por lotes com smoke de import
entre lotes, mais 1 correção manual mecânica (UP035 anotação). Os 2 restantes
são justificados (I001 em one-liners comprimidos de teste). Diff: 452
arquivos, +1287/−846 — todo ele reordenação/remoção de imports e noqa mortos.

## Execução (OBSERVED)

| Lote | Achados | Corrigidos | Smoke |
|---|---|---|---|
| tests/ | 149 | 147 | collect-only: 1773 testes, 0 erros de import |
| tools/ | 187 | 187 | — |
| dtwin/ | 452 | 451 | — |
| webapp/ | 33 | 33 | collect-only: 1773 testes, 0 erros de import |

Correção manual (mecânica, uso apenas em anotação):
`dtwin/datasets/chaos_download.py` — `typing.ContextManager` →
`contextlib.AbstractContextManager` (UP035; fix marcado unsafe pelo ruff só
por ser reescrita de anotação; uso verificado por grep: 1 type hint).

## Estado final das 4 regras

`ruff check --select I001,RUF100,UP035,F401`: **2 achados** (eram 731).
Residuais justificados, NÃO corrigidos de propósito:
- `tests/test_openswisshcc_lesion_localizer.py:84` e
  `tests/test_openswisshcc_multisequence_chunks.py:26` — I001 em imports de
  função dentro de linhas comprimidas por ponto-e-vírgula ("import time;…").
  "Ordenar o bloco" não tem conteúdo aí; reescrever one-liners densos é risco
  sem valor. Ficam como estilo aceito do arquivo.

Regras de defeito real (F821,F811,B023,PLE etc.): **All checks passed**
(re-verificado após os fixes — a wave não introduziu nada).

## O que sobra no baseline de estilo (documentado, fora do escopo autorizado)

Estatística pós-wave (todas as regras): dominada por BLE001 (65, blind-except
— padrão deliberado do codebase em vários pontos), UP009 (50), RUF046 (36),
RUF022 (24), ISC004 (18) e cauda menor. Nenhuma dessas é mecânica-segura em
lote; adotá-las seria decisão de política de estilo → exit review da fase
registra como baseline aceito, não como dívida obrigatória.

## Portão da wave

- Suíte completa (2m32s): **1768 passed / 4 skipped / 1 failed ambiental**
  (test_environment_report_accepts_free_gpu, pré-existente) — resultado
  idêntico ao portão da wave 1: zero regressões após 818 fixes + 1 manual.

## Classificação de evidência

- OBSERVED: contagens por lote, saídas ruff, collect-only, suíte.
- SOURCE_SUPPORTED: justificativa dos 2 residuais (leitura dos sítios);
  equivalência da troca de anotação (grep de uso).
- INFERRED: nada material.

## CONTEXT_EFFICIENCY

- O próprio ruff fez 818/819 das mudanças; zero releitura de módulos —
  leituras somente dos 3 sítios residuais.
- Smoke barato (collect-only, ~8s) entre lotes em vez de suíte completa por
  lote; suíte completa 1× ao final.

## Proibições respeitadas

Sem `--unsafe-fixes`; nenhuma semântica tocada (imports/noqa apenas);
nenhum teste enfraquecido; nenhum commit/push (aguarda solicitação).
