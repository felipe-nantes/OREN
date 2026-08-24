# EVIDENCE — TASK-2026-08-24-FAIL-01 (H-02: composição das 16 falhas)

Data: 2026-08-24 · Executor: agente (Fable 5, UltraCode) · Tipo: MEDIÇÃO
(denominador 467 intocado; outer não consumido; nenhum label protegido lido).

## RESUMO

H-02 CONCLUÍDA — e com uma lição de processo: a pergunta já tinha sido
respondida por um experimento real de 2026-07-31 (docs/158) que NÃO estava no
ledger. Esta task (a) reconstruiu a composição por rota independente e os
números BATEM exatamente com a doc, (b) computou a banda de teto no regime
467, (c) registrou o experimento pré-ciclo no ledger (LEDGER-SEED-006) e
(d) validou que a decisão de 31/07 permanece a correta.

## OBSERVED — rota A (esta task, só artefatos congelados)

1. **Identificação**: 16/467 linhas com `technical_failure=true` no OOF
   oficial; todas com `panel_count: 0` e prediction TECHNICAL_FAILURE.
2. **Causa registrada**: `candidate_dataset_stage_a_v1/technical_failures.jsonl`
   — 16× `no_verified_liver_enriched_panel_collection` (monocausal neste
   nível: sem máscara hepática válida → sem painel → sem embedding).
3. **Composição por coorte**: 14 LLD + 2 OpenSwiss (1 consumed_holdout +
   1 development); consistente com as 14 falhas do regime LLD-335 e com o
   manifest do stage-A (expected 467, materialized 451; fontes preparadas
   full321=335−14 e full130=132−2).
4. **Composição por LABEL das 14 LLD** derivada dos agregados
   `by_clinical_subtype` (sem ler labels por caso): hcc=5 → 5 POSITIVAS;
   hemangioma=6 + cisto=2 + fnh=1 → 9 NEGATIVAS.
5. **Gap 448 vs 451 dos monofásicos explicado**: +3
   `expected_source_phase_unavailable` (art/del) — falha distinta, não
   relacionada às 16.
6. **Banda de teto no 467** (tp=167 tn=188 fp=59 fn=53; x = falhas
   positivas ∈ [5,7] pelas 2 OSW desconhecidas):
   - teto absoluto (recuperação+classificação perfeitas): sens 78,2-79,1 /
     spec 79,8-80,6;
   - realista (classificadas na taxa atual): sens 77,7-78,4 / spec 79,0-79,7.

## OBSERVED — rota B (docs/158, experimento real de 2026-07-31)

Retry com MESMO timeout/gate em máquina saudável, previsão pré-registrada:
- **9/9 "infraestrutura" recuperadas** (8 timeout 75s + 1 RAM; rodaram em
  35-84s) e **0/5 "reais"** (segmentação completa acha 0/8/216 voxels);
- labels da auditoria: recuperadas = 2 HCC + 7 neg; restantes = 3 HCC +
  1 FNH + 1 hemangioma → total LLD positivas = **5** — IGUAL à rota A;
- melhor caso LLD com os 9: sens 74,52% (<75) — gate continua reprovado;
- números oficiais subestimam o sistema em ~+1pp sens/+3pp spec no LLD
  (limitação de EXECUÇÃO, documentada);
- decisão registrada: documentar; regenerar a cadeia assinada só quando
  houver outro motivo (custo horas + risco de vínculo de assinatura).

## Convergência das rotas

Duas derivações independentes (agregados congelados × auditoria de retry)
produzem a MESMA composição — validação cruzada forte de ambas.

## RECOMENDAÇÃO (saída da task)

1. **Nenhum experimento novo**: a recuperação já foi demonstrada, o teto é
   conhecido, e a decisão de 31/07 (adiar a regeneração até haver outro
   gatilho de regeneração da cadeia) permanece racional — o ganho não muda
   nenhum gate e o risco de assinatura é real.
2. **Gatilho registrado**: se OPT_07 (baseline v2) um dia regenerar a cadeia,
   os 9 casos ambientais entram como segunda fonte incremental
   (`build_candidate_dataset` aceita lista de sources — caminho já mapeado
   na doc).
3. **Residual aberto (máquina de origem, BLK)**: classificar as 2 falhas
   OSW (infra vs real) e inspecionar visualmente os 5 casos reais (dado
   truncado vs limitação do segmentador) — candidatos a task na máquina
   detentora.
4. Endpoint D12 (failure patterns por coorte): sem assimetria dramática
   (2/132 OSW vs 14/335 LLD).

## CONTEXT_EFFICIENCY

- 5 comandos fecharam a task: identificação (1), rastreio de manifesto (1),
  registro de falhas + agregados (1), preparação ausente + banda (1), doc
  (1). A varredura por case_id achou o registro dedicado em 1 passo.
- Lição incorporada ao ledger: garimpar docs/ por experimentos pré-ciclo
  ANTES de propor qualquer investigação.

## Critérios de saída

- [x] Taxonomia (2 níveis: registro + naturezas via docs/158)
- [x] Composição por coorte e por label (rotas cruzadas)
- [x] Banda de teto analítico no 467
- [x] Ledger (LEDGER-SEED-006 + FAIL-01) + W-040 RESOLVED
- [x] Recomendação: arquivar (sem proposta gated) + residuais BLK declarados
