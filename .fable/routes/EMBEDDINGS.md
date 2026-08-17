# EMBEDDINGS

TRIGGERS: MedSigLIP, vector, dimension, normalization, pooling, `.npy`, extraction.  
REAL_PATHS: `dtwin/learning/medsiglip_embeddings.py`, `dtwin/learning/protocol.py`, embedding configs in `configs/training/`, and extract/verify tools in `tools/`.  
MODULES: MEDSIGLIP_EMBEDDINGS, PANELS_REPRESENTATION, ML_CLASSIFIERS_SPLITS.  
MINIMUM_CONTEXT: MODEL_LOADING, CACHE_ARTIFACTS, PANELS, protocol/revision.  
REFERENCES: PyTorch/reproducibility; model primary docs.  
CONTRACTS: actual config currently model `google/medsiglip-448`, revision full hash, 448 input, float16 CUDA→float32 output, L2, offline; dimension must be verified, not presumed.  
RISKS: HIGH.  
AUTHORITY: validate/cache tests/benchmark options; no representation/model change without HG-09.  
REQUIRED_TESTS: finite/dtype/dimension/norm, deterministic tolerance, input/model/config hash invalidation, corruption/truncation, CPU/GPU tolerance.  
HUMAN_GATE: HG-09, HG-07 if training/evaluation.  
STOP_CONDITIONS: missing full revision/preprocessing identity, incompatible cache, output drift without tolerance.  
EXPECTED_EVIDENCE: input/panel/model/config/output hashes, environment, vector stats, cache decision.
