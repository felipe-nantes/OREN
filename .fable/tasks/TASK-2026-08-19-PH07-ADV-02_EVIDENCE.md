# EVIDENCE — TASK-2026-08-19-PH07-ADV-02 (PHASE_07, wave 2: mutação seletiva + loaders)

Data: 2026-08-19 · Executor: agente · Autorização: Felipe Nantes ("autorizo", 2026-08-19)

## RESUMO

Wave 2 concluída. mutmut 3.7.0 é INCOMPATÍVEL com Windows nativo (OBSERVED:
o CLI recusa execução — "To run mutmut on Windows, please use the WSL",
issue upstream boxed/mutmut#397); o fallback pré-autorizado (sondas dirigidas
com restauração hash-verificada) executou 9 mutantes: **9/9 KILLED**.
25 testes novos fecham G1/G2 (loaders anti-vazamento de robustness) e G6
(braços de raise do validador de splits). Nenhum código de produção alterado;
working tree limpo de mutantes (restauração comprovada por
`git hash-object == HEAD` em todas as sondas).

## Cobertura antes → depois (branch)

| Módulo | Wave 1 | Wave 2 | Nota |
|---|---|---|---|
| dtwin/learning/splits.py | 87,4% | **100,0%** | validador SCI-003 integralmente afirmado |
| dtwin/learning/robustness.py | 63,3% | **≥82,7%** | resta só `render_markdown_report` (416-495, G3 MÉDIA) |

(Medição wave 2 = corrida dirigida sobre os arquivos de teste dos dois
módulos; limite inferior do valor de suíte completa.)

## Testes novos (25, todos passando)

- `tests/test_robustness_frozen_loaders.py` (15): fixtures 100% sintéticas.
  Afirma cada guarda fail-closed de `load_frozen_oof_predictions` (assinatura
  divergente, predições adulteradas, flag de holdout ≠ False literal — incluindo
  ausência —, ground truth embutido nas predições), `_json`/`_jsonl` (ausente,
  inválido, registro não-objeto), `_percentile([])`, `clinical_subtype_map`
  (case_id vazio), e `evaluate_robustness` fim-a-fim sobre candidato + protocolo
  sintéticos (schema, contagens, LODO, report_signature, research_only) e o
  braço "caso fora do protocolo protegido".
- `tests/test_splits_validation_negative.py` (10): corrupções dirigidas de um
  artefato válido do próprio gerador, uma por braço de raise de
  `validate_nested_splits`: schema, folds ausentes, duplicata no fold,
  universos divergentes, vazamento interno, fold interno sem cobertura exata,
  caso repetido em dois testes externos, caso nunca testado, case_count
  divergente + `build_nested_splits([])`.

## Ledger de mutantes — executados (9/9 KILLED)

JSON: `evidence/PH07/mutation_probes_2026-08-19.json` (cada entrada com
`restored_ok: true`).

| Sonda | Mutante (guarda desligada / perturbação) | Veredicto |
|---|---|---|
| P1 | splits: vazamento treino∩teste externo | KILLED |
| P2 | splits: duplicata dentro do fold | KILLED |
| P3 | splits: case_count divergente | KILLED |
| P4 | robustness: verificação de assinatura do freeze | KILLED |
| P5 | robustness: flag de holdout | KILLED |
| P6 | segmentation_contract: máscara vazia | KILLED |
| P7 | segmentation_contract: chaves obrigatórias do recibo | KILLED |
| P8 | metrics: acurácia com denominador sem falhas (viola SCI-004) | KILLED |
| P9 | metrics: Wilson com total+1 (viola SCI-013) | KILLED |

P8/P9 confirmam que os testes de propriedade realmente mordem as âncoras
SCI-004/SCI-013 — não apenas executam as linhas.

## Ledger de mutantes — sobreviventes POR PROVA DE COBERTURA (sem execução)

Braço de raise sem teste ⇒ mutante "guarda deletada" sobrevive por construção
(prova determinística via coverage_branch_2026-08-18.json; execução seria
desperdício). Sobreviventes remanescentes após a wave 2:

| # | Local | Guarda descoberta | Criticidade |
|---|---|---|---|
| S1 | volumetry.py 571-598 (`verify_volumetry_artifacts`) | schema/contrato, hash CSV, contagens, **volume ≠ voxels×spacing/1000 (GEO-004, linhas 587-590)**, gate Couinaud | **ALTA** |
| S2 | segmentation_contract.py 91-98 | geometria: tamanho/spacing ≤0, não-finito, direção singular | ALTA |
| S3 | segmentation_contract.py 136-143, 178-188, 218-222 | manifesto nativo, máscara ausente/ilegível/não-finita, manifesto de qualidade | MÉDIA-ALTA |
| S4 | segmentation_contract.py 274-291 | early-returns de `approved_visualization_mask` — inclui **hash da máscara ≠ recibo (linha 290-291)** | ALTA (é o gate de exibição) |
| S5 | robustness.py 416-495 | `render_markdown_report` (apresentação) | MÉDIA |
| S6 | volumetry.py 56-68, 277-334 demais braços | roles/qualidade | MÉDIA |

## Classificação de evidência

- OBSERVED: recusa do mutmut no Windows; 9/9 KILLED com restauração
  hash-verificada; 25 testes passando; cobertura antes/depois.
- SOURCE_SUPPORTED: sobreviventes S1-S6 (prova = linhas ausentes no JSON de
  cobertura da wave 1 + leitura simbólica das faixas).
- INFERRED: criticidades do ledger.
- UNKNOWN: nada novo.

## CONTEXT_EFFICIENCY

- Sobreviventes triviais provados por cobertura, não por execução — 0 corridas
  de pytest gastas em veredictos já determinísticos.
- 9 sondas executadas com testes-ALVO (2-4s cada), não suíte completa.
- Leituras simbólicas apenas das faixas do gap ledger; nenhuma releitura
  integral de módulo.
- Runner de sondas em script standalone (evita corrupção de heredoc no
  Windows, lição registrada), com try/finally + verificação por hash.

## Proibições respeitadas

Produção intocada (working tree: apenas .fable/ + 2 arquivos de teste novos);
nenhum teste enfraquecido; nenhum commit/push.

## Próxima wave proposta (aguarda autorização)

Wave 3 — matar os sobreviventes S1-S4 com testes negativos sintéticos
(mesma técnica desta wave: artefatos válidos corrompidos um braço por vez),
prioridade S1 (GEO-004) e S4 (gate de exibição); S5 aceitar como apresentação
ou cobrir com teste de fumaça; na sequência, varreduras estáticas restantes
(ruff triado + ast-grep) e exit review da fase.
