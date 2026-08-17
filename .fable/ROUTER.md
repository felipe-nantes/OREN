# Repository-aware task router

Antes de análise profunda ou edição, gere `templates/TASK_CARD.md`. Routing é cumulativo: ative a rota primária, suas rotas transitivas e qualquer rota indicada pelo downstream real.

## Algoritmo

1. Extraia outcome, paths/símbolos, verbo (`explain`, `diagnose`, `change`, `benchmark`) e restrições.
2. Resolva paths com Graphify query e busca direta; confira que existem.
3. Escolha módulo primário em `modules/INDEX.md`; trace imports, subprocess, HTTP, artifacts e scientific dependency.
4. Ative triggers abaixo. Se duas rotas forem plausíveis, carregue ambas até excluir uma por evidência.
5. Preencha impactos científico, geométrico, estatístico, privacidade, segurança e performance.
6. Risco final = maior risco direto/transitivo. Consulte contracts/human gates.
7. Defina baseline/testes/evidence antes de editar. Em STOP condition, emita STOP_REPORT.

## Contexto base sempre carregado

`CLAUDE.md`, `START_HERE.md`, `TASK_PROTOCOL.md`, este router e `CURRENT_STATE.md`. Carregue `SCIENTIFIC_CONTRACTS.yaml` + `HUMAN_GATES.md` sempre que houver qualquer possibilidade científica/geométrica.

## Trigger matrix

