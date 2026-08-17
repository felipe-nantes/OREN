# DICOM

TRIGGERS: DICOM, series/study/SOP UID, phase, sequence, slice order, MPR/MIP/subtraction, transfer syntax.  
REAL_PATHS: `dtwin/core.py`, `dtwin/learning/raw_dicom_phase_resolver.py`, `dtwin/learning/multiphase_ingest.py`, `webapp/server.py`, `dtwin/datasets/dicom_utils.py`.  
MODULES: CORE_IO_GEOMETRY, DICOM_MULTIPHASE_INGEST, WEBAPP_API_ORCHESTRATION.  
MINIMUM_CONTEXT: GEOMETRY, DEIDENTIFICATION, PIPELINE routes; relevant profile/config.  
REFERENCES: DICOM PS3.3/3.5/3.15 and pydicom cards.  
CONTRACTS: no series mixing; physical ordering; explicit derived policy; phase semantics; MR-only where configured.  
RISKS: HIGH_SCIENTIFIC_GEOMETRIC.  
AUTHORITY: reproduce/write tests/options; no selection/phase change without HG-02.  
REQUIRED_TESTS: synthetic DICOM permutations, missing/duplicate/irregular/multiframe/codec, real minimal integration, PHI negative tests.  
HUMAN_GATE: HG-02; HG-11 when data/privacy.  
STOP_CONDITIONS: ambiguous study/phase/orientation, missing tags, PHI, unknown contract.  
EXPECTED_EVIDENCE: tags (sanitized), chosen/rejected series rationale, geometry, hashes, downstream impact.

