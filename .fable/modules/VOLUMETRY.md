# MODULE_ID: VOLUMETRY

MODULE_NAME: Volumetria voxel-based e partição hepática

## REAL_PATHS

- dtwin/volumetry.py
- dtwin/stages.py
- profiles/figado.yaml
- tests/test_volumetry.py
- tests/test_engine_finalize.py

STATUS: PRODUCTION

## RESPONSIBILITY

Medir volume e dimensões físicas diretamente das máscaras, calcular métricas de componentes/borda, avaliar qualidade técnica, particionar Couinaud quando disponível e publicar JSON/CSV verificáveis.

## ENTRYPOINTS

- measure_mask
- build_volumetry_manifest
- verify_volumetry_artifacts
- stage7_export_publish

## PUBLIC INTERFACES

VolumetryStructure; measurement_class; measure_mask; build_volumetry_manifest; verify_volumetry_artifacts.

## INPUTS

Máscaras de fígado/lesão/candidato/segmentos/vasos; imagem de referência; quality manifest; configuração e output_dir.

## OUTPUTS

oren-volumetry-manifest-v1; volumetry_manifest.json; CSV; volumes mL, dimensões mm, quality grade e technical range.

## SIDE_EFFECTS

Lê máscaras e qualidade; escreve JSON/CSV atomicamente; inclui referências/hashes no viewer manifest.

## UPSTREAM

PIPELINE_ENGINE_STAGES; SEGMENTATION_RUNTIME; SEGMENTATION_SHADOW_CONTRACT; CANDIDATE_LOCALIZATION; CONFIG_PROFILES.

## DOWNSTREAM

VIEWER_ARTIFACTS_3D; FRONTEND_DESKTOP; WEBXR_QUEST; ARTIFACT_PROVENANCE; aprovação humana.

## ARTIFACTS_READ

Máscaras NIfTI, imagem de referência e segmentation quality manifest.

## ARTIFACTS_WRITTEN

volumetry_manifest.json e CSV com hashes/provenance.

## DEPENDENCIES

SimpleITK; NumPy; scipy/connected components; hashing; filesystem.

## OBSERVED_BEHAVIOR

Volume é voxels positivos × spacing, nunca derivado da malha. A máscara medida já pode ter sido refinada ou substituída por shadow/union. Grade A–D mede consistência técnica, não acurácia anatômica; technical range não é intervalo de confiança clínico.

## SOFTWARE_CONTRACTS

JSON/CSV devem ser atômicos, mutuamente verificáveis e incluir schema/hash. Registros inutilizáveis devem permanecer explícitos, não omitidos.

## GEOMETRIC_CONTRACTS

Unidades são mm e mL; geometry finita e compatível é obrigatória; cálculo usa espaçamento físico; partições devem formar exatamente o órgão para serem utilizáveis.

## SCIENTIFIC_CONTRACTS

Máscara-fonte, thresholds de qualidade, classes de medida, partição Couinaud e technical range exigem aprovação científica.

## DOMAIN_POLICIES

automatic_unconfirmed_candidate deve permanecer distinguível de lesão manual/confirmada. Volumetria requer revisão da máscara; não constitui recomendação clínica.

## KNOWN_FAILURE_MODES

Máscara vazia; geometria não finita/incompatível; partição Couinaud incompleta; CSV/JSON divergentes; quality manifest ausente.

## SILENT_FAILURE_MODES

Medir máscara pós-processada não aprovada; interpretar grade A como validade anatômica; publicar segmentos marcados unusable; unidade/reference grid erradas.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; OUT_OF_AUTHORITY para segurança/uso clínico.

## HUMAN_GATES

HG-03 para geometria; HG-05 para máscara-fonte; HG-08 para grades/thresholds; HG-10 para relação com 3D; HG-12 para claim clínico.

## EXISTING_TESTS

tests/test_volumetry.py; tests/test_engine_finalize.py; integração em tests/test_webapp.py e tests/test_viewer_artifacts.py.

## TEST_GAPS

Phantoms anisotrópicos/rotacionados; approval-before-measurement; impacto de cada pós-processo; partição Couinaud fail-closed end-to-end; tolerância entre ferramentas de referência.

## REQUIRED_TEST_TYPES

UNIT; CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; MUTATION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MEDICAL_GEOMETRY.md; .fable/references/STATISTICS.md; profiles/figado.yaml; docs/230_VOLYRCS_ARQUITETURA_DO_PRODUTO.md.

## OPEN_QUESTIONS

Qual máscara aprovada é autoritativa para cada medida? Quem assina a revisão? Segmentos Couinaud reprovados devem ser omitidos ou apenas marcados?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar máscara-fonte, unidade, fórmula, quality grade, technical range, classes, partição ou gate Couinaud sem HG-03/HG-05/HG-08 e validação humana.

