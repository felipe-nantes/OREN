# Module cards — ARGOS/OREN

Este índice roteia tarefas para módulos reais do commit inspecionado. STATUS descreve maturidade operacional do código; PRODUCTION significa caminho ativo do runtime, não validação clínica. Qualquer claim clínico permanece fora da autoridade do agente.

| MODULE_ID | STATUS | RISK_LEVEL | ESCOPO |
|---|---|---|---|
| [CORE_IO_GEOMETRY](CORE_IO_GEOMETRY.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | I/O médico, geometria e layout Case |
| [PIPELINE_ENGINE_STAGES](PIPELINE_ENGINE_STAGES.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | CLI e stages 1–7 |
| [DICOM_MULTIPHASE_INGEST](DICOM_MULTIPHASE_INGEST.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | seleção de séries/fases e harmonização |
| [SEGMENTATION_RUNTIME](SEGMENTATION_RUNTIME.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | TotalSegmentator e subprocessos |
| [SEGMENTATION_SHADOW_CONTRACT](SEGMENTATION_SHADOW_CONTRACT.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | máscara secundária, fusão e promoção |
| [PANELS_REPRESENTATION](PANELS_REPRESENTATION.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | representação visual para inferência |
| [MEDGEMMA_INFERENCE](MEDGEMMA_INFERENCE.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | cliente, screening e gateway MedGemma |
| [MEDSIGLIP_EMBEDDINGS](MEDSIGLIP_EMBEDDINGS.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | embeddings e identidade de representação |
| [ML_CLASSIFIERS_SPLITS](ML_CLASSIFIERS_SPLITS.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | classificadores, folds e OOF |
| [BENCHMARK_METRICS_REPORTING](BENCHMARK_METRICS_REPORTING.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | métricas, denominadores e relatórios |
| [DATASETS_REGISTRY](DATASETS_REGISTRY.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | schemas, ingestão e registry |
| [RAG_TEXT](RAG_TEXT.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | corpus BM25 e grounding |
| [GRAPHRAG_METADATA](GRAPHRAG_METADATA.md) | EXPERIMENTAL | MEDIUM | metadados desidentificados em Neo4j |
| [CANDIDATE_LOCALIZATION](CANDIDATE_LOCALIZATION.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | região candidata não confirmada |
| [VOLUMETRY](VOLUMETRY.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | volumes derivados de máscaras |
| [VIEWER_ARTIFACTS_3D](VIEWER_ARTIFACTS_3D.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | malhas, PNGs e manifestos |
| [WEBAPP_API_ORCHESTRATION](WEBAPP_API_ORCHESTRATION.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | API, jobs e fluxo principal |
| [FRONTEND_DESKTOP](FRONTEND_DESKTOP.md) | PRODUCTION | MEDIUM | upload, status e viewer desktop |
| [WEBXR_QUEST](WEBXR_QUEST.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | WebXR, sessões Quest e LOD |
| [DOCKER_LAUNCHERS](DOCKER_LAUNCHERS.md) | PRODUCTION | MEDIUM | imagens, Compose, TLS e launchers |
| [CONFIG_PROFILES](CONFIG_PROFILES.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | perfis, modelos e thresholds |
| [ARTIFACT_PROVENANCE](ARTIFACT_PROVENANCE.md) | PRODUCTION | HIGH_SCIENTIFIC_GEOMETRIC | hashes, manifestos e restauração |
| [TEST_SUITE](TEST_SUITE.md) | PRODUCTION | MEDIUM | pytest, CI e verificadores |
| [EXPERIMENTAL_BENCHMARKS](EXPERIMENTAL_BENCHMARKS.md) | EXPERIMENTAL | HIGH_SCIENTIFIC_GEOMETRIC | coortes e estudos históricos |

Regras de composição:

- Carregar apenas os cards necessários e suas dependências transitivas.
- O risco final é o maior risco entre os módulos envolvidos.
- Consultar .fable/HUMAN_GATES.md antes de qualquer alteração HIGH ou OUT_OF_AUTHORITY.
- ARRAY não substitui geometria médica: origin, spacing, direction, affine, convenção e grade de referência continuam obrigatórios.

