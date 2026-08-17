# MODULE_ID: PIPELINE_ENGINE_STAGES

MODULE_NAME: Orquestração CLI e stages 1–7

## REAL_PATHS

- digital_twin.py
- dtwin/engine.py
- dtwin/stages.py
- tests/test_engine_prepare.py
- tests/test_engine_finalize.py
- tests/test_stage1_ingest.py
- tests/test_stage2_normalize.py

STATUS: PRODUCTION

## RESPONSIBILITY

Executar prepare/finalize/doctor e coordenar ingestão, normalização, segmentação, handoff/importação de lesão, refinamento, malhas e publicação.

## ENTRYPOINTS

- digital-twin prepare
- digital-twin finalize
- digital-twin doctor
- digital_twin.main
- dtwin.engine.Engine.prepare
- dtwin.engine.Engine.finalize

## PUBLIC INTERFACES

Engine; stage1_ingest; stage2_normalize; stage3_segment_organ; stage4a_prepare_lesion; stage4b_import_lesion; stage5_refine; stage6_mesh; stage7_export_publish.

## INPUTS

Diretório DICOM; perfil YAML; root/case_id; device/fast; máscara manual opcional; máscaras shadow/union/candidato.

## OUTPUTS

Case persistido com volume, máscaras, malhas, volumetria, PNGs, manifestos e viewer.

## SIDE_EFFECTS

Cria e atualiza árvore do caso; invoca segmentadores; arquiva itens para treinamento; escreve artefatos científicos e de visualização.

## UPSTREAM

CORE_IO_GEOMETRY; CONFIG_PROFILES; SEGMENTATION_RUNTIME; SEGMENTATION_SHADOW_CONTRACT; CANDIDATE_LOCALIZATION.

## DOWNSTREAM

VOLUMETRY; VIEWER_ARTIFACTS_3D; ARTIFACT_PROVENANCE; WEBAPP_API_ORCHESTRATION; FRONTEND_DESKTOP; WEBXR_QUEST.

## ARTIFACTS_READ

DICOM, profile YAML, NIfTI, máscaras de órgão/lesão/anatomia/candidato e manifestos prévios.

## ARTIFACTS_WRITTEN

Volume/normalização; máscaras raw/clean; VTP/STL/LOD; volumetry_manifest.json/CSV; PNGs; viewer_manifest.json; manifestos do caso.

## DEPENDENCIES

SimpleITK; NumPy; scikit-image; PyVista; CORE_IO_GEOMETRY; módulos de volumetria, viewer e XR.

## OBSERVED_BEHAVIOR

prepare executa stages 1–4a; finalize executa 4b–7. O webapp também chama finalize --no-lesion por subprocesso. Stage 5 prefere shadow aprovada, depois union e por fim máscara original. O caminho é operacional, mas o projeto se declara modo Pesquisa.

## SOFTWARE_CONTRACTS

Ordem dos stages e pré-condições de arquivo devem ser explícitas; rerun deve ser idempotente ou falhar claramente; publicação não deve expor arquivos parciais.

## GEOMETRIC_CONTRACTS

Todas as máscaras devem compartilhar grade física da referência. Interpolação de labels deve ser nearest-neighbor. Malha deve manter coordenadas físicas/unidades e rastrear a máscara-fonte.

## SCIENTIFIC_CONTRACTS

Normalização, morfologia, isolamento, modelos, isovalue, smoothing, decimation e gates são candidatos a contratos; não os promover sem fonte L1/L2 ou aprovação.

## DOMAIN_POLICIES

Órgão obrigatório falha fechado; anatomias opcionais geram aviso. Ausência de lesão pode ser declarada por --no-lesion. Publicação atual é research-only.

## KNOWN_FAILURE_MODES

DICOM inválido; segmentação ausente; máscara manual incompatível; máscara vazia; falha de malha; artefato incompleto; dependência externa indisponível.

## SILENT_FAILURE_MODES

Máscara de mesmo shape em geometria errada; refinamento alterar volume sem revisão; archive de máscara incompatível antes do gate completo; rerun consumir artefato stale.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-03, HG-04, HG-05, HG-08, HG-10 e HG-11 conforme o stage; HG-12 para qualquer claim clínico.

## EXISTING_TESTS

tests/test_engine_prepare.py; tests/test_engine_finalize.py; tests/test_stage1_ingest.py; tests/test_stage2_normalize.py; tests/test_stages_units.py.

## TEST_GAPS

Crash/resume entre stages; direction incompatível; concorrência no mesmo case_id; golden E2E real com DICOM desidentificado; regressão quantitativa de cada operação de máscara/malha.

## REQUIRED_TEST_TYPES

CHARACTERIZATION; CONTRACT; INVARIANT; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; FAULT_INJECTION; PERFORMANCE.

## RELEVANT_REFERENCES

.fable/ARCHITECTURE.md; .fable/DEPENDENCY_MAP.md; .fable/CONTRACTS.md; .fable/HUMAN_GATES.md; profiles/figado.yaml; README.md.

## OPEN_QUESTIONS

Quais stages permanecerão no produto extraído? Qual máscara deve ser aprovada antes da volumetria? Qual estratégia de resume é autorizada?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não reordenar stages nem alterar normalização, seleção de máscara, refinamento, labels, thresholds ou operações quantitativas 3D sem contratos, regressão e gate humano.
