# PHASE 03 — Characterization

STATUS: NOT_STARTED

OBJECTIVE: protect unknown legacy behavior without calling it correct.  
INPUTS: module contracts/gaps, baseline, minimal fixtures.  
TASKS: mark small characterization tests; capture legacy artifacts/edge behavior; avoid giant snapshots.  
OUTPUTS: reproducible tests labeled `OBSERVED_BEHAVIOR`.  
ENTRY_CRITERIA: uncertainty and target paths bounded.  
EXIT_CRITERIA: intended investigation can change code without losing unknown behavior silently.  
BLOCKERS: PHI/licensing/irreproducible GPU.  
EVIDENCE: test IDs, fixtures, commands, limitations.  

