# MODULE_ID: MEDGEMMA_INFERENCE

MODULE_NAME: Inferência e screening MedGemma

## REAL_PATHS

- dtwin/medgemma_client.py
- dtwin/medgemma_screening.py
- dtwin/medgemma_benchmark.py
- dtwin/medgemma_spotlight.py
- dtwin/medgemma_volumetric.py
- tools/medgemma_server.py
- tools/medgemma_server_base.py
- configs/medgemma_27b.yaml
- configs/medgemma_local_4b.yaml
- tests/test_medgemma_client.py
- tests/test_medgemma_screening.py
- tests/test_medgemma_server.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Carregar configuração, construir prompt, chamar backend HTTP/local MedGemma, validar JSON, persistir envelope de screening e suportar benchmarks/fallback monofásico.

## ENTRYPOINTS

- dtwin.medgemma_screening.main
- run_screening
- create_medgemma_client
- HTTPJSONMedGemmaClient
- tools/medgemma_server.py

## PUBLIC INTERFACES

load_screening_config; model_trace; effective_config_sha256; build_medgemma_prompt; validate_medgemma_report; validate_configured_medgemma_report; build_report_envelope.

## INPUTS

Painéis e manifestos; YAML de modelo/prompt/backend; endpoint e pesos; contexto RAG opcional.

## OUTPUTS

Relatório JSON validado, envelope com hashes/model trace, erros estruturados e artefatos de benchmark.

## SIDE_EFFECTS

Chamadas HTTP/processo de modelo; uso GPU/MPS/CPU; leitura de pesos; gravação atômica de relatórios; limpeza de artefatos prévios.

## UPSTREAM

PANELS_REPRESENTATION; RAG_TEXT; CONFIG_PROFILES; backend Transformers/Ollama/gateway.

## DOWNSTREAM

ML_CLASSIFIERS_SPLITS; BENCHMARK_METRICS_REPORTING; WEBAPP_API_ORCHESTRATION; CANDIDATE_LOCALIZATION no fluxo observado.

## ARTIFACTS_READ

PNGs/manifestos de painel; YAML MedGemma; índice/contexto RAG; pesos e revisões.

## ARTIFACTS_WRITTEN

Report/envelope JSON, hashes de configuração/prompt e outputs de screening/benchmark.

## DEPENDENCIES

HTTPX/urllib conforme backend; Transformers; accelerate; bitsandbytes; protobuf; sentencepiece; PANELS_REPRESENTATION.

## OBSERVED_BEHAVIOR

Valida schema e pode repetir a chamada com prompt de correção. É usado em screening/benchmark e no caminho monofásico; o fluxo individual multifásico principal atual usa MedSigLIP supervisionado. Nenhuma resposta constitui diagnóstico validado.

## SOFTWARE_CONTRACTS

Config efetiva, backend, modelo/revisão, prompt e entradas devem ser hash/rastreáveis. JSON inválido deve falhar ou ficar explicitamente inconclusivo, nunca ser coercido silenciosamente.

## GEOMETRIC_CONTRACTS

MedGemma recebe representação 2D; a proveniência dos slices/fases deve permanecer ligada ao exame e não pode ser interpretada como geometria 3D completa.

## SCIENTIFIC_CONTRACTS

Prompt, schema, modelo/revisão, quantização, agregação e retry fazem parte do experimento e exigem fonte/aprovação.

## DOMAIN_POLICIES

Saídas são research-only; falha do modelo deve ser contabilizada; qualquer claim clínico é OUT_OF_AUTHORITY.

## KNOWN_FAILURE_MODES

Endpoint indisponível; OOM; timeout; JSON inválido; revisão/peso ausente; painel ausente; configuração incoerente.

## SILENT_FAILURE_MODES

Backend/model drift; prompt alterado sem invalidar cache; retry mudar semântica; texto plausível passar por resultado científico; falhas serem removidas do denominador.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; OUT_OF_AUTHORITY para interpretação clínica.

## HUMAN_GATES

HG-06 para labels; HG-08 para threshold/denominador; HG-09 para modelo/prompt/representação; HG-12 para claim clínico.

## EXISTING_TESTS

tests/test_medgemma_client.py; tests/test_medgemma_screening.py; tests/test_medgemma_server.py; tests/test_medgemma_spotlight.py; tests/test_medgemma_volumetric.py; testes de painéis MedGemma.

## TEST_GAPS

Pin real de pesos/revisão; fault injection de timeout/retry; device agreement; prompt regression; modelo real no CI; contabilização de todas as falhas.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; FAULT_INJECTION; PERFORMANCE; REPRODUCIBILITY.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/PYTORCH.md; .fable/references/REPRODUCIBILITY.md; configs/medgemma_27b.yaml; README.md.

## OPEN_QUESTIONS

Quais revisões e backends estão congelados? MedGemma permanecerá no produto extraído ou apenas no repositório de pesquisa?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar modelo/revisão, prompt, schema, quantização, retry, agregação, fallback ou denominadores sem HG-08/HG-09 e benchmark reproduzível; não emitir claim clínico.

