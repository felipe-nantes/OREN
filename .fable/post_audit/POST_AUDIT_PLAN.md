# POST_AUDIT_PLAN — plano mestre do ciclo POST_AUDIT_OPTIMIZATION

Data: 2026-08-20 · Base: AUDITED_BASELINE_V1 (`origin/main = 9288785`) ·
Planner: agente (Claude Code) · Aprovador de execução: Felipe Nantes.

## 1. Fases do ciclo

| Fase | Objetivo | Card |
|---|---|---|
| OPT_00_WEAKNESS_INVENTORY | consolidar tudo que a auditoria encontrou | `plans/OPT_00_WEAKNESS_INVENTORY.md` |
| OPT_01_BEHAVIOR_PRESERVING_REFACTOR | estrutura/testabilidade sem alterar ciência | `plans/OPT_01_...md` |
| OPT_02_ROBUSTNESS_CORRECTIONS | bugs de integridade/confiabilidade | `plans/OPT_02_...md` |
| OPT_03_OOF_HYPOTHESIS_GENERATION | hipóteses baseadas em evidência | `plans/OPT_03_...md` |
| OPT_04_CONTROLLED_MICROEXPERIMENTS | uma hipótese por vez (futuro; NÃO nesta execução) | `plans/OPT_04_...md` |
| OPT_05_ADVERSARIAL_VALIDATION | tentar refutar cada candidato | `plans/OPT_05_...md` |
| OPT_06_CANDIDATE_PROMOTION | decidir substituição de baseline | `plans/OPT_06_...md` |
| OPT_07_BASELINE_V2_FREEZE | novo baseline somente pós-aprovação | `plans/OPT_07_...md` |

Regra herdada do pack: uma fase por vez, cada uma autorizada explicitamente
pelo aprovador; task cards + evidence packages; commit/push só sob pedido.

## 2. Política anti-consumo do outer OOF (NORMATIVA)

Contexto: SR-006 já documenta que a seleção do bundle final usa os folds
externos e que sua métrica é otimista (o próprio código registra
`generalization_estimate_source: nested_oof_etapa_c`). Se candidatos A, B, C
forem escolhidos olhando repetidamente o outer OOF, o outer passa a
participar do desenvolvimento e perde independência.

**DEVELOPMENT SIGNAL ≠ FINAL PERFORMANCE ESTIMATE.**

Opções de regime (decisão humana antes de OPT_04; trade-offs explícitos):

| Opção | Descrição | Prós | Contras |
|---|---|---|---|
| a | Seleção exclusivamente por inner CV | preserva outer intacto | inner é otimista; menos poder p/ triagem |
| b | Outer congelado + ORÇAMENTO de inspeções (contador no ledger) | pragmático, auditável | ainda consome; exige disciplina |
| c | Triagem por surrogate/dev regimes (ablações já congeladas como dev signal) | zero consumo do outer | dev signal pode não transferir |
| d | Avaliação final LOCKED: 1 leitura do outer por candidato promovível | máxima proteção | lenta; exige pré-comprometimento |
| e | Se o conjunto já estiver excessivamente consumido: novo regime de avaliação (nova partição/coorte) | reset limpo | custo alto; HG-06/07 obrigatório |

**REGIME DECIDIDO em 2026-08-24 (HUMAN_DECISIONS item 19): c + d + b.**
Triagem/desenvolvimento somente com dev signals/inner CV (zero leituras do
outer); promoção com no máximo 1 leitura LOCKED do outer por candidato
promovível, com endpoints PRÉ-registrados (CANDIDATE_COMPARISON preenchido
ANTES da leitura); toda leitura registrada em `EXPERIMENT_LEDGER.yaml`
(`outer_inspection_counter` + experiment_id). Medições que NÃO leem o outer
(probes sobre embeddings congelados, análises de falha) não consomem
orçamento. Guarda de engenharia: testes negativos de proveniência do
estimando (`tests/test_estimand_provenance_negative.py`, sonda P20 KILLED).

