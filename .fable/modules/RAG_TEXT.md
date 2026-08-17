# MODULE_ID: RAG_TEXT

MODULE_NAME: RAG textual BM25 e grounding

## REAL_PATHS

- dtwin/rag/chunking.py
- dtwin/rag/index.py
- dtwin/rag/retriever.py
- dtwin/rag/grounding.py
- dtwin/rag/dataset_index.py
- tools/build_rag_corpus.py
- tools/build_rag_index.py
- tools/eval_rag_retrieval.py
- tests/test_rag_chunking.py
- tests/test_rag_index.py
- tests/test_rag_sidecar.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Fragmentar corpus permitido, construir/carregar índice BM25, recuperar trechos auditáveis e anexar contexto grounded a prompts de pesquisa.

## ENTRYPOINTS

- build_bm25_index
- load_bm25_index
- search_bm25
- build_rag_context
- persist_rag_context
- append_rag_to_prompt

## PUBLIC INTERFACES

CorpusDocument/CorpusChunk; IndexedChunk; tokenize; chunk_document; validate_chunks; build_rag_prompt_addendum.

## INPUTS

Corpus e manifestos; config RAG; query/query_ids; limites de top-k/tamanho; repo_root.

## OUTPUTS

Índice BM25 JSON, chunks, contexto com sources/hashes e prompt addendum.

## SIDE_EFFECTS

Lê corpus; grava índice/contexto atômico; inclui texto recuperado em prompts MedGemma.

## UPSTREAM

DATASETS_REGISTRY; corpus documental permitido; CONFIG_PROFILES.

## DOWNSTREAM

MEDGEMMA_INFERENCE; EXPERIMENTAL_BENCHMARKS.

## ARTIFACTS_READ

Corpus manifest, chunks, índice e queries de avaliação.

## ARTIFACTS_WRITTEN

Corpus chunked, índice BM25, context JSON e logs de retrieval.

## DEPENDENCIES

Python math/JSON/YAML; hashing; filesystem.

## OBSERVED_BEHAVIOR

Usa BM25 determinístico, valida paths dentro do repo e falha fechado quando índice obrigatório falta. É usado por screening MedGemma e benchmarks específicos.

## SOFTWARE_CONTRACTS

Índice deve corresponder ao corpus/hash/config; paths não podem escapar do repo; contexto deve citar source/chunk e respeitar limites; modo disabled deve ser explícito.

## GEOMETRIC_CONTRACTS

Não aplicável diretamente; referências a geometria não substituem metadados do exame.

## SCIENTIFIC_CONTRACTS

Corpus, chunking, tokenização, top-k e conteúdo inserido no prompt alteram a representação experimental.

## DOMAIN_POLICIES

Não indexar PHI, segredos ou private clinical data; retrieval não transforma texto em verdade clínica.

## KNOWN_FAILURE_MODES

Índice ausente/corrompido; corpus drift; path traversal; query vazia; chunks sem source.

## SILENT_FAILURE_MODES

Índice stale; corpus contém label/ground truth; retrieval muda por configuração; source não correspondente; contexto truncado remove ressalvas.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC quando usado em inferência; MEDIUM isoladamente como indexação.

## HUMAN_GATES

HG-09 para representação/prompt; HG-06 para leakage; HG-11 para conteúdo sensível; HG-12 para claims.

## EXISTING_TESTS

tests/test_rag_chunking.py; tests/test_rag_index.py; tests/test_rag_index_hardening.py; tests/test_rag_sidecar.py; tests/test_rag_retrieval_eval.py.

## TEST_GAPS

Poisoning/prompt injection; PHI scanning; corpus/version drift; recuperação adversarial; avaliação downstream congelada.

## REQUIRED_TEST_TYPES

CONTRACT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; ADVERSARIAL; SECURITY.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/PRIVACY_SECURITY.md; .fable/references/SECURITY_PRIVACY.md; .fable/references/REPRODUCIBILITY.md.

## OPEN_QUESTIONS

Quais fontes são autorizadas? O corpus é label-blind para cada experimento? Qual baseline de retrieval está congelado?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar corpus, chunking, tokenização, ranking, top-k, grounding ou inclusão no prompt sem HG-09, auditoria de leakage/privacidade e regressão.

