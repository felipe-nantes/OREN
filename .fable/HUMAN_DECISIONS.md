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

## Bloco 5 — 2026-08-20 (PHASE_09)

13. **APROVO HG-03 para TASK-2026-08-20-PH09-HRR-01, opção A1 nos dois
    sítios, escopo `webapp/server.py::_mesma_geometria_sitk` (gate da união
    de fases) e `dtwin/stages.py::stage5_refine` (defesa de geometria),
    aprovador Felipe Nantes, 2026-08-20**: adicionar checagem de direction
    (`np.allclose(..., rtol=0, atol=1e-6)`) à conjunção existente de ambos os
    comparadores, mantendo size/spacing/origin EXATOS como hoje (delta
    mínimo, estritamente mais fail-closed). Máscara de fase com direction
    divergente cai no bucket `geometria_divergente`; união divergente no
    stage5 é descartada com warning e fallback para a venosa. Os
    characterization tests da PHASE_03 são atualizados para o novo
    comportamento aprovado (viram spec tests citando esta decisão). Evidência
    da reprodução: `evidence/PH09/demo_direction_blind_2026-08-20.json`
    (voxel fantasma a 8 mm via OR em array space). O sítio
    `multiphase_ingest` foi verificado e INOCENTADO (resample físico já trata
    direction).

14. **APROVO HG-02 para TASK-2026-08-20-PH09-HRR-02, opção B1 (auditabilidade
    apenas), escopo `dtwin/learning/raw_dicom_phase_resolver.py`, aprovador
    Felipe Nantes, 2026-08-20**: o manifesto de resolução de fases passa a
    registrar (a) colisões de papel no texto da série
    (`ambiguous_text_roles` por série selecionada +
    `series_with_ambiguous_text_roles` global) e (b) séries dinâmicas
    elegíveis não selecionadas pela heurística primeira/segunda/última
    (`unselected_eligible_dynamic_series`). NENHUMA heurística de seleção
    alterada — mesmas séries, mesmos códigos de erro, mesma confiança; campos
    são aditivos ao schema v1 (único consumidor externo lê apenas
    series_hash). Fecha os 2 itens abertos do TD-014.

15. **APROVO remoção para TASK-2026-08-20-PH09-HRR-03, opção R1, escopo
    `webapp/seg_worker.py` + `tools/freeze_segmentation_visualization_baseline.py`
    (lista TRACKED_FILES), aprovador Felipe Nantes, 2026-08-20**: remoção do
    launcher legado comprovadamente inalcançável em runtime (zero imports,
    zero invocações por string; sucessor ativo = `dtwin/seg_worker.py`,
    coberto por teste de integração). O baseline histórico
    `configs/baselines/segmentation_visualization_v1.json` permanece intocado
    (5/5 pins já stale; sem verificador programático). Follow-up PHASE_10:
    decidir destino do mecanismo de baseline (freeze v2 verificado ou
    aposentadoria).

## Bloco 6 — 2026-08-20 (PHASE_10, encerramento)

16. **APROVO aposentadoria do mecanismo de baseline v1 para
    TASK-2026-08-20-PH10-CON-01, aprovador Felipe Nantes, 2026-08-20**:
    `configs/baselines/segmentation_visualization_v1.json` fica anotado como
    registro HISTÓRICO congelado do snapshot original (5/5 pins stale por
    evolução aprovada; nenhum verificador programático jamais o consumiu);
    o freeze tool ganha a mesma anotação. Nenhum freeze v2.
17. **RATIFICO o SAFETY_KERNEL.md** (redigido em 2026-08-18 sob autorização,
    exclusivamente de conteúdo já ratificado, com hashes das 5 fontes
    canônicas), aprovador Felipe Nantes, 2026-08-20. Em divergência, a fonte
    canônica prevalece (SOURCE_OF_TRUTH_CONFLICT), como declarado no próprio
    documento.
18. **APROVO o fechamento formal da PHASE_03_CHARACTERIZATION** (os 4 P0s
    caracterizados e revisados em 2026-08-17/18; waves extras opcionais
    declinadas no encerramento), aprovador Felipe Nantes, 2026-08-20.

## Bloco 7 — 2026-08-24 (ciclo POST_AUDIT)

19. **APROVO HG-07/HG-08 para TASK-2026-08-24-GOV-01, aprovador Felipe
    Nantes, 2026-08-24**, nas duas propostas:
    (A) testes negativos de proveniência do estimando (test-only; produção
    intocada): a superfície de apresentação nunca expõe
    `cross_validated_selection_metrics` (otimista: 79,1/80,1 em população
    de 451 computáveis) como generalização; âncora honesta obrigatória
    (nested-OOF 75,91/76,11 em 467 com falhas no denominador, SCI-004).
    Fecha o lado de engenharia do SR-006.
    (B) regime de consumo do outer OOF para o ciclo POST_AUDIT = **c+d+b**:
    triagem/desenvolvimento somente com dev signals/inner CV (zero leituras
    do outer); promoção com no máximo 1 leitura LOCKED do outer por
    candidato promovível, com endpoints PRÉ-registrados
    (CANDIDATE_COMPARISON antes da leitura); toda leitura registrada no
    `outer_inspection_counter` do EXPERIMENT_LEDGER com experiment_id.

20. **RATIFICO as tolerâncias GPU/CUDA para TASK-2026-08-24-REP-01
    (estende e fecha o item EM ABERTO da decisão 9), aprovador Felipe
    Nantes, 2026-08-24**:
    - **GPU run-to-run** (mesmo stack: RTX 4060 Laptop, torch 2.6.0+cu124,
      cudnn 90100): igualdade BITWISE exigível — medida com delta ZERO em
      7 famílias de ops (matmul, softmax, layernorm, conv3d, interpolate
      trilinear, sum, mean) × 2 regimes (determinístico E padrão de
      produção) × 3 repetições in-process + 3 processos independentes com
      sha256 idêntico. Mudança de GPU/driver/torch/cudnn exige re-sonda
      antes de aceitar novos números (mesma cláusula do item 9).
    - **GPU vs CPU**: igualdade bitwise NUNCA assumida. Arrays float32:
      rtol ≤ 1e-2 com atol ≤ 1e-4 × amplitude do tensor (medidos:
      elementwise ~1e-7 rel; acumulações até ~4e-3 rel). Decisões
      derivadas (máscaras binárias, classes, contagens/LOGIC) devem
      coincidir EXATAMENTE.
    Evidência: post_audit/evidence/REP-01/gpu_tolerance_probe_2026-08-24.json.
    **BLK-GPU-TOLERANCES FECHADO.**
