# OpenSwissHCC holdout v21 — resultado final e decisão metodológica

## Estado

O protocolo v21 foi executado e avaliado nos 44 casos congelados do holdout
OpenSwissHCC. As predições e o protocolo foram assinados antes da abertura
tardia dos labels. Nenhuma máscara pública de lesão foi aberta ou usada.

```text
protocol_signature: 7911331092e23fb6c9ea91b8b622a74a9cdfaaa34b52909ad25060ecf1b1b782
label_authorization_signature: 3af12c444faa5646b8dec0f1112ff0636b0fd11e4c50c92364fa88ea7f5a019b
labels_opened_after_freeze: true
lesion_masks_read: 0
lesion_masks_used: false
```

## Correção da distribuição protegida

O primeiro gate de materialização abortou ao encontrar 24 positivos e 20
negativos, pois o avaliador esperava incorretamente 19/25. A auditoria mostrou
que 19/25 vinha do fixture sintético de teste, não do arquivo público oficial.

O loader autoritativo considera um sujeito positivo quando qualquer linha do
`participants.tsv` possui `HCC=1`. Ele valida a distribuição completa de 63
positivos e 69 negativos. Nos sujeitos congelados `sub-045` a `sub-088`, os
casos `sub-048` a `sub-071` são positivos: 24 positivos e 20 negativos.

Foram corrigidos somente:

- as contagens protegidas do avaliador tardio;
- o fixture e as expectativas dos testes;
- a documentação da distribuição.

Predições, sinais, calibrador, limiar, hashes e assinatura do protocolo não
foram alterados. A correção passou em 14 testes focais antes da nova
materialização.

## Resultado primário

```text
casos: 44
positivos: 24
negativos: 20
TP: 20
TN: 7
FP: 13
FN: 4
sensibilidade: 83,33%
especificidade: 35,00%
acurácia: 61,36%
ROC-AUC: 0,4979
```

Intervalos de confiança de Wilson de 95%:

```text
sensibilidade: 64,15% a 93,32%
especificidade: 18,12% a 56,71%
acurácia: 46,62% a 74,28%
```

Tempo por caso:

```text
média: 38,25 s
mediana: 35,90 s
p95: 53,08 s
máximo: 78,42 s
limite: 180 s
```

Gates:

```text
sensibilidade >= 75%: aprovado
especificidade >= 75%: reprovado
tempo <= 180 s: aprovado
qualificação conjunta: reprovada
```

## Diagnóstico retrospectivo dos sinais

Esta auditoria foi executada somente depois do freeze e da abertura autorizada
dos labels. Ela serve para explicar a falha; não autoriza retunar o v21 neste
holdout.

ROC-AUC dos sinais disponíveis:

| Sinal | ROC-AUC |
|---|---:|
| MedSigLIP, maior probabilidade axial | 0,6375 |
| Localizador, log do volume candidato | 0,5938 |
| MedSigLIP, média axial | 0,5646 |
| MedSigLIP, média de todas as vistas | 0,5562 |
| MedGemma, `P(NEGATIVA)` | 0,5531 |
| MedSigLIP, probabilidade sagital | 0,5021 |
| Fusão v21 congelada | 0,4979 |
| MedGemma, `P(POSITIVA)-P(NEGATIVA)` | 0,4719 |
| MedGemma, `P(POSITIVA)` | 0,4698 |
| MedGemma, `P(INCONCLUSIVA)-P(NEGATIVA)` | 0,4552 |

O calibrador v21 usava:

```text
40% MedGemma: P(INCONCLUSIVA) - P(NEGATIVA)
40% MedSigLIP: -P(positiva na vista sagital)
20% localizador: log1p(volume candidato)
```

Os dois sinais com 80% do peso ficaram praticamente aleatórios no holdout. O
localizador marcou candidatos em 42/44 casos e, isoladamente, também não
separou as classes com a qualidade necessária.

## Auditoria de limiar

Foi testada retrospectivamente a fronteira de todos os limiares possíveis,
sem publicar um novo protocolo:

| Sinal | Algum limiar atinge 75%/75%? | Melhor mínimo entre sens./esp. |
|---|---|---:|
| Fusão v21 | não | 45,0% |
| MedGemma `P(POSITIVA)` | não | 50,0% |
| MedGemma positiva menos negativa | não | 50,0% |
| MedSigLIP máximo axial | não | 60,0% |
| MedSigLIP média axial | não | 54,17% |
| Localizador | não | 62,5% |

Para a fusão v21, o melhor ponto com sensibilidade de 75% teria
especificidade de apenas 45%. Portanto, trocar somente o limiar não resolve o
problema.

## Conclusão

O MedGemma 1.5 4B com o protocolo v21 não está qualificado para a meta do
projeto. O resultado válido é:

```text
sensibilidade aprovada + tempo aprovado + especificidade reprovada
```

O holdout v21 está consumido. Ele não pode ser reutilizado para escolher pesos,
features, prompts ou limiares do protocolo sucessor. Qualquer análise adicional
nele deve ser declarada retrospectiva e exploratória.

## Próximo ciclo permitido

O protocolo sucessor deve ser desenvolvido exclusivamente nos 87 casos de
desenvolvimento e nas coortes públicas externas já preparadas. As prioridades
são:

1. abandonar os dois sinais dominantes que não generalizaram;
2. gerar representação com localização focal real, sem máscara de lesão na
   inferência;
3. separar explicitamente HCC/lesão focal de cirrose, vasos, artefatos e
   variantes anatômicas;
4. usar sequências originais e evidência temporal, não somente um painel RGB;
5. exigir validação interna aninhada e estabilidade por subgrupo antes de
   congelar um sucessor;
6. avaliar o sucessor em uma nova coorte independente, nunca selecionar pelo
   desempenho retrospectivo deste holdout;
7. transportar o mesmo protocolo congelado ao Mac e comparar o MedGemma 27B
   sem alterar a representação ou o ground truth.

## Artefatos e validação

```text
evaluation.json SHA-256:
a6c096e29a25951d79d05114fe63adb7fe3304d9113d8788137dd4b338c9132c

report.md SHA-256:
3955622d80eed74fbbf268ccb0714aa5a0bba2131d657135296ea8972d1d9bb5

authorization.json SHA-256:
fafeeb8897524bfafb8c04aaeae2330c5e410c9358a71520eaf54bd13fa5c7ca

holdout_labels.jsonl SHA-256:
9cd81bdc01286c2d57ffd27408dec14441118b043cb76f3780c7e61287d0596f
```

Após a correção do avaliador e a geração do resultado real, a suíte completa
foi reexecutada:

```text
867 testes aprovados
0 falhas
396 avisos de depreciação
72,82 segundos
```
