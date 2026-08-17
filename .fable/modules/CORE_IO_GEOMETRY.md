# MODULE_ID: CORE_IO_GEOMETRY

MODULE_NAME: Core de I/O, geometria médica e layout de casos

## REAL_PATHS

- dtwin/core.py
- tests/test_core_profile.py
- tests/test_stages_units.py

STATUS: PRODUCTION

## RESPONSIBILITY

Fornecer erros de pipeline, leitura/escrita de imagens, conversão SimpleITK–NumPy, transformação de índices zyx para coordenadas físicas LPS, hashing, carregamento de perfil e paths canônicos de Case.

## ENTRYPOINTS

- dtwin.core.read_dicom_series
- dtwin.core.read_image
- dtwin.core.save_image
- dtwin.core.load_profile
- dtwin.core.Case

## PUBLIC INTERFACES

- PipelineError
- array_from; array_to_image; world_vertices_from_index
- sha256_of; now_utc
- Case e suas propriedades de artefato

## INPUTS

Diretórios DICOM; NIfTI/imagens SimpleITK; arrays zyx; perfil YAML; diretório raiz e case_id.

## OUTPUTS

Imagens SimpleITK; arrays NumPy; vértices físicos LPS; hashes; configuração; paths e manifesto do caso.

## SIDE_EFFECTS

Leitura de DICOM/imagens/perfis; criação de diretórios de caso; escrita de imagens e manifesto por consumidores.

## UPSTREAM

SimpleITK, NumPy, PyYAML, filesystem e metadados DICOM.

## DOWNSTREAM

PIPELINE_ENGINE_STAGES; DICOM_MULTIPHASE_INGEST; SEGMENTATION_RUNTIME; CANDIDATE_LOCALIZATION; VOLUMETRY; VIEWER_ARTIFACTS_3D; WEBAPP_API_ORCHESTRATION.

## ARTIFACTS_READ

DICOM; NIfTI; profiles/figado.yaml; manifestos de caso.

## ARTIFACTS_WRITTEN

Imagens e diretórios referenciados por Case; hashes e timestamps incorporados em manifestos downstream.

## DEPENDENCIES

SimpleITK; NumPy; PyYAML; pathlib; hashlib.

## OBSERVED_BEHAVIOR

Arrays são tratados em ordem zyx e coordenadas físicas em LPS. read_dicom_series usa nomes GDCM da pasta sem exigir SeriesInstanceUID explícito; em pasta mista a seleção pode ser ambígua. Isto é comportamento observado, não contrato científico aprovado.

## SOFTWARE_CONTRACTS

Falhas de pipeline devem usar PipelineError; paths devem permanecer dentro do Case; hashes devem refletir bytes reais; escrita/leitura deve rejeitar ausência ou imagem inválida.

## GEOMETRIC_CONTRACTS

Preservar size, origin, spacing, direction, dimensão, unidades e convenção LPS. array_to_image deve copiar a geometria da referência. Transformações zyx→índice xyz→LPS devem ser testadas com phantom assimétrico.

## SCIENTIFIC_CONTRACTS

Nenhum contrato científico novo deve ser inferido do comportamento atual.

## DOMAIN_POLICIES

Política de case_id e layout de artefatos vem do perfil e de Case; DICOM/PHI deve seguir minimização e retenção autorizadas.

## KNOWN_FAILURE_MODES

Pasta vazia; DICOM ilegível; série mista; dimensão incompatível; perfil ausente/malformado; path ou arquivo ausente.

## SILENT_FAILURE_MODES

Série errada porém legível; flip/orientação incorreta com shape igual; perda de direction ao converter arrays; reutilização de path de caso incompatível.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-02 para seleção DICOM; HG-03 para geometria/convenções; HG-11 para PHI; HG-01 se comportamento for promovido a contrato científico.

## EXISTING_TESTS

tests/test_core_profile.py; tests/test_stages_units.py; cobertura indireta em tests/test_stage1_ingest.py e tests/test_engine_finalize.py.

## TEST_GAPS

Seleção explícita em pasta multi-series; round-trip LPS/RAS; direction divergente com shape/spacing/origin iguais; DICOMs derivados/duplicados; falhas de escrita.

## REQUIRED_TEST_TYPES

UNIT; CHARACTERIZATION; CONTRACT; PROPERTY; NEGATIVE; GEOMETRIC_REGRESSION; INTEGRATION; FAULT_INJECTION.

## RELEVANT_REFERENCES

.fable/CONTRACTS.md; .fable/HUMAN_GATES.md; .fable/references/DICOM.md; .fable/references/MEDICAL_GEOMETRY.md; README.md.

## OPEN_QUESTIONS

Qual SeriesInstanceUID deve ser autoritativo no CLI? Qual política de retenção e desidentificação vale para o Case?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar ordem de eixos, LPS/RAS, cópia de geometria, seleção de série, política de case_id ou layout persistido sem baseline, testes geométricos e aprovação nos gates aplicáveis.

