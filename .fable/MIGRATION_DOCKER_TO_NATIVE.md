# Migração Docker → nativo — matriz de responsabilidades

TASK: `TASK-2026-08-18-MIGR-01` · BASE_COMMIT: `42a8514` · Data: 2026-08-18

## Achado estruturante da Wave 0

**O código de aplicação já é livre de Docker.** Varredura por `ARGOS_CONTAINER`,
`ARGOS_DOCKER_*`, `host.docker.internal`, `/opt/argos`, `/home/argos` em
`dtwin/`, `webapp/` e `viewer/`: **zero ocorrências**. Todo o acoplamento vive
na camada de infraestrutura (`compose*.yaml`, `docker/`, `.env.docker`,
`tools/*docker*`, `tests/test_docker_integration.py`) e em um único tool legado
(`tools/medgemma_server_v14.py:324`).

Consequência: a migração é **remoção de infraestrutura + consolidação de
launchers**, não cirurgia no pipeline. O risco científico é estruturalmente
baixo, desde que as proibições sejam respeitadas.

## Matriz: responsabilidade → substituto nativo → teste de paridade

| # | Responsabilidade (hoje no Docker) | Substituto nativo | Estado | Teste de paridade |
|---|---|---|---|---|
| 1 | Webapp FastAPI (`argos`, uvicorn :8000) | `run_win.ps1` §2 — uvicorn :8080 loopback | **JÁ EXISTE** | `GET /api/health` 200 |
| 2 | Gateway MedGemma (`medgemma`, :8001) | `run_win.ps1` §1 — `tools/medgemma_server.py` | **JÁ EXISTE** (valida `model_id`) | `GET :8001/health` → `ready` + model_id esperado |
| 3 | Proxy Nginx :8080→8000 | uvicorn serve direto em :8080 | **SUBSTITUÍVEL** | smoke HTTP + upload grande |
| 4 | TLS Quest :8443 (nginx + `/certs`) | `setup_quest_https.ps1` + `run_quest_win.ps1` | **JÁ EXISTE** | handshake TLS + `/api/health` |
| 5 | `client_max_body_size 20g` | uvicorn sem limite de corpo por padrão | **NEUTRO** | upload DICOM grande |
| 6 | Headers `X-Forwarded-*` / `--proxy-headers` | desnecessários sem proxy | **NEUTRO** | — |
| 7 | Neo4j (`neo4j`, :7474/:7687) | serviço nativo local opcional; `configs/graphrag_neo4j.yaml` já usa `bolt://localhost:7687` | **LACUNA** (instalação/instruções) | conexão bolt + falha explícita se ausente |
| 8 | Graphify (`graphify`, imagem própria) | `tools/graphify_argos.ps1` → `.local\graphify-venv` | **JÁ NATIVO E ISOLADO** | `-Action Status` |
| 9 | TotalSegmentator (na imagem) | extra `[seg]` no `.venv-win`; pesos em `%USERPROFILE%\.totalsegmentator` | **JÁ EXISTE** (preflight cobre) | import + preflight |
| 10 | MRSegmentator (`/opt/conda/bin/mrsegmentator`) | `.venv-mrseg\Scripts\mrsegmentator.exe` (**já presente no repo**) | **LACUNA** (só apontar `WEBAPP_MRSEGMENTATOR_EXE`) | executável resolve |
| 11 | Persistência `casos/` (bind `ARGOS_CASES_DIR`) | diretório local `casos/` | **NATIVO POR PADRÃO** | escrita/leitura de caso |
| 12 | Cache HF (bind ro + `HF_HUB_OFFLINE=1`) | `%USERPROFILE%\.cache\huggingface` | **LACUNA** (launcher não define offline) | carga do 4B sem rede |
| 13 | Health checks (4 serviços) | polling HTTP no launcher | **JÁ EXISTE** (falta Neo4j) | preflight |
| 14 | Logs (`docker logs`) | `casos/run_gateway.{out,err}.log` + webapp em foreground | **JÁ EXISTE** | arquivos criados |
| 15 | Timeouts (`WEBAPP_PREP_TIMEOUT_GPU=900` etc.) | env no launcher; código tem defaults | **LACUNA** (paridade de valores) | env efetiva |
| 16 | Secret `NEO4J_PASSWORD` (`.env.docker`) | env local / arquivo ignorado pelo Git | **LACUNA** | ausência de secret versionado |
| 17 | Rede isolada `argos_internal` | loopback 127.0.0.1 | **NATIVO** | binds em 127.0.0.1 |
| 18 | `host.docker.internal` | 127.0.0.1 | **DESAPARECE** | grep = 0 no runtime |

