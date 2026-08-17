# DATASETS_REGISTRY

TRIGGERS: dataset ingest/registry/manifest/license, CHAOS/LLD/OpenSwiss/LiverHccSeg/TCGA.  
REAL_PATHS: `dtwin/datasets/`, `configs/datasets/`, benchmark importers/preparations, `data/`/`casos/` ignored roots.  
MODULES: DATASETS_REGISTRY, EXPERIMENTAL_BENCHMARKS.  
MINIMUM_CONTEXT: PRIVACY, DICOM/NIfTI, AUDIT_PROVENANCE, target protocol/labels.  
REFERENCES: dataset primary license/source, DICOM/geometry/reproducibility.  
CONTRACTS: format/modality truthful; MR-only where declared; raw UIDs not persisted; research-only; labels/masks isolated from inference; patient identity/group preserved safely.  
RISKS: HIGH.  
AUTHORITY: validate manifests/licensing/geometry; no cohort/label/inclusion change without HG-06/11.  
REQUIRED_TESTS: MR vs CT, corrupt NIfTI/DICOM, duplicate/path, annotation geometry, source hash/license, label isolation, unsafe archive.  
HUMAN_GATE: HG-06/HG-11.  
STOP_CONDITIONS: license/consent/label mapping/patient group ambiguous, PHI detected.  
EXPECTED_EVIDENCE: source/license/version/hash, cases/series counts, exclusions/failures and protected-data boundaries.

