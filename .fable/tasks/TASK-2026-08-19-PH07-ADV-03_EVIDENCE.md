# EVIDENCE — TASK-2026-08-19-PH07-ADV-03 (PHASE_07, wave 3: S1-S4 + estático + exit review)

Data: 2026-08-19 · Executor: agente · Autorização: Felipe Nantes ("autorizo", 2026-08-19)

## RESUMO

Wave 3 concluída. Os sobreviventes críticos S1-S4 da wave 2 foram mortos com
34 testes negativos sintéticos novos (todos passando) e 6 sondas dirigidas de
confirmação — **6/6 KILLED** (total da fase: **15/15 KILLED**). Varredura
estática de defeito real: 7 achados B023, todos classificados benignos no uso
atual. Nenhum código de produção alterado.

## Testes novos (34, todos passando)

- `tests/test_volumetry_verification_negative.py` (12): par manifesto+CSV
  sintético válido corrompido um braço por vez em
  `verify_volumetry_artifacts` — artefatos incompletos, manifesto ilegível,
  schema/contrato, hash do CSV, contagens divergentes, papel duplicado,
  estrutura fantasma, **GEO-004 nos dois sentidos (volume JSON e volume CSV
  vs voxels × spacing / 1000)** e gate Couinaud aprovado sem partição exata.
- `tests/test_segmentation_contract_negative.py` (22): geometria (origem NaN,
  direção quase-singular det=1e-9), manifesto nativo (ausente/papel
  inválido/ilegível), máscara visual (ausente/ilegível/não-finita via .mha),
  manifesto de qualidade (schema/backend/tempo), e o gate de exibição
  `approved_visualization_mask` — recibo ilegível, schema estranho, status
  reprovado, recibo confessando violação (ground_truth_read/lesion_masks_read/
  production_files_written), **hash divergente (máscara trocada após o
  carimbo)**, hash ausente, e o caminho feliz (recibo completo → path).

## Ledger de mutantes — wave 3 (6/6 KILLED)

JSON: `evidence/PH07/mutation_probes_w3_2026-08-19.json` (restauração
hash-verificada em todas).

| Sonda | Mutante (guarda desligada) | Veredicto |
|---|---|---|
| P10 | volumetry: checagem GEO-004 do volume JSON | KILLED |
| P11 | volumetry: gate Couinaud sem partição exata | KILLED |
| P12 | volumetry: schema/contrato do manifesto | KILLED |
| P13 | segmentation_contract: hash da máscara vs recibo | KILLED |
| P14 | segmentation_contract: geometria finita | KILLED |
| P15 | segmentation_contract: direção singular | KILLED |

## Achados OBSERVED da wave

1. **Writer NIfTI do ITK sanitiza NaN→0 no round-trip** (float32 preservado,
   NaN vira 0.0). Consequência: máscara NIfTI escrita pelo ITK nunca chega
   não-finita ao validador; o braço protege contra arquivos de OUTROS writers
   (nibabel, custom). Teste usa .mha (MetaImage), que preserva NaN.
2. **SimpleITK recusa construir** spacing ≤ 0 e direção toda-zero
   (SetSpacing/SetDirection lançam). Os braços 91/93 de `image_geometry` e o
   arm de direção singular EXATA são defensivos contra estados
   não-construíveis via API — mas direção QUASE-singular (det=1e-9) é
   construível e o braço 98 a rejeita (testado e kill-verificado, P15).

## Varredura estática de defeito real

`evidence/PH07/ruff_defeitos_reais_2026-08-19.txt` — ruff com
F821,F811,F702,B002,B006,B008,B015,B023,B031,B032,PLE sobre
dtwin/webapp/tools/tests: **7 achados, todos B023** (closure não vincula
variável de loop), em `openswisshcc_multisequence_audit.py`,
`openswisshcc_multisequence_geometry.py` e
`run_raw_phase_equivalence_benchmark.py`. Classificação (SOURCE_SUPPORTED,
leitura dos sítios): todas as closures são invocadas DENTRO da própria
iteração (resolve() chamado imediatamente; lambda consumida durante
build_multiphase_case) → comportamento correto hoje; risco latente apenas sob
refactor para execução adiada. → higiene PHASE_08 (bind por default arg),
sem defeito ativo. Zero F821/F811/PLE em todo o repositório.

## Justificativas formais dos sobreviventes restantes

- S5 `render_markdown_report` (robustness 416-495): apresentação; nenhum
  número novo é computado (formata o report já assinado). ACEITO como risco
  documentado; teste de fumaça é candidato opcional PHASE_08.
- S6 volumetry 56-68/277-334: classificação de papéis e graduação consultiva
  de qualidade (A/B/C/D) — não altera quantidades físicas (GEO-004 agora
  kill-verificado é a âncora); parcialmente exercitado pela suíte existente.
  ACEITO; candidatos de teste em PHASE_08 se houver refactor.
- G8 resolver/ingest/visual_inference braços dispersos: protegidos por
  characterization tests (PHASE_03) + TD-014 registrado. ACEITO.
- G9 scripts one-shot 0-17%: BLK-PROTECTED-SOURCES/BLK-FULL-REEXECUTION;
  resultados congelados no lock. JUSTIFICADO (inalterado da wave 1).

## Classificação de evidência

- OBSERVED: 34 testes passando; 6/6 KILLED com restauração hash-verificada;
  sanitização NaN do ITK; recusas do SimpleITK; saída do ruff.
- SOURCE_SUPPORTED: classificação dos B023; justificativas S5/S6 (leitura das
  faixas + cobertura wave 1).
- INFERRED: nada material.
- UNKNOWN: nada novo.

## CONTEXT_EFFICIENCY

- Probes empíricos de construtibilidade ANTES de escrever testes (2 comandos)
  evitaram testes impossíveis e produziram evidência OBSERVED reutilizável.
- 6 sondas com testes-alvo (<1s cada); sobreviventes restantes justificados
  por prova de cobertura, sem execução.
- Leituras simbólicas apenas das faixas do ledger; runner reutilizado da
  wave 2 com lista de sondas trocada.

## Proibições respeitadas

Produção intocada; nenhum teste enfraquecido; nenhum commit/push.

## Exit review da PHASE_07 — ver TASK-2026-08-19-PH07-EXIT.md
