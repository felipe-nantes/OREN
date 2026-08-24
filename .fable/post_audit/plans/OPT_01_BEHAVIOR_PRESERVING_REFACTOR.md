# OPT_01 — BEHAVIOR_PRESERVING_REFACTOR

Objetivo: melhorar estrutura/testabilidade SEM alterar ciência.

Backlog: PURE_REFACTOR_BACKLOG.yaml (REF-01..REF-06). Template obrigatório:
templates/PURE_REFACTOR.yaml, um por refactor.

Regras:
- behavioral_oracle definido ANTES do primeiro edit;
- suíte completa + regressões + hashes de artefato por refactor;
- tolerâncias ratificadas (item 9) são o limite numérico;
- se QUALQUER saída científica mudar: STOP_AND_RECLASSIFY_AS_SCIENTIFIC_CHANGE;
- excluídos da trilha: W-004 (tolerâncias — HG-03) e W-002 (stages — plano gated próprio).

Ordem recomendada: REF-01 (atomic, oracle forte) -> REF-02 (mypy triage) ->
REF-04/REF-05 (docs/smoke) -> REF-06 (configs, com verificação de pinagem) ->
REF-03 (server.py, design UltraCode primeiro).

Critério de saída: refactors aplicados com oracles verdes e zero mudança
científica; ou adiados com registro.
