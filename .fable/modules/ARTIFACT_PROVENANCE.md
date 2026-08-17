# MODULE_ID: ARTIFACT_PROVENANCE

MODULE_NAME: Provenance, hashes, manifestos e restauração

## REAL_PATHS

- dtwin/core.py
- dtwin/stages.py
- dtwin/segmentation_contract.py
- dtwin/benchmark/hashing.py
- dtwin/benchmark/runner.py
- dtwin/benchmark/reporting.py
- dtwin/volumetry.py
- dtwin/viewer_artifacts.py
- webapp/server.py
- tests/test_engine_finalize.py
- tests/test_benchmark_reporting.py

STATUS: PRODUCTION

## RESPONSIBILITY

Identificar inputs/config/modelos, calcular hashes, publicar manifestos/recibos atômicos, verificar artefatos e restaurar jobs concluídos.

## ENTRYPOINTS

- sha256_of e funções canonical_sha256/sha256_file
- Case.manifest
- build_run_manifest
- write_run_outputs
- build_volumetry_manifest
- verify_volumetry_artifacts
- approved_visualization_mask
- webapp._restore_completed_job

## PUBLIC INTERFACES

Schemas de caso, benchmark, segmentação, volumetria e viewer; hashes canônicos; writers atômicos; restore/allowlist da API.

## INPUTS

Arquivos-fonte; configs efetivas; model trace; commit/ambiente; manifestos anteriores; outputs de cada stage.

## OUTPUTS

Hashes SHA-256; manifests/receipts JSON; CSV/Markdown; artifact allowlists e estado restaurável.

## SIDE_EFFECTS

Lê todos os artefatos; grava/renomeia arquivos temporários; restaura estado de job; publica diretórios.

## UPSTREAM

Todos os produtores de dados/modelos/configs; filesystem; Git/environment.

## DOWNSTREAM

Cache/resume; BENCHMARK_METRICS_REPORTING; VOLUMETRY; VIEWER_ARTIFACTS_3D; WEBAPP_API_ORCHESTRATION; auditoria.

## ARTIFACTS_READ

Inputs, configs, pesos, masks, images, runs e manifestos existentes.

## ARTIFACTS_WRITTEN

Manifestos, receipts, hashes, reports, allowlists e approval metadata.

## DEPENDENCIES

hashlib; JSON/CSV; atomic replace; pathlib; schemas distribuídos pelos módulos.

## OBSERVED_BEHAVIOR

Há múltiplos helpers de hash/write atomic. Volumetria e reports usam replace atômico; outros caminhos usam write_text direto. Restore aceita formatos atuais e legado. O Graphify identifica hash/writers como god nodes.

## SOFTWARE_CONTRACTS

Identidade deve cobrir source, config efetiva, preprocessing, model revision e software quando relevante. Arquivo parcial/stale/corrupto deve falhar fechado. Manifesto e bytes devem concordar.

## GEOMETRIC_CONTRACTS

Provenance de imagem/máscara/malha deve incluir referência e geometria suficiente para impedir reúso em grade incompatível.

## SCIENTIFIC_CONTRACTS

Reproduzir um resultado exige identidade do desenho científico, coorte, modelo, thresholds e failure accounting, não apenas hash do arquivo final.

## DOMAIN_POLICIES

Manifestos não devem conter PHI/segredos; approval deve identificar revisor, artefato, versão e decisão de forma imutável.

## KNOWN_FAILURE_MODES

Write interrompido; hash divergente; manifesto ausente; schema antigo; restore incompleto; config/model trace ausente.

## SILENT_FAILURE_MODES

Cache identity incompleta; artifact stale aceito; arquivo sobrescrito após aprovação; approval sem identidade; hash do output sem source lineage.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC quando provenance sustenta resultado; MEDIUM para mecanismo de storage.

## HUMAN_GATES

HG-09 para identidade de modelo/representação; HG-11 para conteúdo; gate científico correspondente ao artefato; HG-12 para aprovação clínica.

## EXISTING_TESTS

tests/test_engine_finalize.py; tests/test_benchmark_reporting.py; tests/test_benchmark_runner.py; tests/test_segmentation_contract.py; tests/test_volumetry.py; tests/test_viewer_artifacts.py; tests/test_webapp.py.

## TEST_GAPS

Corrupção/truncamento; TOCTOU; concorrência; schema migration; cache invalidation matrix; arquivo alterado após approval; provenance E2E completa.

## REQUIRED_TEST_TYPES

CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; FAULT_INJECTION; CONCURRENCY; SECURITY; SCIENTIFIC_REGRESSION.

## RELEVANT_REFERENCES

.fable/EVIDENCE_PACKAGE_SCHEMA.md; .fable/REPRODUCIBILITY.md; .fable/CONTRACTS.md; .fable/HUMAN_GATES.md; .fable/references/REPRODUCIBILITY.md.

## OPEN_QUESTIONS

Qual schema canônico unifica os manifestos? Que componentes formam a identidade mínima? Como tornar approval append-only e ligado à máscara exata?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar schema, canonicalização, hash identity, atomicidade, restore, allowlist ou vínculo approval–artifact sem migration, fault injection e revisão humana.

