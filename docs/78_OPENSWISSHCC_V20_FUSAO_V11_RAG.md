# OpenSwissHCC v20 — fusão cega v11 + RAG v19

## Hipótese predefinida

O v11 é o melhor candidato 4B observado, mas ficou um verdadeiro positivo abaixo
de 75% de sensibilidade no LOOCV. O v19 acrescenta contexto textual RAG a uma
entrada visual com cobertura comprovada. Antes de abrir os resultados do v19, o
v20 fixa a seguinte fusão:

| Sinal | Peso |
|---|---:|
| MedGemma v4 — margem de incerteza | 0,32 |
| MedSigLIP v5 — sagital invertido | 0,32 |
| Localizador v10 — log do volume | 0,16 |
| MedGemma v19 — log-odds atlas + RAG | 0,20 |

Os três pesos do v11 foram multiplicados por 0,8, preservando sua proporção. O
novo leitor recebe 0,2. Não haverá busca de pesos depois dos labels.

Cada componente será transformado por ECDF usando somente o treino do fold. O
limiar também será escolhido somente no treino. A métrica primária será LOOCV e
a robustez exigirá 50/50 repetições estratificadas passando 75%/75%.

## Tempo e segurança

```text
tempo conservador = máximo v11 + máximo v19
85,3486 s + 19,0979 s = 104,4465 s
gate de 180 s: aprovado por projeção conservadora
tempo DICOM end-to-end: ainda não comprovado para v20
```

O bundle contém somente sinais cegos e hashes. Ground truth, máscaras de lesão,
subtipos protegidos e holdout não são permitidos. A avaliação exige autorização
explícita independente após o protocolo estar assinado.

## Artefatos congelados

O bundle cego foi construído para os 87 casos, sem decisão ou métrica:

```text
SHA-256 dos sinais:
b226d7382f0f9e49dbcadfc24f056cd455d6e3c66fb9eb0e295f3599a02912b7

ground truth lido: não
holdout aberto: não
tempo conservador: 104,4465 s
```

O protocolo foi congelado com assinatura:

```text
be8652b3a96070b3821c8780fef3985a4f2be26f0d10cc93443de8e924fa6750
```

O vetor de quatro sinais está vinculado pelo hash:

```text
a6d892300f5e99c521f9f3a9fcf549fb5ca8b35d4521a311da5de8fb2528027d
```

Os pesos, transformações, estimadores, limiar e gate de robustez não poderão ser
alterados depois da abertura dos labels.

## Preflight do bloqueio protegido

O bundle e o protocolo reais foram validados pelo avaliador. Sem a flag explícita,
a execução abortou antes de ler labels:

```text
[ABORTADO] Abertura dos labels protegidos para v20 não foi autorizada.
```

Com a flag e um caminho sintético contendo `holdout`, o caminho também foi
recusado antes de qualquer leitura:

```text
[ABORTADO] Avaliador v20 aceita somente development_labels.jsonl, nunca holdout.
```

Nenhum diretório de avaliação foi criado.

## Resultado protegido

Após autorização explícita vinculada à assinatura, o v20 obteve por LOOCV:

```text
sensibilidade: 69,23%
especificidade: 77,08%
repetições passando 75%/75%: 0/50
gate de desenvolvimento: reprovado
holdout aberto: não
```

O v20 não foi promovido; o v11 permanece o melhor candidato 4B. A análise
completa está em `docs/79_OPENSWISSHCC_V19_V20_RESULTADOS.md`.
