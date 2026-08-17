# MODULE_ID: TEST_SUITE

MODULE_NAME: Suíte pytest, CI e verificadores operacionais

## REAL_PATHS

- tests/
- .github/workflows/tests.yml
- pyproject.toml
- tools/smoke_test_argos_docker_e2e.py
- tools/verify_argos_docker_job.py
- tools/verify_argos_docker_static.py
- tools/verify_argos_docker_runtime.ps1

STATUS: PRODUCTION

## RESPONSIBILITY

Caracterizar comportamento, proteger contratos unitários/integrados, executar pytest no CI e fornecer smoke/verificação Docker separada.

## ENTRYPOINTS

- pytest -q
- workflow .github/workflows/tests.yml
- tools/smoke_test_argos_docker_e2e.py
- tools/verify_argos_docker_job.py

## PUBLIC INTERFACES

Fixtures e testes em tests/; configuração tool.pytest em pyproject.toml; commands dos verificadores.

## INPUTS

Código/configs; fixtures sintéticas/temporárias; ambiente Python; Docker/pesos/dados desidentificados para E2E.

## OUTPUTS

Pass/fail, logs, relatórios dos verificadores e evidência de regressão.

## SIDE_EFFECTS

Cria tmp artifacts; pode iniciar containers/modelos em verificadores; CI instala dependências.

## UPSTREAM

Todos os módulos e contratos; pyproject.toml; ambiente/hardware.

## DOWNSTREAM

Gates humanos, CI, releases, evidence packages e decisões de mudança.

## ARTIFACTS_READ

Código, configs, fixtures, imagens/DICOM sintéticos e baselines.

## ARTIFACTS_WRITTEN

Temporários pytest, caches/logs e outputs dos smoke tools; nenhum deve conter PHI.

## DEPENDENCIES

pytest; FastAPI/httpx; dependências do projeto; Docker opcional. Ruff, mypy, coverage, Hypothesis, mutation e pip-audit não estavam configurados/instalados na inspeção.

## OBSERVED_BEHAVIOR

O repositório possui 256 arquivos test_*.py e cerca de 1.508 funções de teste textuais no commit inspecionado. CI usa Python 3.13, instala .[dev], executa doctor e pytest -q. Docker/GPU real não integra o workflow padrão.

## SOFTWARE_CONTRACTS

Testes devem ser determinísticos, isolados e deixar claro quando apenas caracterizam comportamento. Falha não pode ser escondida por skip/xpass sem rationale.

## GEOMETRIC_CONTRACTS

Testes de imagem devem verificar origin, spacing, direction, affine/convenção e landmarks físicos, não somente shape/array.

## SCIENTIFIC_CONTRACTS

Testes existentes não promovem comportamento a correção científica; baselines científicos exigem fonte e gate.

## DOMAIN_POLICIES

Preferir fixtures sintéticas, phantoms e dados públicos desidentificados; nunca incluir PHI, segredos ou dados clínicos privados.

## KNOWN_FAILURE_MODES

Suite lenta; dependência/peso ausente; hardware específico; teste flaky; coleta divergente; fixture stale.

## SILENT_FAILURE_MODES

Assert fraco; mock não representar runtime; coverage alta sem mutation; teste congelar defeito; E2E apenas estático; contagem documentada stale.

## RISK_LEVEL

MEDIUM; HIGH quando teste define/protege contrato científico.

## HUMAN_GATES

Gate do módulo protegido; HG-01 para promover teste a contrato científico; HG-11 para fixtures médicas.

## EXISTING_TESTS

tests/ completo; .github/workflows/tests.yml; verificadores Docker em tools/.

## TEST_GAPS

Coverage; static typing/lint; property testing; mutation; security/dependency audit; fault injection sistemático; GPU/Docker/browser/headset E2E; performance baseline.

## REQUIRED_TEST_TYPES

CHARACTERIZATION; UNIT; CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; PERFORMANCE; FAULT_INJECTION; MUTATION.

## RELEVANT_REFERENCES

.fable/TEST_STRATEGY.md; .fable/TOOLING.md; .fable/HUMAN_GATES.md; .fable/references/TESTING.md; .fable/references/REPRODUCIBILITY.md.

## OPEN_QUESTIONS

Qual baseline coletado é autoritativo? Quais testes caros pertencem ao CI/release/manual gate? Quais characterization tests protegem comportamento ainda não aprovado?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não remover/enfraquecer asserts, mudar fixtures científicas, atualizar golden outputs, adicionar skips ou reinterpretar characterization como correção sem evidência e aprovação pertinente.

