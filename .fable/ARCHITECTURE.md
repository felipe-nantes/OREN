# Arquitetura e boundaries

## Estado atual

O checkout contém dois produtos sobrepostos: (1) motor DICOM→segmentação→volumetria→3D/WebXR e (2) plataforma de pesquisa/classificação MedGemma/MedSigLIP/benchmarks. Os namespaces `learning` e `benchmark` são mistos e têm imports no runtime web.

## Layering observado

1. Entradas: CLI, FastAPI/upload, configs/profiles.
2. Ingest/geometry: core + raw phase resolver + multiphase ingest.
3. Segmentation: isolated TotalSegmentator/MRSegmentator, mask contracts/shadow.
4. Representation/AI: panels, RAG, embeddings, classifiers, MedGemma.
5. Post-inference: candidate localizer.
6. Artifact engine: refine, volumetry, mesh, 2D refs, manifest/LOD.
7. Delivery/review: webapp, desktop viewer, WebXR/Quest.
8. Evaluation: protected labels, splits, OOF, metrics/reporting.

## Architectural invariants

- Ground truth/lesion masks do not enter feature inference unless an approved supervised-training protocol says so.
- Candidate localization runs after frozen decision and is not feedback by default.
- Geometry travels with the medical image/mask.
- Authoritative volume derives from mask voxels, not render mesh.
- Published artifacts are hash/allowlist verified and require human review.
- Fail closed; no fabricated masks/results.

## Coupling hotspots

- `webapp/server.py` spans transport, domain/scientific rules, concurrency, storage and UI delivery.
- `dtwin/stages.py` spans ingest through publication.
- config constants and geometry helpers are duplicated.
- runtime imports research namespaces.

## Target boundary for future refactor (proposal, not implementation)

`StudyResolver → OrganSegmenter → LesionCandidate/LesionMaskReview → MaskApproval → VolumetryCalculator → ArtifactPublisher → Viewer/Review` with separate Evaluation/ML adapters. This is an architectural option requiring Phase 08/09 evidence; it is not a frozen scientific contract.

## Rule for architecture changes

First characterize public interfaces/artifacts and consumers. Extract one seam at a time, preserve behavior, then run integration and scientific/geometric regressions. Moving a scientific constant or helper can still be HIGH if import/order/default semantics change.

