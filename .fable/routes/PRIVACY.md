# PRIVACY

TRIGGERS: PHI/LGPD, retention, identifiers, public/private dataset, sharing/log/screenshot.  
REAL_PATHS: DICOM ingest/resolver, `webapp/server.py`, dataset registry, `.gitignore`, logs/manifests.  
MODULES: DICOM_MULTIPHASE_INGEST, DATASETS_REGISTRY, WEBAPP_API_ORCHESTRATION.  
MINIMUM_CONTEXT: `PRIVACY_SECURITY.md`, DEIDENTIFICATION, SECURITY.  
REFERENCES: DICOM PS3.15/security privacy.  
CONTRACTS: minimize; pack/Git contain no patient/private data; UIDs/dates/private tags/pixels considered; purpose/retention explicit.  
RISKS: HIGH privacy.  
AUTHORITY: policy/code audit on synthetic/public data; no access/disclosure expansion.  
REQUIRED_TESTS: PHI key/value/path/log scans, retention cleanup, unauthorized artifact rejection.  
HUMAN_GATE: HG-11.  
STOP_CONDITIONS: PHI or unclear data authority.  
EXPECTED_EVIDENCE: dataset/source/license/de-ID status, minimized fields, residual risk and human approval.

