# MODULE_ID: SEGMENTATION_SHADOW_CONTRACT

MODULE_NAME: Contrato experimental de shadow mask e fusão protegida

## REAL_PATHS

- dtwin/segmentation_contract.py
- dtwin/segmentation_shadow.py
- configs/segmentation_visualization_v2.yaml
- tests/test_segmentation_contract.py
- tests/test_segmentation_shadow.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Confinar artefatos experimentais, validar geometria/qualidade, decidir execução secundária, fundir máscaras de forma protegida e expor somente máscara de visualização com recibo completo.

## ENTRYPOINTS

- experimental_paths
- validate_visualization_mask
- approved_visualization_mask
- should_run_secondary
- protected_adaptive_fusion
- run_phase_aware_shadow

## PUBLIC INTERFACES

ExperimentalSegmentationPaths; image_geometry; same_geometry; build_native_input_manifest; build_quality_manifest; atomic_write_experimental_json; mask_quality_metrics; mask_agreement.

## INPUTS

Imagem nativa, máscara primária, máscara secundária, fases disponíveis e configs/segmentation_visualization_v2.yaml.

## OUTPUTS

Máscara shadow/union de visualização; manifestos de input/qualidade/seleção; recibo de aprovação técnica.

## SIDE_EFFECTS

Cria árvore experimental protegida; executa segmentador secundário; grava máscara e JSONs atômicos; pode alterar a máscara-fonte usada downstream.

## UPSTREAM

SEGMENTATION_RUNTIME; DICOM_MULTIPHASE_INGEST; CONFIG_PROFILES.

## DOWNSTREAM

PIPELINE_ENGINE_STAGES; VOLUMETRY; VIEWER_ARTIFACTS_3D; ARTIFACT_PROVENANCE.

## ARTIFACTS_READ

Volume de referência, máscaras primária/secundária, fases e configuração.

## ARTIFACTS_WRITTEN

Native input manifest; quality manifest; máscara experimental; recibo safe_complete.

## DEPENDENCIES

SimpleITK; NumPy; CORE_IO_GEOMETRY; segmentador secundário configurado.

## OBSERVED_BEHAVIOR

O caminho está integrado e pode ser default quando disponível, apesar do docstring dizer que não participa da produção. A promoção exige recibo completo; gatilhos e fusão usam thresholds configurados. Toda saída permanece research-only.

## SOFTWARE_CONTRACTS

Artefatos experimentais não podem escapar do diretório permitido; JSON deve ser atômico; aprovação deve falhar fechado se recibo/hash/arquivo estiver incompleto.

## GEOMETRIC_CONTRACTS

Máscaras devem coincidir em size, origin, spacing e direction; fusão deve preservar grade/dtype/labels e registrar fonte.

## SCIENTIFIC_CONTRACTS

Critérios de disparo, escolha de fonte, distâncias e frações de fusão são decisões científicas não alteráveis sem aprovação.

## DOMAIN_POLICIES

Máscara secundária é apenas suporte visual experimental; protected artifacts e política de promoção vêm do YAML.

## KNOWN_FAILURE_MODES

Secundário indisponível; geometria divergente; recibo incompleto; máscara vazia; threshold reprovar; escrita parcial.

## SILENT_FAILURE_MODES

Fusão mudar volume sem revisão; configuração drift; máscara tecnicamente plausível ser tratada como verdade anatômica; fallback consumir artefato stale.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-05 para fusão/pós-processo; HG-03/HG-04 para geometria; HG-08 para thresholds; HG-09 para segmentador secundário.

## EXISTING_TESTS

tests/test_segmentation_contract.py; tests/test_segmentation_shadow.py; integração em tests/test_engine_finalize.py e tests/test_webapp.py.

## TEST_GAPS

Fault injection em recibos; concorrência; drift de config/modelo; impacto volumétrico em coorte aprovada; direção divergente; promoção/rejeição adversarial.

## REQUIRED_TEST_TYPES

CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; FAULT_INJECTION; MUTATION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/CONTRACTS.md; .fable/references/MEDICAL_GEOMETRY.md; configs/segmentation_visualization_v2.yaml; docs/221_VOLUMETRIA_ADAPTATIVA_E_VISUALIZADOR_CONCLUIDOS.md.

## OPEN_QUESTIONS

Qual modelo/versão secundária está aprovado? Quais thresholds têm fonte científica? A máscara promovida pode alimentar volumetria antes de aprovação humana?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar isolamento, gate, thresholds, fonte secundária, fusão, recibo ou precedência de máscara sem autorização e análise before/after volumétrica.
