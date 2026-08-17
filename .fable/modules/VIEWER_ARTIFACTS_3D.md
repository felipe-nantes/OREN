# MODULE_ID: VIEWER_ARTIFACTS_3D

MODULE_NAME: Artefatos científicos e visualização 3D

## REAL_PATHS

- dtwin/viewer_artifacts.py
- dtwin/stages.py
- viewer/index.html
- viewer/app.js
- viewer/argos-viewer.css
- viewer/vendor/three.module.js
- viewer/vendor/STLLoader.js
- viewer/vendor/OrbitControls.js
- tests/test_viewer_artifacts.py
- tests/test_viewer_presets.py

STATUS: PRODUCTION

## RESPONSIBILITY

Gerar métricas de fidelidade, imagens de referência, relações anatômicas, STL/LODs e viewer manifest; carregar e apresentar estruturas no viewer Three.js.

## ENTRYPOINTS

- compute_mesh_metrics
- generate_reference_images
- acquisition_summary
- nearest_surface_relationships
- lesion_segment_overlap
- stage6_mesh
- stage7_export_publish
- viewer/index.html

## PUBLIC INTERFACES

Funções públicas de dtwin.viewer_artifacts; schema argos-viewer-manifest-v2; assets e controles expostos por viewer/app.js.

## INPUTS

Máscaras/imagem de referência; VTP/STL; volumes/relationships; config de malha/material; viewer manifest.

## OUTPUTS

STL, LODs, fidelity metrics, PNGs, relationships, viewer_manifest.json e cena 3D interativa.

## SIDE_EFFECTS

Executa marching cubes/smoothing/decimation; grava imagens/malhas/JSON; browser carrega assets e mantém estado de visualização/medição.

## UPSTREAM

PIPELINE_ENGINE_STAGES; VOLUMETRY; CONFIG_PROFILES; ARTIFACT_PROVENANCE.

## DOWNSTREAM

WEBAPP_API_ORCHESTRATION; FRONTEND_DESKTOP; WEBXR_QUEST; aprovação/revisão humana.

## ARTIFACTS_READ

Imagem/máscaras, malhas intermediárias, volumetria e material packs.

## ARTIFACTS_WRITTEN

STL/LOD; PNGs; mesh quality; relationships; viewer_manifest.json.

## DEPENDENCIES

PyVista/VTK; scikit-image; SimpleITK; Pillow; Three.js; STLLoader; OrbitControls.

## OBSERVED_BEHAVIOR

Fidelidade de malha é comparada à máscara-fonte, não a ground truth humana. Stage 7 publica fígado/lesão/candidato/anatomias e inclui volumetria. Há label Fígado hardcoded no plano de exportação, portanto o pipeline não é plenamente órgão-agnóstico.

## SOFTWARE_CONTRACTS

Manifesto deve allowlistar assets, hashes e schema; arquivos devem existir e corresponder ao hash; viewer não deve buscar paths arbitrários.

## GEOMETRIC_CONTRACTS

STL deve manter espaço físico/unidade; isovalue, smoothing, decimation, componentes e LOD devem ter erro quantitativo limitado e registrado. Qualidade visual é distinta de correção geométrica.

## SCIENTIFIC_CONTRACTS

Máscara-fonte, isovalue, target volume, smoothing, decimation, fidelidade e relações anatômicas são decisões quantitativas.

## DOMAIN_POLICIES

Candidato não confirmado deve ser visualmente/semanticamente distinto; métricas e warnings não podem sugerir validação clínica.

## KNOWN_FAILURE_MODES

Máscara vazia; marching cubes falhar; STL degenerado; hash/asset ausente; browser/WebGL incompatível.

## SILENT_FAILURE_MODES

Mesh visualmente plausível mas espelhada/escalada; decimation alterar volume; LOD incorreto; viewer exibir unidade/rótulo errado; quality metric ser lida como verdade anatômica.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-03 para coordenadas; HG-05 para máscara; HG-10 para operações 3D; HG-12 para claims.

## EXISTING_TESTS

tests/test_viewer_artifacts.py; tests/test_viewer_presets.py; tests/test_engine_finalize.py; testes de contratos viewer em tests/test_webapp.py.

## TEST_GAPS

Phantoms sphere/cube assimétricos; watertightness/topologia; golden screenshots; cross-browser/WebGL; comparação com ferramenta independente; asset corruption.

## REQUIRED_TEST_TYPES

CONTRACT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; PERFORMANCE; VISUAL_REGRESSION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MESH_3D.md; .fable/references/MEDICAL_GEOMETRY.md; viewer/README.md; profiles/figado.yaml.

## OPEN_QUESTIONS

Quais tolerâncias de fidelidade e topologia são aprovadas? Viewer deve mostrar máscaras reprovadas? Como generalizar labels/materials por órgão?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar máscara-fonte, coordinate space, isovalue, smoothing, decimation, LOD, unidade, métricas ou semântica visual de candidato sem HG-10 e regressão geométrica.

