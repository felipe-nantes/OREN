# OpenSwissHCC v16 — resultados e diagnóstico

Data: 2026-07-17  
Estado: gate de acurácia reprovado; holdout fechado  
Uso: pesquisa com revisão humana obrigatória

## 1. Autorização e integridade

Foi autorizada a abertura exclusiva de `development_labels.jsonl` para avaliar os 87 casos pelo protocolo v16 assinado:

`a6953feb887e5a649a8f44edf3e75f11d70a9ff1f045f57db9d3dc0209a8cea5`

O holdout permaneceu fechado. Nenhum score, limiar, prompt, peso ou regra de agregação foi alterado após a abertura dos labels.

Coorte:

- positivos: 39;
- negativos: 48;
- total: 87;
- SHA-256 dos labels de desenvolvimento: `406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020`.

## 2. Resultado primário

O sinal primário congelado foi o maior log-odds `POSITIVA/NEGATIVA` entre os candidatos do caso. O limiar de cada decisão LOOCV foi ajustado somente nos outros 86 casos.

| Métrica LOOCV | Resultado |
|---|---:|
| TP | 19 |
| FN | 20 |
| TN | 21 |
| FP | 27 |
| Sensibilidade | **48,72%** |
| Especificidade | **43,75%** |
| Acurácia balanceada | 46,23% |
| Gate simultâneo 75%/75% | **reprovado** |

Intervalos de confiança Wilson de 95%:

- sensibilidade: 33,87% a 63,80%;
- especificidade: 30,70% a 57,72%.

## 3. Robustez

Validação estratificada 5-fold repetida 50 vezes, com limiar ajustado dentro de cada treino:

| Métrica | Resultado |
|---|---:|
| Repetições aprovadas em 75%/75% | **0/50** |
| Sensibilidade mediana | 48,72% |
| Especificidade mediana | 43,75% |
| Sensibilidade mínima | 41,03% |
| Especificidade mínima | 41,67% |

A falha não é marginal nem causada por uma única divisão da coorte.

## 4. Diagnósticos secundários predefinidos

### Limiar zero dos log-odds

- sensibilidade: 25,64%;
- especificidade: 64,58%;
- TP/FN: 10/29;
- TN/FP: 31/17.

### Classificação categórica do candidato selecionado

- sensibilidade: 25,64%;
- especificidade: 58,33%;
- TP/FN: 10/29;
- TN/FP: 28/20;
- inconclusivos: 3, contados como erro.

Esses diagnósticos não podem substituir o resultado primário.

## 5. Tempo

O scoring dos candidatos preparados passou o gate:

- mínimo: 20,3923 s;
- mediana: 65,0938 s;
- média: 56,9085 s;
- máximo: 109,0265 s;
- casos abaixo de 180 s: 87/87.

O caminho completo desde DICOM cru ainda não foi medido ponta a ponta; por isso o objetivo operacional total continua não comprovado.

## 6. Análise exploratória pós-hoc

Esta seção explica a falha, mas não pode promover retrospectivamente outra configuração.

### Separação do score

- AUC do score v16: 44,15%;
- AUC com sinal invertido: 55,85%;
- mediana nos positivos: -0,2500;
- mediana nos negativos: -0,1875;
- correlação de Spearman entre quantidade de candidatos e score: aproximadamente 0,39.

O score não ordena adequadamente positivos acima de negativos. Invertê-lo também não produz discriminação suficiente.

### Quantidade de candidatos

| Candidatos | Casos | Positivos | Negativos | AUC exploratória |
|---:|---:|---:|---:|---:|
| 1 | 13 | 9 | 4 | 41,67% |
| 2 | 12 | 6 | 6 | 76,39% |
| 3 | 59 | 24 | 35 | 45,95% |
| 5 | 3 | 0 | 3 | não calculável |

O subgrupo de dois candidatos é pequeno e não pode sustentar seleção de modelo. Nos três casos com cinco candidatos, todos negativos, a regra por máximo produziu falso positivo no limiar aparente.

