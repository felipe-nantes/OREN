# CONFIG_PROFILES

TRIGGERS: YAML/JSON config, profile, default, env var, scenario/feature flag, scientific constant.  
REAL_PATHS: `profiles/figado.yaml`, `configs/`, `compose*.yaml`, `webapp/server.py` env/default registry, loaders in core/learning/benchmark.  
MODULES: CONFIG_PROFILES and every consumer.  
MINIMUM_CONTEXT: semantic routes for each key, contracts and provenance/cache.  
REFERENCES: YAML/Python/reproducibility plus target model/geometry refs.  
CONTRACTS: schema/version/allowed path; config hash in artifacts; no browser arbitrary path; defaults explicit; numbers not promoted to scientific contract without source.  
RISKS: MEDIUM syntactic, HIGH semantic.  
AUTHORITY: validate/document; value/default change follows target HG.  
REQUIRED_TESTS: missing/unknown/wrong type/range, default parity, config hash invalidation, all authorized scenarios, no secret path injection.  
HUMAN_GATE: HG-01 and target HG-02–10.  
STOP_CONDITIONS: key authority/rationale unknown, hidden default or conflicting configs.  
EXPECTED_EVIDENCE: resolved config+source/hash, consumers/downstream, before/after semantics and tests.

