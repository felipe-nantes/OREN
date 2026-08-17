# MODULE_ID: GRAPHRAG_METADATA

MODULE_NAME: GraphRAG de metadados desidentificados

## REAL_PATHS

- dtwin/graphrag/config.py
- dtwin/graphrag/schema.py
- dtwin/graphrag/ingest_registry.py
- dtwin/graphrag/neo4j_store.py
- dtwin/graphrag/context.py
- dtwin/graphrag/query.py
- configs/graphrag_neo4j_docker.yaml
- tests/test_graphrag_metadata.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Validar records de registry, ingerir metadados permitidos no Neo4j e produzir contexto GraphRAG sem pixels/PHI para consultas de pesquisa.

## ENTRYPOINTS

- dtwin.graphrag.ingest_registry.main
- dtwin.graphrag.query.main
- Neo4jStore
- build_metadata_graphrag_context

## PUBLIC INTERFACES

GraphRagConfig; Neo4jConnectionConfig; load_graphrag_config; validate_registry_record; registry_record_to_graph_params; ingest_records.

## INPUTS

Registry JSONL validado; config Neo4j; query e limites de contexto.

## OUTPUTS

Nós/relações de metadados e contexto textual auditável.

## SIDE_EFFECTS

Conecta/escreve no Neo4j; lê registry; consulta grafo; pode criar índices/constraints.

## UPSTREAM

DATASETS_REGISTRY; configs/graphrag_neo4j_docker.yaml; Neo4j.

## DOWNSTREAM

Ferramentas de pesquisa/consulta; não foi observado no pipeline web principal.

## ARTIFACTS_READ

Registry JSONL e configuração de conexão.

## ARTIFACTS_WRITTEN

Banco Neo4j e saída de contexto/query.

## DEPENDENCIES

neo4j Python driver; PyYAML; DATASETS_REGISTRY.

## OBSERVED_BEHAVIOR

Schema rejeita chaves proibidas e mapeia records a relações permitidas. Uso observado é CLI/testes e perfil Docker offline, não runtime principal.

## SOFTWARE_CONTRACTS

Somente campos allowlisted entram no grafo; ingestão deve ser idempotente; conexão/credenciais não entram em logs/pack; queries devem ser parametrizadas.

## GEOMETRIC_CONTRACTS

Não aplicável para pixels; metadados geométricos resumidos não substituem imagem/referência física.

## SCIENTIFIC_CONTRACTS

Ontologia, relações MIMIC e filtros de contexto podem alterar recuperação e exigem validação quando usados em experimento.

## DOMAIN_POLICIES

Não armazenar PHI, pixels, paths identificáveis ou ground truth não autorizado.

## KNOWN_FAILURE_MODES

Neo4j indisponível; schema inválido; credencial ausente; record proibido; ingest parcial.

## SILENT_FAILURE_MODES

Merge colidir IDs; relação stale; campo identificável escapar da allowlist; query retornar contexto incompleto sem indicação.

## RISK_LEVEL

MEDIUM; HIGH se alterar coorte, labels ou inferência científica.

## HUMAN_GATES

HG-11 para dados/credenciais; HG-06 para labels/coorte; HG-09 se contexto alimentar modelo.

## EXISTING_TESTS

tests/test_graphrag_metadata.py.

## TEST_GAPS

Integração Neo4j real; rollback de ingest parcial; concorrência; schema migration; privacy adversarial; query injection.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; FAULT_INJECTION; SECURITY; PRIVACY.

## RELEVANT_REFERENCES

.fable/PRIVACY_SECURITY.md; .fable/HUMAN_GATES.md; .fable/references/SECURITY_PRIVACY.md; configs/graphrag_neo4j_docker.yaml.

## OPEN_QUESTIONS

O GraphRAG continuará no produto extraído? Quais propriedades/relations são autorizadas e qual retenção do banco?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não ampliar allowlist, alterar IDs/ontologia/relações, armazenar novos campos ou ligar GraphRAG à inferência sem revisão de privacidade e gates pertinentes.

