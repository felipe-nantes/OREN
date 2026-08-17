# TASK_CARD — TASK-2026-08-17-PH00-BASELINE-01

Gerado em 2026-08-17 (America/Sao_Paulo) por Claude Fable 5, sessão em worktree `claude/fable-engineering-phase-00-b0172f`.

```yaml
TASK_ID: TASK-2026-08-17-PH00-BASELINE-01
TASK_DESCRIPTION: >
  PHASE_00_FREEZE — estabelecer baseline executável reproduzível do snapshot
  9683eaa sem alterar semântica: fingerprint de ambiente, execução da suíte
  global de testes, doctor, e registro de comandos reproduzíveis e logs sem PHI.
TASK_TYPE: baseline_capture (investigação + execução de testes; nenhum patch)
REQUESTED_OUTCOME: >
  Exit criteria da PHASE_00: suíte global executada em ambiente escolhido;
  failures/warnings explicados; container/backend relevantes identificados;
  comandos reproduzíveis registrados em manifest.
FILES_DIRECTLY_MENTIONED:
  - .fable/plans/PHASE_00_FREEZE.md
  - .fable/CURRENT_STATE.md
FILES_SUSPECTED:
  - pyproject.toml
  - requirements.txt
  - compose.yaml
  - compose.portable.yaml
  - .github/ (workflow de CI com doctor + pytest)
  - tests/ (258 arquivos; 1.610 testes coletados)
PRIMARY_MODULE: cross-cutting (TESTS_BUILD_ENVIRONMENT)
SECONDARY_MODULES: [DOCKER_DEPLOYMENT, DEPENDENCIES, PERFORMANCE]
UPSTREAM_DEPENDENCIES: [.venv-win (pytest 9.1.1, Python 3.13.14), host Python 3.13.14]
DOWNSTREAM_DEPENDENCIES: [todas as fases 01-10 dependem deste baseline]
SCIENTIFIC_IMPACT: NONE_DIRECT (nenhuma semântica alterada; baseline protege contratos futuros)
GEOMETRIC_IMPACT: NONE_DIRECT
STATISTICAL_IMPACT: NONE_DIRECT
PRIVACY_IMPACT: >
  LOW — logs de teste não devem conter PHI; testes usam fixtures do repo.
  Nenhum dado médico externo será aberto (HG-11 não acionado se mantido).
SECURITY_IMPACT: NONE_DIRECT (nenhuma superfície alterada)
PERFORMANCE_IMPACT: NONE (somente medição)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: >
  Investigação/report + execução read-only de testes: dentro da autoridade.
  Escolha do ambiente oficial de baseline: AWAITING_HUMAN (CURRENT_STATE.md).
  Instalação de ferramentas estáticas no ambiente: requer autorização explícita.
REQUIRED_CONTEXT:
  - CLAUDE.md, START_HERE.md, TASK_PROTOCOL.md, ROUTER.md, CURRENT_STATE.md
  - plans/PHASE_00_FREEZE.md
  - SESSION_PROTOCOL.md, HUMAN_GATES.md
REQUIRED_REFERENCES: [REPRODUCIBILITY.md, TOOLING.md]
REQUIRED_CONTRACTS: []  # nenhuma alteração semântica; contratos não são tocados
REQUIRED_SCIENTIFIC_CONTRACTS: []  # leitura apenas; nenhuma edição de SCIENTIFIC_CONTRACTS.yaml
BASELINE_REQUIRED: true  # esta task É o baseline
CHARACTERIZATION_REQUIRED: false
CONTRACT_TESTS_REQUIRED: false
PROPERTY_TESTS_REQUIRED: false
INTEGRATION_TESTS_REQUIRED: false  # executa a suíte existente, não cria novos testes
SCIENTIFIC_REGRESSION_REQUIRED: false
MUTATION_TESTING_REQUIRED: false
BENCHMARK_REQUIRED: false  # perf baseline "onde aplicável"; adiado se ferramentas ausentes
ALLOWED_ACTIONS:
  - comandos read-only de git/ambiente (rev-parse, status, versions, nvidia-smi, docker version)
  - pytest --collect-only e execução da suíte no ambiente autorizado
  - executar `doctor` (diagnóstico, sem mutação)
  - capturar pip freeze / hashes de dependency files em logs no pack
  - escrever manifest de baseline e logs sob .fable/ (sem PHI)
  - atualizar CURRENT_STATE.md e produzir SESSION_HANDOFF ao término
FORBIDDEN_ACTIONS:
  - alterar qualquer código, config, profile ou contrato
  - commit/push (decisão de versionamento do pack é AWAITING_HUMAN)
  - instalar/atualizar pacotes em .venv-win sem autorização explícita
  - ligar/reconfigurar Docker Desktop ou qualquer serviço do sistema
  - abrir dados médicos, labels protegidos ou máscaras de lesão
  - tratar resultado de teste observado como aprovação científica
HUMAN_GATE: >
  Nenhum HG-01..HG-12 acionado por captura read-only. Decisão humana pendente
  (CURRENT_STATE): ambiente oficial de baseline (Windows .venv-win vs Docker
  vs Mac/MPS) e tolerâncias numéricas por backend.
STOP_CONDITIONS:
  - suíte exigir dados/credenciais ausentes ou dados sensíveis reais
  - evidência de PHI em fixtures/logs durante execução
  - divergência de HEAD/dirty state em relação ao snapshot documentado
  - falhas em massa indicando ambiente irreproduzível (baseline inválido)
EXPECTED_EVIDENCE_PACKAGE: >
  Manifest de baseline (commit, dirty state, ambiente, hardware, comandos),
  log completo do pytest (contagens pass/fail/skip/warning explicadas),
  saída do doctor, e atualização de CURRENT_STATE.md + SESSION_HANDOFF.
```

## Verificação de estado executada (2026-08-17, read-only)

- Worktree `claude/fable-engineering-phase-00-b0172f`: HEAD `9683eaa796d01e946597f3fe1351556aa8fcb141` = `BASE_COMMIT` do pack; worktree limpo.
- Repo principal `main`: mesmo HEAD; dirty state = exatamente os 4 paths pré-existentes documentados (`.fable/`, `CLAUDE.md`, `docs/186_...zip`, `viewer/assets/materials/liver_realistic_v1_source.png`). Nenhuma divergência nova.
- Host Python 3.13.14; `.venv-win` Python 3.13.14 com pytest 9.1.1. `import dtwin` a partir do worktree resolve para o código do worktree (idêntico ao snapshot, worktree limpo).
- GPU: RTX 4060 Laptop 8.188 MiB, driver 610.62. Docker CLI 29.7.2 presente, daemon indisponível (npipe não encontrado) — blocker de baseline containerizado persiste.
- `pytest --collect-only -q -p no:cacheprovider` no worktree: **1.610 testes coletados em 11,05 s**, warnings consistentes com o snapshot (swigvarlink DeprecationWarning, StarletteDeprecationWarning). Baseline documental válido.

STATUS: DONE (2026-08-17) — humano escolheu ambiente Docker ("ligue o docker") e adiou ferramentas estáticas; baseline canônico: 2 failed / 1605 passed / 3 skipped / 78 warnings em 39,86 s no container `argos-runtime:local`; doctor exit 0. Evidência: `TASK-2026-08-17-PH00-BASELINE-01_EVIDENCE.md` e `../evidence/PH00/`.
