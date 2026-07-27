# OpenSwissHCC v18-v2 — resultados formais

## Escopo e integridade

O protocolo v18-v2 foi avaliado somente após autorização explícita para abrir os
rótulos protegidos dos 87 casos de desenvolvimento. O holdout permaneceu fechado.

```text
protocolo: v18-v2 — atlas axial em blocos
assinatura: f84fe44d0cb26f20620dc81092702485eb571d70eb7e567b0889a4df3c05ac6b
casos: 87
positivos: 39
negativos: 48
holdout aberto: não
uso: pesquisa, com revisão humana obrigatória
```

O avaliador verificou os hashes, a cobertura exata dos frames, a ausência de
duplicações, as probabilidades de cada bloco, o cálculo de log-odds, a regra de
agregação pelo maior score, a quantidade de requisições e os tempos registrados.

## Resultado primário

O sinal primário congelado foi o maior log-odds `POSITIVA/NEGATIVA` entre os
blocos do caso. O limiar foi estimado por LOOCV: para cada caso, somente os outros
86 casos foram usados para selecionar o limiar.

| Métrica | Resultado |
|---|---:|
| Verdadeiros positivos | 16 |
| Falsos negativos | 23 |
| Verdadeiros negativos | 20 |
| Falsos positivos | 28 |
| Sensibilidade | 41,03% |
| Especificidade | 41,67% |
| Acurácia balanceada | 41,35% |
| Meta simultânea 75%/75% | **não atingida** |

Intervalos de confiança de Wilson de 95%:

```text
sensibilidade: 27,08% a 56,58%
especificidade: 28,85% a 55,72%
```

## Diagnósticos secundários

Os diagnósticos secundários não podem substituir o resultado primário:

```text
ROC-AUC aparente: 0,4271

limiar aparente:
  sensibilidade: 43,59%
  especificidade: 41,67%

argmax bruto:
  TP: 11
  FN: 28
  TN: 34
  FP: 14
  sensibilidade: 28,21%
  especificidade: 70,83%
  inconclusivos: 1, contado como erro
```

A ROC-AUC abaixo de 0,5 confirma que o score contínuo dos blocos não ordena os
casos positivos acima dos negativos de forma útil neste conjunto.

## Gate de tempo

O tempo medido corresponde ao leitor 4B sobre o atlas já pré-computado, não ao
pipeline DICOM completo.

```text
requisições: 207
mínimo por caso: 4,8696 s
mediana por caso: 7,5227 s
média por caso: 7,6448 s
máximo por caso: 11,1118 s
casos abaixo de 180 s: 87/87
gate de tempo do leitor: aprovado
gate end-to-end DICOM de 180 s: ainda não demonstrado
```

## Interpretação

O experimento respondeu negativamente à hipótese do v18: apresentar o atlas em
blocos menores não resolveu a diluição de lesões focais observada no v17. O
protocolo é tecnicamente estável e rápido, mas não tem discriminação diagnóstica
suficiente e não deve ser promovido para o fluxo principal nem para o holdout.

Em comparação, o v11 continua sendo o melhor candidato histórico do 4B, com
74,36% de sensibilidade e 75,00% de especificidade por LOOCV. Ele ainda falha a
meta por um verdadeiro positivo e também não está qualificado para uso final.

Os resultados v17 e v18 indicam que aumentar ou fragmentar a cobertura visual,
isoladamente, não supera o teto atual do leitor 4B. Continuar ajustando variantes
no mesmo conjunto de desenvolvimento aumentaria o risco de sobreajuste sem
evidência de ganho generalizável.

## Decisão

```text
v18-v2 promovido: não
meta 75%/75% atingida: não
tempo do leitor <= 180 s: sim
tempo end-to-end <= 180 s comprovado: não
holdout autorizado: não
holdout aberto: não
qualificado: não
```

O próximo passo defensável é preservar o v11 como candidato 4B mais forte e
transferir os protocolos congelados para avaliação do 27B no Mac, usando o mesmo
conjunto de desenvolvimento e mantendo o holdout fechado. Para uma nova tentativa
com o 4B, deve-se preferir evidência independente ou uma mudança de capacidade
material — por exemplo, um localizador supervisionado validado — em vez de novos
ajustes pós-rótulo no mesmo desenvolvimento.

