# EVIDENCE PACKAGE — TASK-2026-08-18-PH03-CHAR-03

```yaml
TASK_ID: TASK-2026-08-18-PH03-CHAR-03
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em bd278b5 (código científico = 9683eaa); teste novo NÃO commitado
TASK_DESCRIPTION: PHASE_03 wave 3 — characterization da seleção de fases em DICOM bruto (P0 #3), com fixtures sintéticas.
ROUTE: [DICOM (characterization), DEIDENTIFICATION (verificada por fixtures sintéticas), GEOMETRY (gate), TESTS_BUILD_ENVIRONMENT]
MODULES: [DICOM_MULTIPHASE_INGEST, CORE_IO_GEOMETRY, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/learning/raw_dicom_phase_resolver.py (integral: vocabulários, _normalized_text, _orientation, _explicit_role, RawSeries, _geometry_compatible, _select, _materialize, resolve_raw_dicom_phases)
  - tests/test_raw_dicom_phase_resolver.py (12 testes existentes, para não duplicar)
FILES_CHANGED:
  - tests/test_characterization_dicom_phase_selection.py (NOVO; 7 testes; DICOM sintéticos via pydicom em tmp_path)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: >
  Explicitamente permitido por HG-02 ("construir fixtures, caracterizar seleção,
  apontar ambiguidade"); nenhuma heurística escolhida ou alterada.
CONTRACTS_INVOLVED: [GEO-IMAGE-01 (leitura)]
SCIENTIFIC_CONTRACTS_INVOLVED: [ARGOS-GEO-001 (leitura; derivados excluídos / seleção trifásica — não alterado)]
BASELINE: suíte verde nos 2 backends; 12 testes existentes do resolver intactos
BUG_REPRODUCTION: N/A (nenhum bug; ambiguidades registradas como observação)
TESTS_BEFORE: ["tests/test_raw_dicom_phase_resolver.py: 12 testes"]
TESTS_ADDED:
  - "::test_observed_rotulo_com_dois_papeis_nao_e_confiavel_e_cai_para_ordem_temporal"
  - "::test_observed_nome_da_pasta_sozinho_determina_o_papel_explicito"
  - "::test_observed_geometria_incompativel_mascara_o_motivo_como_insuficiencia"
  - "::test_observed_series_sagitais_nao_sao_elegiveis"
  - "::test_observed_serie_com_menos_de_tres_frames_nao_e_elegivel"
  - "::test_observed_com_quatro_dinamicas_a_fase_do_meio_e_descartada"
  - "::test_observed_series_in_phase_e_opposed_sao_ignoradas_mesmo_com_rotulo_de_fase"
TESTS_AFTER:
  - "host Windows: 7 passed (0.76s) isolados; 19 passed (1.71s) junto com os 12 existentes"
  - "container POSIX: PENDING — daemon Docker caiu novamente (bug de sockets órfãos); a rodar assim que subir"
STATIC_ANALYSIS: NOT_RUN (adiado por decisão)
BRANCH_COVERAGE: NOT_APPLICABLE
MUTATION_RESULT: NOT_APPLICABLE (fase 07)
PROPERTY_TEST_RESULT: NOT_APPLICABLE (fase 04 — candidato: property test de ordenação temporal)
INTEGRATION_RESULT: NOT_APPLICABLE (resolver isolado; ingest end-to-end é fase 05)
SCIENTIFIC_REGRESSION_RESULT: NOT_APPLICABLE
GEOMETRIC_REGRESSION_RESULT: NOT_APPLICABLE
BENCHMARK_BEFORE: NOT_APPLICABLE
BENCHMARK_AFTER: NOT_APPLICABLE
BEHAVIOR_CHANGE: NONE (somente proteção)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Fixtures sintéticas não reproduzem a variedade de exportações reais de scanner; caracterizam a LÓGICA, não a cobertura de vocabulário do mundo real.
  - O caminho monofásico (fallback) já era coberto pelos testes existentes; não reexaminado aqui.
UNRESOLVED_RISKS:
  - "AMBIGUIDADE 1 (candidata HG-02): rótulo casando com dois papéis ('T1 ARTERIAL AND PORTAL VENOUS') é descartado como não rotulado e a série ainda assim entra na ordenação temporal, recebendo ARTERIAL por ser a mais precoce. O rótulo contraditório não interrompe o exame."
  - "AMBIGUIDADE 2 (candidata HG-02): com 4+ séries dinâmicas, a seleção é primeira/segunda/ÚLTIMA — as intermediárias são descartadas em silêncio, sem registro no manifesto de que existiam fases não usadas."
  - "WART (candidata HG-02/HG-03): reprovação no gate de geometria (Rows divergente) é reportada como `insufficient_dynamic_phases`; o motivo geométrico real fica mascarado no código de erro, dificultando triagem operacional."
  - "OBSERVAÇÃO: o nome da pasta tem peso igual ao dos metadados na decisão de papel — uma pasta renomeada muda a fase resolvida."
HUMAN_GATE: nenhum acionado; 3 ambiguidades/warts encaminhadas como candidatas HG-02
APPROVAL_STATUS: dentro do escopo autorizado da fase
DIFF_SUMMARY: 1 arquivo de teste novo (~200 linhas), fixtures sintéticas autocontidas
ROLLBACK: deletar tests/test_characterization_dicom_phase_selection.py
FINAL_STATUS: DONE (não commitado; commit quando solicitado)
```

## Verificação de privacidade (HG-11 não acionado)

As fixtures são geradas em `tmp_path` com `PatientName = "SYNTHETIC^PHANTOM"` e UIDs gerados por `pydicom.uid.generate_uid()`. Nenhum arquivo de `casos/`, label protegido ou máscara de lesão foi lido. Nenhum dado real entra no repositório ou no pack.
