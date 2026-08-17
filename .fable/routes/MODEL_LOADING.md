# MODEL_LOADING

TRIGGERS: model ID/revision, weights, Hugging Face/Ollama, device, dtype, quantization, offline, OOM.  
REAL_PATHS: `dtwin/learning/medsiglip_embeddings.py`, `dtwin/medgemma_client.py`, `tools/medgemma_server*.py`, `configs/medgemma*.yaml`, `configs/training/medsiglip*.yaml`, `compose*.yaml`.  
MODULES: MEDGEMMA_INFERENCE, MEDSIGLIP_EMBEDDINGS, DOCKER_LAUNCHERS.  
MINIMUM_CONTEXT: target representation, CACHE_ARTIFACTS, REPRODUCIBILITY, PERFORMANCE.  
REFERENCES: PyTorch/Transformers/model official card.  
CONTRACTS: full model/revision and preprocessing identity; fail closed; no silent backend downgrade; offline policy when frozen.  
RISKS: MEDIUM infrastructure, HIGH model/representation.  
AUTHORITY: diagnose/test/propose; revision/dtype/representation needs HG-09.  
REQUIRED_TESTS: missing/corrupt weights, wrong revision/config, health/schema, OOM/timeout, cache invalidation, CPU/GPU tolerance.  
HUMAN_GATE: HG-09.  
STOP_CONDITIONS: model identity/license unavailable, silent fallback, unknown output contract.  
EXPECTED_EVIDENCE: model/revision/hash, backend/device/dtype, dependency versions, health and output validation.

