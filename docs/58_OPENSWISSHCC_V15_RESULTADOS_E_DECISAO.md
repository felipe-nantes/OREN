# OpenSwissHCC v15 — resultados e decisão

Data da avaliação: 16 de julho de 2026.

## Escopo autorizado

Os 87 labels protegidos de desenvolvimento foram abertos exclusivamente para avaliar o protocolo v15 previamente congelado e assinado:

```text
7e3914c332a1a997234e89e2e10a19625764fbd4e8437a58df30477adf66621e
```

O holdout permaneceu fechado.

## Coorte

- casos: 87;
- positivos: 39;
- negativos: 48;
- uso: somente pesquisa;
- revisão humana: obrigatória.

## Resultado primário

O candidato primário combinava, com peso igual, o leitor v11 e o score volumétrico v15. Toda transformação e todo limiar foram ajustados somente nos folds de treino.

| Métrica LOOCV | Resultado |
|---|---:|
| Verdadeiros positivos | 22 |
| Falsos negativos | 17 |
| Verdadeiros negativos | 29 |
| Falsos positivos | 19 |
| Sensibilidade | 56,41% |
| Especificidade | 60,42% |
| Acurácia balanceada | 58,41% |
| Menor métrica do gate | 56,41% |

Intervalos de confiança de Wilson de 95%:

- sensibilidade: 40,98% a 70,70%;
- especificidade: 46,31% a 72,98%.

O candidato não atingiu sensibilidade ≥75% nem especificidade ≥75%.

## Robustez

Repeated stratified 5-fold, com 50 repetições totalmente aninhadas:

| Medida | Resultado |
|---|---:|
| Repetições que atingiram 75%/75% | 0/50 |
| Sensibilidade mediana | 56,41% |
| Especificidade mediana | 60,42% |
| Sensibilidade mínima | 51,28% |
| Especificidade mínima | 54,17% |

A falha não foi marginal nem dependente de uma única divisão da coorte.

## Diagnósticos secundários

Os diagnósticos abaixo foram pré-especificados como não elegíveis para substituir o candidato primário.

| Leitor | Sensibilidade | Especificidade | TP/FN | TN/FP |
|---|---:|---:|---:|---:|
| v11 isolado, LOOCV | 74,36% | 75,00% | 29/10 | 36/12 |
| v15 isolado, LOOCV | 53,85% | 54,17% | 21/18 | 26/22 |
| v15 categórico bruto | 10,26% | 43,75% | 4/35 | 21/27 |

O v15 categórico bruto produziu 44 resultados `INCONCLUSIVA`. Conforme o protocolo, cada inconclusivo foi contado como erro na métrica correspondente.

## Tempo

- tempo conservador combinado: 102,3612 segundos;
- gate temporal: 180 segundos;
- resultado: aprovado.

O objetivo de tempo foi cumprido, mas o objetivo de desempenho não foi.

## Complementaridade exploratória

A comparação das predições fora da amostra mostrou:

| Relação | Casos |
|---|---:|
| Ambos corretos | 38 |
| Somente v11 correto | 27 |
| Somente v15 correto | 9 |
| Ambos errados | 13 |

Entre os erros do v11, o v15 corrigiu:

- 4 casos positivos;
- 5 casos negativos;
- 9 casos no total.

Entre os erros do v15, o v11 corrigiu:

- 12 casos positivos;
- 15 casos negativos;
- 27 casos no total.

Um oráculo que soubesse qual leitor está certo alcançaria 84,62% de sensibilidade e 85,42% de especificidade. Isso **não é uma métrica de modelo**, pois a escolha do leitor correto exige conhecer o ground truth.

Foi testada uma única regra exploratória sem parâmetro ajustável: em discordância, escolher o leitor mais distante de seu limiar treinado; empates permanecem com o v11. A regra reproduziu 56,41% de sensibilidade e 60,42% de especificidade. Nenhuma busca adicional de pesos, margens ou exceções foi realizada.

## Interpretação

O score volumétrico v15 contém alguma informação complementar, mas sua confiança global não identifica de forma confiável quando essa informação está correta. A fusão igual e a arbitragem por distância do limiar transferiram muitos erros do v15 para o v11.

Além disso, a limitação para 32 cortes resolveu o tempo, mas reduziu a cobertura do volume preparado. Isso pode contribuir para perda de lesões pequenas ou evidências distribuídas, embora o experimento atual não isole causalmente esse fator.

## Decisão metodológica

```text
development_gate_passed = false
holdout_opened = false
qualified = false
```

Consequências:

1. o protocolo v15 é rejeitado;
2. nenhum peso ou limiar será reajustado retrospectivamente;
3. o holdout não será aberto;
4. o v15 não substituirá o v11;
5. o resultado negativo será preservado para auditoria.

## Próxima direção recomendada

O v11 permanece o melhor candidato e está a um verdadeiro positivo adicional do limiar de 75% de sensibilidade, mantendo exatamente 75% de especificidade. A próxima hipótese não deve ser outra fusão global com o v15.

A direção recomendada é um leitor de evidência localizada:

1. usar candidatos do localizador apenas como regiões de atenção, nunca como ground truth;
2. apresentar ao MedGemma pares ou pequenos blocos da mesma região entre fases/sequências;
3. pedir decisão focal `lesão versus vaso/variante/artefato`;
4. agregar candidatos de forma determinística ao nível do caso;
5. preservar o v11 como leitor principal e avaliar o novo componente separadamente antes de qualquer ensemble;
6. congelar representação, prompt, agregação e gate antes da nova rodada;
7. usar o desenvolvimento como conjunto iterativo e reservar o holdout para uma única confirmação final.

Essa abordagem ataca a principal deficiência observada: o score global não localiza nem explica qual evidência deve corrigir o v11.

## Artefatos e hashes

- Avaliação: `casos/qualification/openswisshcc_v1/evaluations/dev_v15_fusion87/evaluation.json`
- Features: `casos/qualification/openswisshcc_v1/evaluations/dev_v15_fusion87/case_features.csv`
- SHA-256 da avaliação: `615CF988A114FC792C950529FE73780A4658D08EEF9175589B77245C52B8FA5B`
- SHA-256 das features: `D5283585FDA102BB9343FAEBB67D87A3F6D0981A8996D0EBC36194FA885FB3A0`
- SHA-256 do protocolo: `1C7F696757009546188F82076B1FB8704DAA78541A816FBDD62A1233609FDB21`
- SHA-256 dos labels protegidos: `406A746124C10BF6B8A43D4A2B500D9582F22A6DC01529CCB7B27769C8E32020`

## Estado de segurança

- `ground_truth_read=true` somente para desenvolvimento autorizado;
- `metrics_calculated=true`;
- `holdout_opened=false`;
- `research_only=true`;
- `clinical_use_allowed=false`;
- `requires_human_review=true`.
