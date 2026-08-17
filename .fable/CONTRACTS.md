# Registro de contratos

Este arquivo organiza contratos não numéricos e aponta os contratos científicos versionados. `OBSERVED_BEHAVIOR` não é aprovação.

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

