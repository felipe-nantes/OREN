# Condições obrigatórias de parada

Pare antes de editar ou continuar quando houver:

- `SOURCE_OF_TRUTH_CONFLICT`
- `SCIENTIFIC_CONTRACT_UNKNOWN`
- `GEOMETRY_AMBIGUOUS`
- `LABEL_MAPPING_AMBIGUOUS`
- `POSSIBLE_PATIENT_LEAKAGE`
- `THRESHOLD_CHANGE_REQUIRED`
- `DENOMINATOR_CHANGE_REQUIRED`
- `COHORT_CHANGE_REQUIRED`
- `INCLUSION_EXCLUSION_CHANGE_REQUIRED`
- `PHI_DETECTED`
- `BASELINE_NOT_REPRODUCIBLE`
- `HIGH_RISK_CHANGE_NEEDS_APPROVAL`
- `CLINICAL_CLAIM_REQUIRED`
- `REQUIRED_DATA_MISSING`
- `RESULT_CANNOT_BE_REPRODUCED`
- transformação/grade/interpolador não identificados;
- artefato/hash/model revision incompatível;
- mudança downstream não delimitada;
- aprovação sem escopo verificável.

## Ação de parada

Não abandone e não aplique workaround silencioso. Preserve evidência, reverta somente escrita parcial própria quando seguro, e gere `templates/STOP_REPORT.md` contendo TASK_ID, razão, arquivos, evidência, risco, contrato, conhecido/desconhecido, opções, testes, decisão e pergunta humana sugerida.

