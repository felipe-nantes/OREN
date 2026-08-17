# LOCALIZATION

TRIGGERS: lesion candidate, ROI, box, top-k, localizer, `liver_lesions_mr`.  
REAL_PATHS: `dtwin/candidate_region.py`, `dtwin/candidate_subprocess.py`, `dtwin/candidate_worker.py`, localizer modules in `dtwin/benchmark/`, `webapp/server.py`.  
MODULES: CANDIDATE_LOCALIZATION, WEBAPP_API_ORCHESTRATION.  
MINIMUM_CONTEXT: GEOMETRY, SEGMENTATION, PIPELINE, endpoint/protocol.  
REFERENCES: geometry, Metrics Reloaded.  
CONTRACTS: automatic unconfirmed candidate; post-inference; no feedback by default; not a validated lesion mask/volume.  
RISKS: HIGH.  
AUTHORITY: audit recall/geometry and propose; no use as diagnosis/truth or feedback without approval.  
REQUIRED_TESTS: geometry clip-to-liver, empty/multiple candidates, tamper/hash, post-inference ordering, top-k denominators, failure isolation.  
HUMAN_GATE: HG-05/06/07/10; HG-12 for clinical interpretation.  
STOP_CONDITIONS: lesion GT used during inference, candidate called confirmed, missing reference geometry.  
EXPECTED_EVIDENCE: candidate provenance/role, boxes/mask hashes, recall endpoint/denominator and review status.