Mapeamento `.env.docker` → nativo: `ARGOS_CASES_DIR`→`casos/`;
`TOTALSEG_HOME_DIR`/`MRSEGMENTATOR_HOME_DIR`→`%USERPROFILE%\.*`;
`HF_HUB_DIR`→cache HF do usuário; `QUEST_CERT_DIR`→dir local de certificados;
`MEDGEMMA_BASE_URL`→`http://127.0.0.1:8001`; `ARGOS_DOCKER_STATE_DIR`→dirs do
Neo4j nativo.

## Lacunas a fechar na Wave 2

1. Neo4j nativo opcional (instalação + config + falha explícita).
2. `WEBAPP_MRSEGMENTATOR_EXE` → `.venv-mrseg\Scripts\mrsegmentator.exe`.
3. `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` no launcher.
4. Timeouts do compose replicados no launcher (paridade de valores).
5. Mecanismo local de secret para `NEO4J_PASSWORD`.
6. Consolidar Quest no launcher principal (sem Nginx).

## Human gates acionados

- **HG-11 / DOM-002 (PH-01)** — `configs/graphrag_neo4j_docker.yaml` contém
  `privacy.remove_png_metadata: true` e `privacy.require_visible_phi_confirmation: true`
  que **não existem** em `configs/graphrag_neo4j.yaml` (a config nativa).
  Nenhum código referencia a variante docker (órfã), mas migrar para nativo-only
  sem tratar isso deixa a postura de privacidade documentada abaixo da variante
  Docker. Requer decisão humana: (a) portar as flags para a config nativa,
  (b) declarar que não se aplicam, ou (c) manter como está e registrar o risco.
  **Não alterarei config de privacidade sem essa decisão.**

## Testes Docker a substituir

`tests/test_docker_integration.py` — 12 testes, exclusivamente Docker
(asserções sobre compose, Dockerfile e `ARGOS_CONTAINER`). Cobertura nativa
equivalente será escrita na Wave 5 (preflight, portas, loopback, health,
secrets, paths locais).

---

# WAVE 1 — Plano de migração

## Arquitetura nativa final

```
Windows 11 (caminho principal)
  INICIAR_OREN.cmd ─→ run_win.ps1  (launcher canônico)
        │  §0 preflight: venv, config, deps, CUDA, pesos 4B  [existe]
        │  §0b NOVO: env de paridade (timeouts, HF offline, MRSegmentator,
        │             TotalSeg paths) + Neo4j opcional (detecta ou falha claro)
        │  §1 gateway MedGemma 4B :8001 (loopback, health + model_id)  [existe]
        │  §2 webapp uvicorn :8080 (loopback, foreground)  [existe]
        └─ Ctrl+C encerra apenas o que ele iniciou  [existe]

  Quest:   setup_quest_https.ps1 → run_quest_win.ps1 (TLS :8443 nativo)  [existe]
  Graphify: tools/graphify_argos.ps1 → .local\graphify-venv  [já isolado]
  Neo4j:   serviço nativo local opcional (GraphRAG falha explícito se ausente)

macOS (preservado)
  run_mac.sh → Ollama + MedGemma 27B + gateway + webapp  [sem alteração]
```

Sem Docker, sem Compose, sem WSL-para-Docker, sem Nginx, sem `host.docker.internal`.

## Arquivos — reutilizar / alterar / substituir / excluir

**Reutilizar sem tocar:** `run_mac.sh`, `tools/graphify_argos.ps1`,
`tools/medgemma_server.py` (já loopback-only), `tools/setup_medgemma.py`,
`configs/graphrag_neo4j.yaml`, `setup_quest_https.ps1`,
`servir_certificado_quest.ps1`, `INICIAR_OREN*.cmd` (não citam Docker).

**Alterar:** `run_win.ps1` (env de paridade + Neo4j opcional + preflight
MRSegmentator); `tools/medgemma_server_v14.py` (remover branch
`ARGOS_CONTAINER` — endurece para loopback); `README.md`, `RUNBOOK_MAC.md`,
`SYNC.md`, `AGENTS.md` (referências Docker); `.gitignore` (certificados).

