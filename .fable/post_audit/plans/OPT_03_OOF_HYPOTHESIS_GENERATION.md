# OPT_03 — OOF_HYPOTHESIS_GENERATION

Objetivo: produzir hipóteses de melhoria baseadas em evidência.

Base: OOF_IMPROVEMENT_REGISTER.yaml (H-01..H-05) + resultados das medições
(H-01..H-04 são medições que NÃO consomem o outer e não mudam nada).

Regras:
- nenhuma hipótese sem evidência citável (SR/TD/docs/ledger/medição);
- "melhorar OOF" não é hipótese; mecanismo explícito obrigatório;
- checar o EXPERIMENT_LEDGER antes de formular (do_not_repeat);
- prioridade guiada por POST_AUDIT_PLAN §4 (information gain primeiro);
- ANTES de qualquer experimento interventivo: decidir o regime anti-consumo
  do outer (POST_AUDIT_PLAN §2) com o aprovador — decisão humana formal.

Saída: hipóteses refinadas/novas no register, cada uma pronta para virar
MICROEXPERIMENT (fase 04) ou arquivada com razão.
Critério de saída: fila priorizada aprovada pelo humano + regime de
avaliação decidido.
