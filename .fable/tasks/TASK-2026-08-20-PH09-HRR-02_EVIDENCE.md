# EVIDENCE — TASK-2026-08-20-PH09-HRR-02 (PHASE_09, wave 2: auditabilidade DICOM, HG-02)

Data: 2026-08-20 · Executor: agente · Status: **DECISÃO RECEBIDA E APLICADA**
(ordem cronológica preservada: proposta → STOP → B1 aprovada → aplicação)

## Comportamento atual (OBSERVED, código lido nos sítios)

1. **Colisão de papéis** — `raw_dicom_phase_resolver._explicit_role` (118-126):
   texto que casa com 2+ conjuntos de tokens (arterial/venosa/tardia) retorna
   `None` → a série vira "não-rotulada", mas continua elegível no caminho
   temporal (`ordered_axial_t1_postcontrast_series`) e pode receber um papel
   por posição — o manifesto não registra que houve colisão.
2. **Intermediárias descartadas** — `_select` (281-285): com 4+ séries
   dinâmicas elegíveis, seleciona `dynamic[0]/[1]/[-1]`; as intermediárias
   não aparecem em lugar nenhum do manifesto (`series_discovered` conta tudo,
   sem dizer o que era elegível e ficou de fora).

Protegidos por `tests/test_characterization_dicom_phase_selection.py`
(PHASE_03; revisão humana da época manteve como risco documentado — SEM
correção desenhada então). Registro: TD-014 (HIGH, planned fase 09, HG-02).

## Raio de impacto (SOURCE_SUPPORTED)

- Consumidores do manifesto: APENAS
  `tools/run_raw_phase_equivalence_benchmark.py`, que lê
  `selected[phase]["series_hash"]` — campos ADITIVOS não o afetam.
- `_select`: 1 único caller (`resolve_raw_dicom_phases`).
- Schema `argos-raw-dicom-phase-resolution-v1`: verificado por igualdade de
  string; campos novos não quebram nenhum leitor existente.

## PROPOSTA (auditabilidade apenas — seleção bit a bit idêntica)

- `RawSeries.ambiguous_roles: tuple[str, ...]` populado quando o texto casa
  com 2+ papéis (refatorando `_explicit_role` para expor os matches; retorno
  público inalterado).
- `_select` passa a retornar também um dict de auditoria (caller único):
  séries dinâmicas elegíveis do estudo vencedor NÃO selecionadas
  (series_hash/series_number/frames).
- Manifesto ganha campos aditivos:
  - `selected[role].ambiguous_text_roles` (quando não vazio);
  - `series_with_ambiguous_text_roles` (contagem global);
  - `unselected_eligible_dynamic_series` (lista; vazia no caminho explícito).
- NENHUMA heurística de seleção alterada — mesmas séries escolhidas, mesmos
  códigos de erro, mesma confiança.

Alternativas: B2 = também mudar a seleção (rejeitar/penalizar séries com
colisão de papéis) — NÃO recomendada nesta wave (mudaria escolhas; seria
outra proposta com regressão própria); C = manter como está.

## Plano de teste (se aprovada)

1. Characterization existente INTACTA (seleção não muda; asserts atuais
   continuam passando) + asserts novos sobre os campos de auditoria.
2. Testes novos: colisão de 2 papéis → manifesto registra; 4 dinâmicas →
   intermediária listada em `unselected_eligible_dynamic_series`.
3. Sonda de mutação (campo de auditoria suprimido → KILLED).
4. Suíte completa antes/depois.

## Classificação de evidência

- OBSERVED: código dos sítios; consumidores via grep.
- SOURCE_SUPPORTED: aditividade do schema; caller único de _select.
- INFERRED: nada material.

## STOP — aguardando decisão HG-02

---

## PÓS-GATE: decisão recebida e aplicada (2026-08-20)

**APROVADO B1** (Felipe Nantes, via AskUserQuestion; registro formal em
HUMAN_DECISIONS.md item 14). Fecha os 2 itens abertos do TD-014.

### Aplicação

- `_explicit_role_matches` extraído (retorno público de `_explicit_role`
  inalterado); `RawSeries.ambiguous_roles` populado em `_read_series`.
- `_select` retorna 4º elemento de auditoria (caller único): intermediárias
  elegíveis não selecionadas (`dynamic[2:-1]`) do estudo vencedor.
- Manifesto: campos aditivos `series_with_ambiguous_text_roles`,
  `unselected_eligible_dynamic_series` e `ambiguous_text_roles` por série
  selecionada (quando não vazio). Seleção bit a bit idêntica.

### Verificação (OBSERVED)

- Characterization ESTENDIDA (não invertida): os 2 testes dos itens do
  TD-014 mantêm os asserts de seleção originais e ganham asserts dos campos
  de auditoria (colisão [arterial, venous] registrada; série 9 listada como
  descartada). 19 passed nos arquivos do resolver.
- Sondas de mutação: **2/2 KILLED**
  (`evidence/PH09/mutation_probes_w2_2026-08-20.json`) — P18 lista de
  descartadas suprimida; P19 registro de colisão suprimido.
- Suíte completa (portão, 2m27s): **1769 passed / 4 skipped / 1 failed
  ambiental** (pré-existente) — zero regressões. Wave 2 DONE.
