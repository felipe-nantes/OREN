# Registro de contratos

Este arquivo organiza contratos não numéricos e aponta os contratos científicos versionados. `OBSERVED_BEHAVIOR` não é aprovação.

## Verificação 2026-08-17 (TASK-2026-08-17-PH02-CONTRACTS-01)

Owner de todos os contratos: **Felipe Nantes** (aprovador dos gates). Os científicos foram ratificados/congelados em `HUMAN_DECISIONS.md`. Verificação dos 15 não científicos contra o código (mecanismo existe e opera como declarado; não é prova de execução exaustiva):

| Contrato | Evidência verificada | Teste protetor localizado | Status |
|---|---|---|---|
| SW-ATOMIC-01 | `benchmark/reporting.py:11-19` (`_atomic_text` tmp+replace); `learning/protocol.py:37-50` (`atomic_write_json` com `os.replace`) | test_benchmark_metrics.py e correlatos citam atomicidade | VERIFIED (cobertura de parcial-exposto a aprofundar na fase 03) |
| SW-FAIL-CLOSED-01 | `raise PipelineError`: core.py ×8, benchmark/runner.py ×11, webapp/server.py ×13 | espalhado pela suíte (asserts de raise) | VERIFIED_OBSERVED |
| SW-ARTIFACT-01 | `learning/visual_inference.py:78-84` (assinatura+hash do bundle); `webapp/server.py:880-884` (`sha256_of` por artefato); `medsiglip_embeddings.py:154,308,439` (dimensão/manifests) | tests/test_learning_visual_inference.py:30-73 | VERIFIED |
| SW-HTTP-01 | `medgemma_client.py:777,850,861` (contrato `dtwin-medgemma-v1` verificado no health e declarado no payload) | tests/test_medgemma_client.py, test_medgemma_server.py | VERIFIED |
| SW-XR-01 | `webapp/server.py:1673-1690` (sessão por token hasheado SHA-256, expiração → 401), `:1720` (QR sem token em logs), `:1807-1863` (roles com pattern/limite); allowlist/hash `:789-884` | tests/test_viewer_xr.py, test_webapp.py, test_viewer_presets.py | VERIFIED |
| GEO-IMAGE-01 | princípio implementado via GEO-CONVERT/GEO-MASK (abaixo) | — (princípio) | VERIFIED_BY_COMPOSITION |
| GEO-CONVERT-01 | `core.py:90` (`CopyInformation` na conversão) | tests/test_core_geometry.py (proteção parcial, como já registrado) | VERIFIED (gap: round-trip property test — fase 04) |
| GEO-MASK-01 | `segmentation_contract.py:79-109` (`image_geometry`, `same_geometry` tol 1e-5); `volumetry.py:161-164` (abort); `webapp/server.py:907-908` | tests/test_segmentation_contract.py, test_volumetry.py | VERIFIED |
| GEO-LABEL-01 | `sitkNearestNeighbor` em multiphase_ingest.py:211 e 6+ módulos benchmark/ | tests/test_learning_multiphase_ingest.py | VERIFIED_OBSERVED (auditoria exaustiva de todo call de resample = fase 04) |
| GEO-MESH-01 | `figado.yaml:122` (LPS); volume autoritativo por voxels = ARGOS-GEO-004 ratificado (`volumetry.py:161-170`) | tests/test_volumetry.py, test_engine_finalize.py | VERIFIED |
| POL-RESEARCH-01 | `stages.py:1229` (`acknowledge_research_only`); `server.py:1058,1227,1529,1625` (`research_only: True` nos payloads) | tests/test_engine_finalize.py, test_webapp.py | VERIFIED |
| POL-PHI-01 | `.gitignore:20-21,43-55` (casos/, flywheel/, labels protegidos fora do git) | — (política de repo; revisão humana) | VERIFIED_OBSERVED |
| POL-ENDPOINT-01 | `visual_inference.py:160-166` (`ground_truth_used/lesion_mask_used/changes_frozen_decision: False`); `figado.yaml:64-70` | tests/test_learning_visual_inference.py | VERIFIED (= ARGOS-SCI-011 ratificado) |
| POL-VOLUME-01 | `volumetry.py:52` (`automatic_unconfirmed_candidate`) | tests/test_volumetry.py | VERIFIED |
| POL-FAILURE-01 | = ARGOS-SCI-004 ratificado (lock.json:24-28; metrics.py) | tests/test_benchmark_metrics.py | VERIFIED |

