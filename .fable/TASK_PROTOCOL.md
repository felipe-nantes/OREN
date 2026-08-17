# Protocolo padrão de task

```text
RECEIVE TASK
  → READ CURRENT STATE
  → GENERATE TASK CARD
  → ROUTE (incluindo trânsito upstream/downstream)
  → LOAD MINIMUM SUFFICIENT CONTEXT
  → TRACE IMPACT
  → CLASSIFY RISK/AUTHORITY
  → IDENTIFY CONTRACTS
  → ESTABLISH BASELINE
  → CHARACTERIZE IF NECESSARY
  → WRITE CONTRACT/PROPERTY TESTS
  → RUN INTEGRATION/SCIENTIFIC/GEOMETRIC TESTS IF APPLICABLE
  → RUN STATIC/MUTATION/ADVERSARIAL CHECKS IF APPLICABLE
  → PROPOSE ONE SMALL CHANGE
  → CHECK HUMAN GATE
  → IF AUTHORIZED, APPLY SMALL PATCH
  → RETEST AND COMPARE
  → GENERATE EVIDENCE PACKAGE
  → UPDATE CURRENT STATE AND HANDOFF
```

## Regras de decisão

- Investigação/report-only não autoriza patch.
- Diagnose não autoriza correção, salvo pedido explícito que inclua implementação.
- `OBSERVED_BEHAVIOR` pode receber characterization test, não rótulo de correto.
- LOW pode avançar após baseline/testes. MEDIUM exige proposta cautelosa e, se semântica científica for possível, promoção a HIGH. HIGH precisa do human gate. OUT_OF_AUTHORITY termina em STOP_REPORT.
- Toda tarefa segue Definition of Done de `LONG_PLAN.md`; `pytest passou` isoladamente nunca basta.