**Substituir:** `tests/test_docker_integration.py` (12 testes) →
`tests/test_native_runtime.py` (cobertura nativa equivalente, Wave 5).

**Excluir (Wave 4, só após paridade):** `compose.yaml`,
`compose.portable.yaml`, `docker/` (5 arquivos), `.dockerignore`,
`.env.docker`, `configs/graphrag_neo4j_docker.yaml` (órfã — ver PH-01), e 15
tools Docker-only: `ensure_docker_desktop.ps1`, `export_argos_portable.ps1`,
`import_argos_portable.sh`, `initialize_argos_docker.{ps1,sh}`,
`setup_docker_windows.ps1`, `smoke_test_argos_docker_e2e.py`,
`start_argos_docker.ps1`, `start_argos_docker_mac.sh`, `stop_argos_docker.ps1`,
`verify_argos_docker_job.py`, `verify_argos_docker_portable.sh`,
`verify_argos_docker_runtime.ps1`, `verify_argos_docker_static.py`,
`verify_medgemma_container.ps1`.

## Ciclo de vida (Wave 2)

| Aspecto | Decisão |
|---|---|
| Inicialização | ordem gateway → webapp, com health gate entre elas (já implementado) |
| Encerramento | `finally` mata só o PID que o launcher criou; nunca varre processos por nome |
| Health | `/health` (gateway, valida `model_id`), `/api/health` (webapp), bolt (Neo4j opcional) |
| Logs | `casos/run_gateway.{out,err}.log`; webapp em foreground |
| PIDs | objeto de processo em memória do launcher (sem arquivo de PID) |
| Porta ocupada | `Get-NetTCPConnection` + probe HTTP antes de subir; erro acionável |
| Retomada | idempotente: gateway já pronto com o modelo certo é reaproveitado |
| Erros | `Die()` com o comando exato de correção (padrão já existente) |

## Regra de segurança preservada

Todos os binds permanecem em `127.0.0.1`, exceto o caminho Quest (TLS
explícito, autorizado). A remoção do branch `ARGOS_CONTAINER` elimina a única
exceção que permitia `0.0.0.0`.

## Baseline de testes (Wave 0)

```
.venv-win\Scripts\python.exe -m pytest -q -p no:cacheprovider
1 failed, 1625 passed, 3 skipped, 1348 warnings em 142,28s
```

1629 = 1610 (baseline PHASE_00) + 19 (os 3 arquivos de characterization da
Fase 03, já commitados separadamente). Contagem bate.

**A única falha é pré-existente e não relacionada a esta migração:**
`tests/test_learning_environment.py::test_environment_report_accepts_free_gpu`
— `training_ready` depende de `shutil.disk_usage()` no host real
(`dtwin/learning/environment.py:94-109`), não do mock de GPU. É dependente do
espaço livre em disco desta máquina no momento da execução, não de Docker.
Não será tocado por esta task (fora de escopo; achado a registrar em
`TECHNICAL_DEBT_REGISTER.md` separadamente).

**Baseline aceito como PASS para fins desta migração**: 1625/1629 passando,
1 falha pré-existente e ambiental, 3 skips por design (dado de paciente não
versionado).

## Resolução do human gate PH-01 (2026-08-18)

Investigação mais funda: `dtwin/graphrag/config.py::load_graphrag_config()` —
único código que carrega `argos-graphrag-neo4j-config-v1` — lê apenas
`safety.research_only` e `safety.clinical_use_allowed`. A dataclass
`GraphRagConfig` não tem campo `privacy`. O bloco `safety.privacy.*` do
arquivo Docker **nunca foi consumido, nem em Docker**. Não é uma proteção que
a migração remove; é YAML morto num arquivo já órfão.

**Decisão do humano (2026-08-18): documentar e descartar.** Nenhuma flag
portada para `configs/graphrag_neo4j.yaml`. A variante docker será excluída
normalmente na Wave 4, sem perda de comportamento real. HG-11/DOM-002: não
acionado de fato — risco fechado, não apenas registrado.

## Resolução de human gates adicionais (2026-08-18, durante Wave 3/4)

