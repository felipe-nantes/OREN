# MODULE_ID: CONFIG_PROFILES

MODULE_NAME: Perfis e configurações científicas/operacionais

## REAL_PATHS

- profiles/figado.yaml
- configs/segmentation_visualization_v2.yaml
- configs/medgemma_27b.yaml
- configs/medsiglip_liver_zero_shot.yaml
- configs/training/
- configs/benchmark/
- configs/graphrag_neo4j_docker.yaml
- tests/test_core_profile.py

STATUS: PRODUCTION

## RESPONSIBILITY

Centralizar parte dos labels, tasks, modelos, parâmetros de refinamento/malha, segmentação experimental, inferência, treinamento, benchmarks e serviços.

## ENTRYPOINTS

- dtwin.core.load_profile
- loaders específicos de MedGemma, MedSigLIP, datasets, benchmark e GraphRAG

## PUBLIC INTERFACES

profiles/figado.yaml e schemas/contratos YAML/JSON consumidos pelos módulos.

## INPUTS

Arquivos YAML/JSON versionados; overrides de ambiente/CLI quando suportados.

## OUTPUTS

Dicionários/configurações efetivas e hashes incorporados em artefatos/runs.

## SIDE_EFFECTS

Leitura de filesystem; overrides podem mudar runtime; configs acionam modelos, thresholds e paths externos.

## UPSTREAM

Decisões humanas, documentação científica, ambiente e disponibilidade de modelos/dados.

## DOWNSTREAM

Todos os módulos de ingestão, segmentação, painéis, inferência, ML, volumetria, viewer, RAG e Docker.

## ARTIFACTS_READ

YAML/JSON sob profiles/ e configs/.

## ARTIFACTS_WRITTEN

Nenhum pelo módulo declarativo; consumidores gravam config efetiva/hash nos artefatos quando implementado.

## DEPENDENCIES

PyYAML/JSON; loaders específicos; env vars.

## OBSERVED_BEHAVIOR

profiles/figado.yaml fixa TotalSegmentator, anatomias, candidato, refinamento, malha e fidelidade. Thresholds também aparecem em webapp/server.py e dtwin/benchmark, portanto a política não está totalmente centralizada. Muitas configs são experimentais/históricas.

## SOFTWARE_CONTRACTS

Config deve validar schema/tipos/faixas; identidade efetiva deve incluir overrides; path relativo deve resolver de forma determinística; chave desconhecida não deve ser ignorada silenciosamente.

## GEOMETRIC_CONTRACTS

Spacing, raio, tolerâncias, isovalue, resampling e unidades precisam ser explícitos e versionados.

## SCIENTIFIC_CONTRACTS

Valores numéricos ou labels só são contratos quando suportados por fonte/aprovação; presença em YAML é apenas implementação atual.

## DOMAIN_POLICIES

Separar config operacional de decisão científica e indicar status confirmed/unverified/legacy; segredos e PHI nunca entram em configs versionadas.

## KNOWN_FAILURE_MODES

YAML inválido; chave ausente; path externo ausente; tipo/faixa incorreto; config incompatível com modelo.

## SILENT_FAILURE_MODES

Default implícito; override não registrado; config histórica usada como atual; threshold duplicado divergir; chave ignorada.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC para valores semânticos; MEDIUM para paths/infra.

## HUMAN_GATES

HG-01 para contratos; HG-02 a HG-10 conforme chave; HG-11 para paths/secrets; HG-12 para claims.

## EXISTING_TESTS

tests/test_core_profile.py; tests/test_openswisshcc_configs.py; tests/test_openswisshcc_config_variants.py; testes específicos de loaders.

## TEST_GAPS

Schema único; unknown-key rejection; config efetiva completa; detecção de duplicação/drift; compatibilidade cross-module; inventário de thresholds com provenance.

## REQUIRED_TEST_TYPES

CONTRACT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; MUTATION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/CONTRACTS.md; .fable/REPRODUCIBILITY.md; profiles/figado.yaml; configs/segmentation_visualization_v2.yaml.

## OPEN_QUESTIONS

Quais configs são current, frozen, deprecated ou legacy? Qual schema autoritativo? Quais números possuem rationale aprovado?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar labels, tasks, thresholds, modelo/revisão, preprocessing, geometria, folds, métricas ou defaults científicos; não consolidar duplicatas sem provar equivalência.

