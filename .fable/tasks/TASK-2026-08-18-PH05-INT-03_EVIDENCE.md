# EVIDENCE PACKAGE — TASK-2026-08-18-PH05-INT-03 (wave 3 + exit review)

```yaml
TASK_ID: TASK-2026-08-18-PH05-INT-03
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em 515b7b3; testes novos NAO commitados
TASK_DESCRIPTION: >
  PHASE_05 wave 3 — cadeia real DICOM bruto -> resolver -> read_phase_series
  (GDCM multi-slice) -> harmonizacao na grade venosa, com fixtures DICOM
  sinteticas COM PixelData. Exit review da fase.
ROUTE: [DICOM, HARMONIZATION_RESAMPLING, GEOMETRY, TESTS_BUILD_ENVIRONMENT]
MODULES: [DICOM_MULTIPHASE_INGEST, CORE_IO_GEOMETRY, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/learning/multiphase_ingest.py (read_phase_series, harmonize_to_reference)
  - dtwin/learning/raw_dicom_phase_resolver.py (materializacao)
  - tests/test_learning_multiphase_ingest.py + test_raw_dicom_phase_resolver.py (cobertura previa isolada)
FILES_CHANGED:
  - tests/test_integration_dicom_to_harmonized.py (NOVO; 3 testes)
RISK_LEVEL: LOW
CONTRACTS_INVOLVED: [ARGOS-GEO-001 (leitura), ARGOS-GEO-002 (divisao de gates exercitada)]
BASELINE: 1703 passed / 1 failed ambiental / 4 skipped
TESTS_ADDED:
  - "cadeia completa: estudo trifasico sintetico (MR 16-bit, 8 fatias/serie, SOP Class registrado) -> resolver materializa -> GDCM monta cada serie -> harmonizacao com cobertura 1.0, grade identica a venosa e INTENSIDADE preservada voxel a voxel (orgao 800 / fundo 300)"
  - "ordenacao fisica: o conteudo por fatia (base+indice) prova que o eixo Z segue ImagePositionPatient, nao nome de arquivo, atraves da cadeia inteira"
  - "fase disjunta: resolver ACEITA (extensao fisica nao e criterio dele) e a harmonizacao REPROVA (cobertura < 0.5) — a divisao de responsabilidade ratificada em ARGOS-GEO-002, agora exercitada de ponta a ponta"
TESTS_AFTER:
  - "arquivo isolado: 3 passed, 2.91s"
  - "suite completa: 1706 passed, 1 failed (ambiental pre-existente), 4 skipped"
BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Fixture exigiu SOP Class MR registrado (1.2.840.10008.5.1.4.1.1.4) — GDCM recusa UID aleatorio; documentado para futuras fixtures.
HUMAN_GATE: nenhum
DIFF_SUMMARY: 1 arquivo de teste novo (~185 linhas)
ROLLBACK: deletar o arquivo de teste
FINAL_STATUS: DONE (nao commitado)
```

## EXIT REVIEW — PHASE_05_INTEGRATION

EXIT_CRITERIA do card: "each critical stage succeeds and fails closed;
resume/idempotency verified."

| Item do card | Cobertura | Onde |
|---|---|---|
| DICOM -> imagem -> harmonizacao | SUCESSO + FALHA (cobertura insuficiente) exercitados com arquivos reais | wave 3 |
| -> mask -> volume/representation | fail-closed exercitado (corrupcao entre estagios, pesos ausentes); SUCESSO real bloqueado por GPU/pesos — BLOCKER declarado no proprio card | wave 1 |
| subprocess crash | worker real spawnado, exit 2 (PipelineError) verificado, extracao de erro coberta; runtime NUL-corrompido reparado com backup | wave 1 |
| artifact corruption | mascara corrompida -> PipelineError sem reescrever STL; verificadores de artefato cobertos na PHASE_04 | wave 1 |
| API/viewer | TestClient (cobertura previa extensa) + uvicorn REAL: boot, conflito de porta, liberacao | wave 2 |
| E2E nativo | uvicorn real automatizado; o E2E completo com gateway MedGemma na GPU foi validado MANUALMENTE nesta sessao (2026-08-18: usuario testou o app via run_win.ps1 — gateway 4B carregado, health backend:pronto, webapp navegavel, encerramento limpo com GPU liberada) | wave 2 + sessao |
| resume/idempotency | ja cobertos por tests/test_webapp.py (restart + tamper fail-closed); concorrencia adicionada (zero updates perdidos; achado TD-015) | wave 2 |

BLOCKERS remanescentes (declarados, nao ocultados): sucesso automatizado da
segmentacao real (TotalSegmentator + pesos + GPU) e do gateway MedGemma em
teste — cobertos apenas por execucao manual documentada. Candidatos a smoke
test opcional marcado (@pytest.mark.gpu) em fase futura.

VEREDITO: EXIT_CRITERIA satisfeito no escopo automatizavel sem GPU, com o
caminho de sucesso pesado validado manualmente e os blockers explicitos.
**PHASE_05 = DONE.**
