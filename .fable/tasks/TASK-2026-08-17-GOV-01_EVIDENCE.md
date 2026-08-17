# EVIDENCE PACKAGE — TASK-2026-08-17-GOV-01 (governança: decisões humanas)

```yaml
TASK_ID: TASK-2026-08-17-GOV-01
DATE: 2026-08-17 (America/Sao_Paulo)
BASE_COMMIT: 9683eaa796d01e946597f3fe1351556aa8fcb141
TASK_DESCRIPTION: >
  Sessão de decisões humanas (8 itens) via seleção interativa pelo aprovador
  Felipe Nantes; registro formal em HUMAN_DECISIONS.md e atualização do
  SCIENTIFIC_CONTRACTS.yaml sob HG-01 exercido pelo humano.
ROUTE: [governança do pack; sem rota de código]
MODULES: [cross-cutting]
FILES_ANALYZED: [SCIENTIFIC_CONTRACTS.yaml, HUMAN_GATES.md, CURRENT_STATE.md]
FILES_CHANGED:
  - .fable/HUMAN_DECISIONS.md (novo)
  - .fable/SCIENTIFIC_CONTRACTS.yaml (bloco ratification; GEO-002 escopado; GEO-002/SW-001/DOM-002 status CONFLICT→CONFIRMED com rationale de decisão)
RISK_LEVEL: LOW (registro de decisão; nenhuma semântica de código alterada)
AUTHORITY_LEVEL: HG-01 exercido pelo humano; edições do registro executadas conforme aprovação textual
CONTRACTS_INVOLVED: [ARGOS-SW-001]
SCIENTIFIC_CONTRACTS_INVOLVED: [todos — ratificação; GEO-002/SW-001/DOM-002 resolvidos]
BASELINE: N/A (documental)
BUG_REPRODUCTION: N/A
TESTS_BEFORE: [N/A]
TESTS_ADDED: []
TESTS_AFTER: [N/A]
STATIC_ANALYSIS: NOT_APPLICABLE
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE
PROPERTY_TEST_RESULT: NOT_APPLICABLE
INTEGRATION_RESULT: NOT_APPLICABLE
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE (nenhum valor científico alterado; apenas status/escopo/registro)
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE (nenhum código tocado nesta task)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE (valores 0.80/0.50/hash/de-ID permanecem exatamente como implementados; o que mudou foi o STATUS de decisão)
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Correção do termo "assinado" no manuscrito é pendência editorial externa ao repo.
UNRESOLVED_RISKS:
  - Reconciliação 451/16 por ledger segue pendente (BLOCKER pré-existente, não coberto por estas decisões).
HUMAN_GATE: HG-01 — 4 aprovações formais (HUMAN_DECISIONS.md itens 1-4) + 4 decisões operacionais (itens 5-8)
APPROVAL_STATUS: aprovado por Felipe Nantes (fnantes07@gmail.com), 2026-08-17, sessão interativa
DIFF_SUMMARY: ver FILES_CHANGED; diffs mínimos e citáveis
ROLLBACK: restaurar SCIENTIFIC_CONTRACTS.yaml anterior e remover HUMAN_DECISIONS.md (exigiria nova decisão humana)
FINAL_STATUS: DONE
```
