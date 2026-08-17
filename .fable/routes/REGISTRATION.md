# REGISTRATION

TRIGGERS: register, alignment, fixed/moving, transform, elastix, metric/optimizer.  
REAL_PATHS: `dtwin/benchmark/openswisshcc_registration.py`, `dtwin/benchmark/openswisshcc_alignment.py`, `dtwin/benchmark/openswisshcc_multisequence_geometry.py`, `dtwin/learning/multiphase_ingest.py`.  
MODULES: EXPERIMENTAL_BENCHMARKS, DICOM_MULTIPHASE_INGEST.  
MINIMUM_CONTEXT: GEOMETRY + HARMONIZATION_RESAMPLING + target scientific protocol.  
REFERENCES: ITK/SimpleITK registration, registration papers.  
CONTRACTS: fixed/moving and transform direction explicit; parameter/metric/optimizer/reference recorded; Dice is not universal proof.  
RISKS: HIGH.  
AUTHORITY: run synthetic/retrospective audit and propose; no method/parameter change without HG-04.  
REQUIRED_TESTS: identity, recoverable known transform, landmarks, before/after overlap, degeneracy/failure.  
HUMAN_GATE: HG-04.  
STOP_CONDITIONS: labels/masks used during blind inference, ambiguous transform or missing reference.  
EXPECTED_EVIDENCE: transform manifests, sanitized landmarks, failure modes and downstream outputs.
