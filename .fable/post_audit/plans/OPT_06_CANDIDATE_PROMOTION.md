# OPT_06 — CANDIDATE_PROMOTION

Objetivo: determinar se um candidato pode substituir o baseline.

Processo:
1. CANDIDATE_COMPARISON.yaml completo (endpoints PRÉ-registrados antes da
   leitura final do outer);
2. leitura final do outer conforme regime aprovado (registrada no contador);
3. CANDIDATE_PROMOTION_GATE.yaml: TODOS os 16 campos verificados;
4. red flags (coorte pior, dependência de origem maior, falhas maiores,
   variância maior, leakage suspeito) bloqueiam por padrão;
5. decisão humana formal (formato HUMAN_GATES.md) citando a comparação;
6. ledger atualizado (decision: PROMOTED/REJECTED).

Melhora deve ser REPRODUCIBLE, não single-run.
Critério de saída: decisão formal registrada, qualquer que seja.
