# Validação do router — tasks A–L

Simulação somente leitura no snapshot `9683eaa…`. Nenhuma task abaixo autoriza alteração.

## A — “Remova código morto.”

- ROUTE: DEAD_CODE_DUPLICATION + DEPENDENCIES + STATIC_MECHANICAL + TESTS_BUILD_ENVIRONMENT.
- FILES/MODULES EXPECTED: alvo ainda desconhecido; começar por inventory/Graphify/CLI/config/subprocess/docs/tests/history. Candidato inicial: `webapp/server.py::_find_largest_compatible_series_legacy`.
- CONTEXT: legacy register, dependency map, target module card.
- RISK: UNKNOWN→MEDIUM; só LOW após `CONFIRMED_DEAD`.
- AUTHORITY: investigar/classificar; não remover ainda.
- TESTS: reachability, packaging e suíte global.
- HUMAN GATE: gate da rota semântica afetada se houver histórico científico; nenhum gate é presumido até delimitar o alvo.
- EXPECTED ACTION: pedir alvo ou produzir lista comprovada; nunca bulk-delete.

## B — “Existe patient leakage entre folds.”

- ROUTE: CROSS_VALIDATION + ML_CLASSIFICATION + METRICS_STATISTICS + LOGGING_AUDIT_PROVENANCE.
- FILES/MODULES EXPECTED: `dtwin/learning/splits.py`, `dtwin/learning/protocol.py`, classifiers in `dtwin/learning/`, protected protocols/splits in `configs/training/`.
- CONTEXT: cohort/group contracts, scientific contracts, sklearn nested-CV refs.
- RISK: HIGH/critical.
- AUTHORITY: auditar e testar; não mudar folds/labels.
- TESTS: disjoint groups, duplicate patient aliases, fit trace e one OOF.
- HUMAN GATE: HG-06, HG-07 e HG-08.
- EXPECTED ACTION: se overlap possível, STOP_REPORT antes de métricas.

## C — “A imagem parece invertida.”

- ROUTE: GEOMETRY + DICOM + HARMONIZATION_RESAMPLING; PANELS e RECONSTRUCTION_3D conforme a tela.
- FILES/MODULES EXPECTED: `dtwin/core.py`, `dtwin/learning/multiphase_ingest.py`, `dtwin/medgemma_panel.py`, `dtwin/viewer_artifacts.py`, `dtwin/stages.py`.
- CONTEXT: DICOM/ITK/NiBabel coordinates and full geometry tuple.
- RISK: HIGH.
- AUTHORITY: somente phantom/reprodução/testes até aprovação.
- TESTS: asymmetric landmark, oblique, LPS↔RAS e pixel-to-physical round-trip.
- HUMAN GATE: HG-03 e HG-04 quando resampling/registration estiver envolvido.
- EXPECTED ACTION: determine whether source, transform, render camera or convention; no blind flip.

## D — “O cache está reutilizando embeddings antigos.”

- ROUTE: EMBEDDINGS + CACHE_ARTIFACTS + MODEL_LOADING + LOGGING_AUDIT_PROVENANCE.
- FILES/MODULES EXPECTED: `dtwin/learning/medsiglip_embeddings.py`, `dtwin/learning/protocol.py`, `configs/training/`, consumers in `dtwin/learning/`.
- CONTEXT: full input/model/revision/preprocessing/config identity.
- RISK: HIGH porque scores podem mudar.
- AUTHORITY: reproduzir, fault-test e propor; não mudar identidade/representação.
- TESTS: mutar cada chave de identidade, corrupção, truncamento e atomicidade.
- HUMAN GATE: HG-09 se chave/representação mudar; HG-01 se contrato científico for redefinido.
- EXPECTED ACTION: invalidate only by approved identity contract; evidence of stale reuse.

## E — “Mude o threshold para melhorar sensitivity.”

- ROUTE: METRICS_STATISTICS + CROSS_VALIDATION + ML_CLASSIFICATION.
- FILES/MODULES EXPECTED: `configs/training/`, `dtwin/learning/medsiglip_multiclass_classifier.py`, `dtwin/benchmark/metrics.py`.
- CONTEXT: endpoint, inner/outer split, denominators, 75/75 internal gate.
- RISK: HIGH.
- AUTHORITY: auditar e propor; a mudança semântica solicitada é proibida sem aprovação.
- TESTS: inner-only selection, confusion matrix/CI/strata completos e comparação externa.
- HUMAN GATE: HG-08 e HG-07.
- EXPECTED ACTION: STOP_REPORT and scientific change request; never tune on final set.

## F — “A malha 3D está deformada.”

- ROUTE: RECONSTRUCTION_3D + GEOMETRY + SEGMENTATION + VOLUMETRY + FRONTEND.
- FILES/MODULES EXPECTED: `dtwin/stages.py`, `dtwin/viewer_artifacts.py`, `dtwin/viewer_xr.py`, `profiles/figado.yaml`, source mask artifact.
- CONTEXT: source mask/geometry, mesh parameters, visual vs quantitative contract.
- RISK: HIGH.
- AUTHORITY: medir, usar phantom e propor opções; não mudar cleanup.
- TESTS: cube/sphere, spacing, topology, volume/surface error e LOD.
- HUMAN GATE: HG-03 e HG-10.
- EXPECTED ACTION: isolate mask defect vs meshing vs render/LOD before proposal.

## G — “Otimize a geração de painéis.”

