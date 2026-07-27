# OpenSwissHCC v11 — resultado protegido e teto das abordagens sem treino

## Escopo autorizado

Foi autorizada explicitamente a abertura de:

```text
development_labels.jsonl
```

exclusivamente para avaliar os 87 casos de desenvolvimento pelo protocolo v11
congelado. O holdout permaneceu fechado antes, durante e depois da avaliação.

Nenhum peso, componente, direção, transformação ou regra de threshold foi
alterado após a abertura dos labels.

## Preflight congelado

Antes da avaliação foram confirmados:

- 87 casos cegos;
- `ground_truth_read=false` no bundle;
- `holdout_opened=false`;
- SHA-256 do resumo cego:
  `95177db344109ca46d183c09721c012dcb0a3215b9d8c26bcb06844cc5908dbf`;
- SHA-256 do protocolo:
  `60def4536e59786a4b5bbc809debf2c3cc3470dfe8862762a607257402e429dc`;
- assinatura canônica do protocolo:
  `e161db5eb6e30245d1dd4ac9f5e0ff4662ae6b48a6a880b5b1ddab1f8599393a`.

## Coorte

| Classe | Casos |
|---|---:|
| HCC presente | 39 |
| HCC ausente | 48 |
| Total | 87 |

O caso 72 continuou sendo a única exclusão técnica, definida e assinada antes da
abertura dos labels.

## Fusão avaliada

| Sinal cego | Peso congelado |
|---|---:|
| MedGemma v4 — `P(INCONCLUSIVA) - P(NEGATIVA)` | 0,40 |
| MedSigLIP v5 — probabilidade sagital invertida | 0,40 |
| Localizador v10 — `log1p(volume candidato)` | 0,20 |

Cada componente foi convertido por ECDF usando somente o treino do fold. A fusão
foi a média ponderada e o threshold também foi escolhido somente no treino.

## Resultado aparente

O ajuste em todo o desenvolvimento encontrou threshold `0,5241379310`:

| Medida | Resultado |
|---|---:|
| Verdadeiros positivos | 30 |
| Falsos negativos | 9 |
| Verdadeiros negativos | 37 |
| Falsos positivos | 11 |
| Sensibilidade | 76,92% |
| Especificidade | 77,08% |
| Acurácia balanceada | 77,00% |

Esse resultado aparente passou 75%/75%, mas não é a estimativa primária porque o
mesmo conjunto participou da transformação e do threshold.

## Resultado primário LOOCV

| Medida | Resultado |
|---|---:|
| Verdadeiros positivos | 29 |
| Falsos negativos | 10 |
| Verdadeiros negativos | 36 |
| Falsos positivos | 12 |
| Sensibilidade | **74,36%** |
| Especificidade | **75,00%** |
| Acurácia balanceada | 74,68% |
| Gate simultâneo 75%/75% | **reprovado** |

A sensibilidade ficou um verdadeiro positivo abaixo do mínimo: seriam
necessários 30/39 positivos corretamente classificados para atingir 76,92%; o
LOOCV obteve 29/39.

Intervalos de Wilson de 95%:

- sensibilidade: 58,92% a 85,43%;
- especificidade: 61,22% a 85,08%.

## Estabilidade em 50 repetições

| Medida | Resultado |
|---|---:|
| Repetições que passaram 75%/75% | **12/50** |
| Mediana da sensibilidade | 74,36% |
| Mediana da especificidade | 75,00% |
| Menor sensibilidade | 69,23% |
| Menor especificidade | 68,75% |

O protocolo exigia 50/50 repetições aprovadas. A v11 não demonstrou estabilidade
suficiente mesmo estando próxima do corte no LOOCV.

## Tempo e segurança

- soma conservadora dos maiores tempos dos componentes: 85,3486 s;
- gate de 180 s: aprovado;
- `holdout_opened=false`;
- `qualified=false`;
- `research_only=true`;
- `clinical_use_allowed=false`;
- `requires_human_review=true`.

O gargalo permanece a generalização discriminativa, não a latência.

## Artefatos

```text
casos/qualification/openswisshcc_v1/evaluation/dev_v11_fusion87/evaluation.json
casos/qualification/openswisshcc_v1/evaluation/dev_v11_fusion87/case_features.csv
```

- SHA-256 de `evaluation.json`:
  `5aa1bb13d1ebf44131025af1b3338078dd8852a2f0f2a6437e82aa02dc055cdc`;
- SHA-256 de `case_features.csv`:
  `10a38b0ae64b741ea4ec4be53cab4219331e7394514da36ca6324bfe03ce01c7`;
- SHA-256 dos labels protegidos de desenvolvimento:
  `406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020`.

## Decisão metodológica

1. A v11 não está qualificada.
2. O holdout não pode ser aberto.
3. Não escolher outro threshold usando os mesmos 87 labels.
4. Não ajustar pesos 40/40/20 após observar este resultado.
5. Não procurar sucessivamente novas combinações entre v4, v5, v9 e v10 no
   mesmo desenvolvimento.
6. Registrar como atingido o teto observado das abordagens atuais sem treino.
7. Preservar a v11 como melhor candidato experimental reprodutível: ela melhorou
   substancialmente sobre v9 e v10, mas não sustentou o gate pré-declarado.

## Próximo caminho cientificamente defensável

Para continuar buscando 75%/75%, é necessário mudar a fonte de informação ou o
desenho experimental, não apenas recalibrar a mesma coorte. As opções defensáveis
são:

1. obter uma nova coorte pública de desenvolvimento, independente do holdout,
   para desenvolver uma nova hipótese sem reutilizar repetidamente os mesmos 87
   labels;
2. usar um detector/encoder de lesão hepática treinado ou adaptado para RM,
   mantendo o MedGemma 4B como leitor e gerador do relatório;
3. reconsiderar LoRA/QLoRA ou aprendizado supervisionado quando houver dados,
   infraestrutura e revisão especializada;
4. publicar o resultado atual como estudo experimental negativo/limítrofe, com
   revisão humana obrigatória e sem afirmar desempenho de 75%.

Sem uma dessas mudanças, abrir o holdout ou ajustar novamente a v11 aumentaria o
risco de sobreajuste e invalidaria a alegação científica.
