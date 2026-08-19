# EVIDENCE PACKAGE — TASK-2026-08-18-PH05-INT-02

```yaml
TASK_ID: TASK-2026-08-18-PH05-INT-02
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em 515b7b3; teste novo NAO commitado
TASK_DESCRIPTION: >
  PHASE_05 wave 2 — fronteira real do webapp: uvicorn em subprocess de
  verdade (boot, health por socket, conflito de porta, liberacao) e
  concorrencia de jobs (LONG_PLAN P1 #8).
ROUTE: [ORCHESTRATION, MEMORY_CONCURRENCY, FRONTEND (fronteira), TESTS_BUILD_ENVIRONMENT]
MODULES: [WEBAPP_API_ORCHESTRATION, TEST_SUITE]
FILES_ANALYZED:
  - webapp/server.py:308-340 (_jobs, _lock, _set, snapshot-persist fora do lock)
  - webapp/server.py:1560-1584 (_persist_completed_job_state: allowlist sanitizada, tmp+replace SEM try/finally)
  - tests/test_webapp.py (cobertura previa: restart/tamper ja cobertos — nao duplicado)
FILES_CHANGED:
  - tests/test_integration_webapp_boundary.py (NOVO; 3 testes)
RISK_LEVEL: LOW (testes; nenhum codigo de producao alterado)
CONTRACTS_INVOLVED: [SW-ATOMIC-01 (fronteira), SW-FAIL-CLOSED-01 (leitura)]
BASELINE: 1700 passed / 1 failed ambiental / 4 skipped
TESTS_ADDED:
  - "uvicorn REAL: boot em porta efemera (health por HTTP de socket), segunda instancia na mesma porta falha (exit != 0), primeira continua saudavel, porta liberada apos terminate — a fronteira exata em que run_win.ps1 confia (8s)"
  - "concorrencia: 16 threads x 50 updates em _set — ZERO atualizacoes perdidas; 8 conclusoes concorrentes — arquivo final integro com schema oren-webapp-completed-job-v1"
  - "atomicidade no disco: leitor continuo durante 200 ciclos de conclusao NUNCA observa JSON parcial (OSError transitoria de sharing violation do Windows tolerada e documentada como realidade da plataforma, nao corrupcao)"
TESTS_AFTER:
  - "arquivo isolado: 3 passed, 10.8s"
  - "suite completa: ver fechamento da wave"
MUTATION_RESULT: NAO_APLICADO (criterio da fase e exercicio real de fronteira; modos de falha verificados empiricamente antes dos asserts)
BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Gateway MedGemma real nao sobe no teste (exige pesos/GPU — BLOCKER do card); a integracao webapp<->gateway real fica para execucao manual via run_win.ps1 (ja validada nesta sessao quando o usuario testou o app).
UNRESOLVED_RISKS:
  - "TD-015 (NOVO, achado desta wave): WinError 5 em replaces concorrentes do estado final do job, apenas logado (fail-open na trilha de restore) + 3 temporarios vazados observados (sem try/finally). Destino integro; correcao candidata = retry + try/finally, fase 08."
HUMAN_GATE: nenhum
DIFF_SUMMARY: 1 arquivo de teste novo (~215 linhas); TD-015 registrado
ROLLBACK: deletar o arquivo de teste
FINAL_STATUS: DONE (nao commitado)
```

## Notas de metodo

1. Meu assert inicial esperava o dict de job INTEIRO no estado persistido e
   falhou; a leitura de `_persist_completed_job_state` mostrou uma ALLOWLIST
   sanitizada por design (state/step/progress/result/...). O teste foi
   corrigido para o contrato real — o design esta certo, o teste e que estava
   errado.
2. O leitor concorrente inicialmente tratava OSError como corrupcao; no
   Windows, sharing violation transitoria durante os.replace e realidade da
   plataforma, nao violacao de atomicidade. O teste agora distingue:
   JSONDecodeError (parcial) = falha; OSError transitoria = tolerada.
3. O achado TD-015 nasceu de uma falha "indesejada" do meu proprio teste —
   os logs de `falha ao persistir estado final` sob corrida eram genuinos e
   viraram o registro de divida com evidencia reproduzivel.

## Adendo — contraexemplo do Hypothesis em teste da PHASE_04 (corrigido)

Durante a suite completa desta wave, o Hypothesis encontrou um contraexemplo
NOVO no `test_property_splits_isolation.py` (PHASE_04): coorte com
`outer=3/inner=3` em que minha margem estatica de grupos por classe nao
garante a precondicao do gerador — o balanceamento de `_assign_groups` e por
CASOS, nao por grupos, entao uma classe pode ficar com menos grupos que
`inner` no treino externo. **O `splits.py` esta correto (falha fechado com
PipelineError)**; o defeito era o teste tratar essa rejeicao legitima como
falha do invariante. Correcao: helper `_splits_ou_descarta` com
`hypothesis.assume()` — exemplos rejeitados pela precondicao sao descartados
(a rejeicao em si ja e coberta pela characterization da PHASE_03). Estabilidade
verificada em 3 rodadas consecutivas + suite completa (1703 passed).
