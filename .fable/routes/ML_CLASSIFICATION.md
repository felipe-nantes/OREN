# ML_CLASSIFICATION

TRIGGERS: classifier, prediction, score, aggregation, logistic/MLP/LoRA, false positive/negative.  
REAL_PATHS: `dtwin/learning/medsiglip_classifier.py`, `dtwin/learning/medsiglip_multiclass_classifier.py`, `dtwin/learning/medsiglip_head_classifier.py`, `dtwin/learning/medsiglip_partial_finetune.py`, `dtwin/learning/multi_signal_fusion.py`, `dtwin/learning/multi_signal_production.py`, `dtwin/learning/visual_inference.py`.  
MODULES: ML_CLASSIFIERS_SPLITS, MEDSIGLIP_EMBEDDINGS.  
MINIMUM_CONTEXT: PANELS, EMBEDDINGS, CROSS_VALIDATION, METRICS, protected-label protocol.  
REFERENCES: sklearn, PyTorch, statistics/reproducibility.  
CONTRACTS: labels isolated; learned transforms train-only; threshold/tuning inner-only; one OOF per unit; target endpoint fixed.  
RISKS: HIGH.  
AUTHORITY: reproduce/audit/test/options; no model/labels/objective change without HG-06/07/08/09.  
REQUIRED_TESTS: leakage, permuted labels, fit boundaries, aggregation/threshold, technical failures, deterministic seed, external/LODO if claim.  
HUMAN_GATE: HG-06–09.  
STOP_CONDITIONS: patient classification asked as diagnosis, label ambiguity, leakage, missing split/protocol.  
EXPECTED_EVIDENCE: training/eval ledger, configs/hashes, folds, OOF, confusion/CI and limitations.
