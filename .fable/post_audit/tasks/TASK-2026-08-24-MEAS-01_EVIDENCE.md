# EVIDENCE — TASK-2026-08-24-MEAS-01 (H-03 estabilidade + H-04 coortes)

Data: 2026-08-24 · Executor: agente (Fable 5, UltraCode) · Tipo: MEDIÇÃO
label-free e determinística (sem RNG) sobre artefatos congelados. Nenhum
label protegido lido; nenhuma métrica nova do outer produzida
(outer_inspection_counter permanece 0); nenhuma regra adotada.

## H-03 — estabilidade do mecanismo de seleção (OBSERVED)

Fonte: `fold_selection.json` (hiperparâmetros + métricas INNER congeladas
por fold) e `oof_predictions.jsonl` (scores/thresholds, sem labels).

**1. Dispersão da seleção por fold** — instabilidade real e estruturada:

| fold | C | agregação | threshold | inner bal |
|---|---|---|---|---|
| 0 | 0,01 | top2_mean | 0,502 | 0,7535 |
| 1 | 0,01 | top2_mean | 0,508 | 0,7209 |
| 2 | **1,0** | **max** | **0,848** | 0,7061 |
| 3 | 0,1 | mean | 0,480 | 0,7219 |
| 4 | 0,01 | mean | 0,414 | 0,7402 |

4 dos 5 folds convergem para uma banda estreita (thr 0,41-0,51; C baixo;
mean/top2_mean). **O fold 2 é um ponto de operação qualitativamente
diferente** (C=1,0, max, thr=0,848) — a regra maxmin de seleção saltou de
regime. Amplitude de threshold: 0,434.

**2. Impacto decisório da instabilidade é LIMITADO (label-free):**
- Fragilidade: só 0,9% dos 451 computáveis têm score a <0,02 do threshold
  do seu fold (4,7% a <0,05; 9,5% a <0,10) — decisões majoritariamente
  longe da fronteira.
- Transplante de threshold: usar o threshold de qualquer fold "normal" em
  todos os casos flipa apenas 2,2-3,6% das predições; usar o do fold 2
  flipa 22,8%. Threshold global mediano: 2,4% de flips.

**3. Triangulação dos três regimes de estimativa** (fecha o quadro do
SR-006 com números): inner por fold 0,706-0,753 (levemente PESSIMISTA,
como esperado de treinos menores) < outer honesto 0,760 < métrica de
seleção do bundle 0,796. O otimismo mora na seleção-sobre-outer, não no
inner — o inner é um dev signal são.

## H-04 — decomposição por coorte (OBSERVED, agregados já publicados)

| coorte | n | sens [IC95] | spec [IC95] |
|---|---|---|---|
| lld_mmri | 335 | 0,733 [0,658-0,796] | 0,770 [0,703-0,825] |
| osw_consumed_holdout | 44 | 0,833 [0,642-0,933] | 0,650 [0,433-0,819] |
| osw_development | 88 | 0,821 [0,673-0,910] | 0,776 [0,641-0,870] |

- Padrão: OSW com sens MAIOR e (holdout) spec menor; LLD com sens menor —
  mas os ICs por coorte são LARGOS (n=44!) e se sobrepõem: nenhuma
  conclusão por coorte é definitiva neste n (sustenta a contenção de
  claims do manuscrito).
- **Reponderação**: balanced accuracy varia só **0,62 pp** entre os 3
  esquemas (0,759 → 0,765) — o agregado NÃO é frágil à composição no nível
  bal. Porém o MIX sens/spec é sensível: igual-peso empurra sens a 0,795 e
  spec a 0,732 — o peso oficial por caso é o mais conservador em sens.
- Nota de honestidade: o agregado oficial pondera sens por POSITIVOS e spec
  por NEGATIVOS (tp/220, tn/247); meu esquema "por caso" é aproximação
  (0,7586 vs 0,7591 — 0,05 pp; declarado).

## RECOMENDAÇÃO

1. **Nenhum microexperimento justificado agora.** A instabilidade de
   seleção existe (fold 2) mas seu impacto decisório é limitado (flips
   2-4% fora do outlier), e qualquer mudança na regra de seleção é
   SCIENTIFIC_CHANGE (HG-07/08) com ganho esperado pequeno. Documentar e
   revisitar SOMENTE se uma promoção futura depender de escolha de
   threshold — nesse caso o candidato natural é restringir o espaço de
   busca/estabilizar a regra maxmin, via MICROEXPERIMENT gated.
2. O inner CV é confirmado como dev signal são para o regime c+d+b (não é
   otimista); a métrica de seleção do bundle segue proibida como
   generalização (testes da GOV-01 já a pinam).
3. Promotion gate: manter `cohort_results_reviewed` com consciência de IC —
   em n=44, deltas por coorte menores que ~15 pp são indistinguíveis de
   ruído.

## CONTEXT_EFFICIENCY

- 1 script determinístico fechou as duas hipóteses; fold_selection.json
  (achado na FAIL-01) supriu a camada inner sem labels.
- H-03 + H-04 na mesma sessão como planejado no TOP_10 (rank 7).

## Critérios de saída

- [x] Dispersão de seleção + fragilidade + transplantes (label-free)
- [x] Triangulação inner/outer/seleção
- [x] Por coorte com Wilson + 3 esquemas de peso a priori
- [x] Evidence + ledger + recomendação (arquivar; gatilho de revisita
      registrado)
