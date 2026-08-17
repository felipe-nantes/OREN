# PANELS

TRIGGERS: panel, tile, crop, liver-enriched, RGB, FOV, axial/coronal/sagittal, window.  
REAL_PATHS: `dtwin/medgemma_panel.py`, `dtwin/medgemma_panel_multiphase.py`, `dtwin/medgemma_panel_liver_enriched.py`, `dtwin/medgemma_panel_full_fov.py`, `dtwin/learning/exam_to_panels.py`.  
MODULES: PANELS_REPRESENTATION, DICOM_MULTIPHASE_INGEST, SEGMENTATION.  
MINIMUM_CONTEXT: representation config, GEOMETRY, downstream MedGemma/MedSigLIP/cache.  
REFERENCES: project scientific contracts; geometry.  
CONTRACTS: channel semantics and order fixed; no lesion mark/PHI; deterministic names/hashes; coverage/crop recorded.  
RISKS: HIGH (representation contract).  
AUTHORITY: audit/benchmark/propose only until HG-09.  
REQUIRED_TESTS: deterministic bytes/order, channel identity, small/large/empty mask, geometry, PHI/overlay absence, pixel/byte limits, embedding regression.  
HUMAN_GATE: HG-09; HG-05 if mask used.  
STOP_CONDITIONS: unknown sequence/channel, hidden label/lesion leakage or incomplete representation.  
EXPECTED_EVIDENCE: panel manifests/hashes, pixel diffs, coverage and downstream score/benchmark comparison.
