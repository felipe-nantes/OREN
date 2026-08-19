# Registro de decisões humanas

Formato mínimo de HUMAN_GATES.md. Aprovador em todas: **Felipe Nantes (fnantes07@gmail.com)**, via sessão interativa Claude Code (worktree `fable-engineering-phase-00-b0172f`), data **2026-08-17**. Task de registro: `TASK-2026-08-17-GOV-01`.

## Bloco 1 — contratos (HG-01)

1. **APROVO HG-01 para TASK-2026-08-17-GOV-01, opção "dois contratos escopados", escopo ARGOS-GEO-002**: o Dice ≥ 0,80 entre máscaras hepáticas automáticas governa o alinhamento das coortes OpenSwissHCC (`dtwin/benchmark/openswisshcc_alignment.py`); a cobertura ≥ 0,50 da grade venosa governa o ingest DICOM bruto do produto (`dtwin/learning/multiphase_ingest.py`). São dois contratos com escopos distintos; nenhum substitui o outro; nenhuma mudança de código decorrente.
2. **APROVO HG-01 para TASK-2026-08-17-GOV-01, opção "ratificar hash-integridade", escopo ARGOS-SW-001**: o contrato declara integridade por SHA-256 canônico (manifest) + SHA-256 (modelo), sem claim de autenticação/assinatura com chave. O termo "assinado" do manuscrito deve ser corrigido na próxima revisão textual (pendência editorial, não de engenharia).
3. **APROVO HG-01 para TASK-2026-08-17-GOV-01, opção "ratificar comportamento atual", escopo ARGOS-DOM-002**: as regras vigentes ficam ratificadas como contrato — caminho NIfTI descarta headers DICOM; o resolver de fases retém bytes DICOM originais; revisão humana de PHI queimada permanece obrigatória (não automática); o modo demo autoassume a confirmação humana documentada.
4. **APROVO HG-01 para TASK-2026-08-17-GOV-01, opção "ratificar todos", escopo SCI-001..013, GEO-001, GEO-003, GEO-004, DOM-001**: os 16 contratos CONFIRMED ficam **congelados**. Evidência da ratificação: verificação da wave 3 (`RUNTIME_EDGES.md`, 15 MATCH + 1 MATCH_TRANSITIVE). Mudança futura somente via HG-01 com regressão científica.

## Bloco 2 — operacionais

5. **Graphify**: regenerar `graphify-out/` versionado com extração code-only reproduzível no snapshot `9683eaa` (política de `tools/graphify_argos.ps1` preservada; sem nós de documento). Mudança LOW em artefato derivado; commit separado, quando solicitado.
6. **Testes Windows-only**: autorizado `@pytest.mark.skipif(os.name != "nt")` nos 2 testes (`tests/test_learning_monophase_slice_candidates.py::test_windows_publish_fallback_copies_manifest_last_and_verifies_hashes`, `tests/test_operational_timing_relative_workspace.py::test_relative_workspace_still_exposes_operational_timing_artifact`), com baseline antes/depois em container (POSIX) e host Windows. Mudança LOW na suíte.
7. **Versionamento do pack**: `git add .fable/ CLAUDE.md` + commit no repo principal, sem push até solicitação.
8. **Tolerâncias numéricas por backend**: serão medidas e propostas na PHASE_06 (scientific regression), com separação LOGIC vs NUMERICAL. Até lá, nenhuma igualdade bitwise cross-backend é assumida.

## Decisões anteriores da mesma data (já registradas em evidence packages)

- Ambiente oficial de baseline executável = container Docker (`argos-runtime:local`) — PHASE_00.
- Ferramentas estáticas: instalação adiada — PHASE_00.
- Autorização das fases: PHASE_00 (implícita no pack), PHASE_01, e blocos de decisão desta página.

## Bloco 3 — 2026-08-18 (PHASE_06)

9. **APROVO tolerâncias numéricas por backend para TASK-2026-08-18-PH06-REG-02**
   (fecha o item 8 de 2026-08-17), aprovador Felipe Nantes, 2026-08-18:
   - **LOGIC** (splits/digests/contagens/voxel_count/denominadores): igualdade
     EXATA obrigatória entre backends; divergência = bug.
   - **NUMERICAL escalar CPU** (Wilson, volumes, coberturas, médias):
     tolerância relativa ≤ 1e-12.
   - **NUMERICAL array CPU** (resample/harmonização): zero voxels divergentes
     (>1e-9 rel) no escopo de versões testado; mudança de major de
     numpy/SimpleITK exige re-executar a sonda antes de aceitar novos números.
   - **GPU/CUDA**: EM ABERTO — não medida; igualdade bitwise não assumida.
   Evidência: delta observado = ZERO (bitwise) entre Windows/py3.13/numpy2.5 e
   Linux/py3.11/numpy2.2 (`evidence/PH06/probe_*.json`).

## Bloco 4 — 2026-08-18 (protocolo context-efficient)

10. **Ferramentas estáticas revertidas** (fecha o restante do adiamento de
    2026-08-17): ruff 0.16.3, mypy 2.3.1 e ast-grep-cli 0.45.1 instalados no
    `.venv-win`. Baseline ruff capturado em
    `evidence/TOOLING/ruff_baseline_2026-08-18.txt` (~900 achados, dominados
    por estilo; correções ficam para PHASE_07/08). Ainda ausentes: coverage,
    pip-audit, mutmut, pytest-benchmark (instalar quando a PHASE_07 exigir).
11. **SAFETY_KERNEL.md autorizado e redigido** exclusivamente a partir do
    conteúdo ratificado (HUMAN_GATES, STOP_CONDITIONS, SCI-001/GEO-003/
    SCI-005/SCI-006, POL-PHI-01, DOM-002, tolerâncias do item 9), com hashes
    das fontes canônicas. Não cria regras novas; pendente de revisão do
    operador.
12. **Migração de formato autorizada e executada**: `CURRENT_STATE.yaml` e
    `ROUTER.yaml` são os canônicos; os `.md` viraram stubs de ponteiro
    (histórico preservado no git). Inconsistências de header acumuladas no
    CURRENT_STATE.md foram normalizadas na migração.
