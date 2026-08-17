# GEOMETRY

TRIGGERS: origin, spacing, direction, affine, axis, LPS/RAS, flip/inversion, physical point, orientation.  
REAL_PATHS: `dtwin/core.py`, `dtwin/stages.py`, `dtwin/segmentation_contract.py`, `dtwin/volumetry.py`, `dtwin/viewer_artifacts.py`, `webapp/server.py`.  
MODULES: CORE_IO_GEOMETRY plus every mask/image/mesh consumer.  
MINIMUM_CONTEXT: HARMONIZATION_RESAMPLING, SEGMENTATION/3D as applicable.  
REFERENCES: DICOM, SimpleITK, NiBabel medical geometry cards.  
CONTRACTS: ARRAY != IMAGE GEOMETRY; preserve origin/spacing/direction/convention/reference grid; explicit units.  
RISKS: HIGH_SCIENTIFIC_GEOMETRIC.  
AUTHORITY: phantoms/tests/hypothetical patch; no convention/tolerance change without HG-03.  
REQUIRED_TESTS: asymmetric landmarks, index↔physical round-trip, oblique direction, flips/permutations, LPS↔RAS, geometry mismatch failure.  
HUMAN_GATE: HG-03, sometimes HG-04/HG-10.  
STOP_CONDITIONS: unknown convention, transform direction or tolerance.  
EXPECTED_EVIDENCE: before/after physical coordinates, full geometry tuple, unit/tolerance and downstream trace.

