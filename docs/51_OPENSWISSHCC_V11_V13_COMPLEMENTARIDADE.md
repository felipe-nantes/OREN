# OpenSwissHCC — complementaridade exploratória v11 × v13

Data: 2026-07-15

## Escopo

Esta análise usa somente os 87 casos de desenvolvimento, cujos labels já foram
abertos para as avaliações v11 e v13. O holdout permaneceu fechado.

O objetivo é diagnosticar se as decisões categóricas do v13 conseguem corrigir
de forma identificável os erros LOOCV do v11. Nenhuma regra de ensemble foi
selecionada.

## Reprodução do v11

A função LOOCV congelada do protocolo v11 reproduziu:

- TP = 29;
- FN = 10;
- TN = 36;
- FP = 12;
- sensibilidade = 74,36%;
- especificidade = 75,00%.

Assinatura do protocolo v11:

`e161db5eb6e30245d1dd4ac9f5e0ff4662ae6b48a6a880b5b1ddab1f8599393a`

## Correção de erros entre leitores

| Situação | Casos |
|---|---:|
| Ambos corretos | 26 |
| Somente v11 correto | 39 |
| Somente v13 correto | 9 |
| Ambos errados ou v13 inconclusivo | 13 |

O v13 corrigiu nove erros do v11:

- cinco casos positivos;
- quatro casos negativos.

O v11 corrigiu 39 erros ou inconclusivos do v13:

- 14 positivos;
- 25 negativos.

## Teto-oráculo

Se um oráculo soubesse, após ver o ground truth, qual leitor escolher em cada
caso, o teto seria:

- sensibilidade: 34/39 = 87,18%;
- especificidade: 40/48 = 83,33%.

Esse valor não é uma métrica do modelo e não pode ser reportado como desempenho
do ARGOS. Ele demonstra somente que há erros não idênticos entre as rotas.

## Tabela cruzada

| v11 | v13 | Positivos reais | Negativos reais | Total |
|---|---|---:|---:|---:|
| `NEGATIVA` | `INCONCLUSIVA` | 3 | 7 | 10 |
| `NEGATIVA` | `NEGATIVA` | 2 | 11 | 13 |
| `NEGATIVA` | `POSITIVA` | 5 | 18 | 23 |
| `POSITIVA` | `INCONCLUSIVA` | 7 | 2 | 9 |
| `POSITIVA` | `NEGATIVA` | 7 | 4 | 11 |
| `POSITIVA` | `POSITIVA` | 15 | 6 | 21 |

As discordâncias não oferecem uma regra categórica útil:

- trocar v11 negativo por v13 positivo recuperaria cinco positivos, mas criaria
  18 falsos positivos;
- trocar v11 positivo por v13 negativo recuperaria quatro negativos, mas
  criaria sete falsos negativos;
- tratar discordância como inconclusiva aumentaria os erros na métrica
  primária.

## Limitação técnica decisiva

Os artefatos v13 persistiram somente `resultado_hipotese`. Não há:

- probabilidade por classe;
- margem entre positiva e negativa;
- confiança calibrável;
- score contínuo de evidência.

Logo, não existe informação suficiente para identificar antecipadamente os
nove casos em que o v13 corrige o v11.

## Decisão

Um ensemble categórico v11+v13 não é justificável e não será promovido a
candidato de qualificação.

O v13 permanece útil como resultado negativo de pesquisa: aumentar a entrada
para até 50 cortes T1 venosos manteve o tempo abaixo de 180 segundos, mas não
melhorou a classificação.

Qualquer candidato futuro deve ser congelado antes de nova avaliação e precisa
fornecer um sinal contínuo auditável ou uma nova fonte de evidência. O holdout
deve permanecer fechado até que sensibilidade e especificidade de
desenvolvimento atinjam 75% com estabilidade.

