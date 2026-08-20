# EVIDENCE — TASK-2026-08-19-PH08-REF-01 (PHASE_08, wave 1: correções LOW do handoff)

Data: 2026-08-19 · Executor: agente · Autorização da fase: Felipe Nantes
("commit e push, depois inicie a PHASE_08"). Baseline: suíte do fechamento da
PHASE_07 (1765 passed / 4 skipped / 1 falha ambiental, run de 2026-08-19).

## RESUMO

4 itens do handoff adversarial corrigidos com diffs mínimos, todos
behavior-preserving no caminho feliz e endurecendo apenas o caminho de falha:
TD-015 (retry + try/finally no persist), TD-007 (try/finally no _atomic_text),
narrowing de tipo em robustness (mypy zerado no módulo) e 7×B023 (ruff
zerado). 3 testes novos + 1 teste fortalecido; verificação estática e
targeted verde; suíte completa como portão da wave.

## Diffs de produção (6 arquivos, todos LOW)

1. `webapp/server.py::_persist_completed_job_state` (TD-015): replace com
   retry 5× e backoff (0,05s·n) sob PermissionError; temporário limpo em
   try/finally. Falha terminal continua estourando para `_set` (que loga) —
   semântica do chamador preservada; a janela de restore sem estado exige
   agora 5 negações consecutivas em ~0,5s em vez de 1.
2. `dtwin/benchmark/reporting.py::_atomic_text` (TD-007): try/finally; iguala
   o contrato dos 3 helpers atômicos canônicos (SW-ATOMIC-01).
3. `dtwin/learning/robustness.py:226-239`: walrus nos set-comprehensions de
   subtipos. **Correção de entendimento (OBSERVED)**: o filtro por truthiness
   JÁ excluía None/vazio em runtime — o "TypeError latente" da wave 1 da
   PHASE_07 era INFERRED e estava errado; o braço sempre foi seguro. A mudança
   é clareza de tipo (mypy narrowing), com semântica idêntica elemento a
   elemento (mesmo filtro, mesmo set).
4. `openswisshcc_multisequence_audit.py` / `_geometry.py` /
   `run_raw_phase_equivalence_benchmark.py` (7×B023): variáveis de loop
   vinculadas por default (keyword-only) em `resolve`/`segment`/lambda.
   Invocação intra-iteração já provada na PHASE_07 ⇒ comportamento idêntico;
   agora também idêntico sob refactor futuro para execução adiada.

## Testes

- NOVOS (3): `test_persist_reexecuta_replace_sob_permission_error_e_limpa_tmp`
  (retry exercitado de verdade: 2 falhas simuladas → sucesso, zero tmp),
  `test_persist_estoura_apos_esgotar_retries_sem_vazar_tmp` (contenção
  permanente → PermissionError propagado, zero tmp),
  `test_atomic_text_nao_vaza_temporario_em_falha` (TD-007).
- FORTALECIDO (1): `test_atualizacoes_concorrentes_de_job_nao_se_perdem` — o
  print observacional de temporários vazados virou `assert == []` (a
  caracterização do defeito virou guarda de regressão da correção).

## Verificação (OBSERVED)

- ruff (F821,F811,F702,B002,B006,B008,B015,B023,B031,B032,PLE sobre
  dtwin/webapp/tools/tests): **All checks passed** (era 7×B023).
- mypy `dtwin/learning/robustness.py`: **0 achados no módulo** (eram 2;
  os 21 restantes do run são de outros módulos, baseline conhecido).
- py_compile dos 3 scripts one-shot: OK.
- Targeted (boundary + reporting + robustness + subtype + loaders):
  **37 passed**.
- Suíte completa (portão): **1768 passed / 4 skipped / 1 failed ambiental**
  (test_environment_report_accepts_free_gpu, pré-existente) em 2m58s —
  +3 testes vs baseline, zero regressões.

## Classificação de evidência

- OBSERVED: saídas ruff/mypy/pytest acima; retry exercitado com contador.
- SOURCE_SUPPORTED: preservação de semântica dos 4 diffs (leitura dos sítios
  + invocação intra-iteração provada na PHASE_07).
- INFERRED: nada material.
- CORREÇÃO DE REGISTRO: o item 3 corrige uma inferência errada da PHASE_07
  (honestidade epistêmica > narrativa de "bug corrigido").

## CONTEXT_EFFICIENCY

- Alvos localizados por grep no registro de débito (TD-015 tinha
  linha/arquivo/candidato de correção registrados — o registro pagou).
- Releitura simbólica apenas dos 6 sítios editados; teste de contenção
  existente reaproveitado como guarda (1 assert trocado, não um teste novo).
- Suíte completa 1× em background como portão; verificações rápidas
  (ruff/mypy/py_compile/targeted) antes, para falhar barato.

## Proibições respeitadas

Nenhuma semântica científica tocada; nenhum teste enfraquecido (1 fortalecido);
nenhum commit/push (aguarda solicitação).
