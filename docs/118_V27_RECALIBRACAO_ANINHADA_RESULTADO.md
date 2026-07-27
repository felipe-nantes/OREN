# V27 — recalibração aninhada dos sinais congelados

## Objetivo

Testar se os sinais já produzidos pelas versões v23–v26 continham informação
complementar suficiente para formar um decisor final acima de 75% de
sensibilidade e 75% de especificidade, sem nova inferência e sem usar o caso
avaliado no ajuste.

O protocolo foi congelado antes da geração das predições:

```text
c1bab29b40b32294ffc01bcf0d7161fcc8a37bf53c0a15c8d09423790d1e198d
```

## Método

O candidato primário usou 25 sinais congelados:

- quatro sinais determinísticos da família v23;
- probabilidades e consistência entre os três painéis liver-enriched v24;
- probabilidades, consistência e campos estruturados pathology-target v25;
- os mesmos sinais do leitor pathology-target + RAG v26.

Foi aplicada regressão logística com:

- balanceamento de classes;
- padronização ajustada apenas no treino externo;
- regularização L2 escolhida entre `0.01, 0.1, 1, 10 e 100`;
- seleção da regularização por validação interna estratificada de cinco folds;
- limiar calculado somente a partir das predições internas out-of-fold;
- LOOCV por paciente como estimador primário;
- 50 repetições de cinco folds como teste de estabilidade.

O label do paciente externo não participou da padronização, ajuste do modelo,
seleção da regularização ou seleção do limiar. As duas falhas técnicas
preexistentes permaneceram no denominador e contaram como erros. Nenhuma
máscara de lesão foi aberta.

## Resultado primário

Matriz de confusão:

```text
TP = 39
TN = 38
FP = 31
FN = 24
```

| Métrica | Resultado |
|---|---:|
| Sensibilidade | 61,90% |
| Especificidade | 55,07% |
| Acurácia balanceada | 58,49% |
| ROC-AUC | 0,6264 |
| Repetições que atingiram 75/75 | 0/50 |
| Sensibilidade mediana 50×5 | 61,90% |
| Especificidade mediana 50×5 | 57,97% |
| Sensibilidade mínima 50×5 | 44,44% |
| Especificidade mínima 50×5 | 47,83% |

IC 95% por bootstrap:

- sensibilidade: 49,21%–73,02%;
- especificidade: 43,48%–66,67%.

O candidato falhou nos dois eixos e ficou abaixo do v23 puro da coorte
completa, que obteve 65,08% de sensibilidade e 60,87% de especificidade.

## Ablações predeclaradas

| Família | Sensibilidade | Especificidade | Balanced accuracy | AUC |
|---|---:|---:|---:|---:|
| v23 bruto recalibrado | 66,67% | 60,87% | 63,77% | 0,6181 |
| v23 + v24 liver-enriched | 60,32% | 59,42% | 59,87% | 0,6117 |
| v23 + v25 pathology-target | 61,90% | 60,87% | 61,39% | 0,6352 |
| v23 + v26 pathology-target + RAG | 60,32% | 57,97% | 59,14% | 0,6579 |
| todos os sinais, candidato primário | 61,90% | 55,07% | 58,49% | 0,6264 |

Nenhuma ablação atingiu 75/75. A melhor acurácia balanceada entre as
recalibrações foi a família v23 bruta, ainda sem superar de forma relevante o
v23 original. Os leitores v24–v26 não forneceram ganho incremental estável.

## Conclusão

A tentativa foi metodologicamente válida, reproduzível e sem vazamento do caso
avaliado, mas foi rejeitada. O resultado mostra que o problema atual não é
apenas escolher pesos ou limiar melhores: os sinais 4B congelados não contêm
separação suficiente e estável na coorte OpenSwissHCC completa.

Não é correto reajustar novamente famílias, regularização ou limiar usando os
mesmos 132 casos e reapresentá-los como uma confirmação nova. O melhor resultado
histórico de 82,05%/79,17% continua verdadeiro apenas para os 87 casos de
desenvolvimento daquele experimento; ele não se sustentou na coorte ampliada.

O próximo avanço justificável precisa introduzir informação nova, não nova
calibração dos mesmos sinais. As opções mais defensáveis são:

1. transferir o protocolo visual congelado para o MedGemma 27B no Mac;
2. gerar um leitor visual com discriminação realmente diferente do 4B;
3. obter uma nova coorte para confirmação depois de congelar o candidato;
4. manter o v23 como referência atual até que uma dessas opções seja avaliada.

## Artefatos

```text
configs/benchmark/openswisshcc_v27_nested_recalibration_protocol_v1.json
casos/qualification/openswisshcc_v1/prepared/v27_nested_recalibration_predictions_v1
casos/qualification/openswisshcc_v1/evaluation/v27_nested_recalibration_v1/evaluation.json
```

Assinaturas:

```text
protocolo:
c1bab29b40b32294ffc01bcf0d7161fcc8a37bf53c0a15c8d09423790d1e198d

freeze das predições:
555399b273bd2224709188c3a5305ce5861547d42102cb32b94906daabd78248

avaliação:
6d8e4c39a0c51cbc6dbb6cd18a6300cb5f8f03cb80e924bc72bc3616dd7ff68f
```