**PH-02 — distribuição portátil ARM64 (SEM substituto nativo, por definição).**
`compose.portable.yaml`, `docker/Dockerfile.argos-portable`,
`tools/export_argos_portable.ps1`, `tools/import_argos_portable.sh`,
`tools/start_argos_docker_mac.sh`, `tools/verify_argos_docker_portable.sh`
existem para distribuir o ARGOS como container pronto para quem NÃO tem
Python/CUDA/deps instalados (Mac ARM64) — é zero-setup por construção, o que
Docker resolve e nativo não pode replicar (rodar nativo pressupõe ambiente já
preparado). **Decisão do humano: preservados, fora do escopo desta migração.**
Não removidos nas Waves 4. `tests/test_docker_integration.py::test_portable_*`
(2 testes) permanecem cobrindo esses artefatos residuais — não fazem parte da
substituição nativa; são excluídos do escopo de remoção de testes.

**PH-03 — isolamento de rede do Graphify (risco residual aceito).**
`network_mode: none` do Docker é isolamento kernel-level, sem burlar mesmo com
API key configurada. `tools/graphify_argos.ps1` (`.local\graphify-venv`) roda
como processo comum com acesso a rede; a única barreira nativa é a flag
`--code-only`, que já impede ingestão de docs/imagens (não PHI diretamente,
pois graphify opera sobre código-fonte). **Decisão do humano: documentar como
risco residual conhecido e aceito, sem mitigação técnica agora.** Não bloqueia
a migração (não toca dado científico/PHI).

## Correção ao plano da Wave 1 (feita durante a Wave 4)

A investigação de dependências revelou que `export_argos_portable.ps1` empacota
`compose.yaml`, `compose.portable.yaml`, `docker/` inteiro (via
`docker/entrypoint.sh`, compartilhado por `Dockerfile.argos` E
`Dockerfile.argos-portable`) e `.dockerignore` como pré-requisitos para
construir a imagem portátil no Mac de destino — todos amarrados ao fluxo
preservado por decisão humana (PH-02). Sem acesso a hardware Mac real para
validar qualquer edição fina, a decisão responsável foi **não tocar** nesse
conjunto: tratá-lo como unidade congelada, não como alvo de poda seletiva.
`docker/Dockerfile.graphify` também foi mantido para não deixar `compose.yaml`
com um serviço referenciando um Dockerfile inexistente.

**Lista de remoção revisada e efetivamente executada** (zero dependentes reais
confirmados por grep, nenhum uso pelo fluxo preservado):

- `tools/ensure_docker_desktop.ps1`
- `tools/setup_docker_windows.ps1`
- `tools/smoke_test_argos_docker_e2e.py`
- `tools/start_argos_docker.ps1`
- `tools/stop_argos_docker.ps1`
- `tools/verify_argos_docker_job.py`
- `tools/verify_argos_docker_static.py`
- `tools/verify_medgemma_container.ps1`
- `tools/initialize_argos_docker.ps1` (Windows; a variante `.sh` fica — usada pelo fluxo Mac preservado)
- `tests/test_docker_integration.py` (substituído por `test_native_runtime.py` + `test_portable_distribution.py`)
- `configs/graphrag_neo4j_docker.yaml` (órfã, flags mortas — PH-01)
- `.env.docker` (arquivo LOCAL não versionado desta máquina; regenerável pelo fluxo Mac quando necessário — apenas o arquivo de trabalho local, não a entrada do `.gitignore`)

**Permanecem intocados** (unidade preservada da distribuição portátil):
`compose.yaml`, `compose.portable.yaml`, `docker/` (5 arquivos), `.dockerignore`.

## Segunda correção à lista de remoção (achado tardio, durante verificação da suíte)

A primeira rodada de `git rm` (12 arquivos) quebrou 2 testes fora do inventário
original: `tests/test_quest_dynamic_launcher.py::test_docker_start_*` e
`::test_docker_desktop_is_started_*`. Investigação revelou uma dependência
funcional real que a Wave 0/1 não mapeou:

**`INICIAR_OREN_QUEST.cmd` → `tools/start_oren_quest_dynamic.ps1` →
`tools/start_argos_docker.ps1` → `tools/ensure_docker_desktop.ps1` +
`tools/setup_docker_windows.ps1` + `tools/initialize_argos_docker.ps1`.**

