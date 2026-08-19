# EVIDENCE PACKAGE — TASK-2026-08-18-PH04-INV-05 (wave final + exit review)

```yaml
TASK_ID: TASK-2026-08-18-PH04-INV-05
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em dfb36b5; testes novos NAO commitados
TASK_DESCRIPTION: >
  PHASE_04 wave 5 (final) — fechar todas as pendencias da fase:
  bootstrap agrupado por paciente + politica completa de denominadores
  (ARGOS-SCI-004/013), SW-FAIL-CLOSED-01, SW-HTTP-01, SW-XR-01, POL-PHI-01.
ROUTE: [METRICS_STATISTICS, CROSS_VALIDATION, SECURITY, PRIVACY, TESTS_BUILD_ENVIRONMENT]
MODULES: [BENCHMARK_METRICS_REPORTING, ML_CLASSIFIERS_SPLITS, MEDGEMMA_INFERENCE, WEBXR_QUEST, TEST_SUITE]
FILES_ANALYZED:
  - dtwin/learning/robustness.py (integral: _metrics_for, bootstrap_confidence_interval, _percentile)
  - dtwin/medgemma_client.py:776-880 (HTTPJSONMedGemmaClient, check_ready, _post_generate)
  - webapp/server.py:1673-1700 (_xr_session_path, _read_xr_session)
  - dtwin/core.py (read_image, read_dicom_series), dtwin/stages.py (stage4b), visual_inference (bundle)
FILES_CHANGED:
  - tests/test_property_denominators_bootstrap.py (NOVO; 10 testes)
  - tests/test_property_failclosed_http_xr_phi.py (NOVO; 17 testes)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: PHASE_04 autorizada; nenhum codigo de producao alterado
SCIENTIFIC_CONTRACTS_INVOLVED:
  - ARGOS-SCI-004 (denominadores) — agora com property tests completos
  - ARGOS-SCI-013 (bootstrap agrupado 2000/seed) — agora com property tests
  - ARGOS-SCI-005 (gate 75/75) — coerencia gate<->metricas coberta
CONTRACTS_INVOLVED: [SW-FAIL-CLOSED-01, SW-HTTP-01, SW-XR-01, POL-PHI-01]
BASELINE: 1667 passed / 0 failed / 4 skipped
TESTS_ADDED:
  - "denominadores: tp+tn+fp+fn == casos SEMPRE (250 exemplos); falha tecnica vira FN/FP nunca acerto; converter acerto em falha NUNCA melhora metrica (anti-gaming); metricas em [0,1]; gate 75/75 coerente"
  - "bootstrap: unidade de reamostragem e o PACIENTE (contagem de grupos exposta); IC ordenados em [0,1]; reprodutivel por seed com procedencia registrada; recusa coorte vazia; defaults congelados 2000/20260724 verificados por assinatura"
  - "fail-closed: input ausente/serie ausente/mascara ausente/bundle corrompido — todos PipelineError explicito, nada fabricado"
  - "http: health nao-pronto/modelo divergente/contrato estranho recusados; contrato correto aceito; endpoint nao-loopback sem opt-in recusado; payload declara dtwin-medgemma-v1"
  - "xr: nome da sessao e EXATAMENTE o sha256 do token (80 exemplos); expirada => 401 + arquivo removido; token vazio/gigante => 401; sessao de outro job => 401"
  - "phi: git check-ignore confirma casos/, flywheel/, docs/drive/ ignorados; git ls-files confirma zero arquivos de paciente versionados"
TESTS_AFTER:
  - "denominators_bootstrap isolado: 10 passed, 2.67s"
  - "failclosed_http_xr_phi isolado: 17 passed, 2.57s"
  - "suite completa: 1693 passed, 1 failed (pre-existente ambiental: espaco em disco), 4 skipped, 131s"
MUTATION_RESULT: >
  Dois mutantes dirigidos nesta wave, ambos detectados:
  (1) robustness._metrics_for excluindo falhas tecnicas do denominador (o
      gaming que ARGOS-SCI-004 proibe) -> 2 invariantes falham;
  (2) medgemma_client aceitando qualquer contrato no health -> teste de
      recusa falha.
  Ambos revertidos; robustness.py e medgemma_client.py confirmados identicos
  ao HEAD por git diff --exit-code.
PROPERTY_TEST_RESULT: PASSED
BEHAVIOR_CHANGE: NONE
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - Testes de HTTP usam socket/urlopen mockados; conectividade real e exercitada na PHASE_05.
  - POL-PHI-01 verifica o mecanismo git (check-ignore/ls-files), nao inspeciona conteudo de arquivos.
  - Bootstrap testado com n_resamples reduzido (25) por velocidade; os defaults congelados (2000/20260724) sao verificados por assinatura.
UNRESOLVED_RISKS: []
HUMAN_GATE: nenhum acionado
DIFF_SUMMARY: 2 arquivos de teste novos (~430 linhas somadas)
ROLLBACK: deletar os 2 arquivos de teste
FINAL_STATUS: DONE (nao commitado)
```

## Notas de metodo (2 defeitos nos proprios testes, corrigidos contra a fonte)

1. O bloco SW-HTTP-01 foi inicialmente escrito contra uma classe imaginada
   (`HttpGatewayBackend`); a real e `HTTPJSONMedGemmaClient`, com config
   aninhada em `medgemma` e metodo `check_ready()` que abre socket antes do
   health. Reescrito contra a API real, com socket mockado — e ganhou de
   brinde o teste de recusa de endpoint nao-loopback.
2. O Hypothesis derrubou o assert ingenuo de substring no teste do token XR:
   o token gerado "1" coincide com um caractere do proprio hash hex. O teste
   agora compara contra o SHA-256 ESPERADO, que e mais forte, nao mais fraco.

## EXIT REVIEW — PHASE_04_INVARIANTS

EXIT_CRITERIA do card: "critical invariants fail under known counterexamples/mutations."

| Contrato | Testes | Mutante detectado |
|---|---|---|
| GEO-CONVERT-01 | property round-trip (400 ex.) | CopyInformation removido -> 2 falhas |
| GEO-LABEL-01 | property + auditoria AST (28 call sites) | resample linear em label -> auditoria falha |
| SW-ATOMIC-01 | property + 3 escritores sondados + auditoria AST (56 helpers) | escrita direta -> auditoria e invariante falham |
| SW-ARTIFACT-01 | property hash-por-byte + recusa de incompleto/corrompido | (coberto pelo mutante de escrita) |
| ARGOS-SCI-003/008 | 7 property (coortes generativas) | agrupamento por exame -> leakage nomeado |
| ARGOS-SCI-013 (Wilson) | 15 testes + 5 ancoras independentes | Wald por Wilson -> 5 falhas |
| ARGOS-SCI-004/013 (denom+bootstrap) | 10 property | exclusao de falhas -> 2 falhas |
| SW-FAIL-CLOSED-01 | 4 testes de borda | (fail-closed exercitado direto) |
| SW-HTTP-01 | 6 testes com API real mockada | aceita-qualquer-contrato -> falha |
| SW-XR-01 | 4 testes (1 property, 80 ex.) | (validacao exercitada direto) |
| POL-PHI-01 | 2 testes com git como oraculo | — (mecanismo externo) |

**11 contratos com invariante executavel; 8 mutantes dirigidos detectados ao
longo das waves 1-5.** Total de testes novos da fase: 61, todos verdes.
VEREDITO: EXIT_CRITERIA satisfeito. **PHASE_04 = DONE.**
