# Estado persistente

LAST_UPDATED: 2026-08-17 (tarde) America/Sao_Paulo  
PACK_SCHEMA: argos-fable-engineering-pack-v1  
BASE_COMMIT: `9683eaa796d01e946597f3fe1351556aa8fcb141`  
BRANCH: `main` (sessão executada no worktree `claude/fable-engineering-phase-00-b0172f`, mesmo HEAD)  
CURRENT_PHASE: `PHASE_01_CARTOGRAPHY` → **DONE** (2026-08-17, waves 1-4)  
CURRENT_WAVE: `wave-4-depmap-cards-exit-review` = DONE  
CURRENT_MODULE: `cross-cutting`  
LAST_COMPLETED_TASK: `TASK-2026-08-17-PH01-CARTO-04` (20 edges estáticos VERIFIED; 259/259 paths dos module cards existem; exit review: PHASE_01 DONE)  
NEXT_RECOMMENDED_TASK: `iniciar PHASE_02_CONTRACTS (aguardando autorização humana para nova fase)`  
STATUS: `DONE` (fase 01) / avanço de fase aguarda o humano

## Snapshot observado

- Repositório: 1.267 paths versionados; 251 em `dtwin/`, 307 em `tools/`, 258 arquivos de teste, 247 documentos e 121 configs.
- Código Python versionado: 147.797 linhas em 792 arquivos no snapshot; hotspots incluem `webapp/server.py` (3.610), `dtwin/learning/medsiglip_multiclass_classifier.py` (1.395) e `dtwin/stages.py` (1.243).
- Python do host: 3.13.14. `.venv-win` (pytest 9.1.1): coleta = 1.610 testes (11,05 s nesta sessão; 18,09 s no snapshot).
- Container `argos-runtime:local` (`sha256:a5e278043304…`, criada 2026-08-14): Python 3.11.11, torch 2.6.0+cu124, CUDA visível (RTX 4060, driver 610.62).
- Ferramentas no host: pytest somente em `.venv-win`; coverage.py, Hypothesis, Ruff, mypy, pip-audit, mutmut e pytest-benchmark ausentes (instalação ADIADA por decisão humana de 2026-08-17).
- Hardware observado: Lenovo 83DG, ~31,7 GiB RAM; NVIDIA RTX 4060 Laptop 8.188 MiB, driver 610.62/CUDA UMD 13.3.
- Docker CLI 29.7.2 + Docker Desktop 4.86.0: daemon FUNCIONAL nesta sessão (destravado após remoção de sockets órfãos de 14/08; ver KNOWN_FAILURES).
- CI: GitHub Actions **ubuntu-latest**, Python 3.13, `pip install -e .[dev]`, `doctor`, `pytest -q`; sem gates de lint/typing/coverage/mutação/supply-chain.
- Graphify arquitetural presente em `graphify-out/`; GraphRAG clínico/metadados é outro subsistema.

## Dirty state

Untracked pré-existentes, não tocados: `docs/186_RELATORIO_CIENTIFICO_CONSOLIDADO_ARGOS.zip`, `viewer/assets/materials/liver_realistic_v1_source.png`.

Decisão de 2026-08-17 (HUMAN_DECISIONS.md item 7): o pack `.fable/` + `CLAUDE.md` foram **versionados por commit** no repo principal (sem push). Mudanças aplicadas e **ainda não commitadas** (commits separados, quando solicitados — uma mudança por pacote):

- `tests/test_learning_monophase_slice_candidates.py` + `tests/test_operational_timing_relative_workspace.py` — skipif de plataforma (TASK-2026-08-17-CHG-01).
- `graphify-out/` — regeneração code-only, 4 substituídos + GRAPH_TREE.html removido (TASK-2026-08-17-CHG-02).

## BLOCKERS

- (resolvido 2026-08-17) ~~Baseline global não executado~~ → suíte executada em container; ver TEST_BASELINE.
- (resolvido 2026-08-17) ~~Docker daemon desligado~~ → destravado; causa raiz e correção em KNOWN_FAILURES.
- Dependências com limites amplos e sem lockfile Python integral para todos os extras/hardware (persiste; `evidence/PH00/container_pip_freeze.txt` é o freeze do container de baseline).
- Evidências numéricas do manuscrito não reexecutadas contra artefatos neste snapshot (persiste).
- Baseline estático/coverage/benchmark NOT_RUN (adiado por decisão humana).

## AWAITING_HUMAN_DECISIONS

