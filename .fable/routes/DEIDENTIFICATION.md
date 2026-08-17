# DEIDENTIFICATION

TRIGGERS: anonymize, pseudonym, PatientName/ID, UID/date/private tag, overlay, burned-in pixel, retention.  
REAL_PATHS: `dtwin/stages.py`, `dtwin/learning/raw_dicom_phase_resolver.py`, `dtwin/datasets/dicom_utils.py`, `webapp/server.py`, `.gitignore`.  
MODULES: DICOM_MULTIPHASE_INGEST, DATASETS_REGISTRY, WEBAPP_API_ORCHESTRATION.  
MINIMUM_CONTEXT: PRIVACY_SECURITY, DICOM route, storage/artifact flow.  
REFERENCES: DICOM PS3.15, security/privacy card.  
CONTRACTS: data minimization; no PHI in Git/pack/log; conversion does not prove de-ID.  
RISKS: HIGH privacy.  
AUTHORITY: inspect synthetic/public metadata and propose; never expose PHI.  
REQUIRED_TESTS: tag/private/overlay/pixel/name/log scans, failure on unsafe output, retention cleanup integration.  
HUMAN_GATE: HG-11.  
STOP_CONDITIONS: actual PHI encountered, legal basis/retention unknown.  
EXPECTED_EVIDENCE: sanitized inventory, policy/profile used, residual-risk checklist, deletion/storage proof.

