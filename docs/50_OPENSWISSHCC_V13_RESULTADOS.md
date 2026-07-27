# OpenSwissHCC v13 — resultado da entrada 3D nativa

Data da avaliação: 2026-07-15

## Conclusão

O protocolo v13 cumpriu o limite operacional de 180 segundos, mas não cumpriu
o gate de desempenho. A configuração está rejeitada como candidata à
qualificação.

O holdout permaneceu fechado e não pode ser aberto com este resultado.

## Coorte e abertura tardia dos labels

- 87 casos inferidos antes da abertura do ground truth;
- 39 casos positivos e 48 negativos;
- um caso tecnicamente excluído antes da inferência:
  `anon-openswiss-cb2c5c63fc28b8ee`;
- o arquivo protegido contém os 87 casos avaliados e esse único registro
  adicional, cuja exclusão foi informada explicitamente ao avaliador;
- nenhum caso inferido ficou sem label;
- `INCONCLUSIVA` foi contada como erro na métrica primária;
- labels abertos somente depois da validação integral das 87 previsões;
- holdout não lido.

## Métricas primárias

| Métrica | Resultado | Gate |
|---|---:|---:|
| Sensibilidade | **51,28%** | 75% |
| IC95% da sensibilidade | 36,20%–66,13% | — |
| Especificidade | **31,25%** | 75% |
| IC95% da especificidade | 19,95%–45,33% | — |
| Acurácia | 40,23% | — |
| Cobertura decisiva | 78,16% | — |
| Inconclusivos | 19/87 (21,84%) | contam como erro |

O gate conjunto de sensibilidade e especificidade falhou.

## Matriz de confusão penalizada

|  | Predição positiva/erro positivo | Predição negativa/erro negativo |
|---|---:|---:|
| Verdade positiva | TP = 20 | FN = 19 |
| Verdade negativa | FP = 33 | TN = 15 |

Detalhamento categórico:

| Verdade | `POSITIVA` | `NEGATIVA` | `INCONCLUSIVA` |
|---|---:|---:|---:|
| Positiva (39) | 20 | 9 | 10 |
| Negativa (48) | 24 | 15 | 9 |

Mesmo removendo os inconclusivos apenas para uma análise secundária, o
desempenho continuou insuficiente:

- sensibilidade decisions-only: 68,97%;
- especificidade decisions-only: 38,46%;
- acurácia decisions-only: 51,47%.

## Tempo

| Estatística | Resultado |
|---|---:|
| Mínimo | 91,2307 s |
| Média | 139,4026 s |
| Mediana | 145,3736 s |
| P95 | 147,8211 s |
| Máximo | 149,4518 s |
| Casos aprovados no teto de 180 s | 87/87 |

O gate temporal passou com margem de 30,5482 segundos no pior caso.

## Integridade e assinaturas

- bundle:
  `0e647375dd48d11c30f28e63f7fd55cf2a07510f2ce0f6cee642d2b2b7bc2f2e`;
- protocolo:
  `11616f927c361f13852607395e3861060b1cf957ffe7a9ffc45ace013dffe9e3`;
- progresso da inferência:
  `2cd3e5dac3c3b54b8b994cea73d74dfc4eec3b2809d2433c794b17c5254998ba`;
- resumo da inferência:
  `82d6c307acc8f6008eab49f6c04d3c74a4fae12a6a1e07c81ed0a9fc5863893e`;
- labels de desenvolvimento:
  `406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020`;
- avaliação final:
  `86ccc32393a25706ecb5e91707fd7b1373e2da17d8b962b0477609400ed43336`.

Artefatos autoritativos:

`casos/qualification/openswisshcc_v1/evaluation/dev_v13_highdimensional87/`

## Interpretação restrita aos dados observados

A entrada T1 venosa 3D com até 50 cortes não resolveu o gargalo de
classificação no desenvolvimento:

- perdeu 19 dos 39 positivos quando inconclusivos são penalizados;
- classificou incorretamente 33 dos 48 negativos;
- produziu 19 respostas inconclusivas;
- o problema não foi o tempo, timeout ou falha técnica.

Portanto, aumentar a dimensionalidade visual por si só não foi suficiente. O
v13 não deve substituir o v11 e não justifica nova tentativa no holdout.

## Próximo passo metodologicamente permitido

Os labels de desenvolvimento já foram abertos para esta análise. É permitido
usar esses 87 casos para pesquisa exploratória, desde que uma nova configuração
seja declarada como desenvolvimento e validada posteriormente em dados
independentes.

A próxima análise deve medir a complementaridade entre os erros v11 e v13:

1. comparar os pares de predição por caso;
2. calcular quantos erros v11 são corrigidos ou agravados pelo v13;
3. estimar o teto-oráculo apenas como diagnóstico, nunca como métrica do modelo;
4. somente propor um ensemble se houver ganho consistente em validação cruzada;
5. manter o holdout fechado durante toda essa exploração.

