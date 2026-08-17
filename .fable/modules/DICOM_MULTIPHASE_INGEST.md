# MODULE_ID: DICOM_MULTIPHASE_INGEST

MODULE_NAME: Resolução DICOM multifásica e harmonização

## REAL_PATHS

- dtwin/learning/raw_dicom_phase_resolver.py
- dtwin/learning/multiphase_ingest.py
- tests/test_raw_dicom_phase_resolver.py
- tests/test_learning_multiphase_ingest.py

STATUS: PRODUCTION

## RESPONSIBILITY

Descobrir pastas de fase ou resolver séries DICOM brutas, selecionar arterial/venosa/delayed, ler slices espacialmente, harmonizar fases na grade venosa e materializar um caso multifásico.

## ENTRYPOINTS

- resolve_raw_dicom_phases
- discover_phase_folders
- read_phase_series
- harmonize_to_reference
- build_multiphase_case

## PUBLIC INTERFACES

RawPhaseResolutionError; RawSeries; RawPhaseResolution; MultiphaseCase; normalize_phase_name.

## INPUTS

Árvore DICOM bruta ou pastas de fases; callback de segmentação venosa; diretório de caso; min_slices.

## OUTPUTS

Mapeamento de fases, imagens harmonizadas, máscara hepática venosa, coverage, manifestos e cópias/hardlinks de séries selecionadas.

## SIDE_EFFECTS

Lê tags DICOM; cria resolved_raw_phases; pode hardlinkar/copiar DICOM original; grava volumes/manifestos; chama segmentação.

## UPSTREAM

CORE_IO_GEOMETRY; pydicom; SimpleITK; filesystem; CONFIG_PROFILES.

## DOWNSTREAM

SEGMENTATION_RUNTIME; PANELS_REPRESENTATION; WEBAPP_API_ORCHESTRATION; MEDSIGLIP_EMBEDDINGS; MEDGEMMA_INFERENCE.

## ARTIFACTS_READ

Arquivos DICOM e metadados de série/fase.

## ARTIFACTS_WRITTEN

resolved_raw_phases; volumes por fase; máscara venosa; manifestos de resolução e caso multifásico.

## DEPENDENCIES

pydicom; SimpleITK; NumPy; CORE_IO_GEOMETRY; SEGMENTATION_RUNTIME via callback.

## OBSERVED_BEHAVIOR

Prefere pastas explicitamente nomeadas; caso contrário usa tags/texto e ordem temporal para resolver séries pós-contraste. Ambiguidade falha fechado. Fases arterial/delayed são reamostradas para a referência venosa; coverage mínimo observado é 0,5. DICOM original pode permanecer no caso.

## SOFTWARE_CONTRACTS

Seleção deve ser determinística e auditável; séries ambíguas não devem ser escolhidas silenciosamente; manifesto deve registrar estratégia/confiança; falhas não podem deixar resolução parcialmente aceita.

## GEOMETRIC_CONTRACTS

Ordenar por posição física, validar orientação/compatibilidade, nomear fixed/moving, registrar transform e coverage, preservar referência venosa e usar interpolador correto por tipo de dado.

## SCIENTIFIC_CONTRACTS

Mapeamento de fases, referência venosa, limiar de coverage e tratamento de fases ausentes exigem confirmação; comportamento observado não basta.

## DOMAIN_POLICIES

Fallback monofásico é permitido apenas para insufficient_dynamic_phases no webapp; estudo ambíguo falha fechado. PHI deve ter política explícita de retenção.

## KNOWN_FAILURE_MODES

Metadados ausentes; séries derivadas; orientação incompatível; poucos slices; fases ausentes; coverage insuficiente; leitura DICOM falhar.

## SILENT_FAILURE_MODES

Fase semanticamente errada porém geometricamente válida; hardlink reter PHI; ordenação espacial errada; derived/MPR selecionado como fonte; registro inadequado sem landmark aparente.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-02 para série/fase; HG-03 para orientação; HG-04 para resampling/registro; HG-11 para DICOM/PHI.

## EXISTING_TESTS

tests/test_raw_dicom_phase_resolver.py; tests/test_learning_multiphase_ingest.py; cobertura de integração em tests/test_webapp.py.

## TEST_GAPS

Transfer syntaxes diversas; duplicatas; MPR/MIP/subtração; InstanceNumber enganoso; séries com direction divergente; missing tags; burned-in PHI; property tests de permutação de slices.

## REQUIRED_TEST_TYPES

CHARACTERIZATION; CONTRACT; PROPERTY; NEGATIVE; INTEGRATION; GEOMETRIC_REGRESSION; SCIENTIFIC_REGRESSION; FAULT_INJECTION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/PRIVACY_SECURITY.md; .fable/references/DICOM.md; .fable/references/MEDICAL_GEOMETRY.md; docs/230_VOLYRCS_ARQUITETURA_DO_PRODUTO.md.

## OPEN_QUESTIONS

Quais tags e prioridades estão aprovadas para cada protocolo? DICOM bruto deve ser removido após ingestão? Registration além de resample de grade é necessário?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar seleção de série/fase, heurísticas temporais, reference grid, interpolação, coverage, fallback ou retenção DICOM sem gate humano e regressão específica.

