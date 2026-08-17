ID: REF-FABLE-PLATFORM-001

TITLE: Verified platform behavior for Claude Code context and tools

SOURCE:
- Claude Code official documentation: How Claude Code works.
- Claude Code official documentation: Common workflows, Reference files and directories.
- Claude Code official documentation: Memory, including CLAUDE.md imports.
- Claude Code official documentation: Tools reference.

URL:
- https://code.claude.com/docs/en/how-claude-code-works
- https://code.claude.com/docs/en/tutorials
- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/tools-reference

AUTHORITY_LEVEL: `OFFICIAL_PRIMARY_DOCUMENTATION` para o comportamento documentado do Claude Code. Não constitui evidência da existência, identidade ou capacidade de um modelo chamado `Fable 5`.

VERSION_OR_DATE: Documentação oficial online consultada como referência corrente; nenhuma versão de Claude Code ou modelo é presumida. Registrar data de consulta e versão efetivamente usada quando disponível.

TOPICS:
- ciclo gather context -> take action -> verify;
- acesso a arquivos e ferramentas;
- `@path` em prompts;
- imports `@path/to/import` em CLAUDE.md;
- diretórios, múltiplas referências e contexto;
- permissões e revisão humana;
- limites de alegações sobre modelo/plataforma.

AFFECTED_ROUTES:
- operador -> prompt -> contexto;
- `@arquivo` -> conteúdo em contexto;
- `@diretório` -> listagem em contexto;
- CLAUDE.md -> import de referência;
- agente -> ferramentas -> diff/testes -> operador.

KEY_RULES:
- `Fable 5` permanece `NOT_VERIFIED`: não há neste corpus uma fonte oficial verificada que sustente sua existência, retenção, safeguards, fallback ou capacidades.
- Não codificar no engineering pack alegações específicas sobre `Fable 5` até que uma fonte oficial autêntica seja verificada e registrada.
- Em prompts do Claude Code, `@src/file.py` referencia um arquivo; diretório referenciado fornece listagem, não automaticamente todo o conteúdo; caminhos podem ser relativos ou absolutos e múltiplos arquivos podem ser referenciados.
- Em `CLAUDE.md`, `@path/to/import` importa instruções adicionais. Caminho relativo resolve em relação ao arquivo que contém o import; imports podem ser recursivos até o limite documentado pela plataforma.
- Exemplo válido em CLAUDE.md: `Leia @.fable/EVIDENCE_HIERARCHY.md e @.fable/references/INDEX.md antes da auditoria.`
- Referenciar somente os arquivos necessários; não usar `@path` para incluir PHI, segredos, credenciais ou dumps de ambiente.
- O agente deve reunir contexto, agir dentro da autoridade concedida e verificar resultados; acesso a ferramentas não concede autoridade científica ou clínica.
- Revisar diff, testes e pacote de evidências antes de aceitar mudanças de risco médio ou alto.
- Usar somente documentação oficial atual do Claude Code para afirmações operacionais da plataforma.

WHEN_FABLE_SHOULD_READ:
- No início de toda sessão de auditoria assistida.
- Antes de importar cartões por `@path` ou configurar CLAUDE.md.
- Quando alguém fizer afirmação sobre capacidades, retenção, segurança ou fallback do agente/modelo.
- Antes de ampliar permissões ou contexto do agente.

LIMITATIONS:
- A documentação do Claude Code descreve a ferramenta, não valida um modelo denominado `Fable 5`.
- Funcionalidades podem variar por superfície, versão e modo remoto; confirmar a página oficial atual.
- `@path` controla contexto, não desidentifica nem torna seguro o conteúdo.
- Este cartão não substitui política institucional, avaliação de fornecedor ou contrato de tratamento de dados.
