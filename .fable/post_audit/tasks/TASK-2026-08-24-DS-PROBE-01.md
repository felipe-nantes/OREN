# TASK-2026-08-24-DS-PROBE-01 — localização do sinal de domínio por variante de representação

STATUS: DONE (2026-08-24) - evidencia em TASK-2026-08-24-DS-PROBE-01_EVIDENCE.md
Autorização: Felipe Nantes, 2026-08-24 ("commit e push, depois siga para a
DS-PROBE-01"). Especificação: FIRST_TASK.md (H-01 do OOF_IMPROVEMENT_REGISTER;
W-031/SR-007). Executor: Fable 5 · Effort: UltraCode · Tipo: MEDIÇÃO.

## Objetivo

Medir a separabilidade de ORIGEM (coorte) entre as variantes de embedding já
congeladas em casos/qualification/hybrid_v1/, com probe determinística
(regressão logística linear, seed fixa, CV agrupada por paciente), global e
condicionada — para LOCALIZAR onde o sinal de domínio entra/persiste. As
probes globais de docs/131 (100%/98,75%) NÃO são repetidas como resultado
principal (servem só de sanity).

## Endpoints

- Primário: AUC da probe de origem por variante de representação.
- Secundários: probe condicionada (ver nota de viabilidade abaixo), por par
  de coortes, gap entre variantes, cobertura de casos por variante.
- Nota de viabilidade: condicionar ao LABEL VERDADEIRO exige as fontes de
  labels protegidos, AUSENTES desta máquina (BLK-PROTECTED-SOURCES) e cuja
  leitura o prompt da task proíbe. Fallback declarado: condicionar à
  PREDIÇÃO OOF congelada (presente nos freezes, sem ground truth por design)
  — proxy mais fraco, rotulado como tal na evidência.

## Proibições (da FIRST_TASK)

- Não alterar modelo/thresholds/folds/labels/embeddings/preprocessing ou
  qualquer código de produção.
- Não ler labels clínicos protegidos; dataset_id/case_id bastam.
- Não ler o outer OOF como métrica de desenvolvimento (esta medição não
  consome outer_inspection_counter).
- PHI nunca entra em logs/pack.
- Se artefatos insuficientes: PARAR, registrar no ledger, reportar.

## Critérios de saída

- Inventário de variantes (existência/shape/cobertura) registrado.
- Tabela comparativa de probes com seed fixa, reproduzida 2× com números
  idênticos.
- Evidence package + entrada no EXPERIMENT_LEDGER + recomendação final
  (qual hipótese interventiva se justifica, ou nenhuma).
