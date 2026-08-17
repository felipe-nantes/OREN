# Protocolo de sessão

## Ao iniciar

1. Ler `CLAUDE.md`, `START_HERE.md`, `CURRENT_STATE.md` e `LONG_PLAN.md`.
2. Conferir commit, branch e dirty state; separar mudanças pré-existentes.
3. Identificar task ativa ou gerar novo `TASK_ID`.
4. Executar routing e criar `TASK_CARD`.
5. Carregar contexto mínimo e dependências upstream/downstream.
6. Verificar blockers, riscos e decisões humanas pendentes.
7. Confirmar que a ação solicitada está dentro da autoridade.
8. Capturar baseline antes da primeira edição.

## Durante

- Trabalhar em investigação pequena e delimitada.
- Preservar dados/artefatos do usuário e não alterar scientific contracts implicitamente.
- Registrar comandos e descobertas à medida que surgem.
- Uma recusa legítima deve ser registrada; use apenas fallback oficial, nunca jailbreak/obfuscação.

## Ao terminar

1. Completar pacote de evidências.
2. Registrar arquivos analisados/alterados, testes, riscos e decisões.
3. Atualizar `CURRENT_STATE.md` e a fase do `LONG_PLAN.md`.
4. Atualizar mapas/contratos apenas quando a evidência mudou.
5. Produzir `SESSION_HANDOFF` com próximo passo delimitado.
6. Se bloqueado, produzir `STOP_REPORT`, não fingir conclusão.

## Recuperação após interrupção

Revalidar commit, arquivos parciais, hashes, staging e processos. Não confiar em “último comando iniciado”. Somente resultados persistidos e verificados contam como concluídos.

