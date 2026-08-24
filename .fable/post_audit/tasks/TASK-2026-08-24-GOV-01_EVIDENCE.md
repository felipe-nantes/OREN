# EVIDENCE — TASK-2026-08-24-GOV-01 (proveniência do estimando + regime do outer)

Data: 2026-08-24 · Executor: agente (Fable 5, UltraCode) · Status: **PARADO
NO GATE HG-07/HG-08** (nenhuma mudança aplicada).

## OBSERVED — estado atual (código e artefatos lidos)

1. **Seleção** (`medsiglip_multiclass_classifier.py:1277-1302`): (C,
   agregação, threshold) escolhidos por CV sobre os folds externos
   congelados; modelo final ajustado em todos os casos. Docstring declara o
   procedimento e que a estimativa de generalização é a nested-OOF, não
   qualquer re-medição in-sample.
2. **Bundle congelado** (`medsiglip_multiclass_production_bundle_v1`):
   - `cross_validated_selection_metrics`: sens 79,07 / spec 80,08 / bal
     79,58 — **otimismo de +3,2/+4,0 pp** sobre o honesto 75,91/76,11;
   - população da seleção = 451 computáveis (tp+tn+fp+fn=451,
     technical_failures=0) — **regime de denominador DIFERENTE** do honesto
     (467 com falhas dentro, SCI-004): dois motivos para nunca compará-los;
   - guardas já presentes: `generalization_estimate_source:
     nested_oof_etapa_c`, `in_sample_performance_is_not_a_generalization_estimate`,
     `training_case_ids`/`training_case_set_sha256` (detecção de in-sample).
3. **Apresentação** (`webapp/server.py:2354-2370` `_visual_model_info`): JÁ
   honesta — expõe `generalization_estimate_source` + `oof_reference` com a
   âncora 75,91/76,11 e NÃO expõe a métrica de seleção; há guard
   `metrics_are_generalization_estimate` com warning citando docs/121.
4. **Lacunas confirmadas (o que o SR-006 pede e não existe):**
   - ZERO testes pinando esse enquadramento — grep: nenhum teste referencia
     `cross_validated_selection_metrics` como proibição; uma edição futura
     em `_visual_model_info` (ou nova rota) poderia promover a métrica de
     seleção sem quebrar nada;
   - regime de consumo do outer para o ciclo experimental nunca formalizado
     (o `outer_inspection_counter` do ledger existe, mas sem regra decidida).

## PROPOSTA A — testes negativos de proveniência (TEST-ONLY, produção intocada)

Novo arquivo `tests/test_estimand_provenance_negative.py` (~4 testes):
1. `_visual_model_info` NUNCA contém chaves/valores de
   `cross_validated_selection_metrics` (nem sensitivity/specificity soltos
   vindos do manifesto de seleção) e SEMPRE contém
   `generalization_estimate_source` + `oof_reference`.
2. Manifesto do bundle: presença obrigatória das guardas
   (`generalization_estimate_source`,
   `in_sample_performance_is_not_a_generalization_estimate`,
   `training_case_set_sha256`) — contrato de schema pinado.
3. A rota da API que serve o model-info não expõe a métrica de seleção
   (teste via TestClient existente do test_webapp).
4. Sonda de mutação pós-aprovação: expor a métrica no dict → teste falha
   (KILLED), padrão das fases 07-09.
Risco: ZERO ao comportamento (nenhuma linha de produção muda — o
comportamento atual já é o desejado; os testes o CONGELAM como spec).
Fecha o DECISION_REQUIRED do SR-006 no lado de engenharia → SR-006 pode ir
a RESOLVED-engenharia (ponta editorial do manuscrito permanece).

## PROPOSTA B — regime anti-consumo do outer (POST_AUDIT_PLAN §2)

Recomendação do planner (combinação c+d+b):
- **c** Triagem/desenvolvimento: SOMENTE dev signals (ablações congeladas,
  inner CV, medições) — zero leituras do outer;
- **d** Promoção: 1 leitura LOCKED do outer por candidato promovível, com
  endpoints PRÉ-registrados (CANDIDATE_COMPARISON antes da leitura);
- **b** Auditoria: toda leitura registrada no `outer_inspection_counter` do
  ledger com experiment_id.
Alternativas na mesa: (a) inner-only estrito; (e) novo regime de avaliação
se o conjunto for considerado consumido (custo alto, HG-06/07).

## STOP — aguardando decisão HG-07/HG-08 nas duas propostas

---

## PÓS-GATE: decisões recebidas e aplicadas (2026-08-24)

**APROVADAS A e B** (Felipe Nantes, via AskUserQuestion; registro formal em
HUMAN_DECISIONS.md item 19 — bloco 7).

### Aplicação

- A: `tests/test_estimand_provenance_negative.py` (5 testes — model-info sem
  métrica de seleção nem valores vazados, âncora honesta obrigatória, zero
  chaves de métrica, fallback limpo, guardas do bundle real com skipif).
- B: regime c+d+b gravado como DECIDIDO no POST_AUDIT_PLAN §2.
- SR-006 → RESOLVED-ENGENHARIA (ponta editorial permanece); W-030 → RESOLVED.

### Verificação (OBSERVED)

- 5/5 testes novos verdes.
- Sonda de envenenamento P20 (expor cross_validated_selection_metrics no
  model-info) → **KILLED**, restauração hash-verificada
  (`evidence/GOV-01/gov01_mutation_probe_2026-08-24.json`).
- Suíte completa (portão, 2m37s): **1775 passed / 4 skipped / 0 failed** —
  primeira suíte 100% verde do ciclo (GPU livre desta vez; +5 proveniência).

GOV-01 DONE.
