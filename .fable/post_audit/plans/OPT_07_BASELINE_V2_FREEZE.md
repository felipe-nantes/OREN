# OPT_07 — BASELINE_V2_FREEZE

Objetivo: gerar novo baseline SOMENTE após aprovação humana em OPT_06.

Processo (espelha PHASE_00/PHASE_10 da auditoria):
1. congelar artefatos do candidato promovido (freeze + assinaturas na mesma
   convenção do lock atual: prediction_signature, oof_predictions_sha256,
   training_protocol_signature);
2. re-verificar âncoras (467=220+247; 451/16 do novo regime se mudou — só
   com HG-08 previamente aprovado);
3. atualizar SCIENTIFIC_CONTRACTS/CURRENT_STATE/LONG_PLAN via HG-01 quando
   contratos forem tocados;
4. suíte completa + regressões científicas/geométricas como portão;
5. registrar AUDITED_BASELINE_V2 em evidence package próprio;
6. o baseline anterior permanece íntegro e referenciável (nunca sobrescrito).

Critério de saída: baseline v2 congelado, assinado (hash-integridade,
SW-001), documentado e aprovado; ou ciclo encerrado sem promoção (também é
um resultado válido — registrar).
