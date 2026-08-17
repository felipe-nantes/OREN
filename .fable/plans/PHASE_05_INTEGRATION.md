# PHASE 05 — Integration

STATUS: NOT_STARTED

OBJECTIVE: exercise real boundaries and fail/restart behavior.  
INPUTS: unit/contracts, synthetic/public fixtures, runtime services.  
TASKS: DICOM→image→harmonize→mask→volume/representation; subprocess crash; artifact corruption; API/viewer; Docker E2E.  
OUTPUTS: integration suite with expensive boundaries mocked only when necessary.  
ENTRY_CRITERIA: invariants protect critical semantics.  
EXIT_CRITERIA: each critical stage succeeds and fails closed; resume/idempotency verified.  
BLOCKERS: GPU/model/download/certificate/runtime availability.  
EVIDENCE: logs, hashes and artifact manifests.  

