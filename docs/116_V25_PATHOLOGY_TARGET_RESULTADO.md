# V25 — resultado do candidato pathology-target

## Hipótese testada

O candidato predeclarado:

```text
v23 + painéis liver-enriched + prompt/schema pathology-target
```

reutilizou exatamente os 390 painéis verificados do v24. A única mudança de
inferência foi o alvo clínico e o schema, com instruções explícitas para não
tratar vaso, variante anatômica, pseudolesão ou artefato isolado como patologia
alvo.

O RAG permaneceu desativado. O sinal contínuo foi combinado conforme a regra
previamente congelada:

```text
score =
    0,80 × família v23
  + 0,20 × ECDF(max_panel_choice_probability_POSITIVA_pathology_target)
```

Nenhum peso foi reajustado após os resultados.

## Execução 4B

- 130 casos processáveis.
- 390 chamadas.
- Zero novas falhas.
- Duas falhas técnicas anteriores mantidas como erros.
- Tempo médio: 25,19 segundos por caso.
- Tempo máximo: 25,44 segundos.
- Todos os casos abaixo de 180 segundos.
- Predições discretas: 120 `POSITIVA` e 10 `NEGATIVA`.
- Labels e máscaras de lesão permaneceram fechados durante a inferência.

Assinaturas:

- protocolo:
  `2e598c1648ecf2e9104c5d0bfc21baaa14405c44656d64ec2525533a087680f5`
- execução:
  `96cdbe078252338bad6d2ce8ba073d36ce2f7cd2306570d481814da535fcd224`
- verificação:
  `c2e5fa49c20b4daf84796966d5f9c9b114c957a3ce3f580bf17d7bda12c66399`

## Avaliação LOOCV

Matriz de confusão:

```text
TP = 38
TN = 40
FP = 29
FN = 25
```

Resultados:

- sensibilidade: 60,32%;
- especificidade: 57,97%;
- acurácia balanceada: 59,14%;
- ROC-AUC nos 130 casos computáveis: 0,6564;
- IC 95% da sensibilidade: 47,62%–71,43%;
- IC 95% da especificidade: 46,38%–69,57%.

Validação repetida 50×5:

- 0 de 50 repetições atingiram 75%/75%;
- sensibilidade mediana: 63,49%;
- especificidade mediana: 59,42%;
- menor sensibilidade observada: 58,73%;
- menor especificidade observada: 56,52%.

## Comparação

```text
                              sensibilidade   especificidade   pior eixo
v23 puro                         65,08%          60,87%         60,87%
v24 liver-enriched               61,90%          59,42%         59,42%
v25 pathology-target             60,32%          57,97%         57,97%
```

## Conclusão

O prompt pathology-target alterou a decisão discreta na direção pretendida
(dez negativos em vez de um), mas o sinal contínuo não separou melhor as
classes. Após normalização e limiar ajustados somente no treino, ambos os eixos
ficaram abaixo do v23 e do v24.

O candidato foi rejeitado. Não é metodologicamente válido editar novamente o
prompt ou o peso usando estes mesmos resultados e apresentá-lo como validação
independente.

Pela ordem predeclarada, o próximo experimento permitido é:

```text
v23 + liver-enriched + pathology-target + RAG textual
```

Esse próximo candidato só será útil se o contexto recuperado produzir um sinal
contínuo mais discriminativo; melhorar apenas a quantidade de respostas
`NEGATIVA` não é suficiente.
