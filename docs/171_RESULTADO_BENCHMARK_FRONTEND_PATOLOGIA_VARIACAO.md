# Resultado do benchmark frontend — Patologia + Variação

**Data:** 3 de agosto de 2026  
**Benchmark ID:** `9a736ea3cfee`  
**Coorte:** 25 casos LLD-MMRI multifásicos  
**Modo:** `pathology_and_subtype`  
**Modelo:** `hybrid_v1_medsiglip_multiclass_supervised`

## Execução

O teste foi iniciado pelo próprio frontend em:

```text
http://127.0.0.1:8080/benchmark.html
```

Foram enviados 200 arquivos DICOM, organizados em 25 exames:

| Referência | Casos |
|---|---:|
| HCC | 5 |
| FNH | 6 |
| Hemangioma | 7 |
| Cisto hepático | 7 |

Todos os rótulos foram selecionados na interface. O endpoint binário foi
derivado automaticamente: HCC positivo; FNH, hemangioma e cisto negativos para
a patologia-alvo.

## Resultado binário — patologia-alvo

| Métrica | Resultado | IC 95% |
|---|---:|---:|
| Acurácia | 100,0% | 86,7–100,0% |
| Sensibilidade | 100,0% | 56,5–100,0% |
| Especificidade | 100,0% | 83,9–100,0% |
| F1-score | 100,0% | não calculado |
| Cobertura decisiva | 100,0% | — |

Matriz de confusão:

```text
TP=5  TN=20  FP=0  FN=0
```

O gate binário de sensibilidade e especificidade maiores ou iguais a 75% foi
atingido nesta coorte.

## Resultado multiclasse — identificação da variação

| Métrica | Resultado | IC 95% |
|---|---:|---:|
| Acurácia balanceada | 96,43% | não implementado |
| Acurácia top-1 | 96,0% | 80,5–99,3% |
| Subtipo determinado | 100,0% | — |
| Falhas/inconclusivos | 0 | — |

Desempenho por classe:

| Subtipo | Acertos | Recall | IC 95% |
|---|---:|---:|---:|
| HCC | 5/5 | 100,0% | 56,5–100,0% |
| FNH | 6/6 | 100,0% | 61,0–100,0% |
| Hemangioma | 7/7 | 100,0% | 64,6–100,0% |
| Cisto hepático | 6/7 | 85,7% | 48,7–97,4% |

Matriz multiclasse:

```text
Real \ Predito   HCC  FNH  Hemangioma  Cisto  Não determinado
HCC                5    0       0         0          0
FNH                0    6       0         0          0
Hemangioma         0    0       7         0          0
Cisto              0    0       1         6          0
```

O único erro foi:

```text
ARGOS-BLIND-0007
referência: hepatic_cyst
predição: hemangioma
confiança do subtipo: 84,11%
decisão binária: NEGATIVA, correta para a patologia-alvo
```

O gate multiclasse de acurácia balanceada maior ou igual a 75%, com as quatro
classes presentes, foi atingido nesta coorte. O gate combinado também passou.

## Tempo operacional

| Medida | Tempo |
|---|---:|
| Média por exame | 51,82 s |
| Mínimo | 44,37 s |
| Máximo | 99,23 s |

Todos os exames permaneceram abaixo do limite operacional de três minutos.

## Artefatos

```text
casos/webapp/benchmarks/9a736ea3cfee/benchmark_report.json
casos/webapp/benchmarks/9a736ea3cfee/metrics_subtype.json
casos/webapp/benchmarks/9a736ea3cfee/cases.jsonl
casos/webapp/benchmarks/9a736ea3cfee/run_manifest.json
casos/webapp/benchmarks/9a736ea3cfee/summary.md
```

## Interpretação metodológica obrigatória

Este teste comprova que o fluxo real do frontend funciona de ponta a ponta e
que as métricas binárias e multiclasse são calculadas e exibidas corretamente.

Entretanto, os 25 casos LLD-MMRI pertencem ao universo de desenvolvimento do
classificador de produção. O resultado de 96,43% é **in-sample** e não pode ser
apresentado como estimativa de generalização ou validação externa.

A estimativa defensável fora da amostra dentro do desenvolvimento permanece o
nested-OOF documentado. Para demonstrar 75% de identificação de subtipo como
resultado científico independente será necessária uma nova coorte pública com
os quatro subtipos, completamente separada do treinamento.

**Uso:** pesquisa, com revisão humana obrigatória. Não usar para diagnóstico.