- ROUTE: PANELS + PERFORMANCE + EMBEDDINGS + MODEL_LOADING + TESTS_BUILD_ENVIRONMENT.
- FILES/MODULES EXPECTED: panel modules in `dtwin/`, `dtwin/learning/exam_to_panels.py`, `configs/`, `dtwin/learning/medsiglip_embeddings.py`.
- CONTEXT: channel/crop/coverage/bytes contract and hardware baseline.
- RISK: MEDIUM somente para implementação byte-identical; caso contrário HIGH.
- AUTHORITY: perfilar/testar; patch somente se a identidade da saída for comprovadamente preservada, senão propor experimento.
- TESTS: deterministic bytes/pixel diff, coverage, embedding/score regression e timing distributions.
- HUMAN GATE: HG-09 quando pixels/representação mudarem.
- EXPECTED ACTION: profile first; separate no-output-change optimization from representation experiment.

## H — “Existem arquivos duplicados; remova-os.”

- ROUTE: DEAD_CODE_DUPLICATION + DEPENDENCIES + ARCHITECTURE_REFACTOR + TESTS_BUILD_ENVIRONMENT.
- FILES/MODULES EXPECTED: suspected workers in `dtwin/` and `webapp/`, atomic/geometry helpers, historical versions in `dtwin/benchmark/` and `tools/`.
- CONTEXT: runtime edges/manual workflows/provenance.
- RISK: MEDIUM/HIGH até `DUPLICATED_SUSPECTED` ser provado equivalente.
- AUTHORITY: classificar/comparar/propor; não remover pela semelhança de nome.
- TESTS: characterization, import, CLI, subprocess, config e suíte global.
- HUMAN GATE: maior gate semântico atingido pelos duplicados.
- EXPECTED ACTION: classify `DUPLICATED_WITH_INTENT` vs suspected; no removal from name similarity.

## I — “A classificação desse paciente está errada.”

- ROUTE: ML_CLASSIFICATION + PANELS + EMBEDDINGS + MODEL_LOADING + LOGGING_AUDIT_PROVENANCE.
- FILES/MODULES EXPECTED: case artifacts and inference modules, but no PHI/labels without authority.
- CONTEXT: nonclinical boundary, target endpoint, model/config/panel hashes.
- RISK: OUT_OF_AUTHORITY para correção clínica.
- AUTHORITY: apenas auditoria de engenharia contra o contrato congelado; não diagnosticar nem relabel.
- TESTS: schema, provenance, cache e representation contracts.
- HUMAN GATE: HG-11 para dados do paciente e HG-12 para claim clínico.
- EXPECTED ACTION: state inability to diagnose; audit whether implementation followed frozen contract.

## J — “A segmentação muda depois do resampling.”

- ROUTE: SEGMENTATION + HARMONIZATION_RESAMPLING + GEOMETRY + VOLUMETRY.
- FILES/MODULES EXPECTED: `dtwin/learning/multiphase_ingest.py`, `dtwin/segmentation_shadow.py`, `dtwin/stages.py`, `dtwin/segmentation_contract.py`, `dtwin/volumetry.py`.
- CONTEXT: moving/reference grids, interpolator, labels and expected invariant.
- RISK: HIGH.
- AUTHORITY: caracterizar e quantificar; não mudar interpolador/fonte.
- TESTS: identity, label preservation, nearest-neighbor, physical overlap e volume delta.
- HUMAN GATE: HG-03, HG-04 e HG-05.
- EXPECTED ACTION: determine whether expected grid representation or contract violation.

## K — “Esse resultado não reproduz em outra GPU.”

- ROUTE: MODEL_LOADING + PERFORMANCE + EMBEDDINGS + ML_CLASSIFICATION + LOGGING_AUDIT_PROVENANCE.
- FILES/MODULES EXPECTED: `configs/training/`, `dtwin/learning/medsiglip_embeddings.py`, classifier/inference modules in `dtwin/learning/`, artifact manifests.
- CONTEXT: `REPRODUCIBILITY.md`, hardware/backend identity, exact drivers/libs/device/dtype/seeds and approved tolerance.
- RISK: HIGH se score/decisão mudar.
- AUTHORITY: investigar e reproduzir; não mudar tolerância/modelo.
- TESTS: mesmo input/config hash, repeated runs, CPU/GPU distributions e boundary cases.
- HUMAN GATE: HG-09 e HG-08.
- EXPECTED ACTION: separate bitwise drift, numerical tolerance and decision flip; STOP if tolerance unknown.

## L — “Melhore a arquitetura desse módulo.”

- ROUTE: ARCHITECTURE_REFACTOR + DEPENDENCIES + TESTS_BUILD_ENVIRONMENT + todas as rotas semânticas identificadas.
- FILES/MODULES EXPECTED: must be named/routed; likely monoliths `webapp/server.py` or `dtwin/stages.py`.
- CONTEXT: public interfaces, runtime/data/scientific edges, characterization baseline.
- RISK: UNKNOWN→MEDIUM/HIGH.
- AUTHORITY: propor seam delimitada antes de editar; aplicar somente após risco/contratos resolvidos.
- TESTS: characterization, contracts, integration, global, static e mutation aplicável.
- HUMAN GATE: maior gate afetado pelas rotas semânticas.
- EXPECTED ACTION: ask/derive bounded outcome; one behavior-preserving extraction, not whole-repo rewrite.

## Resultado

`12/12 PASS`: todas as tasks ativaram paths reais, contexto transitivo, risco conservador, autoridade/testes/gates e ação esperada. O router foi corrigido para tratar performance/panels, cache/embedding, architecture and patient-level requests as multimódulo rather than single-file work.
