# EVIDENCE — TASK-2026-08-18-PROTO-01 (adoção do protocolo context-efficient)

```yaml
TASK_ID: TASK-2026-08-18-PROTO-01
BASE_COMMIT: 637d9e1
TASK_DESCRIPTION: >
  Executar as 3 autorizações do operador para adoção do protocolo
  context-efficient: (1) redigir SAFETY_KERNEL.md do conteúdo ratificado;
  (2) migrar CURRENT_STATE/ROUTER para YAML canônico; (3) reverter o
  adiamento das ferramentas estáticas.
ROUTE: [TESTS_BUILD_ENVIRONMENT, governança do pack]
RISK_LEVEL: LOW (nenhum código de produção; nenhuma regra normativa NOVA criada)
AUTHORITY_LEVEL: 3 autorizações explícitas do operador (2026-08-18)
FILES_CHANGED:
  - .fable/SAFETY_KERNEL.md (NOVO — consolida ratificado, com hashes das 5 fontes; pendente de revisão do operador)
  - .fable/CURRENT_STATE.yaml (NOVO canônico) + CURRENT_STATE.md (stub)
  - .fable/ROUTER.yaml (NOVO canônico, conteúdo integral) + ROUTER.md (stub)
  - .fable/HUMAN_DECISIONS.md (bloco 4, itens 10-12)
  - .fable/evidence/TOOLING/ruff_baseline_2026-08-18.txt (NOVO)
TOOLING_INSTALADO: [ruff 0.16.3, mypy 2.3.1, ast-grep-cli 0.45.1]
STATIC_ANALYSIS: "baseline ruff: ~900 achados (I001 401, RUF100 108, UP035 89, F401 83...) — capturado, NADA corrigido (fase 07/08)"
CONTEXT_LOADED:
  - ".fable/STOP_CONDITIONS.md (INTEGRAL — fonte do kernel; primeira leitura na sessão)"
  - ".fable/CURRENT_STATE.md (INTEGRAL — migração exige documento inteiro)"
WHY_EACH_FULL_DOCUMENT_WAS_LOADED: "ambas as tasks (kernel e migração) exigem raciocínio de documento inteiro; ROUTER.md e HUMAN_GATES.md já estavam integrais no contexto da sessão — não recarregados"
CONTEXT_EFFICIENCY:
  context_budget: "reconciliação de protocolo: ~2 documentos integrais + verificações determinísticas"
  approximate_retrieved_context: "2 docs integrais (~160 linhas) + 1 ls + 2 baterias de hash/versão"
  full_documents_loaded: 2
  avoidable_context_detected: "nenhum — saída do ruff (~900 linhas potenciais) foi para evidence com só 12 linhas no contexto"
KNOWN_LIMITATIONS:
  - "Serena/Context7 seguem indisponíveis (MCP fora do alcance do agente); substituições declaradas: leitura simbólica dirigida + docs oficiais sob demanda"
  - "SAFETY_KERNEL pendente de revisão do operador (autorizado a redigir, não auto-aprovável)"
  - "Referências textuais a CURRENT_STATE.md/ROUTER.md em documentos antigos apontam para stubs — intencional"
HUMAN_GATE: 3 autorizações registradas (HUMAN_DECISIONS bloco 4)
ROLLBACK: "git checkout dos .md, deletar .yaml/SAFETY_KERNEL, pip uninstall ruff mypy ast-grep-cli"
FINAL_STATUS: DONE (não commitado)
```
