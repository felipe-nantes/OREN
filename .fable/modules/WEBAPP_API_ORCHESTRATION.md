# MODULE_ID: WEBAPP_API_ORCHESTRATION

MODULE_NAME: API FastAPI e orquestração de jobs

## REAL_PATHS

- webapp/server.py
- webapp/__init__.py
- tests/test_webapp.py

STATUS: PRODUCTION

## RESPONSIBILITY

Receber uploads, criar jobs, resolver mono/multifase, coordenar segmentação/painéis/inferência/candidato/finalize, servir artefatos, benchmarks, sessões XR e aprovação.

## ENTRYPOINTS

- webapp.server:app
- POST /api/analyze
- GET /api/status/{job_id}
- POST /api/benchmarks
- GET /api/jobs/{job_id}/model/viewer_manifest.json
- POST /api/jobs/{job_id}/approval
- process_visual_job
- process_job

## PUBLIC INTERFACES

Endpoints /api/health, /api/medgemma-backends, /api/segmentation-visualization, /api/analyze, /api/status, /api/benchmarks, /api/jobs e /api/quest.

## INPUTS

Uploads DICOM; parâmetros enhanced_3d; requests de benchmark, XR e approval; configurações e ambiente; pesos e cases locais.

## OUTPUTS

Job IDs/status; manifests/painéis/model files; benchmark reports; tokens/session state XR; approval.json.

## SIDE_EFFECTS

Grava upload/cases/jobs; inicia threads daemon e subprocessos; lê pesos; serve arquivos; mantém estado em memória; persiste aprovação/eventos.

## UPSTREAM

DICOM_MULTIPHASE_INGEST; SEGMENTATION_RUNTIME; SEGMENTATION_SHADOW_CONTRACT; PANELS_REPRESENTATION; MEDGEMMA_INFERENCE; ML_CLASSIFIERS_SPLITS; CANDIDATE_LOCALIZATION; PIPELINE_ENGINE_STAGES.

## DOWNSTREAM

FRONTEND_DESKTOP; WEBXR_QUEST; VIEWER_ARTIFACTS_3D; operadores e verificadores Docker.

## ARTIFACTS_READ

Uploads; configs; pesos; jobs restauráveis; manifests/painéis/STL/volumetria.

## ARTIFACTS_WRITTEN

_upload; árvore casos/webapp; status in-memory; resultados; approval.json; XR events/session.

## DEPENDENCIES

FastAPI; multipart; threading; subprocess; módulos ARGOS/OREN; filesystem.

## OBSERVED_BEHAVIOR

O fluxo multifásico principal usa hybrid_supervised; somente insufficient_dynamic_phases cai para process_job monofásico. Cada job abre thread daemon. Uploads são lidos integralmente em memória. O caminho multifásico não possui cleanup final equivalente ao monofásico.

## SOFTWARE_CONTRACTS

IDs/paths devem ser confinados; downloads só de allowlist com hash; estados de job devem ser monotônicos; erro não pode expor segredo/PHI; aprovação deve referenciar artefato imutável.

## GEOMETRIC_CONTRACTS

Orquestração não deve contornar gates de size/origin/spacing/direction; decisão de fallback/union deve preservar referência e provenance.

## SCIENTIFIC_CONTRACTS

Seleção de fluxo, modelo, fallback, gatilho de candidato, máscara promovida e ordem de stages são semanticamente científicos.

## DOMAIN_POLICIES

Modo research-only; papel clinician auto-declarado não prova identidade; aprovação funcional atual não é autorização clínica.

## KNOWN_FAILURE_MODES

Upload excessivo; thread/processo falhar; restart perder estado; job parcial; modelo indisponível; arquivo allowlisted ausente.

## SILENT_FAILURE_MODES

PHI retida; job stale restaurado; unbounded concurrency; caller autoatribuir papel clínico; aprovação ocorrer após volumetria/publicação; fallback mudar população analisada.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; segurança/privacidade podem tornar a mudança OUT_OF_AUTHORITY operacionalmente.

## HUMAN_GATES

HG-02 a HG-10 conforme fluxo; HG-11 para uploads/logs/retenção; HG-12 para uso/claim clínico.

## EXISTING_TESTS

tests/test_webapp.py; tests/test_docker_integration.py; tests/test_quest_certificate_server.py; verificadores tools/smoke_test_argos_docker_e2e.py e tools/verify_argos_docker_job.py.

## TEST_GAPS

AuthN/AuthZ; fila/backpressure; crash/restart; concorrência; streaming upload; retenção/deletion; approval assinado antes da medida; E2E GPU em CI.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; SECURITY; PRIVACY; FAULT_INJECTION; PERFORMANCE; CONCURRENCY; SCIENTIFIC_REGRESSION.

## RELEVANT_REFERENCES

.fable/ARCHITECTURE.md; .fable/HUMAN_GATES.md; .fable/PRIVACY_SECURITY.md; .fable/references/SECURITY_PRIVACY.md; README.md.

## OPEN_QUESTIONS

Qual identidade/autorização será usada? Qual fila persistente e política de retenção? A aprovação deve bloquear volumetria/publicação?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar routing/fallback, fluxo científico, limites, retenção, autorização, estado de job, allowlist ou aprovação sem testes E2E e gates humanos correspondentes.
