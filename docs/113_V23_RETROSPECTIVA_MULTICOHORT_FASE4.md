# V23 retrospectiva multicohort — Fase 4

Data: 23 de julho de 2026  
Uso: pesquisa, com revisão humana obrigatória

## Objetivo

Avaliar o v23 na coorte OpenSwissHCC completa sem medir cada caso com um
transform ou limiar ajustado usando o próprio caso.

O estimador principal foi LOOCV por paciente:

1. retirar um paciente;
2. ajustar referências ECDF usando somente os casos computáveis do treino;
3. escolher o limiar usando somente labels do treino;
4. calcular o score do paciente retirado;
5. repetir para os 132 pacientes;
6. congelar todas as predições antes de calcular as métricas finais.

Os pesos permaneceram fixos:

```text
80% v11
+
20% candidate_weighted_linearity
```

Também foram congeladas 6.600 predições out-of-fold do protocolo 50×5-fold e
132 predições secundárias usando o calibrador v23 original.

## Freeze das predições

Diretório:

```text
casos/qualification/openswisshcc_v1/prepared/retrospective_multicohort_phase4_predictions_v1
```

Assinatura:

```text
247c36a87c56b2a0e6a6797611b83d88c77369936875e32f2181c14a9e093347
```

Cobertura:

| Item | Total |
|---|---:|
| Casos | 132 |
| Scores computáveis | 130 |
| Falhas técnicas sem score fabricado | 2 |
| Predições LOOCV | 132 |
| Predições 50×5-fold | 6.600 |
| Predições com calibrador congelado | 132 |

Nenhuma linha de predição contém o label do caso. O código registra
explicitamente que o label do paciente retirado não participa do ECDF nem da
seleção do limiar.

## Resultado principal

Diretório:

```text
casos/qualification/openswisshcc_v1/evaluation/retrospective_multicohort_phase4_v1
```

Assinatura da avaliação:

```text
78231c8aafae61ae551b0c16fea85a540d69b656cc890f5e14eef7e0fe22b9e4
```

### LOOCV — 132 casos

| Métrica | Resultado |
|---|---:|
| Verdadeiros positivos | 41 |
| Falsos negativos | 22 |
| Verdadeiros negativos | 42 |
| Falsos positivos | 27 |
| Sensibilidade | 65,08% |
| Especificidade | 60,87% |
| Acurácia balanceada | 62,97% |
| ROC-AUC nos 130 casos computáveis | 0,6866 |
| Falhas técnicas contabilizadas como erro | 2 |

IC 95% de Wilson:

- sensibilidade: 52,75%–75,67%;
- especificidade: 49,07%–71,52%.

O gate estatístico de 75%/75% não foi atingido.

### Robustez 50×5-fold

| Métrica | Resultado |
|---|---:|
| Execuções que atingiram 75%/75% | 0/50 |
| Sensibilidade mediana | 66,67% |
| Especificidade mediana | 60,87% |
| Sensibilidade mínima | 60,32% |
| Especificidade mínima | 57,97% |

### Calibrador v23 original — estimando secundário

| Métrica | Resultado |
|---|---:|
| Sensibilidade | 77,78% |
| Especificidade | 60,87% |
| Acurácia balanceada | 69,32% |

O calibrador congelado preservou sensibilidade acima de 75%, mas não resolveu a
especificidade. Esse resultado não substitui o LOOCV principal.

## Diagnóstico de domínio

Como verificação de software, a execução restrita aos mesmos 87 casos
historicamente processáveis do desenvolvimento reproduziu exatamente o v23
anterior:

```text
sensibilidade = 82,05%
especificidade = 79,17%
```

Isso confirma que a implementação do score não mudou.

Quando os 132 casos entram juntos no procedimento out-of-fold, a distribuição
dos 44 casos do antigo holdout modifica ECDF e limiares. Uma análise descritiva
posterior ao resultado mostrou:

| Subconjunto histórico | Sensibilidade | Especificidade |
|---|---:|---:|
| development, usando o OOF conjunto | 69,23% | 75,51% |
| holdout consumido, usando o OOF conjunto | 58,33% | 25,00% |

Esse diagnóstico não é uma nova métrica de qualificação nem será usado para
remover casos. Ele mostra que o ganho anterior dependia fortemente da
distribuição dos 87 casos de desenvolvimento e não foi estável na ampliação da
coorte.

## Conclusão metodológica

A tentativa é válida e reproduzível, mas o v23 puro falhou no gate principal.
O resultado anterior de 82,05%/79,17% era verdadeiro para a coorte de
desenvolvimento usada naquele experimento, porém não se sustentou na
retrospectiva OpenSwissHCC completa.

Não se deve ajustar o peso ou o limiar olhando os erros desta avaliação e
reapresentar o mesmo conjunto como confirmação.

O próximo passo permitido pelo contrato é iniciar uma nova família candidata
v24, com as ablações previamente ordenadas:

1. v23 + painéis liver-enriched;
2. adicionar pathology-target;
3. adicionar RAG textual;
4. recalibração aninhada somente dentro dos folds de treino.

O gate de tempo end-to-end desde DICOM bruto permanece pendente e só será
executado para uma configuração que primeiro demonstre sinal estatístico
suficiente.
