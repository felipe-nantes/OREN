ID: REF-TESTING-001

TITLE: Layered testing for legacy scientific software

SOURCE:
- pytest, Hypothesis, coverage.py, pytest-mock, pytest-benchmark, mutmut, and Cosmic Ray official/project documentation.
- Michael Feathers, Working Effectively with Legacy Code.
- Martin Fowler, Refactoring.
- MuTAP and TestPilot primary research papers.

URL:
- https://docs.pytest.org/en/stable/
- https://hypothesis.readthedocs.io/en/latest/
- https://coverage.readthedocs.io/en/7.14.1/branch.html
- https://pytest-mock.readthedocs.io/en/latest/
- https://pytest-benchmark.readthedocs.io/en/stable/
- https://github.com/boxed/mutmut
- https://cosmic-ray.readthedocs.io/
- https://www.pearson.com/en-us/subject-catalog/p/working-effectively-with-legacy-code/P200000008984
- https://www.martinfowler.com/books/refactoring.html
- https://arxiv.org/abs/2308.16557
- https://arxiv.org/abs/2302.06527

AUTHORITY_LEVEL:
- `OFFICIAL_PRIMARY_DOCUMENTATION` para ferramentas.
- `ENGINEERING_RECOMMENDATION` para Feathers e Fowler.
- `PRIMARY_RESEARCH_PREPRINT` para MuTAP e TestPilot.

VERSION_OR_DATE: Documentações `stable`/páginas de projeto sem versão congelada; registrar versões instaladas. Os papers são identificados pelos arXiv IDs `2308.16557` e `2302.06527`; nenhuma versão adicional é presumida.

TOPICS:
- contracts-before-refactoring;
- characterization e specification tests;
- invariantes e property-based testing;
- integração e fault injection;
- scientific regression;
- branch coverage e mutation testing;
- mocks/spies;
- benchmark.

AFFECTED_ROUTES:
- todos os módulos e pipelines;
- código legado -> characterization -> contrato;
- contrato -> teste adversarial;
- patch -> suíte focal/global -> evidência;
- performance -> benchmark controlado.

KEY_RULES:
- Antes de testar ou alterar, mapear inputs, outputs, efeitos colaterais, contratos e risco.
- Characterization test registra comportamento observado e deve ser marcado; não prova correção.
- Separar `tests/characterization`, `contracts`, `properties`, `integration`, `scientific_regression` e `performance`.
- Cada specification test crítico deve citar um ID de contrato.
- Usar Hypothesis quando houver propriedade geral e sempre conservar o contraexemplo reduzido relevante.
- Usar integração real em geometria, I/O e pipeline; mockar apenas fronteiras caras ou externas.
- Incluir negativos, edge cases, corrupção, interrupção, retry, resume e idempotência.
- Scientific regression deve congelar resultados interpretáveis de fixture mínima versionada, não snapshots gigantes sem semântica.
- Preferir branch coverage a statement-only, mas nunca usar coverage como medida de força dos asserts.
- Executar mutation testing nas condições e cálculos críticos; revisar surviving e equivalent mutants.
- Separar benchmark de correção e evitar limites rígidos em hardware não padronizado.
- Uma mudança semântica por patch; manter testes verdes e reverter quando um contrato for violado.

WHEN_FABLE_SHOULD_READ:
- Antes de escrever testes para código existente.
- Antes de propor qualquer refatoração.
- Ao decidir entre unit, property, integration, regression e benchmark.
- Quando coverage sobe sem aumento aparente da capacidade de detectar defeitos.

LIMITATIONS:
- Testes gerados por LLM não demonstram correção por si só.
- Mutation score pode ser afetado por mutants equivalentes e escopo/configuração.
- Golden masters podem congelar bugs; precisam ser classificados como comportamento observado.
- Livros e papers fundamentam método, mas não substituem contratos normativos e científicos do projeto.
