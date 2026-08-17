# Validação do ARGOS/OREN Fable Engineering Pack

VALIDATED_ON: 2026-08-17 America/Sao_Paulo  
BASE_COMMIT: `9683eaa796d01e946597f3fe1351556aa8fcb141`  
PACK_SCHEMA: `argos-fable-engineering-pack-v1`  
VALIDATION_SCOPE: estrutura, schemas, paths, links, routing, contratos, contradições documentais e isolamento das mudanças.  
PACK_VALIDATION_RESULT: `PASS_WITH_DOCUMENTED_BASELINE_BLOCKERS`

## Estrutura

- 27/27 documentos top-level obrigatórios em `.fable/` presentes.
- `CLAUDE.md`: 12/12 seções obrigatórias e 5/5 imports `@path` presentes; 46 linhas.
- 35 route cards; 12/12 campos obrigatórios em cada card.
- 24 module cards + índice; 30/30 campos em cada card; 13 `PRODUCTION` e 11 `EXPERIMENTAL`.
- 11 reference cards + índice; 11/11 campos em cada card.
- 11/11 fases persistentes, de `PHASE_00_FREEZE` a `PHASE_10_CONSOLIDATION`, com todos os campos e status permitido.
- 9/9 templates obrigatórios presentes.
- 12/12 human gates; cada um possui `TRIGGER`, `WHAT_FABLE_MAY_DO`, `WHAT_FABLE_MAY_NOT_DO`, `EVIDENCE_REQUIRED`, `APPROVAL_FORMAT` e `POST_APPROVAL_TESTS`.
- `CURRENT_STATE.md` contém todos os 12 campos de continuidade exigidos.
- `TASK_CARD` contém 35/35 campos; o schema de evidências contém 36/36 campos.

## Paths, links e referências

- 189 `REAL_PATHS` declarados nos module cards: todos existem no snapshot.
- Todos os paths literais declarados em `REAL_PATHS` das routes foram resolvidos; nenhum path abreviado permaneceu.
- 80 links Markdown locais verificados; nenhum link local quebrado.
- 187 referências de repositório em `SCIENTIFIC_CONTRACTS.yaml` verificadas entre `source_location`, `affected_files` e `tests_that_protect_it`; nenhuma não resolvida.
- Os 38 conceitos de routing obrigatórios estão presentes e mapeados para 35 rotas canônicas, com aliases explícitos para rotas combinadas.
- `Fable 5` permanece `NOT_VERIFIED`; o comportamento operacional persistido usa somente documentação oficial verificável do Claude Code.

## Scientific governance

- `SCIENTIFIC_CONTRACTS.yaml` carrega com PyYAML 6.0.3.
- 20 contratos com IDs únicos e schema completo: 17 `CONFIRMED`, 3 `CONFLICT`.
- Categorias: 9 `SCIENTIFIC_CONTRACT`, 5 `DOMAIN_POLICY`, 4 `GEOMETRIC_CONTRACT`, 1 `SOFTWARE_CONTRACT` e 1 limite de `CLINICAL_CLAIM`.
- 37 itens em `MANUSCRIPT_VS_CODE.md`: 22 claims centrais + 15 ambiguidades/contradições prioritárias.
- Status dos 37 itens: 11 `MATCH`, 16 `PARTIAL_MATCH`, 4 `CONFLICT`, 3 `CODE_ONLY`, 2 `MANUSCRIPT_ONLY`, 1 `UNVERIFIED`.
- 27 riscos no registro científico, todos separados de dívida técnica e ligados a route, fase e human gate.
- Os conflitos de contrato permanecem documentados; nenhum foi “resolvido” alterando código, threshold, coorte, geometria, privacidade ou metodologia.

## Router

- Tasks A–L simuladas sem alterar código.
- Cada uma registra `ROUTE`, `FILES/MODULES EXPECTED`, `CONTEXT`, `RISK`, `AUTHORITY`, `TESTS`, `HUMAN GATE` e `EXPECTED ACTION`.
- Resultado: `12/12 PASS`.
- Requests multimódulo, pedidos de threshold, possível leakage, paciente individual, stale cache, geometria, 3D e arquitetura promovem risco/stop corretamente.

## Baseline observado

- HEAD/branch/dirty state, Python, hardware, CUDA/driver, Docker CLI/Compose, CI e tool availability registrados.
- `.venv-win\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider`: 1.610 testes coletados em 18,09 s, quatro warnings.
- Nenhum teste funcional foi executado nesta missão; resultado global permanece `NOT_RUN`.
- Docker daemon estava indisponível; baseline containerizado permanece pendente.
- Coverage.py, Hypothesis, Ruff, mypy, pip-audit, mutmut e pytest-benchmark não foram encontrados e não foram instalados.

## Contradiction checks

- Nenhuma route declara LOW de forma incondicional para módulo científico/geométrico HIGH.
- `CONTRACTS.md` aponta o YAML como fonte operacional e não sobrescreve os três conflitos.
- `LONG_PLAN.md` não permite refactor antes do baseline/contratos/testes aplicáveis.
- `CLAUDE.md` importa `HUMAN_GATES.md` e contém stop rule explícita.
- Module paths, route paths, contract paths e links locais foram resolvidos.
- Nenhum candidato foi promovido a `CONFIRMED_DEAD`; o único `PROBABLY_DEAD` exige prova de reachability antes de remoção.

## Isolamento da missão

- Nenhum arquivo-fonte, teste, config funcional, threshold, label, dataset ou comportamento do ARGOS/OREN foi alterado.
- Arquivos criados/modificados pela missão: somente `CLAUDE.md` e `.fable/`.
- Dois arquivos já não rastreados antes da missão continuam intocados: `docs/186_RELATORIO_CIENTIFICO_CONSOLIDADO_ARGOS.zip` e `viewer/assets/materials/liver_realistic_v1_source.png`.
- Nenhum commit ou push foi realizado.

## Blockers que não invalidam o pack

- A Phase 00 ainda deve executar a suíte completa e estabelecer baselines de ambiente/container/performance.
- Dados protegidos e artefatos OOF necessários para reproduzir os números centrais do manuscrito não estão neste checkout.
- Três conflitos científicos/operacionais exigem decisão humana: gates geométricos entre fases, semântica de “bundle assinado” e política uniforme de desidentificação/revisão de PHI.
- O pack habilita trabalho auditado; não certifica validade clínica, segurança, anatomia verdadeira nem reprodutibilidade integral dos resultados publicados.

READY_FOR_FABLE: `YES` — pronto para iniciar a Phase 00 com safe autonomy; não pronto para uso clínico nem para mudanças científicas autônomas.
