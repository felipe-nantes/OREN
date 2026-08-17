# RAG_GRAPHRAG

TRIGGERS: RAG, BM25, corpus/chunk/retrieval/context, Neo4j/GraphRAG.  
REAL_PATHS: `dtwin/rag/`, `dtwin/graphrag/`, `dtwin/datasets/`, `configs/medgemma_local_4b_rag.yaml`, `configs/medgemma_local_4b_volumetric_rag.yaml`, `configs/graphrag_neo4j.yaml`, `compose.yaml`.  
MODULES: RAG_TEXT, GRAPHRAG_METADATA, DATASETS_REGISTRY.  
MINIMUM_CONTEXT: DATASETS_REGISTRY, PRIVACY, CACHE_ARTIFACTS, downstream prompt/model.  
REFERENCES: source corpus/license, security, reproducibility; primary retrieval docs.  
CONTRACTS: research-only; corpus/index hash; no labels/test leakage; GraphRAG metadata does not diagnose; Graphify engineering is distinct.  
RISKS: MEDIUM infrastructure, HIGH representation/leakage.  
AUTHORITY: audit retrieval/build tests; corpus/prompt/evaluation change requires HG-06/09.  
REQUIRED_TESTS: deterministic chunk/index/search, corrupt/tamper, path safety, retrieval eval, test-set exclusion, prompt injection/PHI.  
HUMAN_GATE: HG-06/09/11.  
STOP_CONDITIONS: license/provenance missing, protected labels in retrieval, clinical authority implied.  
EXPECTED_EVIDENCE: corpus/index/config hashes, query IDs, retrieved chunk provenance, metrics/limitations.
