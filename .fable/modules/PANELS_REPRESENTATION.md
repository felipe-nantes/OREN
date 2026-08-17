# MODULE_ID: PANELS_REPRESENTATION

MODULE_NAME: Representação visual por painéis

## REAL_PATHS

- dtwin/learning/exam_to_panels.py
- dtwin/medgemma_panel.py
- dtwin/medgemma_panel_full_fov.py
- dtwin/medgemma_panel_liver_enriched.py
- dtwin/medgemma_panel_multiphase.py
- tests/test_medgemma_panel.py
- tests/test_medgemma_panel_full_fov.py
- tests/test_medgemma_panel_liver_enriched.py
- tests/test_medgemma_panel_multiphase.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Converter exames mono/multifásicos em painéis RGB e manifestos label-blind usados por MedGemma, MedSigLIP e revisão visual.

## ENTRYPOINTS

- build_exam_panels
- build_monophase_exam_panels
- renderizadores build_panel dos módulos medgemma_panel*

## PUBLIC INTERFACES

ExamPanelResult; anonymous_manifest_case_id; construtores de painéis full_fov, liver_enriched e multiphase.

## INPUTS

Volumes/fases harmonizadas; máscara de fígado quando exigida pela representação; case_id; configuração de layout/windowing.

## OUTPUTS

PNGs RGB, case_manifest.json e manifesto de painéis com spatial_policy/channel map/hashes.

## SIDE_EFFECTS

Cria diretório de painéis; grava PNG/JSON; anonimiza case_id no manifesto; consome memória para renderização.

## UPSTREAM

DICOM_MULTIPHASE_INGEST; SEGMENTATION_RUNTIME; CONFIG_PROFILES.

## DOWNSTREAM

MEDGEMMA_INFERENCE; MEDSIGLIP_EMBEDDINGS; ML_CLASSIFIERS_SPLITS; WEBAPP_API_ORCHESTRATION; FRONTEND_DESKTOP.

## ARTIFACTS_READ

Volumes NIfTI/fases e, conforme política, máscara de órgão.

## ARTIFACTS_WRITTEN

Painéis PNG e manifestos de representação.

## DEPENDENCIES

SimpleITK; NumPy; Pillow; hashing; módulos de painel.

## OBSERVED_BEHAVIOR

build_exam_panels força política liver-enriched observada e verifica no manifesto que máscara/lesão/ground truth/contorno/crop não foram renderizados. O ID publicado é anon-* determinístico. Monofásico representa disponibilidade, não sintetiza fases.

## SOFTWARE_CONTRACTS

Manifesto deve enumerar imagens autoritativas, hashes, política espacial, canais e ausência de ground truth. Ordem e nomes devem ser determinísticos.

## GEOMETRIC_CONTRACTS

Slice selection, orientação, aspect ratio, windowing e mapeamento de fases devem manter semântica explícita; painéis não substituem geometria 3D.

## SCIENTIFIC_CONTRACTS

Layout, slices, canais, windowing, enriquecimento hepático e uso/ausência de máscaras fazem parte da representação científica.

## DOMAIN_POLICIES

Painéis de inferência devem ser label-blind; representação monofásica não deve fabricar informação ausente.

## KNOWN_FAILURE_MODES

Fase ausente; volume vazio; manifesto inconsistente; painel ausente/corrompido; máscara incompatível.

## SILENT_FAILURE_MODES

Troca de ordem/canal; leakage visual de label/lesão; orientação espelhada; windowing drift; cache aceitar painel de revisão diferente.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-03 para orientação; HG-06 para leakage/labels; HG-09 para qualquer mudança de representação.

## EXISTING_TESTS

tests/test_medgemma_panel.py; tests/test_medgemma_panel_full_fov.py; tests/test_medgemma_panel_liver_enriched.py; tests/test_medgemma_panel_multiphase.py; testes de painel em tests/test_webapp.py.

## TEST_GAPS

Golden images versionadas; invariância/variação esperada por spacing/orientation; detecção de leakage; hash de preprocessing; limites de memória; device/browser agreement.

## REQUIRED_TEST_TYPES

CHARACTERIZATION; CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MEDICAL_GEOMETRY.md; .fable/references/REPRODUCIBILITY.md; docs/230_VOLYRCS_ARQUITETURA_DO_PRODUTO.md.

## OPEN_QUESTIONS

Qual representação está congelada para cada modelo? Quais painéis são apenas revisão e quais são inputs científicos?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar slices, orientação, canais, ordem de fases, windowing, crop, máscara renderizada, IDs ou schema do manifesto sem HG-09 e regressão do modelo.
