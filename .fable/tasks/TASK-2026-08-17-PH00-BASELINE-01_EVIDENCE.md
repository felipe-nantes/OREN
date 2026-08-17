# EVIDENCE PACKAGE — TASK-2026-08-17-PH00-BASELINE-01

```yaml
TASK_ID: TASK-2026-08-17-PH00-BASELINE-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141
TASK_DESCRIPTION: >
  PHASE_00_FREEZE — baseline executável reproduzível em ambiente containerizado
  (decisão humana nesta sessão: "ligue o docker"), sem alteração de semântica.
ROUTE: [TESTS_BUILD_ENVIRONMENT, DOCKER_DEPLOYMENT, DEPENDENCIES]
MODULES: [cross-cutting]
FILES_ANALYZED:
  - compose.yaml
  - docker/Dockerfile.argos
  - docker/entrypoint.sh
  - pyproject.toml (extras)
  - .github/workflows/tests.yml
  - tests/test_learning_monophase_slice_candidates.py (falha residual 1)
  - tests/test_operational_timing_relative_workspace.py (falha residual 2)
  - dtwin/learning/monophase_slice_candidates.py:81 (gate os.name == "nt")
FILES_CHANGED: []  # nenhum arquivo do repositório alterado; apenas documentos do pack .fable/
RISK_LEVEL: LOW
AUTHORITY_LEVEL: dentro da autoridade (captura read-only + execução de testes autorizada pelo humano)
CONTRACTS_INVOLVED: []
SCIENTIFIC_CONTRACTS_INVOLVED: []
BASELINE:
  ENVIRONMENT:
    KIND: container Docker (Docker Desktop 4.86.0, engine 29.7.2, WSL2, Windows 11 Home 26200)
    IMAGE: argos-runtime:local
    IMAGE_ID: sha256:a5e27804330442637463cdeb62999059af378b72201eab9568e331974b60d7b8
    IMAGE_CREATED: 2026-08-14T06:10:10Z (código baked na imagem NÃO usado; testes rodaram na árvore montada do worktree em BASE_COMMIT)
    PYTHON_CONTAINER: 3.11.11
    TORCH: 2.6.0+cu124, cuda_available=True, device_count=1 (RTX 4060 Laptop 8188 MiB, driver 610.62)
    EPHEMERAL_ADDITIONS: pytest 9.x, httpx, python-multipart (pip), git (apt) — somente no container; imagem intacta
    OFFLINE_POLICY: HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1
    PIP_FREEZE: evidence/PH00/container_pip_freeze.txt
  COMMANDS:
    RUN2_CANONICAL: >
      docker run --rm -u 0 --gpus all
      -v <worktree@9683eaa>:/workspace:ro -v <scratch>:/scratch
      -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1
      argos-runtime:local bash /scratch/ph00_run_tests_v2.sh
      # script: instala git+pytest efêmeros, cp -a /workspace /tmp/ws,
      # cd /tmp/ws && python -m pytest -q -p no:cacheprovider --basetemp=/tmp/pytest -rA --durations=25
    DOCTOR: docker run --rm -v <worktree>:/workspace:ro -w /workspace argos-runtime:local python digital_twin.py doctor
  RESULTS:
    COLLECT_HOST_VENVWIN: 1610 testes coletados em 11,05 s (Python 3.13.14, pytest 9.1.1) — igual ao snapshot do pack
    RUN1_RO_MOUNT: 13 failed, 1594 passed, 3 skipped, 44 warnings, 49,00 s — 11 falhas ambientais (mount :ro e git ausente)
    RUN2_WRITABLE_TREE: 2 failed, 1605 passed, 3 skipped, 78 warnings, 39,86 s — BASELINE CANÔNICO
    DOCTOR: exit 0, núcleo completo, TotalSegmentator importável (rodado sem --gpus; torch device: cpu esperado nesse modo)
BUG_REPRODUCTION: N/A (nenhum bug corrigido nesta task)
TESTS_BEFORE:
  - resultado global anterior: NOT_RUN (CURRENT_STATE do pack)
TESTS_ADDED: []
TESTS_AFTER:
  - "container linux py3.11: 2 failed, 1605 passed, 3 skipped, 78 warnings (49,00s/39,86s)"
STATIC_ANALYSIS: NOT_RUN (decisão humana nesta sessão: adiar instalação de ruff/mypy/coverage/pip-audit)
BRANCH_COVERAGE: NOT_RUN (mesma decisão)
MUTATION_RESULT: NOT_APPLICABLE (fase 00)
PROPERTY_TEST_RESULT: NOT_APPLICABLE (fase 00)
INTEGRATION_RESULT: incluído na suíte global (testes de webapp/pipeline passaram no RUN2)
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE (nenhuma mudança)
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE (nenhuma mudança)
BENCHMARK_BEFORE: NOT_RUN (pytest-benchmark ausente; adiado)
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE (nenhum código alterado)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Baseline executado com Python 3.11 (imagem) vs 3.13 (host/CI); backends distintos, não comparáveis bitwise.
  - Código da imagem (14/08) difere potencialmente do HEAD; mitigado montando o worktree em BASE_COMMIT como fonte dos testes e do código importado (cwd=/tmp/ws).
  - Estado do CI remoto não verificado (gh ausente no host).
  - doctor executado sem GPU passthrough (preflight de dependências apenas).
UNRESOLVED_RISKS:
  - "FALHA EXPLICADA 1 (plataforma): tests/test_learning_monophase_slice_candidates.py::test_windows_publish_fallback_copies_manifest_last_and_verifies_hashes — o fallback de publicação só existe sob os.name=='nt' (dtwin/learning/monophase_slice_candidates.py:81); teste sem skipif falha em POSIX por construção."
  - "FALHA EXPLICADA 2 (plataforma): tests/test_operational_timing_relative_workspace.py::test_relative_workspace_still_exposes_operational_timing_artifact — espera literal 'case\\\\outputs\\\\operational_timing.json' (separador Windows hardcoded, linha 26); em POSIX o servidor produz 'case/outputs/...'."
  - "INFERÊNCIA L6 (não verificada): CI roda em ubuntu-latest + pytest -q; os dois testes acima deveriam falhar no CI neste commit. Verificar histórico de CI antes de concluir."
  - "3 SKIPPED: tests/test_lld_mmri_v23_predictions.py — exigem calibrador congelado em casos/ (dado derivado de paciente, não versionado). Por design; sem acesso a dados sensíveis nesta sessão (HG-11 não acionado)."
  - "WARNINGS (78): FutureWarnings skimage em dtwin/stages.py:133-136 (binary_opening/closing/min_size deprecados), FutureWarning sklearn (penalty), UserWarnings sklearn (features constantes, batch_size), DeprecationWarning swig, StarletteDeprecationWarning (testclient). Candidatos a fase 08; nenhuma ação agora."
HUMAN_GATE: >
  Nenhum HG-01..12 acionado. Decisões humanas registradas nesta sessão:
  (1) "ligue o docker" — ambiente de baseline = container Docker; autorizou iniciar
  Docker Desktop e o troubleshooting de sockets órfãos; (2) adiar ferramentas estáticas.
APPROVAL_STATUS: ações executadas dentro do escopo autorizado; nenhum patch de código proposto ou aplicado
DIFF_SUMMARY: >
  Repositório: nenhum diff. Pack: novos arquivos .fable/tasks/ (TASK_CARD, evidence,
  handoff), .fable/evidence/PH00/ (logs, pip freeze, scripts), e atualização de
  CURRENT_STATE.md / LONG_PLAN.md / plans/PHASE_00_FREEZE.md.
  Host (fora do repo): diretórios obsoletos renomeados para destravar o Docker
  (%LOCALAPPDATA%\Docker\run -> run.stale-20260817{,-b};
  %LOCALAPPDATA%\docker-secrets-engine -> docker-secrets-engine.stale-20260817);
  removíveis após reboot.
ROLLBACK: >
  Nenhum rollback de código necessário. Para desfazer o pack desta task: remover os
  arquivos novos de .fable/tasks/ e .fable/evidence/PH00/ e restaurar CURRENT_STATE.md,
  LONG_PLAN.md e plans/PHASE_00_FREEZE.md pela versão anterior.
FINAL_STATUS: DONE
```

## Explicação das 11 falhas do RUN1 eliminadas no RUN2

- 6× `OSError: Errno 30` + 5 dependentes: testes de finalize/candidate/CLI criam `flywheel/…` relativo ao cwd; cwd era o mount `:ro`. Com árvore gravável (`/tmp/ws`), todos passam.
- 3× `FileNotFoundError: 'git'` (benchmark_cli/reporting) + 3× benchmark webapp (`'failed' == 'done'`, `run_manifest.json` ausente): a imagem runtime não tem binário `git`; instalado efemeramente via apt, todos passam.
