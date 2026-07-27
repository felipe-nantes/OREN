# V21 — resultado externo do braço positivo LiverHccSeg

Data da avaliação: 2026-07-18.

## Autorização e integridade

A avaliação foi executada somente após autorização explícita para o protocolo:

```text
54cbca7db12d8c4dd32d9319b54320098b4d5ee14928fa93270e7837f2955022
```

O protocolo assinado vincula exatamente:

- os 14 casos preparados sem máscaras de lesão;
- as predições cegas congeladas;
- o calibrador v11 congelado;
- o hash esperado do audit público LiverHccSeg;
- a obrigação de manter o holdout OpenSwissHCC fechado.

O avaliador exige tanto o arquivo do protocolo quanto a assinatura
explicitamente autorizada. Alterar qualquer predição, calibrador, manifesto ou
hash faz a avaliação abortar antes da leitura protegida.

## Resultado

```text
casos positivos: 14
verdadeiros positivos: 11
falsos negativos: 3
sensibilidade: 78,57%
IC 95% Wilson: 52,41%–92,43%
gate nominal de sensibilidade >= 75%: PASS
```

O resultado pontual supera a meta de sensibilidade. Entretanto, o limite
inferior do intervalo de confiança está abaixo de 75%, refletindo o tamanho
pequeno da amostra. A evidência é promissora, mas ainda não demonstra com
precisão estreita que a sensibilidade populacional seja pelo menos 75%.

## Tempo operacional

```text
média: 33,13 s/caso
mediana: 31,80 s/caso
P95 por posto mais próximo: 51,93 s/caso
máximo: 51,93 s/caso
gate <= 180 s: PASS
```

O tempo soma TotalSegmentator, MedSigLIP e MedGemma 1.5 4B, executados em
estágios separados para respeitar a GPU de 8 GB.

## O que este resultado não prova

O LiverHccSeg selecionado contém somente casos tumor-positivos. Por isso:

```text
specificity: null
roc_auc: null
simultaneous_75_75_gate_evaluated: false
qualified: false
```

Não é metodologicamente válido combinar diretamente estes positivos com CHAOS
e declarar uma matriz de confusão primária, porque classe e dataset ficariam
confundidos e os protocolos de RM são diferentes. O CHAOS pode ser usado apenas
como braço secundário de estresse de especificidade e mudança de domínio.

## Estado da meta

```text
sensibilidade pontual >= 75%: demonstrada no braço externo positivo
tempo máximo <= 180 s: demonstrado
especificidade >= 75%: ainda não avaliada externamente nesta v21
meta simultânea 75%/75%: ainda não demonstrada
holdout OpenSwissHCC: fechado
```

O próximo passo prático é medir o comportamento em controles públicos como
estresse secundário e, depois de congelar definitivamente todo o protocolo,
executar uma única avaliação no holdout OpenSwissHCC com positivos e negativos
da mesma coorte.

## Artefatos autoritativos

```text
data/qualification/liverhccseg_v21_positive_evaluation_protocol.json
data/qualification/liverhccseg_v21_positive_evaluation/evaluation.json
data/qualification/liverhccseg_v21_positive_evaluation/report.md
```

```text
evaluation.json sha256:
735dda355fd1a6761dc11ccafc1f44fcb06aa6ff78f6024167522699f35ed9b0

scores sha256:
e88580e542ca8e42552d8e3ba637c9f68a6254530ade26a69e5d105b2f0b6d00

protected selection audit sha256:
7eafc841f8ebaa603741d6019e5a8ac24ba4cbd576ffddd4849997c0d0c68083
```

## Validação de software

```text
791 passed
396 warnings conhecidos
0 falhas
```