O launcher "um clique" do Quest depende do Docker para uma garantia real: subir
gateway MedGemma + webapp juntos, de forma idempotente, ANTES de publicar o QR
code de acesso. O caminho nativo puro (`run_quest_win.ps1`) não replica essa
garantia — ele assume que o gateway já está rodando em outra janela via
`run_win.ps1` (fluxo em duas etapas, não um clique).

**4 arquivos restaurados** (`git checkout HEAD --`): `ensure_docker_desktop.ps1`,
`setup_docker_windows.ps1`, `start_argos_docker.ps1`, `initialize_argos_docker.ps1`.
Continuam sendo infraestrutura Docker ativa — o objetivo "sem Docker" NÃO está
100% cumprido para este único fluxo. Isso é uma correção genuína ao relatório
de progresso, não um detalhe menor: o critério de aceitação #6 do usuário
("nenhum launcher exigirá Docker") permanece pendente para
`INICIAR_OREN_QUEST.cmd` até decisão humana sobre como consolidar a garantia
"sobe tudo, depois publica QR" nativamente.

**Lista de remoção final, efetivamente aplicada e verificada** (suíte completa
volta a 1 failed pré-existente / 1626 passed / 4 skipped, zero regressão):

- `tools/smoke_test_argos_docker_e2e.py`
- `tools/stop_argos_docker.ps1`
- `tools/verify_argos_docker_job.py`
- `tools/verify_argos_docker_static.py`
- `tools/verify_medgemma_container.ps1`
- `tests/test_docker_integration.py` (substituído)
- `configs/graphrag_neo4j_docker.yaml` (órfã)
- `.env.docker` (arquivo local não versionado)

**Continuam vivos (Docker ainda necessário)**: `tools/ensure_docker_desktop.ps1`,
`tools/setup_docker_windows.ps1`, `tools/start_argos_docker.ps1`,
`tools/initialize_argos_docker.ps1`, `compose.yaml`, `compose.portable.yaml`,
`docker/` (5 arquivos), `.dockerignore`.

## Fechamento do gap do Quest (2026-08-18, decisão humana)

Decisão: **fluxo nativo em duas etapas** (`run_win.ps1` numa janela +
`run_quest_win.ps1` em outra), aceitando abrir mão da garantia "um clique sobe
tudo" que o Docker fornecia. `tools/start_oren_quest_dynamic.ps1` foi
reescrito: em vez de invocar `start_argos_docker.ps1`, verifica precondições
nativas via health check (`http://127.0.0.1:8001/health` para o gateway,
`https://127.0.0.1:8443/api/health` para o webapp) e falha com mensagem
acionável apontando os dois scripts que o usuário precisa ter rodando. Toda a
automação que não era Docker (detecção de rede, firewall, geração de QR,
clipboard) foi preservada intacta.

Isso tornou `tools/{start_argos_docker.ps1, ensure_docker_desktop.ps1,
setup_docker_windows.ps1, initialize_argos_docker.ps1}` genuinamente órfãos —
removidos. `tests/test_quest_dynamic_launcher.py` atualizado (2 testes
Docker-only substituídos por equivalentes nativos; suíte do arquivo: 5 passed).

**Resultado: critério de aceitação #6 agora 100% cumprido** — nenhum launcher
ativo (webapp, gateway, desktop, Quest) exige Docker Desktop, Compose ou WSL.
Suíte completa final: **1626 passed, 0 failed, 4 skipped** (o teste ambiental
de disco também passou nesta rodada).

## Lista de remoção final e completa (16 itens)

`tools/{smoke_test_argos_docker_e2e.py, stop_argos_docker.ps1,
verify_argos_docker_job.py, verify_argos_docker_static.py,
verify_medgemma_container.ps1, start_argos_docker.ps1, ensure_docker_desktop.ps1,
setup_docker_windows.ps1, initialize_argos_docker.ps1}` (9),
`tests/test_docker_integration.py` (substituído), `configs/graphrag_neo4j_docker.yaml`
(órfã), `.env.docker` (local).

**Permanecem intocados** (unidade preservada da distribuição portátil, decisão
PH-02): `compose.yaml`, `compose.portable.yaml`, `docker/` (5 arquivos),
`.dockerignore`, `tools/{export_argos_portable.ps1, import_argos_portable.sh,
start_argos_docker_mac.sh, verify_argos_docker_portable.sh,
initialize_argos_docker.sh}`.
