# MODULE_ID: MEDSIGLIP_EMBEDDINGS

MODULE_NAME: Extração e verificação de embeddings MedSigLIP

## REAL_PATHS

- dtwin/learning/medsiglip_embeddings.py
- tools/extract_medsiglip_embeddings.py
- tools/rebind_medsiglip_embeddings.py
- tools/verify_medsiglip_device_agreement.py
- configs/training/medsiglip_frozen_v1.yaml
- tests/test_learning_medsiglip_embeddings.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Carregar backend/config MedSigLIP, extrair vetores de imagens label-blind, persistir NPY/JSONL/manifests e verificar integridade e identidade.

## ENTRYPOINTS

- extract_embeddings
- verify_embeddings
- HuggingFaceMedSigLIPBackend
- tools/extract_medsiglip_embeddings.py

## PUBLIC INTERFACES

ImageEmbeddingBackend; load_embedding_config; HuggingFaceMedSigLIPBackend; extract_embeddings; verify_embeddings.

## INPUTS

Dataset candidato e manifestos; painéis/imagens; config de modelo/preprocessing/device; checkpoint opcional.

## OUTPUTS

Vetores float32 NPY, records JSONL, checkpoints, embedding_manifest.json e embedding_signature.

## SIDE_EFFECTS

Carrega pesos/GPU; cria staging/output; escreve arrays e registros; fsync de checkpoints; pode retomar extração.

## UPSTREAM

PANELS_REPRESENTATION; DATASETS_REGISTRY; CONFIG_PROFILES; Hugging Face/Transformers.

## DOWNSTREAM

ML_CLASSIFIERS_SPLITS; BENCHMARK_METRICS_REPORTING; ARTIFACT_PROVENANCE.

## ARTIFACTS_READ

Dataset manifest/records; imagens; config; pesos/cache; checkpoint prévio.

## ARTIFACTS_WRITTEN

NPY por painel/caso; JSONL; checkpoint; manifesto e assinatura de embeddings.

## DEPENDENCIES

NumPy; PyTorch; Transformers; hashing canônico; filesystem.

## OBSERVED_BEHAVIOR

Usa vision pooler output, output float32 e registra hashes de artefatos/model trace. Rejeita dataset candidato que leu ground truth ou lesion masks. Identidade depende de manifesto/config/modelo.

## SOFTWARE_CONTRACTS

Vetores devem ser finitos, ter shape/dtype esperados e corresponder a source hash. Resume/cache deve rejeitar registros truncados, corrompidos ou de identidade incompatível.

## GEOMETRIC_CONTRACTS

O embedding herda a representação dos painéis; qualquer mudança de orientação/slices/canais deve invalidar identidade e benchmark.

## SCIENTIFIC_CONTRACTS

Modelo/revisão, pooling, dimensão, normalização, preprocessing e tolerância entre devices são parte da representação científica.

## DOMAIN_POLICIES

Extração deve permanecer label-blind; ground truth não pode entrar no caminho de representação.

## KNOWN_FAILURE_MODES

OOM; imagem ausente; vetor não finito; shape divergente; checkpoint truncado; hash de dataset alterado.

## SILENT_FAILURE_MODES

Cache stale; modelo/revisão não pinados; painel alterado com chave reutilizada; device drift; reorder entre records e vetores.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-06 para leakage; HG-09 para modelo/representação; HG-07 se downstream de treinamento mudar.

## EXISTING_TESTS

tests/test_learning_medsiglip_embeddings.py; tests/test_filter_embedding_dataset.py; tests/test_verify_medsiglip_phase13.py.

## TEST_GAPS

Corrupção/truncamento real; concorrência; device agreement com pesos congelados; invalidation por toda dimensão de preprocessing; property tests de ordem/serialização.

## REQUIRED_TEST_TYPES

CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; FAULT_INJECTION; PERFORMANCE.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/PYTORCH.md; .fable/references/REPRODUCIBILITY.md; configs/training/medsiglip_frozen_v1.yaml.

## OPEN_QUESTIONS

Qual model revision é autoritativa? Qual tolerância device agreement está aprovada? O cache inclui toda a identidade de preprocessing?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar modelo, pooling, dimensão, dtype, normalização, preprocessing, chave de cache ou tolerância sem HG-09, invalidation explícita e regressão.

