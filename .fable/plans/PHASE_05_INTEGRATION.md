# PHASE 05 — Integration

STATUS: DONE (2026-08-18 — waves 1-3, TASK-2026-08-18-PH05-INT-01..03)

EXIT_RESULT: fronteiras reais exercitadas — subprocess de segmentação (crash
exit 2, runtime NUL reparado), corrupção entre estágios fail-closed, uvicorn
real (boot/conflito/liberação), concorrência de jobs (achado TD-015), cadeia
DICOM->resolver->GDCM->harmonização com pixels reais (sucesso + reprova por
cobertura). Sucesso GPU-bound validado manualmente na sessão (run_win.ps1);
blockers declarados. Exit review em tasks/TASK-2026-08-18-PH05-INT-03_EVIDENCE.md.

OBJECTIVE: exercise real boundaries and fail/restart behavior.  
INPUTS: unit/contracts, synthetic/public fixtures, runtime services.  
TASKS: DICOM→image→harmonize→mask→volume/representation; subprocess crash; artifact corruption; API/viewer; E2E nativo (launcher run_win.ps1 — item reescrito em 2026-08-18: 'Docker E2E' ficou obsoleto após a migração TASK-2026-08-18-MIGR-01; o caminho oficial é nativo).  
OUTPUTS: integration suite with expensive boundaries mocked only when necessary.  
ENTRY_CRITERIA: invariants protect critical semantics.  
EXIT_CRITERIA: each critical stage succeeds and fails closed; resume/idempotency verified.  
BLOCKERS: GPU/model/download/certificate/runtime availability.  
EVIDENCE: logs, hashes and artifact manifests.  

