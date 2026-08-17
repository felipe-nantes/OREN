# HARMONIZATION_RESAMPLING

TRIGGERS: harmonize, resample, reference grid, isotropic, interpolator, resize/crop/pad.  
REAL_PATHS: `dtwin/learning/multiphase_ingest.py`, `dtwin/stages.py`, `dtwin/segmentation_shadow.py`, OpenSwiss registration/preparation modules.  
MODULES: DICOM_MULTIPHASE_INGEST, PIPELINE_ENGINE_STAGES, SEGMENTATION_SHADOW_CONTRACT.  
MINIMUM_CONTEXT: GEOMETRY; REGISTRATION if transform estimated; SEGMENTATION for labels.  
REFERENCES: SimpleITK/ITK resampling and medical geometry.  
CONTRACTS: named moving/reference; explicit transform direction; linear for intensity only when approved; nearest for labels; preserve physical extent intentionally.  
RISKS: HIGH.  
AUTHORITY: characterize/test/options only until HG-04.  
REQUIRED_TESTS: identity grid, known translation/rotation, anisotropy, label-set preservation, empty/out-of-FOV, round-trip landmarks.  
HUMAN_GATE: HG-04; HG-03/05 as applicable.  
STOP_CONDITIONS: interpolator/reference/transform unknown or differing source authorities.  
EXPECTED_EVIDENCE: grids/transforms/interpolators, physical overlap and quantitative before/after.

