# V26 — resultado do candidato pathology-target + RAG textual

## Hipótese

O terceiro candidato predeclarado preservou:

- a família de sinais v23;
- os 390 painéis liver-enriched previamente verificados;
- o prompt/schema pathology-target;
- a fusão fixa de 80% do v23 e 20% do novo leitor.

A única adição foi o contexto RAG textual local e auditado:

- índice BM25 `liver_mri_rag_v1`;
- seis consultas fixas;
- dez fontes recuperadas;
- critérios de HCC, hemangioma, FNH, DWI/ADC, fases dinâmicas e
  pseudolesões/perfusão.

O contexto e o prompt foram congelados antes da inferência.

## Execução 4B

- 130 casos processáveis;
- 390 chamadas;
- zero novas falhas;
- duas falhas técnicas anteriores mantidas como erros;
- tempo médio: 48,06 segundos;
- tempo máximo: 62,19 segundos;
- todos os casos abaixo de 180 segundos;
- 130 decisões discretas `POSITIVA`;
- nenhuma máscara de lesão aberta ou enviada ao modelo.

Assinaturas:

- protocolo:
  `0cfda1b7ddfb8460df237d32cf5d54fbad1b066f2ca40c880e5211dd3082a776`
- execução:
  `71529185dd484243a57eaaf1589933658c2d5a5d95608f359223a0b33cd64bd1`
- verificação:
  `d7af4196492c4ab1657c1b4ec284e6ec22453d92aa2ebb3fdd5cb1c49b327c0d`

## Avaliação LOOCV

```text
TP = 41
TN = 42
FP = 27
FN = 22
```

- sensibilidade: 65,08%;
- especificidade: 60,87%;
- acurácia balanceada: 62,97%;
- ROC-AUC nos 130 casos computáveis: 0,6752;
- IC 95% da sensibilidade: 52,38%–76,19%;
- IC 95% da especificidade: 49,28%–72,46%.

Validação repetida 50×5:

- 0/50 repetições atingiram 75%/75%;
- sensibilidade mediana: 68,25%;
- especificidade mediana: 60,87%;
- sensibilidade mínima: 60,32%;
- especificidade mínima: 56,52%.

## Comparação

```text
                              sensibilidade   especificidade   pior eixo
v23 puro                         65,08%          60,87%         60,87%
v24 liver-enriched               61,90%          59,42%         59,42%
v25 pathology-target             60,32%          57,97%         57,97%
v26 pathology-target + RAG       65,08%          60,87%         60,87%
```

## Conclusão

O RAG recuperou a perda introduzida pelos candidatos v24/v25, mas não superou o
v23 puro e não atingiu 75%/75%. A decisão discreta ficou ainda mais saturada:
todos os casos foram classificados como positivos pelo leitor. A fusão
contínua conseguiu recuperar o desempenho do v23, mas não acrescentou ganho
independente.

O candidato foi rejeitado pelo gate congelado. Não é válido ajustar novamente
o prompt, as consultas ou o peso de 20% usando estes mesmos resultados como se
fossem uma nova validação.

O próximo e último candidato da ordem predeclarada é a recalibração aninhada
dos sinais já congelados. Ela deve aprender pesos e regularização somente
dentro de cada partição externa de treino, sem usar o caso avaliado, e precisa
superar 75% de sensibilidade e 75% de especificidade de forma out-of-fold.
