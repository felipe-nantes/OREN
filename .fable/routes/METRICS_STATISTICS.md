# METRICS_STATISTICS

TRIGGERS: threshold, sensitivity, specificity, BA, AUC, CI, bootstrap, denominator, failure/inconclusive.  
REAL_PATHS: `dtwin/benchmark/metrics.py`, `dtwin/benchmark/subtype_metrics.py`, `dtwin/benchmark/reporting.py`, classifier evaluators in `dtwin/learning/`, `webapp/server.py`, `configs/training/`, `configs/benchmark/`.  
MODULES: BENCHMARK_METRICS_REPORTING, ML_CLASSIFIERS_SPLITS.  
MINIMUM_CONTEXT: CROSS_VALIDATION, cohort/label/failure contracts, manuscript claims.  
REFERENCES: statistics, Metrics Reloaded, sklearn.  
CONTRACTS: internal 75%/75% is not clinical; Wilson for proportions; bootstrap unit patient when specified; failures/inconclusives count as errors in primary frozen protocol; undefined remains N/E.  
RISKS: HIGH.  
AUTHORITY: recompute/verify/propose; no threshold/metric/denominator change without HG-08.  
REQUIRED_TESTS: exact confusion, absent class, undefined, order invariance, failures, stratification, CI fixtures, threshold isolation.  
HUMAN_GATE: HG-08; HG-06/07 as coupled.  
STOP_CONDITIONS: denominator/cohort/endpoint ambiguous, threshold selected on final set, clinical threshold request.  
EXPECTED_EVIDENCE: TP/TN/FP/FN, n/failures, formulas/method, CI, config and complete before/after.
