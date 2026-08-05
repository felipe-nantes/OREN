# Auditoria externa e cobertura axial monofásica

**Data:** 4 de agosto de 2026  
**Estado:** concluído; braços reprovados não promovidos

## Baseline reproduzido

No conjunto OpenSwissHCC completo já consumido, o classificador MedSigLIP
monofásico tardio obteve:

| Métrica | Resultado |
|---|---:|
| Sensibilidade | 25,40% (16/63) |
| Especificidade | 81,16% (56/69) |
| ROC-AUC | 0,655 |
| Falhas técnicas | 5 |

O conjunto não é mais uma validação externa intacta. Ele é usado somente como
desenvolvimento retrospectivo.

## Auditoria dos falsos negativos

Foram encontrados 47 falsos negativos: 31 no desenvolvimento e 16 no antigo
holdout. As máscaras públicas de lesão do desenvolvimento foram usadas somente
depois da inferência. As máscaras do holdout permaneceram fechadas.

Em 29 dos 31 falsos negativos de desenvolvimento, ao menos um plano enviado ao
classificador intersectava a lesão pública. Dois casos não possuíam máscara
venosa pública auditável. Portanto, o gargalo predominante é reconhecimento da
lesão visível, e não ausência completa da lesão nos 27 cortes amostrados.

```text
audit_signature = 8f4d64ab765497a5c4c9c170a923f60bfacbef084e26f29fc3a789ad1a6a9450
holdout_lesion_masks_opened = false
lesion_masks_used_for_inference = false
```

## Representação axial individual

Foi derivado um tile tardio/venoso 448×448 para cada plano hepático do atlas
v17 já aprovado. O canal azul contém a fase tardia nos painéis multifásicos; nos
fallbacks venosos os três canais são idênticos.

| Item | Resultado |
|---|---:|
| Casos | 87 |
| Cortes | 4.652 |
| Cobertura axial | 100% em 87/87 |
| Ground truth lido na derivação | não |
| Máscara de lesão lida | não |

```text
dataset_signature   = 50422764b34819e725e8aba265539929c35ad1f772fede0039e9ad079d2a3133
embedding_signature = bb13ed0264786404e03ba89f7312825f308600082de8b2c5f9960708eeda2d43
```

## Avaliação nested OOF

| Métrica | Painéis globais | Cortes individuais |
|---|---:|---:|
| Sensibilidade | 56,41% | 53,85% |
| Especificidade | 61,22% | 63,27% |
| Balanceada | 58,82% | 58,56% |
| ROC-AUC | 0,689 | 0,616 |

O braço axial não passou 75%/75% e não foi promovido.

```text
prediction_signature = 067456674093b867c9c1b9210cb84e3c2d2e50057f8470384870b2a92fd94d1b
evaluation_signature = 8763bd6e2c5b89a692f543d7299c113fc27d914c6c269d845a8dbc8e92c54539
```

## Fusão exploratória

| Regra | Sensibilidade | Especificidade |
|---|---:|---:|
| Qualquer leitor positivo (OR) | 69,23% | 44,90% |
| Ambos positivos (AND) | 41,03% | 79,59% |

As regras não atingem a meta conjunta. O próximo ramo permitido é evidência
ortogonal real (T2, DWI e ADC), com registro físico, seleção interna aos folds e
hard negatives por domínio. Aumentar novamente a cobertura tardia ou ajustar um
threshold no conjunto completo não é uma intervenção metodologicamente válida.
