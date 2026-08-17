# MODULE_ID: DATASETS_REGISTRY

MODULE_NAME: Schemas, ingestão e registry de datasets

## REAL_PATHS

- dtwin/datasets/schema.py
- dtwin/datasets/registry.py
- dtwin/datasets/ingest.py
- dtwin/datasets/dicom_utils.py
- dtwin/datasets/nifti_utils.py
- dtwin/datasets/curation.py
- dtwin/datasets/liverhccseg_labels.py
- tests/test_dataset_registry.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Carregar configuração de dataset, descobrir casos DICOM/NIfTI, associar anotações, criar IDs/records normalizados e escrever registry JSONL.

## ENTRYPOINTS

- dtwin.datasets.ingest.main
- load_dataset_config
- ingest_dataset_config
- ingest_dicom_dataset
- ingest_nifti_dataset
- write_jsonl

## PUBLIC INTERFACES

DatasetConfig; RegistryRecord; relative_path; funções de ingestão/curadoria e mapeamento LiverHCCSeg.

## INPUTS

YAML de dataset; root local; DICOM/NIfTI; annotations; regras de glob/labels.

## OUTPUTS

RegistryRecord e JSONL de dataset com paths relativos, IDs, modality/labels e provenance.

## SIDE_EFFECTS

Varre filesystem; lê metadados médicos; grava registry; scripts de dataset podem baixar/curar dados.

## UPSTREAM

Filesystem; pydicom; nibabel/SimpleITK; configs de dataset; fontes públicas/privadas.

## DOWNSTREAM

PANELS_REPRESENTATION; MEDSIGLIP_EMBEDDINGS; ML_CLASSIFIERS_SPLITS; BENCHMARK_METRICS_REPORTING; GRAPHRAG_METADATA; EXPERIMENTAL_BENCHMARKS.

## ARTIFACTS_READ

Configs YAML, imagens, DICOM, annotations e label maps.

## ARTIFACTS_WRITTEN

Registry JSONL, manifests de curadoria e downloads quando acionados por scripts.

## DEPENDENCIES

PyYAML; pydicom; pathlib; schemas dataclass; utilitários DICOM/NIfTI.

## OBSERVED_BEHAVIOR

IDs derivam de dataset_id e path relativo. Ingestão associa annotation por globs/config. O registry é infraestrutura de pesquisa, não parte necessária do viewer clínico.

## SOFTWARE_CONTRACTS

Records devem validar schema; paths devem ser relativos/portáveis; IDs únicos/determinísticos; arquivos ausentes e duplicatas devem ser explícitos.

## GEOMETRIC_CONTRACTS

Ingestão não deve normalizar silenciosamente orientação/affine; metadados de geometria relevantes precisam ser preservados ou auditáveis.

## SCIENTIFIC_CONTRACTS

Coorte, inclusão/exclusão, label map, unidade paciente/caso e associação de anotação são contratos científicos.

## DOMAIN_POLICIES

Não incluir PHI no registry; dados privados não entram no pack/Git; ground truth protegido deve ter acesso segregado.

## KNOWN_FAILURE_MODES

Root ausente; config inválida; annotation faltante; duplicata; DICOM ilegível; label desconhecido.

## SILENT_FAILURE_MODES

Mesmo paciente em IDs diferentes; annotation errada por glob; path revelar PHI; exclusão silenciosa; label mapping drift.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-02/HG-11 para DICOM/PHI; HG-06 para coorte/labels; HG-03 para geometria.

## EXISTING_TESTS

tests/test_dataset_registry.py; tests/test_dataset_audit.py; testes específicos de datasets em tests/.

## TEST_GAPS

Deduplicação patient-level; path PHI scanning; annotation ambiguities; registry round-trip/schema migration; coortes com faltantes; affine/orientation audit.

## REQUIRED_TEST_TYPES

CONTRACT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; PRIVACY; ADVERSARIAL.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/PRIVACY_SECURITY.md; .fable/references/DICOM.md; .fable/references/REPRODUCIBILITY.md.

## OPEN_QUESTIONS

Qual identificador representa paciente de forma estável e desidentificada? Quais configurações e coortes estão congeladas? Qual política de dados ausentes?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar IDs, globs, inclusão/exclusão, deduplicação, labels, associação de annotation ou campos de provenance sem HG-06/HG-11 e auditoria completa.
