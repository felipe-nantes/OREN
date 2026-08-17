# MODULE_ID: CANDIDATE_LOCALIZATION

MODULE_NAME: Localização automática de região candidata de lesão

## REAL_PATHS

- dtwin/candidate_region.py
- dtwin/candidate_subprocess.py
- dtwin/candidate_worker.py
- profiles/figado.yaml
- configs/segmentation_visualization_v2.yaml
- tests/test_candidate_region.py
- tests/test_candidate_subprocess.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Executar segmentador de liver_lesions_mr, validar geometria, filtrar/recortar o resultado ao fígado e persistir uma região candidata explicitamente não confirmada.

## ENTRYPOINTS

- generate_candidate_region
- validate_and_store_candidate
- candidate subprocess/worker
- webapp.server._localize_candidate

## PUBLIC INTERFACES

generate_candidate_region; validate_and_store_candidate; contrato de subprocesso em dtwin/candidate_subprocess.py.

## INPUTS

Volume de referência; máscara hepática; decisão upstream; profile/config; modelo MRSegmentator/TotalSegmentator compatível.

## OUTPUTS

mask_candidate e candidate_manifest com hashes, volume, componentes, overlap e provenance.

## SIDE_EFFECTS

Invoca processo/modelo externo; grava máscara/manifesto; remove temporários; pode alimentar union/refinamento/viewer.

## UPSTREAM

DICOM_MULTIPHASE_INGEST; SEGMENTATION_RUNTIME; ML_CLASSIFIERS_SPLITS no fluxo web atual; CONFIG_PROFILES.

## DOWNSTREAM

SEGMENTATION_SHADOW_CONTRACT; PIPELINE_ENGINE_STAGES; VOLUMETRY; VIEWER_ARTIFACTS_3D.

## ARTIFACTS_READ

Volume do caso, máscara hepática, decisão de classificação e configuração.

## ARTIFACTS_WRITTEN

Máscara candidata NIfTI e candidate_manifest.json.

## DEPENDENCIES

SimpleITK; NumPy; subprocess; MRSegmentator/TotalSegmentator liver_lesions_mr; CORE_IO_GEOMETRY.

## OBSERVED_BEHAVIOR

No webapp, a solicitação ocorre apenas quando a classificação anterior é positiva/subtipada. A máscara é limitada ao fígado e rotulada automatic_unconfirmed_candidate/research-only. Remover classificação elimina o gatilho atual, embora o segmentador possa ser chamado por interface própria.

## SOFTWARE_CONTRACTS

Saída deve ser não vazia ou falhar explicitamente, conter apenas labels permitidos, ter hash/manifesto atômico e nunca ser apresentada como máscara confirmada.

## GEOMETRIC_CONTRACTS

Volume, fígado e candidato devem coincidir em size, origin, spacing e direction. Recorte/filtro deve manter reference grid e registrar perda.

## SCIENTIFIC_CONTRACTS

Modelo/revisão, gatilho upstream, clipping ao fígado, componentes e thresholds são decisões científicas ainda não confirmadas para uso clínico.

## DOMAIN_POLICIES

Candidato automático não equivale a lesão verdadeira, diagnóstico nem anotação; requer revisão humana antes de uso quantitativo.

## KNOWN_FAILURE_MODES

Modelo ausente; candidato vazio; geometria incompatível; máscara hepática vazia; subprocesso falhar; múltiplos componentes inesperados.

## SILENT_FAILURE_MODES

Classificador falso-negativo impedir execução; clipping remover lesão por erro hepático; candidato plausível ser tratado como confirmado; versão do modelo mudar.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; OUT_OF_AUTHORITY para confirmação/diagnóstico.

## HUMAN_GATES

HG-05 para máscara/postprocess; HG-06 para gatilho/labels; HG-08 para thresholds; HG-09 para modelo; HG-12 para interpretação clínica.

## EXISTING_TESTS

tests/test_candidate_region.py; tests/test_candidate_subprocess.py; integração em tests/test_webapp.py e tests/test_engine_finalize.py.

## TEST_GAPS

Validação externa lesion-level; sensibilidade quando fígado está subsegmentado; device/model agreement; candidate review workflow; erro de classificação upstream; direction divergente.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; ADVERSARIAL; PERFORMANCE.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MEDICAL_GEOMETRY.md; profiles/figado.yaml; configs/segmentation_visualization_v2.yaml; docs/221_VOLUMETRIA_ADAPTATIVA_E_VISUALIZADOR_CONCLUIDOS.md.

## OPEN_QUESTIONS

Qual método independente substituirá o gatilho de classificação? A máscara de lesão será segmentação, localização ou candidato? Quem aprova/corrige antes da volumetria?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não trocar modelo/gatilho, remover o rótulo unconfirmed, alterar clipping/componentes/thresholds nem alimentar volumetria clínica sem validação e aprovação humana explícita.