## Software contracts

- `SW-ATOMIC-01`: publicação JSON/CSV/NPY/artefato declarada atômica não pode expor parcial como sucesso. Evidência: `dtwin/benchmark/reporting.py`, `dtwin/learning/protocol.py`, `dtwin/learning/medsiglip_embeddings.py`, `dtwin/volumetry.py`.
- `SW-FAIL-CLOSED-01`: falha de input/modelo/artefato obrigatório não pode fabricar máscara, relatório ou resultado. Evidência: `dtwin/core.py`, `dtwin/benchmark/runner.py`, `webapp/server.py`.
- `SW-ARTIFACT-01`: artefato consumido deve corresponder a hash/config/model/preprocessing/protocol aplicáveis; parcial/corrompido deve ser recusado.
- `SW-HTTP-01`: MedGemma usa contrato `dtwin-medgemma-v1`; respostas passam por schema e revisão humana. Evidência: `dtwin/medgemma_client.py`, `dtwin/medgemma_screening.py`.
- `SW-XR-01`: assets do viewer são allowlisted/hash-verificados e sessões XR são curtas e role-scoped. Evidência: `webapp/server.py`, `dtwin/viewer_xr.py`, testes de webapp/XR.

## Geometric contracts

- `GEO-IMAGE-01`: array não equivale a imagem médica; origin/spacing/direction/affine/convenção/reference grid fazem parte do dado.
- `GEO-CONVERT-01`: conversão array↔SimpleITK preserva geometria de referência. Evidência: `dtwin/core.py`; proteção parcial em `tests/test_core_geometry.py`.
- `GEO-MASK-01`: máscara e imagem quantitativa devem compartilhar geometria física; incompatibilidade aborta. Evidência: `dtwin/segmentation_contract.py`, `dtwin/volumetry.py`, `dtwin/viewer_artifacts.py`.
- `GEO-LABEL-01`: resampling de labels discretos usa nearest-neighbor e não inventa classes; todo uso deve ser verificado por rota.
- `GEO-MESH-01`: malha exportada usa unidades físicas e LPS; volume autoritativo vem de voxels da máscara, não da malha. Evidência: `profiles/figado.yaml`, `dtwin/stages.py`, `dtwin/volumetry.py`.

## Domain policies

- `POL-RESEARCH-01`: `research_only=true`, `clinical_use_allowed=false`, revisão humana obrigatória.
- `POL-PHI-01`: dados/artefatos de pacientes não entram no Git ou no pack; identificadores são minimizados/hasheados.
- `POL-ENDPOINT-01`: localização candidata é pós-inferência e não retroalimenta classificação sem experimento aprovado.
- `POL-VOLUME-01`: candidato é `automatic_unconfirmed_candidate`, nunca volume tumoral confirmado.
- `POL-FAILURE-01`: falhas técnicas e inconclusivos permanecem visíveis; política da métrica é científica e está em `SCIENTIFIC_CONTRACTS.yaml`.

## Scientific contracts

Fonte autoritativa operacional: [SCIENTIFIC_CONTRACTS.yaml](SCIENTIFIC_CONTRACTS.yaml). Toda alteração aciona HG-01 e possivelmente HG-02–HG-10.

## Lacunas

- README, manuscrito e implementação divergem em escopo/estado de algumas features.
- Nem todo número em código/config tem racional científico documentado; veja `SCIENTIFIC_RISK_REGISTER.md`.
- Contratos de tolerância entre CPU/CUDA/MPS não estão integralmente definidos.

