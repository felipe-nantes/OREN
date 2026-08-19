# EVIDENCE PACKAGE — TASK-2026-08-18-PH05-INT-01

```yaml
TASK_ID: TASK-2026-08-18-PH05-INT-01
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em 515b7b3; teste novo NAO commitado
TASK_DESCRIPTION: >
  PHASE_05 wave 1 — fronteira do subprocess de segmentacao e corrupcao entre
  estagios, com subprocess REAL (sem GPU/pesos verdadeiros).
ROUTE: [SEGMENTATION, ORCHESTRATION, MEMORY_CONCURRENCY (leve), CACHE_ARTIFACTS]
MODULES: [SEGMENTATION_RUNTIME, PIPELINE_ENGINE_STAGES, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/segmentation_subprocess.py (integral)
  - dtwin/seg_worker.py (integral; contrato de exit codes 64/65/2/3)
  - tests/conftest.py (fixture synthetic_case)
FILES_CHANGED:
  - tests/test_integration_segmentation_boundary.py (NOVO; 7 testes)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: fase autorizada; card atualizado (Docker E2E -> E2E nativo) antes da execucao
CONTRACTS_INVOLVED: [SW-FAIL-CLOSED-01, SW-ARTIFACT-01 (fronteira de integracao)]
SCIENTIFIC_CONTRACTS_INVOLVED: [nenhum editado]
BASELINE: 1693 passed / 1 failed ambiental / 4 skipped
TESTS_ADDED:
  - "runtime TotalSegmentator: config NUL-corrompida reparada + backup auditavel (o MESMO modo de falha vivido com o Docker Desktop nesta sessao); contador preservado em config valida; pesos ausentes -> RuntimeError ANTES de qualquer spawn"
  - "worker REAL em subprocess: DICOM inexistente -> exit 2 (caminho PipelineError, verificado — nao exit 65 de import), PREP_FAIL extraido como mensagem acionavel; argc invalido -> exit 64"
  - "segmentation_error: marcador vence ruido; cauda truncada a 1000; fallback para exit code"
  - "corrupcao entre estagios: mask_organ corrompida apos prepare -> finalize aborta com PipelineError e NAO reescreve nenhum STL (mtimes identicos)"
TESTS_AFTER:
  - "arquivo isolado: 7 passed, 1.52s (subprocess real: 1.06s)"
  - "suite completa: 1700 passed, 1 failed (pre-existente ambiental), 4 skipped"
MUTATION_RESULT: >
  Nao aplicado nesta wave — o criterio da fase e "succeeds and fails closed",
  provado por execucao real das fronteiras (exit codes especificos verificados
  empiricamente antes de virar assert), nao por mutantes.
BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Caminho de SUCESSO da segmentacao real (TotalSegmentator com pesos) nao exercitado — exige pesos/GPU; BLOCKER declarado no card da fase.
  - Resume/idempotencia do webapp (jobs) fica para wave propria.
HUMAN_GATE: nenhum
DIFF_SUMMARY: 1 arquivo de teste novo (~180 linhas) + card da fase atualizado
ROLLBACK: deletar o arquivo de teste
FINAL_STATUS: DONE (nao commitado)
```

## Nota de método

O assert do crash do worker foi endurecido APÓS verificação empírica: uma
sonda isolada confirmou `returncode=2` + `PREP_FAIL: Pasta DICOM inexistente`
(o caminho PipelineError do motor), e só então o teste passou a exigir
exatamente esse modo de falha — um assert `!= 0` aceitaria silenciosamente um
import quebrado (exit 65), validando a coisa errada.
