# SUBTYPING

TRIGGERS: HCC/FNH/hemangioma/cyst subtype, probability mass, top-1, cascade.  
REAL_PATHS: `dtwin/learning/medsiglip_multiclass_classifier.py`, pairwise subtype modules, `dtwin/benchmark/subtype_metrics.py`, `webapp/server.py`, subtype configs.  
MODULES: ML_CLASSIFIERS_SPLITS, BENCHMARK_METRICS_REPORTING.  
MINIMUM_CONTEXT: ML_CLASSIFICATION, CROSS_VALIDATION, METRICS, label taxonomy.  
REFERENCES: sklearn/statistics/metrics.  
CONTRACTS: subtype endpoint separate from binary; only after positive where frozen; named-mass guard; no clinical diagnosis claim.  
RISKS: HIGH / OUT_OF_AUTHORITY if patient diagnosis requested.  
AUTHORITY: verify implementation/metrics; no labels/guard/cascade change without HG-06/08.  
REQUIRED_TESTS: class mapping/polarity, missing/unknown subtype, technical failure, cascade denominator, OOF vs in-sample separation.  
HUMAN_GATE: HG-06/07/08; HG-12 for claim.  
STOP_CONDITIONS: label ontology ambiguity or diagnosis request.  
EXPECTED_EVIDENCE: classes/source, mapping, stage, complete confusion/BA/top-1 and validation regime.

