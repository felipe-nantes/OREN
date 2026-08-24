# OPT_02 — ROBUSTNESS_CORRECTIONS

Objetivo: corrigir bugs de integridade e confiabilidade.

Backlog: ROBUSTNESS_FIX_BACKLOG.yaml (ROB-01..ROB-11), cada item com
CAN_CHANGE_SCIENTIFIC_RESULT declarado.

Regras:
- CAN_CHANGE_SCIENTIFIC_RESULT POSSIBLE/YES => tratamento de mudança
  científica (proposta gated via templates/SCIENTIFIC_CHANGE_PROPOSAL.yaml);
- NO => processo da PHASE_08 (patch mínimo + teste + suíte verde antes/depois);
- fail-open detectado em rota científica NUNCA é corrigido silenciosamente:
  reproduzir, evidenciar, propor.

Ordem recomendada: ROB-02/ROB-03 (sinal da suíte limpo primeiro — barato),
ROB-04 (CI gates protegem o resto do ciclo), ROB-05 (sonda GPU — fecha
blocker), ROB-01 (BLE001 triage), ROB-06/ROB-07/ROB-08, ROB-09 (HG-11),
ROB-10/ROB-11.

Critério de saída: itens NO aplicados e verificados; itens POSSIBLE/YES com
proposta gated resolvida (aplicada ou registrada).