## 3. Regra de hipótese única

**ONE SCIENTIFIC HYPOTHESIS → ONE MINIMAL PATCH → ONE EVIDENCE PACKAGE.**
Proibido combinar normalization + aggregation + threshold + feature + model +
preprocessing num experimento. O template `templates/MICROEXPERIMENT.yaml`
impõe `single_change` + `explicitly_unchanged`.

## 4. Priority scoring (explícito, qualitativo)

```
PRIORIDADE ≈ (EVIDENCE_STRENGTH × EXPECTED_INFORMATION_GAIN × POTENTIAL_IMPACT
              × SILENT_FAILURE_RISK × DOWNSTREAM_REACH × TESTABILITY)
             ÷ (SCIENTIFIC_RISK × COMPUTATIONAL_COST)
```

Cada fator em escala H/M/L; itens com qualquer fator do numerador H e
denominadores L sobem. Desempate: **information gain > ganho esperado de
OOF** (uma investigação que elimina incerteza grande vence uma otimização
especulativa). O ranking resultante está em `TOP_10_POST_AUDIT_TASKS.md`.

## 5. Effort policy (Fable 5)

| Situação | Effort |
|---|---|
| OOF/científico, nested CV, domain shift, DICOM, geometria, resampling, preprocessing, leakage, root-cause multi-módulo, reconciliação manuscrito/código/contrato, arquitetura com downstream científico, silent failures difíceis | **UltraCode** |
| Correções de robustez com raio médio, triagens com julgamento (BLE001), sondas numéricas | HIGH |
| Refactors com oracle forte, provenance mapping, CI gates | MEDIUM |
| Ruff/format, typing trivial, docs, helpers simples, status updates determinísticos | LOW |

UltraCode NUNCA é automático; cada task recomenda
`recommended_model: Fable 5` + `recommended_effort` + `reason`.

## 6. Endpoints obrigatórios (OOF não é a única métrica)

Nenhum candidato é promovido só por AUC OOF. Endpoints considerados: AUC,
sensitivity, specificity, balanced accuracy, estratificação por coorte, LODO,
transfer behavior, origin probe, failure rate, integridade de denominador
(SCI-004), calibração quando aplicável, variância, reprodutibilidade,
runtime, VRAM, RAM quando medido, integridade de artefatos. Um candidato que
sobe AUC agregada mas aumenta dependência de domínio, piora uma coorte,
aumenta falhas, cria leakage, aumenta variância ou reduz reprodutibilidade
pode ser PIOR — o `CANDIDATE_PROMOTION_GATE.yaml` operacionaliza isso.

## 7. Contexto científico preservado (evidência para priorização, não solução)

Do manuscrito e contratos: melhor regime principal = Etapa C; desempenho
agregado não elimina dependência entre coortes; forte separabilidade de
origem nos embeddings (probes 100%/98,75% — docs/131/134, SR-007);
transferências entre domínios perdem desempenho; novas fontes de
complexidade nem sempre produziram ganho; localização ≠ classificação; ROI
correta demonstra teto diferente da seleção automática (SR-013); OOF,
produção, cascata e in-sample são regimes distintos (SR-006); camada 3D é
auditável, não anatomia verdadeira (GEO-003); denominadores e falhas
permanecem explicitamente reconciliados (SCI-004, 451/16).

## 8. Restrições ambientais (herdadas, não contornáveis)

BLK-PROTECTED-SOURCES (3 fontes de labels protegidos ausentes desta máquina),
BLK-FULL-REEXECUTION (reexecução completa impossível aqui), BLK-DEPS-LOCK.
BLK-GPU-TOLERANCES é FECHÁVEL nesta máquina (RTX 4060) — ver W-016/REP-01.
Artefatos congelados DISPONÍVEIS localmente: `casos/qualification/hybrid_v1/`
(embeddings em múltiplas variantes, OOF de ablações, fusões) — viabilizam
medições sem GPU/retreino.