| Trigger/task | Primary route | Mandatory transitive routes |
|---|---|---|
| import, typing, spelling, pure helper | `STATIC_MECHANICAL` | TESTS_BUILD_ENVIRONMENT |
| DICOM, series, phase, slice, UID, MPR/MIP | `DICOM` | DEIDENTIFICATION, GEOMETRY, PIPELINE |
| anonymize, PHI, private tag, burned-in | `DEIDENTIFICATION` | PRIVACY, SECURITY, AUDIT_PROVENANCE |
| origin/spacing/direction/affine/LPS/RAS/flip | `GEOMETRY` | TESTS_BUILD_ENVIRONMENT; often RECONSTRUCTION_3D and SEGMENTATION |
| harmonize/resample/reference grid/interpolator | `HARMONIZATION_RESAMPLING` | GEOMETRY; REGISTRATION/SEGMENTATION as applicable |
| fixed/moving/transform/registration | `REGISTRATION` | GEOMETRY, HARMONIZATION_RESAMPLING |
| mask/model/task/component/morphology/fusion | `SEGMENTATION` | GEOMETRY, HARMONIZATION_RESAMPLING, VOLUMETRY, RECONSTRUCTION_3D |
| panel/crop/tile/RGB/window/FOV | `PANELS` | GEOMETRY, EMBEDDINGS, MODEL_LOADING and ML_CLASSIFICATION as applicable |
| embedding/vector/norm/dimension/cache | `EMBEDDINGS` | MODEL_LOADING, CACHE_ARTIFACTS, LOGGING_AUDIT_PROVENANCE |
| cache/hash/resume/partial/corrupt/artifact | `CACHE_ARTIFACTS` | LOGGING_AUDIT_PROVENANCE, MEMORY_CONCURRENCY, relevant producer |
| weights/revision/device/dtype/offline | `MODEL_LOADING` | CACHE_ARTIFACTS, LOGGING_AUDIT_PROVENANCE, EMBEDDINGS and ML_CLASSIFICATION as applicable |
| score/classifier/prediction/aggregation | `ML_CLASSIFICATION` | CROSS_VALIDATION, METRICS_STATISTICS, MODEL_LOADING |
| fold/group/leakage/OOF/nested/fit boundary | `CROSS_VALIDATION` | METRICS_STATISTICS, LOGGING_AUDIT_PROVENANCE |
| threshold/sensitivity/specificity/AUC/CI/denominator | `METRICS_STATISTICS` | CROSS_VALIDATION, LOGGING_AUDIT_PROVENANCE |
| candidate/ROI/top-k/box | `LOCALIZATION` | GEOMETRY, SEGMENTATION and ML_CLASSIFICATION as relevant |
| subtype/FNH/HCC/cyst/hemangioma | `SUBTYPING` | ML_CLASSIFICATION, CROSS_VALIDATION, METRICS_STATISTICS |
| volume/mL/voxels/dimensions | `VOLUMETRY` | GEOMETRY, SEGMENTATION, RECONSTRUCTION_3D if displayed |
| mesh/STL/VTP/smoothing/decimation/topology | `RECONSTRUCTION_3D` | GEOMETRY, VOLUMETRY, FRONTEND and WEBXR |
| end-to-end/stage/pipeline | `PIPELINE` | ORCHESTRATION + all stages involved |
| job/thread/subprocess/retry/fallback | `ORCHESTRATION` | MEMORY_CONCURRENCY, CACHE_ARTIFACTS, PIPELINE |
| API/upload/UI/viewer | `FRONTEND` | SECURITY, PRIVACY, PIPELINE |
| Quest/WebXR/MR/hands/XR token | `WEBXR` | FRONTEND, SECURITY, 3D, PERFORMANCE |
| logs/manifest/hash/provenance/audit | `LOGGING_AUDIT_PROVENANCE` | SECURITY, PRIVACY and CACHE_ARTIFACTS as applicable |
| speed/VRAM/RAM/timeout/batch | `PERFORMANCE` | MEMORY_CONCURRENCY, REPRODUCIBILITY; promote if output changes |
| thread/race/backpressure/OOM | `MEMORY_CONCURRENCY` | ORCHESTRATION, CACHE_ARTIFACTS |
| auth/token/path traversal/dependency attack | `SECURITY` | PRIVACY, FRONTEND/DOCKER |
| privacy/data retention/consent | `PRIVACY` | DEIDENTIFICATION, SECURITY |
| refactor/extract/boundary/module | `ARCHITECTURE_REFACTOR` | DEPENDENCIES, TESTS_BUILD_ENVIRONMENT, all semantic routes touched |
| dead/unused/duplicate/remove | `DEAD_CODE_DUPLICATION` | DEPENDENCIES, STATIC_MECHANICAL, TESTS_BUILD_ENVIRONMENT |
| package/version/lock/import cycle | `DEPENDENCIES` | TESTS_BUILD_ENVIRONMENT, MODEL_LOADING if relevant |
| tests/CI/coverage/mutation/lint | `TESTS_BUILD_ENVIRONMENT` | target semantic route |
| Docker/Mac/Windows/launch/install | `DOCKER_DEPLOYMENT` | DEPENDENCIES, SECURITY, LOGGING_AUDIT_PROVENANCE; load `REPRODUCIBILITY.md` |
| RAG/BM25/Neo4j/context | `RAG_GRAPHRAG` | DATASETS_REGISTRY, PRIVACY, CACHE_ARTIFACTS |
| dataset/registry/manifest/license | `DATASETS_REGISTRY` | PRIVACY, LOGGING_AUDIT_PROVENANCE, DICOM and GEOMETRY as applicable |
| YAML/profile/config/default | `CONFIG_PROFILES` | semantic routes for every key changed |

## Aliases obrigatórios para rotas canônicas

- `HARMONIZATION` e `RESAMPLING` → `HARMONIZATION_RESAMPLING`.
- `CACHE` e `ARTIFACTS` → `CACHE_ARTIFACTS`.
- `CLASSIFICATION` → `ML_CLASSIFICATION`.
- `THRESHOLDING`, `METRICS` e `STATISTICS` → `METRICS_STATISTICS`.
- `3D` → `RECONSTRUCTION_3D`.
- `LOGGING`, `AUDIT` e `PROVENANCE` → `LOGGING_AUDIT_PROVENANCE`.
- `MEMORY` e `CONCURRENCY` → `MEMORY_CONCURRENCY`.
- `ARCHITECTURE` → `ARCHITECTURE_REFACTOR`.
- `DEAD_CODE` e `DUPLICATION` → `DEAD_CODE_DUPLICATION`.
- `TESTS` e `BUILD_ENVIRONMENT` → `TESTS_BUILD_ENVIRONMENT`.

## Repository path routing

