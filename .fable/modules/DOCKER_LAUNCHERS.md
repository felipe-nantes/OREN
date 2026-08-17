# MODULE_ID: DOCKER_LAUNCHERS

MODULE_NAME: Imagens Docker, Compose, proxy e launchers

## REAL_PATHS

- compose.yaml
- compose.portable.yaml
- docker/Dockerfile.argos
- docker/Dockerfile.argos-portable
- docker/Dockerfile.graphify
- docker/entrypoint.sh
- docker/nginx.conf
- tools/initialize_argos_docker.ps1
- tools/start_argos_docker.ps1
- tools/stop_argos_docker.ps1
- tools/smoke_test_argos_docker_e2e.py
- tools/verify_argos_docker_job.py
- tests/test_docker_integration.py

STATUS: PRODUCTION

## RESPONSIBILITY

Construir e iniciar runtime GPU/portátil, proxy TLS, Neo4j/Graphify e gateways opcionais; montar pesos/casos; verificar saúde e job E2E.

## ENTRYPOINTS

- docker compose -f compose.yaml
- docker compose -f compose.portable.yaml
- tools/start_argos_docker.ps1
- tools/initialize_argos_docker.ps1
- docker/entrypoint.sh

## PUBLIC INTERFACES

Serviços argos, proxy, neo4j, graphify e medgemma por profiles; portas 8080/8443; healthchecks e bind mounts definidos em Compose.

## INPUTS

Source checkout; imagens base; requirements/pyproject; pesos externos; cases; env vars; certificados; Docker/GPU.

## OUTPUTS

Containers/imagens, serviço HTTP(S), volumes persistentes, logs e relatórios dos verificadores.

## SIDE_EFFECTS

Baixa/builda imagens; instala dependências; abre portas; monta/escreve cases; inicia processos; gera/configura TLS por launchers.

## UPSTREAM

pyproject.toml; WEBAPP_API_ORCHESTRATION; GraphRAG/Neo4j; pesos e runtime CUDA/CPU.

## DOWNSTREAM

FRONTEND_DESKTOP; WEBXR_QUEST; operadores; smoke/verification tools.

## ARTIFACTS_READ

Dockerfiles, Compose/env, pesos, certificados e cases montados.

## ARTIFACTS_WRITTEN

Imagens/containers/logs; cases/artefatos em bind mounts; relatórios de smoke; certificados locais conforme ferramenta.

## DEPENDENCIES

Docker Desktop/Engine; NVIDIA runtime para GPU; Nginx; Bash/PowerShell; rede.

## OBSERVED_BEHAVIOR

Imagem principal usa base CUDA e dependências amplas; portátil fixa algumas versões CPU/ARM64. Proxy expõe 8080 em loopback e 8443 na LAN. E2E real existe em tools, enquanto CI executa contratos estáticos.

## SOFTWARE_CONTRACTS

Healthcheck deve refletir readiness; volumes não podem mascarar paths errados; secrets não entram na imagem/log; startup/stop devem ser idempotentes; builds devem ser reproduzíveis.

## GEOMETRIC_CONTRACTS

Versões de SimpleITK/VTK/segmentadores e hardware não podem alterar silenciosamente outputs geométricos; agreement deve ser medido.

## SCIENTIFIC_CONTRACTS

Imagem/model revision/device e versões numéricas podem afetar resultados; promoção de imagem exige regressão científica quando mudarem.

## DOMAIN_POLICIES

Pesos e dados clínicos permanecem fora da imagem/Git; exposição LAN requer política de autenticação/TLS.

## KNOWN_FAILURE_MODES

Docker/GPU indisponível; build quebrado; mount ausente; porta ocupada; certificado inválido; OOM; healthcheck falso.

## SILENT_FAILURE_MODES

Dependência >= resolver versão nova; CPU/GPU drift; serviço LAN sem auth; bind mount reusar artefato stale; smoke validar apenas happy path.

## RISK_LEVEL

MEDIUM; HIGH quando versão/device muda resultado científico ou quando dados clínicos são expostos.

## HUMAN_GATES

HG-09 para modelo/runtime; HG-11 para mounts/rede/secrets; HG-03/HG-05/HG-10 se outputs numéricos mudarem.

## EXISTING_TESTS

tests/test_docker_integration.py; tools/verify_argos_docker_static.py; tools/verify_argos_docker_runtime.ps1; tools/smoke_test_argos_docker_e2e.py; tools/verify_argos_docker_job.py.

## TEST_GAPS

E2E Docker/GPU no CI; SBOM/vulnerability scan; rebuild determinístico; restore após crash; auth/TLS adversarial; cross-platform agreement.

## REQUIRED_TEST_TYPES

CONTRACT; INTEGRATION; E2E; PERFORMANCE; FAULT_INJECTION; SECURITY; REPRODUCIBILITY; SCIENTIFIC_REGRESSION.

## RELEVANT_REFERENCES

.fable/TOOLING.md; .fable/REPRODUCIBILITY.md; .fable/PRIVACY_SECURITY.md; docs/229_DOCKER_ARGOS_END_TO_END.md; docs/230_RELATORIO_VALIDACAO_DOCKER_PONTA_A_PONTA.md.

## OPEN_QUESTIONS

Quais imagens/digests são baseline? Como autenticar 8443? Quais verificadores entram obrigatoriamente no CI/release?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não atualizar base/dependências/modelos, portas, mounts, TLS, profiles ou hardware path sem baseline, E2E e revisão de segurança/reprodutibilidade.

