# OpenSwissHCC v10 — auditoria de tempo do caminho ROI aprovado

## Objetivo

Fechar as lacunas de tempo do piloto v10 sem modificar as galerias aprovadas, o freeze,
as respostas do MedGemma ou o ground truth.

O profiler regenerou os dois conjuntos de painéis de cada caso e exigiu igualdade byte a
byte com os PNGs aprovados pelo revisor. Depois compôs conservadoramente os tempos reais
dos seguintes estágios:

1. registro arterial/tardio para a fase venosa;
2. localizador `liver_lesions_mr`;
3. renderização dos ROIs morfológicos;
4. renderização dos ROIs de realce;
5. scoring do MedGemma 1.5 4B.

## Resultado

| Medida | Resultado |
|---|---:|
| Casos auditados | 10/10 |
| Média composta | 69,12 s |
| Máximo composto | 75,60 s |
| Casos dentro de 180 s | 10/10 |
| Painéis regenerados byte-idênticos | sim |
| Ground truth lido | não |
| Holdout aberto | não |

Tempos por estágio:

| Estágio | Média | Máximo | Mínimo |
|---|---:|---:|---:|
| Registro de fases | 13,53 s | 14,16 s | 12,85 s |
| Localizador de lesão | 23,58 s | 28,19 s | 21,09 s |
| Renderização morfológica | 0,93 s | 1,10 s | 0,41 s |
| Renderização de realce | 1,06 s | 1,28 s | 0,54 s |
| MedGemma 4B | 30,02 s | 35,68 s | 11,62 s |

## Artefato

```text
casos/qualification/openswisshcc_v1/timing/
dev_v10_localizer_roi_ab_pilot10/summary.json
```

SHA-256:

```text
d5316b28e399ab2ffa4ba1ee91b827db9c3f60de208d02e5a7f0bfbb637a0570
```

## Interpretação correta

O resultado comprova que o caminho do benchmark com entradas NIfTI já preparadas ficou
abaixo de 180 segundos nos dez casos. Não comprova ainda o tempo completo do webapp desde
uma pasta DICOM, pois dois estágios de produção não fazem parte dessas entradas:

- ingestão/conversão DICOM;
- segmentação hepática.

Por isso o resumo registra simultaneamente:

```text
prepared_benchmark_time_gate_evaluable=true
production_end_to_end_time_gate_evaluable=false
```

O próximo teste de tempo deve instrumentar um exame individual real iniciado pelo webapp
ou pelo mesmo backend de produção, incluindo ingestão e segmentação. Somente essa medição
poderá encerrar o requisito de 180 segundos para o fluxo operacional completo.

## Validação

- testes focados antes da execução: 12 aprovados;
- auditoria real: 10 casos concluídos;
- suíte completa após a execução: **512 testes aprovados**;
- falhas: zero;
- avisos: 327, todos de depreciação já conhecidos.
