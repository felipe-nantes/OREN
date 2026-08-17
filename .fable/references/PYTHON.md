ID: REF-PYTHON-001

TITLE: Python language and standard-library behavior

SOURCE:
- Python official documentation: Language Reference and Library Reference.

URL:
- https://docs.python.org/3/reference/
- https://docs.python.org/3/library/

AUTHORITY_LEVEL: `OFFICIAL_PRIMARY_DOCUMENTATION` para a linguagem Python e sua biblioteca padrão.

VERSION_OR_DATE: A versão de produção não é presumida. Ela deve ser obtida de `pyproject.toml`, lockfiles e ambiente executável; consultar a documentação correspondente a essa versão.

TOPICS:
- semântica da linguagem;
- exceções e context managers;
- pathlib, tempfile, hashing e serialização padrão;
- typing;
- concorrência e comportamento dependente de plataforma;
- escrita e substituição de arquivos.

AFFECTED_ROUTES:
- todos os módulos Python;
- I/O -> artefato;
- cache -> persistência;
- pipeline -> tratamento de falha;
- configuração -> runtime.

KEY_RULES:
- Confirmar a versão efetivamente suportada antes de usar sintaxe ou API recente.
- Tornar inputs, outputs, tipos e efeitos colaterais explícitos nas fronteiras críticas.
- Não engolir exceções que mudam o estado científico; falhas devem ser classificadas e rastreadas.
- Escrita atômica, idempotência e integridade são contratos do projeto e precisam de testes por plataforma; não presumir garantias além das documentadas.
- Fechar arquivos e recursos de forma determinística, preferencialmente com context managers.
- Não usar serialização insegura para dados não confiáveis; formato e trust boundary devem ser explícitos.
- Adotar typing gradualmente sem confundir sucesso do type checker com correção de runtime ou científica.
- Evitar dependência implícita de ordem de filesystem, locale, timezone, hash randomization ou detalhes de plataforma.

WHEN_FABLE_SHOULD_READ:
- Antes de introduzir uma API da linguagem/stdlib ou alterar suporte de versão.
- Antes de mudar I/O, serialização, concorrência, tratamento de erro ou atomicidade.
- Ao investigar divergências Windows/Linux/macOS.

LIMITATIONS:
- A documentação Python não define contratos científicos, DICOM ou de bibliotecas de terceiros.
- Compatibilidade real também depende das versões e plataformas declaradas pelo projeto.
- Este cartão não fixa versão do Python nem autoriza atualização de dependências.
