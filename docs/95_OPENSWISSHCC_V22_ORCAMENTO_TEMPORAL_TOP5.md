# OpenSwissHCC v22 — orçamento temporal exact-top5

## Objetivo

Estimar, sem executar nova inferência, se o piloto v22 com até cinco candidatos
por caso pode respeitar o limite de 180 segundos. A projeção usa somente tempos
já medidos com o mesmo MedGemma 1.5 4B e artefatos cegos do v22. Nenhum label ou
máscara de lesão é lido.

## Evidência histórica

O scoring v16 completo contém 229 chamadas ao
`google/medgemma-1.5-4b-it` em 87 casos:

| Estatística por chamada | Segundos |
|---|---:|
| mediana | 21,7607 |
| p95 conservador (`higher`) | 22,4692 |
| p99 conservador (`higher`) | 22,6098 |
| máximo observado | 22,7362 |

Os máximos adicionais medidos foram:

| Componente | Segundos |
|---|---:|
| alinhamento + localizador histórico | 54,9910 |
| renderização de cinco candidatos | 8,6395 |
| geração de propostas v22 | 2,8262 |
| soma conservadora fixa | 66,4567 |

A soma pode contar parcialmente duas vezes o localizador antigo substituído
pelo v22. Ela foi mantida para não transformar uma hipótese favorável em prova.

## Projeções para cinco candidatos

| Cenário | Scoring 4B | Total projetado | Margem para 180 s | Gate projetado |
|---|---:|---:|---:|---|
| p95 | 112,3460 s | 178,8027 s | +1,1973 s | passa |
| p99 | 113,0490 s | 179,5057 s | +0,4943 s | passa |
| pior chamada observada × 5 | 113,6810 s | 180,1377 s | −0,1377 s | falha |

## Decisão

O tempo não está qualificado por projeção. O cenário p99 passa, mas a projeção
mais conservadora excede a meta por aproximadamente 0,14 segundo. Como a margem
é praticamente zero, somente a execução real do piloto exact-top5 pode decidir
o gate.

Após a aprovação humana da galeria, a execução deve registrar separadamente:

1. tempo de cada chamada candidata;
2. soma do scoring por caso;
3. tempo de leitura e validação do bundle;
4. tempo de renderização quando feita na mesma execução;
5. tempo do localizador v22;
6. máximo observado por caso;
7. falha imediata se qualquer caso ultrapassar 180 segundos.

Mesmo que o scoring preparado passe, isso não comprova 180 segundos desde DICOM
cru. Ingestão, segmentação hepática e preparação completa precisam de uma
medição ponta a ponta separada antes da qualificação operacional do webapp.

## Artefato autoritativo

`casos/qualification/openswisshcc_v1/timing/dev_v22_enhancement_t3_exact_top5_projection_v1.json`

SHA-256:

`879719cadf018921005c4262ad4dd3e4e5e09df1318d51f81c72bf5b4ed31c8d`

O artefato declara:

- `strict_worst_observed_projection_passed=false`;
- `actual_v22_pilot_measured=false`;
- `raw_dicom_end_to_end_180_seconds_proven=false`;
- `qualification_decision=pending_actual_v22_pilot`;
- nenhum acesso a ground truth, máscaras ou holdout;
- nenhuma nova inferência.

A regra de classificação e avaliação do piloto foi congelada separadamente em
`docs/96_OPENSWISSHCC_V22_PROTOCOLO_PILOTO_TOP5.md`, antes da criação de qualquer
predição v22.
