# MODULE_ID: SEGMENTATION_RUNTIME

MODULE_NAME: Runtime de segmentação de órgão e anatomias

## REAL_PATHS

- dtwin/stages.py
- dtwin/segmentation_subprocess.py
- dtwin/seg_worker.py
- dtwin/benchmark/lld_mmri_v23_mask_quality.py
- profiles/figado.yaml
- tests/test_segmentation_subprocess.py
- tests/test_engine_prepare.py

STATUS: PRODUCTION

## RESPONSIBILITY

Executar TotalSegmentator total_mr para fígado/anatomias, isolar o processo pesado, preparar ambiente e aplicar gate técnico de plausibilidade com fallback GPU→CPU.

## ENTRYPOINTS

- stage3_segment_organ
- run_segmentation_subprocess
- prepare_totalsegmentator_environment
- webapp.server._segmentar_figado_com_gate

## PUBLIC INTERFACES

run_segmentation_subprocess; segmentation_error; stage3_segment_organ; funções de avaliação/gate em lld_mmri_v23_mask_quality.py.

## INPUTS

Volume/serie venosa; perfil de órgão; device; fast; task/labels do TotalSegmentator.

## OUTPUTS

Máscara de fígado, máscaras anatômicas opcionais, recibo do subprocesso e métricas/gate de plausibilidade.

## SIDE_EFFECTS

Cria workspace temporário; invoca processo/modelo externo; usa GPU/CPU; grava máscaras e manifestos; remove anatomias opcionais inválidas.

## UPSTREAM

CORE_IO_GEOMETRY; DICOM_MULTIPHASE_INGEST; CONFIG_PROFILES; TotalSegmentator; pesos locais.

## DOWNSTREAM

SEGMENTATION_SHADOW_CONTRACT; PANELS_REPRESENTATION; CANDIDATE_LOCALIZATION; PIPELINE_ENGINE_STAGES; VOLUMETRY.

## ARTIFACTS_READ

DICOM/volume de referência; perfil; pesos/cache do segmentador.

## ARTIFACTS_WRITTEN

mask_organ_raw e anatomias; JSON de subprocesso/qualidade; logs temporários.

## DEPENDENCIES

TotalSegmentator; SimpleITK; subprocess; CUDA/CPU; CORE_IO_GEOMETRY.

## OBSERVED_BEHAVIOR

O órgão obrigatório aborta em falha; anatomias opcionais apenas avisam. O webapp tenta GPU e depois CPU e aplica plausibilidade técnica. Os limites observados incluem volume, extensão axial/in-plane e fração do maior componente; isso não certifica anatomia.

## SOFTWARE_CONTRACTS

Subprocesso deve devolver recibo inequívoco, caminho permitido e erro sanitizado; falha não deve promover saída parcial; versão/modelo/device devem ser rastreáveis.

## GEOMETRIC_CONTRACTS

Máscara deve coincidir integralmente com size, origin, spacing e direction da imagem de referência; dtype/labels devem ser esperados; vazio deve falhar.

## SCIENTIFIC_CONTRACTS

Modelo/task, thresholds de plausibilidade e política GPU→CPU não são automaticamente contratos científicos confirmados.

## DOMAIN_POLICIES

TotalSegmentator total_mr e label liver vêm de profiles/figado.yaml; saída é research-only e requer revisão humana.

## KNOWN_FAILURE_MODES

Pesos ausentes; OOM; timeout/processo abortado; máscara vazia; anatomia obrigatória ausente; ambiente CUDA incompatível.

## SILENT_FAILURE_MODES

Máscara plausível porém anatomicamente errada; mudança de versão do modelo; CPU/GPU divergirem; gate técnico ser interpretado como validação clínica.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-05 para modelo/máscara/postprocess; HG-03 para geometria; HG-08 para thresholds; HG-09 para revisão de modelo; HG-12 para claim clínico.

## EXISTING_TESTS

tests/test_segmentation_subprocess.py; tests/test_engine_prepare.py; tests/test_stage1_ingest.py; testes indiretos em tests/test_webapp.py.

## TEST_GAPS

Regressão com coorte aprovada; agreement GPU/CPU; pin/version drift; OOM/timeout; direction divergente; validação anatômica independente; Docker GPU real em CI.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; PERFORMANCE; FAULT_INJECTION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MEDICAL_GEOMETRY.md; .fable/references/PYTORCH.md; profiles/figado.yaml; docs/197_MRSEGMENTATOR_CHAOS20_GPU_RESULTADO.md.

## OPEN_QUESTIONS

Qual versão/peso está congelado para produção? Quais métricas e coortes autorizam promoção? Qual tolerância de device agreement é aceita?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não trocar task/modelo/revisão, labels, thresholds, fallback, postprocess ou geometria de saída sem HG-05/HG-09, baseline e regressão científica.
