# POST_AUDIT_OPTIMIZATION — ciclo pós-auditoria do ARGOS/OREN

Planejado em 2026-08-20 sobre o AUDITED_BASELINE_V1 (auditoria Fable
Engineering Pack completa: 10/10 fases DONE, baseline 1769 passed / 4 skipped
/ 1 falha ambiental, `origin/main = 9288785`, 18 decisões humanas).

Este diretório é o PLANO do ciclo. Nenhum experimento foi executado na sua
criação; nenhum código, teste, contrato, threshold, fold, label ou
denominador foi alterado.

## Princípio fundamental

**OOF BETTER ≠ SYSTEM BETTER. CODE CLEANER ≠ SCIENTIFICALLY EQUIVALENT.**

Dois objetivos que NUNCA se misturam:
- **A. Qualidade interna** → trilhas `PURE_REFACTOR` e `ROBUSTNESS_FIX`
  (preservação de comportamento comprovada por oracle).
- **B. Melhoria científica** → `SCIENTIFIC_CHANGE` / `CONTROLLED_EXPERIMENT`
  (uma hipótese por experimento, gates humanos, promotion gate).

Se um "refactor" muda OOF, previsões, scores, embeddings, folds,
preprocessing, threshold, labels, representação, população, denominador,
geometria ou comportamento do modelo → **STOP_AND_RECLASSIFY_AS_SCIENTIFIC_CHANGE**.

## Fluxo

```
IDENTIFICAR FRAQUEZAS → FORMULAR HIPÓTESES → TESTAR UMA ALTERAÇÃO POR VEZ
→ PRESERVAR VALIDADE EXPERIMENTAL → PROMOVER APENAS CANDIDATOS DEFENSÁVEIS
```

## Navegação

| Arquivo | Conteúdo |
|---|---|
| `POST_AUDIT_PLAN.md` | plano mestre: fases, política anti-consumo do outer OOF, scoring, effort policy |
| `WEAKNESS_REGISTER.yaml` | inventário integral das fraquezas (fases 00-10) |
| `OOF_IMPROVEMENT_REGISTER.yaml` | hipóteses de OOF com evidência (nunca ideias genéricas) |
| `PURE_REFACTOR_BACKLOG.yaml` | trilha A — behavior preserving |
| `ROBUSTNESS_FIX_BACKLOG.yaml` | trilha B — integridade/confiabilidade |
| `DOMAIN_SHIFT_INVESTIGATION_PLAN.md` | eixo prioritário (SR-007) |
| `CANDIDATE_PROMOTION_GATE.yaml` | checklist obrigatório de promoção |
| `EXPERIMENT_LEDGER.yaml` | todo experimento entra, inclusive negativos |
| `TOP_10_POST_AUDIT_TASKS.md` | ranking das próximas tasks |
| `FIRST_TASK.md` | primeira task recomendada (card + prompt) |
| `plans/OPT_00..OPT_07` | as 8 fases do ciclo |
| `templates/` | schemas de microexperimento, refactor, mudança científica, comparação |

## Autoridade

- `SAFETY_KERNEL.md` (RATIFICADO, item 17) e `HUMAN_GATES.md` prevalecem
  sobre tudo aqui. Nenhum modelo/effort confere autoridade científica:
  threshold, label, coorte, denominador, inclusão/exclusão, folds, política
  de fase/sequência, convenção de coordenadas, revisão de modelo, semântica
  de preprocessing, definição de métrica e regras clinicamente significativas
  exigem decisão humana formal (formato de HUMAN_GATES.md).
- Contratos científicos congelados (SCIENTIFIC_CONTRACTS.yaml) mudam somente
  via HG-01.
- Executor previsto: **Fable 5**; effort por task conforme
  `POST_AUDIT_PLAN.md` §Effort policy (UltraCode nunca é automático).
- `research_only: true` — nada neste ciclo produz claim clínico (HG-12).
