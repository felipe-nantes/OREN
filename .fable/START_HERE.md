# Fable Engineering Pack — comece aqui

## Finalidade

Este pacote transforma uma solicitação futura em trabalho delimitado, repository-aware e auditável. Ele não certifica a correção científica do ARGOS/OREN e não autoriza uso clínico. O snapshot documentado é o commit `9683eaa796d01e946597f3fe1351556aa8fcb141` em 2026-08-17.

## Fontes e precedência

- `SOURCE_A`: repositório atual — autoridade sobre o que existe e o comportamento implementado.
- `SOURCE_B`: manuscrito integrado — metodologia declarada e decisões explicitamente congeladas.
- `SOURCE_C`: relatório de pesquisa de auditoria — método recomendado de contracts-before-refactoring.
- `SOURCE_D`: README, planos, resultados e decisões — evidência auxiliar, nunca substituto automático de A–C.

Use a hierarquia L1–L6 de [EVIDENCE_HIERARCHY.md](EVIDENCE_HIERARCHY.md). Mantenha separadas as categorias `OBSERVED_BEHAVIOR`, `SOFTWARE_CONTRACT`, `GEOMETRIC_CONTRACT`, `SCIENTIFIC_CONTRACT`, `DOMAIN_POLICY` e `CLINICAL_CLAIM`.

## Início de toda task

1. Leia `CLAUDE.md`, este arquivo, [TASK_PROTOCOL.md](TASK_PROTOCOL.md), [ROUTER.md](ROUTER.md) e [CURRENT_STATE.md](CURRENT_STATE.md).
2. Gere um `TASK_CARD` usando [templates/TASK_CARD.md](templates/TASK_CARD.md).
3. Calcule rotas primárias e transitivas; abra somente as route/module cards indicadas.
4. Classifique risco e autoridade antes de editar.
5. Se existir qualquer possibilidade científica ou geométrica, leia [SCIENTIFIC_CONTRACTS.yaml](SCIENTIFIC_CONTRACTS.yaml) e [HUMAN_GATES.md](HUMAN_GATES.md).
6. Estabeleça baseline e os testes que discriminam o contrato antes do patch.

## Contexto mínimo suficiente

Sempre carregue os cinco documentos do passo 1. Depois carregue apenas:

- rotas ativadas e suas rotas transitivas;
- module cards dos paths tocados e consumidores downstream;
- contratos citados;
- referências pedidas pela rota;
- plano de fase quando a task pertencer à auditoria longa.

Não carregue automaticamente os 247 arquivos sob `docs/`, os 307 scripts sob `tools/`, os 258 arquivos de teste ou artefatos locais. Não abra dados médicos, labels protegidos ou máscaras de lesão sem necessidade e autoridade explícitas.

## Retomar uma auditoria

Leia [CURRENT_STATE.md](CURRENT_STATE.md), o último `SESSION_HANDOFF`, a fase em [LONG_PLAN.md](LONG_PLAN.md) e decisões humanas pendentes. Confirme commit, dirty state e validade do baseline; não presuma que a sessão anterior terminou corretamente.

## Evidências e término

Use [EVIDENCE_PACKAGE_SCHEMA.md](EVIDENCE_PACKAGE_SCHEMA.md). Uma task só é `DONE` quando rota, risco, contratos, baseline, testes aplicáveis, aprovação, regressões, evidência e estado estiverem completos. Se não puder avançar, use [templates/STOP_REPORT.md](templates/STOP_REPORT.md).

## Navegação rápida

- Trabalho local: [ROUTER.md](ROUTER.md)
- Auditoria cumulativa: [LONG_PLAN.md](LONG_PLAN.md)
- Autoridade: [RISK_AUTHORITY_MATRIX.md](RISK_AUTHORITY_MATRIX.md)
- Aprovações: [HUMAN_GATES.md](HUMAN_GATES.md)
- Arquitetura real: [SYSTEM_MAP.md](SYSTEM_MAP.md)
- Módulos: [modules/INDEX.md](modules/INDEX.md)
- Referências: [references/INDEX.md](references/INDEX.md)
- Validação do pack: [PACK_VALIDATION.md](PACK_VALIDATION.md)
- Fallback compacto: [FABLE_MASTER_BUNDLE.md](FABLE_MASTER_BUNDLE.md)