| Real path | Responsibility / risk | Route and mandatory context |
|---|---|---|
| `dtwin/core.py` | image I/O, Case, geometry/hash; HIGH if geometry | DICOM + GEOMETRY + PIPELINE + CORE_IO_GEOMETRY module |
| `dtwin/stages.py` | full pipeline, masks, mesh/export; HIGH | PIPELINE + every affected stage module |
| `dtwin/learning/raw_dicom_phase_resolver.py` | raw phase selection; HIGH | DICOM + DEIDENTIFICATION + GEOMETRY + HG-02 |
| `dtwin/learning/multiphase_ingest.py` | phase load/harmonize; HIGH | DICOM + HARMONIZATION_RESAMPLING + REGISTRATION |
| `dtwin/segmentation_subprocess.py`, `dtwin/seg_worker.py`, `dtwin/segmentation_contract.py` | masks/gates/subprocess; HIGH | SEGMENTATION + GEOMETRY + VOLUMETRY |
| `dtwin/medgemma_panel.py`, `dtwin/medgemma_panel_multiphase.py`, `dtwin/learning/exam_to_panels.py` | representation; HIGH | PANELS + EMBEDDINGS + MODEL_LOADING |
| `dtwin/learning/medsiglip_embeddings.py` | model preprocessing/cache; HIGH | EMBEDDINGS + MODEL_LOADING + CACHE_ARTIFACTS |
| `dtwin/learning/medsiglip_classifier.py`, `dtwin/learning/medsiglip_multiclass_classifier.py`, `dtwin/learning/splits.py`, `dtwin/learning/protocol.py` | ML/CV/threshold; HIGH | ML_CLASSIFICATION + CROSS_VALIDATION + METRICS_STATISTICS |
| `dtwin/benchmark/metrics.py`, `dtwin/benchmark/reporting.py`, `dtwin/benchmark/runner.py` | denominators/outputs; HIGH for metrics | METRICS_STATISTICS + LOGGING_AUDIT_PROVENANCE + PIPELINE |
| `dtwin/candidate_region.py`, `dtwin/candidate_subprocess.py`, `dtwin/candidate_worker.py` | candidate; HIGH | LOCALIZATION + GEOMETRY |
| `dtwin/volumetry.py` | authoritative mask volume; HIGH | VOLUMETRY + GEOMETRY + SEGMENTATION |
| `dtwin/viewer_artifacts.py`, `dtwin/viewer_xr.py`, `viewer/` | quantitative/display assets; HIGH if measurement | RECONSTRUCTION_3D + FRONTEND + WEBXR |
| `webapp/server.py` | orchestration/API/security/scientific coupling | PIPELINE + FRONTEND + ORCHESTRATION + target routes |
| `profiles/figado.yaml`, `configs/` | behavior/scientific constants | CONFIG_PROFILES + semantic route; never “just YAML” |
| `compose.yaml`, `compose.portable.yaml`, `docker/`, `INICIAR_OREN.cmd`, `INICIAR_OREN_QUEST.cmd` | runtime/deploy | DOCKER_DEPLOYMENT + SECURITY + DEPENDENCIES |

## Common multimodule expansions

- “mask changes after resampling” → GEOMETRY + HARMONIZATION_RESAMPLING + SEGMENTATION + VOLUMETRY.
- “stale embedding cache” → EMBEDDINGS + MODEL_LOADING + CACHE_ARTIFACTS + LOGGING_AUDIT_PROVENANCE.
- “wrong patient classification” → ML_CLASSIFICATION + PANELS + EMBEDDINGS + CROSS_VALIDATION + METRICS_STATISTICS; do not relabel or diagnose.
- “optimize panels” → PANELS + PERFORMANCE + EMBEDDINGS + MODEL_LOADING + TESTS_BUILD_ENVIRONMENT; require SCIENTIFIC_REGRESSION when pixels/representation change.
- “deformed mesh” → RECONSTRUCTION_3D + GEOMETRY + SEGMENTATION + VOLUMETRY; separate visual from quantitative.

## Authority shortcuts

- Text/report-only: inspect and report.
- LOW change: baseline → contract/characterization → patch → focused/global evidence.
- MEDIUM: investigate/test/propose; apply only within explicit authorization and promote if scientific.
- HIGH: no semantic patch until HG approval.
- OUT_OF_AUTHORITY: STOP_REPORT.

Router simulations and results: [ROUTER_VALIDATION.md](ROUTER_VALIDATION.md).
