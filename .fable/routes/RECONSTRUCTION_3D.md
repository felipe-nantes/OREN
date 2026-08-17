# RECONSTRUCTION_3D

TRIGGERS: mesh, STL/VTP, marching cubes, isovalue, smoothing, Taubin, decimation, topology, watertight.  
REAL_PATHS: `dtwin/stages.py`, `dtwin/viewer_artifacts.py`, `dtwin/viewer_xr.py`, `profiles/figado.yaml`, `viewer/`.  
MODULES: VIEWER_ARTIFACTS_3D, PIPELINE_ENGINE_STAGES, WEBXR_QUEST.  
MINIMUM_CONTEXT: GEOMETRY, SEGMENTATION, VOLUMETRY, FRONTEND/PERFORMANCE.  
REFERENCES: scikit-image marching cubes, PyVista/Trimesh, mesh card.  
CONTRACTS: spacing/units/coordinate space explicit; visual quality ≠ quantitative correctness; mask is source; no universal largest-component rule.  
RISKS: HIGH for quantitative operations; MEDIUM visual-only if proven.  
AUTHORITY: phantom/comparison/hypothetical patch; quantitative cleanup needs HG-10.  
REQUIRED_TESTS: cube/sphere analytic, degenerate faces, Euler/watertight/manifold/components, volume/surface error, LOD/clipping, before/after cleanup.  
HUMAN_GATE: HG-10; HG-03/05; HG-12 for anatomy claims.  
STOP_CONDITIONS: units/space/source unknown or visual asset used as true anatomy.  
EXPECTED_EVIDENCE: mesh parameters, source mask hash, metrics before/after, quantitative loss and viewer screenshots only as supplemental evidence.

