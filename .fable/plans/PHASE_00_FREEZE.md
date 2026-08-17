# PHASE 00 — Freeze / baseline

STATUS: DONE (2026-08-17 — TASK-2026-08-17-PH00-BASELINE-01)

OBJECTIVE: congelar snapshot reproduzível sem refatorar.  
INPUTS: HEAD, dirty state, environments, dependencies, hardware, tests, CI, commands.  
TASKS: registrar commit/branch/dirty; Python/packages/OS/GPU/driver; dependency files; Docker images; coleta/execução pytest; doctor; static/coverage/performance baselines onde aplicável.  
OUTPUTS: baseline manifest e logs sem PHI.  
ENTRY_CRITERIA: checkout disponível.  
EXIT_CRITERIA: suíte global executada em ambiente escolhido; failures/warnings explicados; container/backend relevantes identificados; comandos reproduzíveis.  
EXIT_RESULT (2026-08-17): suíte executada no container `argos-runtime:local` (worktree em BASE_COMMIT, árvore gravável): 2 failed / 1605 passed / 3 skipped / 78 warnings em 39,86 s; as 2 falhas são testes Windows-only em POSIX e as 11 do RUN1 eram ambientais (mount ro, git ausente) — todas explicadas; doctor exit 0; comandos e logs em `evidence/PH00/`.  
BLOCKERS: ~~Docker daemon off~~ (resolvido; sockets órfãos removidos); static tools ausentes (ADIADO por decisão humana); ~~suíte ainda não executada~~.  
EVIDENCE: `CURRENT_STATE.md`; `tasks/TASK-2026-08-17-PH00-BASELINE-01_EVIDENCE.md`; `evidence/PH00/`.  

