# SEGMENTATION

TRIGGERS: organ/lesion mask, TotalSegmentator/MRSegmentator, label, morphology, components, fusion/shadow, mask gate.  
REAL_PATHS: `dtwin/stages.py`, `dtwin/segmentation_subprocess.py`, `dtwin/seg_worker.py`, `dtwin/segmentation_contract.py`, `dtwin/segmentation_shadow.py`, `webapp/server.py`, `profiles/figado.yaml`, `configs/segmentation_visualization_v2.yaml`.  
MODULES: SEGMENTATION_RUNTIME, SEGMENTATION_SHADOW_CONTRACT, PIPELINE_ENGINE_STAGES.  
MINIMUM_CONTEXT: GEOMETRY, HARMONIZATION, VOLUMETRY, 3D and source model contract.  
REFERENCES: geometry/testing; model card when available.  
CONTRACTS: compatible physical space; expected dtype/labels; empty/unexpected fail; source/provenance; no universal cleanup.  
RISKS: HIGH.  
AUTHORITY: measure/reproduce/test/options; no semantic task/gate/postprocess change without HG-05.  
REQUIRED_TESTS: empty/corrupt/unexpected labels, geometry mismatch, phase/source selection, component/morphology effect, Dice+surface when reference, downstream volume.  
HUMAN_GATE: HG-05; HG-03/04/09/10 as needed.  
STOP_CONDITIONS: missing mask source/reference/ground truth authority or clinical-quality claim.  
EXPECTED_EVIDENCE: model/revision/task, geometry, mask metrics, rejected cases, before/after volume/topology.

