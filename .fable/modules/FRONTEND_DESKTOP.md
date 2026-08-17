# MODULE_ID: FRONTEND_DESKTOP

MODULE_NAME: Frontend desktop de upload, status e revisão

## REAL_PATHS

- webapp/static/index.html
- webapp/static/argos.css
- webapp/static/oren-motion.js
- webapp/static/benchmark.html
- webapp/static/oren-icon.svg
- tests/test_webapp.py

STATUS: PRODUCTION

## RESPONSIBILITY

Permitir seleção/upload DICOM, escolha de visualização aprimorada, polling de job, exibição de resultado/avisos/volumetria, abertura do viewer e envio de aprovação.

## ENTRYPOINTS

- webapp/static/index.html
- webapp/static/benchmark.html

## PUBLIC INTERFACES

Chamadas browser a /api/analyze, /api/status, /api/segmentation-visualization, /api/benchmarks, manifests/model files e /approval.

## INPUTS

Arquivos escolhidos pelo usuário; respostas JSON da API; viewer manifest; eventos de UI.

## OUTPUTS

Requests de análise/aprovação; estado visual; warnings, métricas e links para viewer.

## SIDE_EFFECTS

Envia arquivos; faz polling; mantém estado no browser; pode iniciar downloads/visualização e persistir decisão via API.

## UPSTREAM

WEBAPP_API_ORCHESTRATION; VOLUMETRY; VIEWER_ARTIFACTS_3D; CONFIG_PROFILES.

## DOWNSTREAM

Usuário desktop/radiologista; viewer Three.js; aprovação do job.

## ARTIFACTS_READ

JSON de capabilities/status; viewer manifest; imagens e modelos servidos pela API.

## ARTIFACTS_WRITTEN

Nenhum arquivo local direto; requests de análise/approval causam persistência no backend.

## DEPENDENCIES

Browser moderno; Fetch API; CSS/JavaScript locais; WEBAPP_API_ORCHESTRATION.

## OBSERVED_BEHAVIOR

A UI envia enhanced_3d e seleciona o caminho conforme capability/default. Exibe resultados research-only e aciona aprovação posterior à geração dos artefatos.

## SOFTWARE_CONTRACTS

Estados loading/error/success devem ser inequívocos; warnings e provenance não podem desaparecer; valores/units devem vir do manifesto; falhas de rede não podem parecer aprovação.

## GEOMETRIC_CONTRACTS

Orientação, unidade e source dos artefatos devem ser exibidos sem reinterpretar coordenadas; UI não corrige geometria.

## SCIENTIFIC_CONTRACTS

Texto, default de enhanced_3d, visibilidade de candidatos/grades e ação de aprovação podem alterar interpretação e workflow.

## DOMAIN_POLICIES

Research-only e limites precisam permanecer visíveis; UI não deve chamar candidato de diagnóstico ou aprovação técnica de validação clínica.

## KNOWN_FAILURE_MODES

Upload interrompido; polling falhar; browser incompatível; manifesto incompleto; asset ausente.

## SILENT_FAILURE_MODES

Warning oculto; unidade/rótulo errado; stale job na tela; botão de aprovação sem identidade; default mudar fluxo científico sem percepção.

## RISK_LEVEL

MEDIUM; HIGH quando texto/default/controle altera interpretação científica.

## HUMAN_GATES

HG-09 para defaults/representação; HG-11 para upload/PHI; HG-12 para texto ou claim clínico.

## EXISTING_TESTS

Contratos HTML/API em tests/test_webapp.py.

## TEST_GAPS

Testes JS unitários; acessibilidade; E2E browser; visual regression; uploads grandes; warning persistence; approval failure/retry; i18n/unidades.

## REQUIRED_TEST_TYPES

UNIT; CONTRACT; NEGATIVE; INTEGRATION; E2E; ACCESSIBILITY; VISUAL_REGRESSION; SECURITY.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/PRIVACY_SECURITY.md; .fable/references/SECURITY_PRIVACY.md; webapp/static/index.html.

## OPEN_QUESTIONS

Quais mensagens/warnings são obrigatórios? Como identificar e autenticar revisor? Qual fluxo de correção de máscara precede aprovação?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar defaults, units, warnings, nomenclatura de candidato, approval UX ou envio de dados sensíveis sem revisão do workflow e gates aplicáveis.

