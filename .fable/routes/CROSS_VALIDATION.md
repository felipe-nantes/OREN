# CROSS_VALIDATION

TRIGGERS: folds, nested CV, patient/group split, OOF, leakage, train/validation/test, LODO.  
REAL_PATHS: `dtwin/learning/splits.py`, `dtwin/learning/protocol.py`, classifier modules in `dtwin/learning/`, `configs/training/hybrid_v1_protocol.yaml`, `configs/training/hybrid_v1_protocol.lock.json`, and retrospective multicohort modules in `dtwin/learning/`.  
MODULES: ML_CLASSIFIERS_SPLITS, EXPERIMENTAL_BENCHMARKS.  
MINIMUM_CONTEXT: labels/cohorts, METRICS_STATISTICS, AUDIT_PROVENANCE.  
REFERENCES: sklearn nested CV; Cawley & Talbot; statistics.  
CONTRACTS: patient/group isolation; 5 outer×4 inner for frozen hybrid protocol; tuning/preprocessing inner; one OOF/exam; outer estimates only.  
RISKS: HIGH; possible leakage is critical STOP.  
AUTHORITY: audit/reproduce/write tests; no split/tuning change without HG-06/07.  
REQUIRED_TESTS: disjoint group sets, duplicate IDs, one OOF, train-only fit, threshold inner-only, deterministic seeds, permutation control.  
HUMAN_GATE: HG-06/HG-07/HG-08.  
STOP_CONDITIONS: overlap/leakage, missing patient group, consumed holdout represented as external.  
EXPECTED_EVIDENCE: fold membership hashes, overlap=0, fit trace, OOF ledger and population role.