Resolvidas em 2026-08-17 (ver `HUMAN_DECISIONS.md`): ratificação dos 16 CONFIRMED (congelados); CONFLICTs GEO-002 (dois contratos escopados), SW-001 (hash-integridade) e DOM-002 (comportamento atual ratificado); graphify-out regenerado code-only; skipif autorizado e aplicado; pack versionado; tolerâncias numéricas → PHASE_06.

Ainda pendentes:

- Autorizar início da PHASE_02_CONTRACTS.
- Resolver ambiguidades restantes de `MANUSCRIPT_VS_CODE.md` que não foram cobertas pelos 3 CONFLICTs decididos (inclui reconciliação 451/16 por ledger e correção editorial de "assinado" no manuscrito).
- Decidir push do commit do pack (commit local feito; push não).

## OPEN_BUGS

Consulte `TECHNICAL_DEBT_REGISTER.md`, `FAILURE_MODES.md` e `LEGACY_AND_DEAD_CODE_CANDIDATES.md`.

Resolvidos em 2026-08-17: os 2 testes Windows-only ganharam `skipif` autorizado (CHG-01; POSIX 12 passed/2 skipped, Windows 14 passed); `graphify-out` regenerado code-only (CHG-02).

Abertos:

- Com o skipif aplicado, o CI ubuntu-latest deve ficar verde; estado real do CI segue não verificado (gh ausente).
- Imagem runtime não contém `git`, mas 6 testes da suíte dependem do binário — divergência ambiente-imagem vs ambiente-teste.
- `webapp/seg_worker.py` (42 linhas) é estaticamente órfão — nenhuma referência de entrada; o runtime copia `dtwin/seg_worker.py` (29 linhas, conteúdo divergente) via `dtwin/segmentation_subprocess.py:94-95`. Candidato a legacy; remoção só com prova de reachability runtime e autorização.
- Docker Desktop 4.86.0: TODO encerramento deixa sockets Unix irremovíveis e o próximo arranque crasha; workaround = renomear `%LOCALAPPDATA%\Docker\run` e `%LOCALAPPDATA%\docker-secrets-engine` antes de iniciar (3 ocorrências em 2026-08-17). Correção definitiva sugerida: atualizar Docker Desktop ou reboot.

## OPEN_RISKS

Consulte `SCIENTIFIC_RISK_REGISTER.md`, `MANUSCRIPT_VS_CODE.md` e contratos `status: CONFLICT` em `SCIENTIFIC_CONTRACTS.yaml`. Nenhum risco resolvido nesta sessão.

## TEST_BASELINE

Ambiente canônico (decisão humana 2026-08-17): container Docker `argos-runtime:local` com worktree em `BASE_COMMIT` montado e árvore de execução gravável (`/tmp/ws`), git+pytest efêmeros, HF offline. Comando completo e script em `tasks/TASK-2026-08-17-PH00-BASELINE-01_EVIDENCE.md` e `evidence/PH00/ph00_run_tests_v2.sh`.

- Coleta host `.venv-win`: **1.610 coletados** (11,05 s), 4 warnings — consistente com snapshot.
- Execução container RUN1 (mount `:ro`, sem git): 13 failed / 1594 passed / 3 skipped / 44 warnings (49,00 s) — 11 falhas ambientais explicadas.
- Execução container RUN2 (canônica): **2 failed / 1605 passed / 3 skipped / 78 warnings (39,86 s)** — 2 falhas restantes são plataforma Windows-vs-POSIX (ver OPEN_BUGS); 3 skips por calibrador não versionado (dado derivado de paciente, por design).
- `python digital_twin.py doctor` no container: exit 0, núcleo completo.
- Logs completos: `evidence/PH00/pytest_run1_ro_mount.log`, `evidence/PH00/pytest_run2_writable_tree.log`.

## KNOWN_FAILURES

- Docker Desktop 4.86.0 crashava na inicialização: sockets Unix órfãos de 14/08 irremovíveis (`%LOCALAPPDATA%\Docker\run\*` e `%LOCALAPPDATA%\docker-secrets-engine\engine.sock`, erro "The file cannot be accessed by the system"). Correção 2026-08-17: renomear diretórios (`run.stale-20260817`, `run.stale-20260817-b`, `docker-secrets-engine.stale-20260817`); Docker recria. Diretórios stale podem ser deletados após reboot. Sem reset de fábrica; nenhum dado/imagem perdido.
- Ferramentas estáticas/adversariais recomendadas seguem ausentes (adiadas).
- Claims por domínio abaixo do gate agregado e transferibilidade externa fraca constam no manuscrito; não são bugs de software automaticamente.
