# V24 — resultado do sinal liver-enriched complementar

## Execução congelada

O candidato v24 preservou o classificador v23 e acrescentou, sem ajuste
posterior aos resultados:

```text
score_v24 =
    0,80 × score_v23
  + 0,20 × ECDF(max_panel_choice_probability_POSITIVA)
```

As ECDFs e os limiares foram ajustados exclusivamente dentro de cada partição
externa de treino.

## Inferência MedGemma 1.5 4B

- 130 casos processáveis.
- 390 chamadas, três painéis por caso.
- Duas falhas técnicas anteriores preservadas e contabilizadas como erros.
- 130 relatórios válidos.
- Zero falhas novas.
- Tempo médio por caso: 21,28 segundos.
- Maior tempo por caso: 22,56 segundos.
- Todos os casos abaixo de 180 segundos.
- Predição discreta: 129 `POSITIVA` e uma `NEGATIVA`.
- O sinal contínuo foi preservado; a decisão discreta não foi usada diretamente
  como classificador final.
- Nenhuma máscara de lesão foi aberta ou enviada ao modelo.

Assinaturas:

- protocolo de inferência:
  `930aa632e80e2d179c5fd9101559465c535872b581618d860f87d45b8431fa8c`
- execução:
  `aa6e23089dd18afae1909197654990f15ba42fad06b96af744a8f73ba6d3e093`
- verificação independente:
  `1f078a93e59dc909bf1446c12c912b094f24728b3a93afa89dc86f8e49b77547`

## Avaliação LOOCV

Matriz de confusão:

```text
TP = 39
TN = 41
FP = 28
FN = 24
```

Resultados:

- sensibilidade: 61,90%;
- especificidade: 59,42%;
- acurácia balanceada: 60,66%;
- ROC-AUC nos 130 casos computáveis: 0,6464;
- IC 95% da sensibilidade: 49,21%–73,02%;
- IC 95% da especificidade: 47,83%–71,01%.

Na validação repetida 50×5:

- 0 de 50 repetições atingiram simultaneamente 75%/75%;
- sensibilidade mediana: 63,49%;
- especificidade mediana: 59,42%.

## Comparação com o v23 puro

```text
                    sensibilidade   especificidade   pior eixo
v23 puro               65,08%          60,87%         60,87%
v24 liver-enriched      61,90%          59,42%         59,42%
```

O candidato reduziu os dois eixos e, portanto, foi rejeitado pelo protocolo
previamente congelado.

## Conclusão

O leitor liver-enriched 4B, nesta formulação, não adiciona informação
discriminativa útil ao v23. A saída discreta quase sempre positiva confirma que
o leitor continua reagindo a achados visuais não específicos. Mesmo usando a
probabilidade contínua e normalização somente no treino, o sinal reduziu a AUC
e o pior eixo.

Não se deve reajustar o peso de 20% sobre estes mesmos resultados. O próximo
candidato predeclarado deve ser testado como uma nova hipótese: prompt/schema
`pathology-target`, mantendo painéis, coorte, regras de tempo e isolamento de
labels.
