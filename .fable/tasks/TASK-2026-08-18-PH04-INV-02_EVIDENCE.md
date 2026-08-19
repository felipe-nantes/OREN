# EVIDENCE PACKAGE — TASK-2026-08-18-PH04-INV-02

```yaml
TASK_ID: TASK-2026-08-18-PH04-INV-02
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em dfb36b5; testes novos NÃO commitados
TASK_DESCRIPTION: >
  PHASE_04 wave 2 — GEO-LABEL-01 ("resampling de labels discretos usa
  nearest-neighbor e não inventa classes; todo uso deve ser verificado por
  rota") codificado em duas metades: o invariante como property test
  (Hypothesis) e a exigência de "verificado por rota" como auditoria
  estrutural por AST. Gap pré-flagged na revisão da PHASE_02.
ROUTE: [GEOMETRY, HARMONIZATION_RESAMPLING, TESTS_BUILD_ENVIRONMENT]
MODULES: [CORE_IO_GEOMETRY, DICOM_MULTIPHASE_INGEST, SEGMENTATION_RUNTIME, TEST_SUITE]
FILES_ANALYZED:
  - 28 call sites de resample em dtwin/ (auditoria exaustiva, ver tabela abaixo)
FILES_CHANGED:
  - tests/test_property_label_resampling.py (NOVO; 4 testes)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: PHASE_04 autorizada; nenhum código de produção alterado
CONTRACTS_INVOLVED: [GEO-LABEL-01]
SCIENTIFIC_CONTRACTS_INVOLVED: [ARGOS-GEO-001 (interpoladores declarados) — leitura, não alterado]
BASELINE: 1628 passed / 1 failed (ambiental) / 4 skipped
BUG_REPRODUCTION: N/A — auditoria não encontrou violação do contrato
TESTS_ADDED:
  - "test_property_nearest_neighbor_nunca_inventa_classe — @given labels+fator de grade, 150 exemplos"
  - "test_interpolacao_linear_inventa_classes_e_por_isso_e_proibida_em_labels — contraste que prova o invariante não-trivial"
  - "test_auditoria_todo_resample_de_label_usa_nearest_neighbor — varredura AST de dtwin/"
  - "test_auditoria_allowlist_nao_tem_entrada_obsoleta — impede allowlist de acumular entradas mortas"
TESTS_AFTER:
  - "arquivo isolado: 4 passed, 3.01s"
  - "suíte completa: 1633 passed, 0 failed, 4 skipped, 103.32s"
STATIC_ANALYSIS: auditoria própria por AST (é o objeto da task)
MUTATION_RESULT: >
  Prova de poder discriminador (EXIT_CRITERIA da fase): módulo mutante
  injetado em dtwin/ com `sitk.Resample(mask, ref, ..., sitk.sitkLinear, ...)`
  → auditoria FALHA e nomeia o módulo. Mutante removido no finally; workspace
  confirmado limpo depois. O invariante em si é discriminado pelo teste de
  contraste (linear fabrica classes que nearest não fabrica).
PROPERTY_TEST_RESULT: PASSED
BEHAVIOR_CHANGE: NONE (nenhum código de produção alterado)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Auditoria cobre `dtwin/`; `tools/` e `webapp/` não têm call sites de resample sobre label (verificado), mas não estão na varredura contínua.
  - A allowlist é por módulo, não por linha — um call site novo COM interpolação contínua dentro de um módulo já autorizado não seria flagrado. Trade-off deliberado: chaves por linha quebram a cada refactor e gerariam falsos positivos crônicos.
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum acionado (nenhuma semântica alterada)
APPROVAL_STATUS: dentro do escopo autorizado
DIFF_SUMMARY: 1 arquivo de teste novo (~190 linhas)
ROLLBACK: deletar tests/test_property_label_resampling.py
FINAL_STATUS: DONE (não commitado)
```

## Auditoria exaustiva — 28 call sites de resample em `dtwin/`

**Resultado: zero violações de GEO-LABEL-01.** O padrão é consistente em todo
o código: dado discreto → `sitkNearestNeighbor`; dado contínuo → `sitkLinear`.

| Módulo | Interpolador | Dado reamostrado | Veredito |
|---|---|---|---|
| `benchmark/liverhccseg_preparation.py:105` | NearestNeighbor | máscara de suporte | OK |
| `benchmark/liverhccseg_preparation.py:117` | Linear | intensidade de fase | OK (contínuo) |
| `benchmark/liver_mask_phase_fusion.py:95` | NearestNeighbor | máscara hepática | OK |
| `benchmark/liver_segmentation_comparison.py:69` | NearestNeighbor | máscara | OK |
| `benchmark/lld_mmri_v23_harmonization.py:104` | Linear | intensidade | OK (contínuo) |
| `benchmark/lld_mmri_v23_harmonization.py:114,152` | NearestNeighbor | suporte/máscara | OK |
| `benchmark/mrsegmentator_chaos_runner.py:75` | NearestNeighbor | máscara hepática | OK |
| `benchmark/openswisshcc_alignment.py:186` | NearestNeighbor | máscara (identity resample) | OK |
| `benchmark/openswisshcc_alignment.py:236` | Linear | intensidade (float32) | OK (contínuo) |
| `learning/monophase_complementary_candidates.py:100,157` | NearestNeighbor | máscara hepática | OK |
| `learning/multiphase_ingest.py:204` | Linear | intensidade da fase | OK (contínuo) |
| `learning/multiphase_ingest.py:210` | NearestNeighbor | suporte (cobertura da grade) | OK |
| `segmentation_shadow.py:32,229` | NearestNeighbor | máscara de visualização | OK |
| `viewer_artifacts.py:60` | Linear | volume de intensidade | OK (contínuo) |
| `stages.py:232` | Linear | **campo de distância com sinal** | OK (contínuo por construção) |

### Achado do processo (o teste encontrou o que o grep perdeu)

A primeira versão da auditoria flagrou
`learning/monophase_complementary_candidates.py` por um
`SetInterpolator(sitk.sitkLinear)` na linha 137 que a inspeção manual por grep
(janela de 8 linhas após `sitk.Resample(`) não tinha alcançado. Investigação:
é `ImageRegistrationMethod.SetInterpolator` — define como a **métrica de
similaridade** é avaliada sobre `fixed`/`moving` normalizados em float32
durante o registro, e **não reamostra label algum**; o resample da máscara,
20 linhas abaixo, usa `sitkNearestNeighbor` corretamente.

Em vez de silenciar via allowlist (o que teria escondido um call site real no
futuro), a auditoria foi tornada **precisa**: agora rastreia atribuições de
`sitk.ResampleImageFilter()` e só considera `SetInterpolator` invocado sobre
essas variáveis, distinguindo reamostragem de avaliação de métrica.
`stages.py` continua corretamente na allowlist (campo de distância).
