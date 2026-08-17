# Estratégia de testes

## Taxonomia

| Tipo | Quando usar | Prova / limite |
|---|---|---|
| CHARACTERIZATION | legado/contrato incerto antes de mudança | congela comportamento observado, não correção |
| UNIT | função pura/regra local | isola lógica, não integra geometria/runtime |
| CONTRACT | API/I/O/semântica aprovada | cita ID de contrato |
| INVARIANT | propriedade que deve sempre valer | cobre classe de entradas |
| PROPERTY | espaço amplo gerado, ex. round-trip | Hypothesis quando disponível |
| NEGATIVE | corrupção, ausência, ambiguidade, PHI | prova fail-closed |
| INTEGRATION | fronteiras reais | mocks só em GPU/download/serviço caro |
| GEOMETRIC_REGRESSION | coordenadas/resampling/malha | phantoms assimétricos e unidades físicas |
| SCIENTIFIC_REGRESSION | folds/labels/metrics/representação | dataset mínimo versionado, denominadores e tolerâncias |
| PERFORMANCE | tempo/memória/GPU | ambiente, warm/cold cache, rounds |
| FAULT_INJECTION | parcial, crash, retry, resume | idempotência e integridade |
| MUTATION | força dos asserts | lógica pura/crítica após cobertura focal |

## Baseline observado

Há 258 arquivos e 1.610 testes coletáveis em `.venv-win`. Eles cobrem geometria básica, DICOM, gates, datasets, RAG, MedGemma, MedSigLIP, benchmarks, volumetria, viewer, WebXR, Docker e launchers. A estrutura ainda é plana em `tests/`; markers explícitos para characterization/contracts/scientific regression não estão configurados em `pyproject.toml`.

## Estratégia futura

1. Não reorganizar a suíte antes de congelar coleta/tempos/falhas.
2. Marcar e documentar testes existentes por tipo/contrato.
3. Adicionar fixtures sintéticas assimétricas para DICOM/geometria e um corpus real mínimo legal/desidentificado.
4. Cobrir round-trips LPS/RAS, flips, permutations, anisotropic→isotropic, transform direction e label preservation.
5. Testar patient/group isolation, one-OOF-per-unit, fit boundaries, permuted labels, threshold inner-only e métricas indefinidas.
6. Injetar truncamento/corrupção/crash em cache, checkpoint, JSON/CSV/NPY e publish directory.
7. Executar branch coverage; depois mutação seletiva em parsing, hashing, geometry helpers, metrics, splits e thresholds.
8. Separar regressão lógica determinística de tolerância numérica por CPU/CUDA/MPS.

## Definition of Done de testes

O teste deve falhar sob mutação relevante ou contraexemplo conhecido. Snapshot grande, igualdade bitwise cross-hardware e coverage isolada não constituem prova científica.