### Agregações alternativas

Análises pós-hoc com máximo, média, mediana, primeiro candidato e mínimo produziram AUC entre 40,22% e 48,85%. Portanto, o problema não se resolve apenas trocando a agregação.

Sinais alternativos derivados das mesmas probabilidades — `P(POSITIVA)`, `P(INCONCLUSIVA)`, `1-P(NEGATIVA)` e margens entre classes — também ficaram próximos ou abaixo do acaso. O melhor sinal não invertido testado atingiu AUC de aproximadamente 50,37%.

## 7. Relação com a v11

A v11 permanece o melhor candidato observado:

- sensibilidade LOOCV: 74,36%;
- especificidade LOOCV: 75,00%;
- faltou um verdadeiro positivo para ultrapassar 75% de sensibilidade.

Comparação caso a caso:

| Situação | Casos |
|---|---:|
| v11 e v16 corretas | 28 |
| somente v11 correta | 37 |
| somente v16 correta | 12 |
| ambas erradas | 10 |

A v16 corrige 12 erros da v11, mas quebra 37 acertos. Um oráculo que conhecesse o ground truth atingiria 92,31% de sensibilidade e 85,42% de especificidade, porém isso não é uma métrica realizável. Não foi identificado sinal confiável para decidir quando usar a v16.

## 8. Interpretação causal

Os resultados rejeitam três explicações simples:

1. **Limiar inadequado:** até o melhor limiar aparente ficou em 48,72%/45,83%.
2. **Agregação por máximo como única causa:** outras agregações continuaram sem discriminação.
3. **Falta de tempo/contexto:** o modelo recebeu os stacks previstos e terminou com ampla margem temporal.

Restam duas hipóteses principais:

1. o localizador não coloca pelo menos um candidato sobre a lesão verdadeira em quantidade suficiente dos positivos;
2. os candidatos cobrem as lesões, mas o MedGemma 4B não consegue distingui-las de parênquima, vaso, variante ou artefato nessa representação.

Sem medir a sobreposição candidato–máscara de lesão, não é possível separar essas causas.

## 9. Próximo passo recomendado

Não abrir o holdout e não executar nova fusão global.

Executar uma auditoria retrospectiva do localizador usando as máscaras públicas de lesão somente após a inferência:

- recall por caso: ao menos um candidato toca/cobre a lesão;
- IoU e fração da lesão coberta;
- distância centro do candidato–centro da lesão;
- recall por tamanho da lesão;
- recall por quantidade de candidatos e por fallback;
- nenhuma máscara enviada ao MedGemma.

Decisão após a auditoria:

- se o recall de candidatos for baixo, corrigir o localizador/gerador de evidências antes de outra inferência;
- se o recall for alto, o gargalo é o leitor 4B e o próximo teste deve usar a mesma entrada congelada no 27B do Mac para isolar capacidade do modelo;
- preservar a v11 como baseline principal;
- usar nova coorte pública independente para desenvolvimento adicional sempre que possível, reduzindo sobreajuste aos mesmos 87 labels.

A abertura das máscaras de lesão exige autorização específica e não autoriza o holdout.

## 10. Artefatos

- avaliação: `casos/qualification/openswisshcc_v1/evaluations/dev_v16_candidate_volume_full87_4b_v1/evaluation.json`;
- scores por caso: `casos/qualification/openswisshcc_v1/evaluations/dev_v16_candidate_volume_full87_4b_v1/case_scores.csv`;
- SHA-256 da avaliação: `2bc476420679f76092820b3ba42008db14b13fe508193b039debca99369b0346`;
- SHA-256 dos scores: `8a1149a40d1b6563ed757072028b0dceca3ee12950f1a8705386b76629e109e9`;
- `holdout_opened=false`;
- `qualified=false`;
- `development_accuracy_gate_passed=false`.
