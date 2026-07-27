# OpenSwissHCC v17 — resultados de desenvolvimento

## Autorização e integridade

Os 87 labels protegidos de desenvolvimento foram abertos somente após
autorização explícita para o protocolo assinado:

```text
3b4a9afafec6c7a90f85f151ffaf088705a27321d8142eab79fd805840067457
```

O holdout permaneceu fechado. Nenhuma nova inferência, alteração de prompt ou
mudança de score ocorreu depois da abertura dos labels.

```text
casos:      87
positivos:  39
negativos:  48
labels SHA: 406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020
```

## Resultado primário predefinido

O estimador primário foi leave-one-out, com o limiar ajustado somente nos outros
86 casos de cada fold.

| Medida | Resultado | Meta |
|---|---:|---:|
| Sensibilidade | 41,03% | ≥75% |
| Especificidade | 45,83% | ≥75% |
| Acurácia balanceada | 43,43% | — |
| Menor das duas métricas | 41,03% | ≥75% |

Matriz de confusão:

```text
TP = 16
FN = 23
TN = 22
FP = 26
```

Intervalos de confiança de Wilson de 95%:

```text
sensibilidade: 27,08% a 56,58%
especificidade: 32,58% a 59,71%
```

O gate de desenvolvimento **falhou**.

## Diagnósticos secundários

```text
ROC-AUC aparente: 0,4428
limiar aparente: -2,2500
sensibilidade aparente: 43,59%
especificidade aparente: 45,83%
```

O argmax bruto classificou os 87 casos como negativos:

```text
sensibilidade: 0%
especificidade: 100%
```

Os diagnósticos secundários não substituem o resultado primário.

## Tempo

```text
máximo do leitor sobre atlas pré-computado: 11,1798 s
gate de 180 s: aprovado
end-to-end desde DICOM: ainda não provado para v17
```

## Interpretação metodológica

A auditoria retrospectiva anterior provou cobertura de 100% dos voxels das 74
lesões públicas nos 37 casos positivos anotados, incluindo todas as lesões
menores que 10 mm. Portanto, a falha v17 não é explicada por ausência das lesões
nos cortes apresentados.

O sinal contínuo do 4B não separou positivos e negativos nesta representação. A
AUC abaixo de 0,5 também mostra que apenas trocar o limiar não recuperará a meta
de 75/75. Inverter o sinal pós-hoc seria uma nova hipótese e, mesmo assim, a AUC
equivalente seria apenas aproximadamente 0,557.

## Decisão

- não abrir o holdout;
- não promover o v17 ao webapp;
- não alegar acurácia de 75%;
- preservar os resultados como experimento negativo válido;
- investigar sinais complementares já congelados e localizadores
  determinísticos no conjunto de desenvolvimento;
- qualquer v18 deverá ser congelado antes de eventual avaliação de holdout.

Artefatos:

```text
casos/qualification/openswisshcc_v1/evaluations/dev_v17_axial_atlas_v1/evaluation.json
casos/qualification/openswisshcc_v1/evaluations/dev_v17_axial_atlas_v1/case_scores.csv
```
