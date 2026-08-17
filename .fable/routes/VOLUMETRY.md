# VOLUMETRY

TRIGGERS: volume, mL/mm³, voxels, dimensions, Couinaud partition, technical range.  
REAL_PATHS: `dtwin/volumetry.py`, `dtwin/stages.py`, `profiles/figado.yaml`, `tests/test_volumetry.py`, docs 220/221.  
MODULES: VOLUMETRY, SEGMENTATION, VIEWER_ARTIFACTS_3D.  
MINIMUM_CONTEXT: GEOMETRY, SEGMENTATION, HARMONIZATION, 3D if display/mesh.  
REFERENCES: SimpleITK geometry, mesh 3D.  
CONTRACTS: authoritative mL = positive mask voxels×spacing product/1000; mesh is not authoritative; source mask/provenance explicit; candidate unconfirmed; Couinaud exact partition when usable.  
RISKS: HIGH.  
AUTHORITY: verify/calculation tests/options; no source/gate/unit/cleanup change without HG-03/05/10.  
REQUIRED_TESTS: analytic masks/anisotropy, geometry mismatch, empty, partition union/disjoint, atomic JSON/CSV and independent tamper verifier.  
HUMAN_GATE: HG-05/HG-10; HG-12 for clinical interpretation.  
STOP_CONDITIONS: mask source/geometry/unit unknown or “clinically accurate” claim.  
EXPECTED_EVIDENCE: voxel count, spacing, formula, source hash, grade meaning/limitations, verifier result.

