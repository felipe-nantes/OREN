# OPT_04 — CONTROLLED_MICROEXPERIMENTS

Objetivo: executar uma hipótese por vez. **NÃO EXECUTAR nesta fase de
planejamento — esta fase só roda com autorização explícita e após OPT_03.**

Regras invariáveis:
- ONE SCIENTIFIC HYPOTHESIS -> ONE MINIMAL PATCH -> ONE EVIDENCE PACKAGE;
- template MICROEXPERIMENT.yaml preenchido e APROVADO antes do patch
  (approval_before_change);
- seleção SOMENTE por inner CV / dev signal (regime aprovado em OPT_03);
- toda leitura do outer registrada no ledger (outer_inspection_counter);
- endpoints de domínio e falha obrigatórios (origin probe, LODO, por coorte,
  failure rate, denominador constante);
- expected_direction declarada A PRIORI (predição falsificável);
- reprodutibilidade: >=2 runs/seeds antes de qualquer conclusão;
- resultado (inclusive negativo) SEMPRE entra no EXPERIMENT_LEDGER;
- candidato nunca sobrescreve baseline (artefatos separados).

Critério de saída por experimento: ledger atualizado com decision + evidence.
