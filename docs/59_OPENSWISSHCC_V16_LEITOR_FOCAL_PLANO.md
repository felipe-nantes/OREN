# OpenSwissHCC v16 — plano do leitor focal volumétrico multissequência

Data: 16 de julho de 2026.

## Motivação

O v11 permanece o melhor baseline, com 74,36% de sensibilidade e 75,00% de especificidade. O v15 global volumétrico cumpriu o tempo, mas degradou o desempenho para 56,41%/60,42% quando combinado ao v11.

A análise de complementaridade mostrou que o v15 corrige alguns erros, mas seu score global não identifica quando está correto. A v16 muda a unidade de análise:

```text
volume hepático inteiro → candidato focal localizado
```

Ela não é uma nova regra sobre os scores v11/v15. É uma nova representação visual, centrada em regiões propostas por um localizador público e nunca por ground truth.

## Hipótese

Um pequeno volume multissequência centrado no mesmo ponto físico permitirá ao MedGemma 1.5 4B diferenciar melhor:

- lesão focal verdadeira;
- vaso contínuo;
- variante anatômica;
- alteração de perfusão;
- gordura focal;
- artefato ou efeito de volume parcial.

## Fontes de evidência

Cada candidato usará, quando tecnicamente disponível:

| Grupo | Frames axiais |
|---|---:|
| T1 nativo | 5 |
| T1 arterial registrado no venoso | 5 |
| T1 venoso | 5 |
| T1 tardio registrado no venoso | 5 |
| T2 nativo | 3 |
| DWI TRACE de maior ordem disponível | 3 |
| ADC nativo | 3 |
| Máximo total | 29 |

Os frames serão ordenados por grupo e por deslocamento relativo ao centro. O prompt declarará explicitamente os intervalos de frames de cada sequência.

## Geometria e renderização

- centro definido no espaço físico LPS;
- referência anatômica: T1 venoso;
- arterial e tardio: registros já auditados para o T1 venoso;
- T1 nativo, T2, TRACE e ADC: centro físico transformado para a geometria nativa;
- crop: 80 mm × 80 mm;
- saída: 384 × 384 pixels, RGB derivado de escala de cinza;
- janela: percentis 1 e 99 calculados conjuntamente em todos os frames do mesmo grupo e candidato;
- nenhum contorno ou pixel sintético será enviado ao modelo;
- grupos fora do FOV ou sem contraste útil serão omitidos e registrados, nunca inventados.

## Seleção adaptativa de candidatos

O run cego do localizador v10 contém:

- 80 casos com candidatos;
- 7 casos sem candidato;
- até 13 componentes por caso.

Regra pré-especificada:

1. ordenar componentes por volume decrescente;
2. usar todos quando existirem até três;
3. quando existirem mais de três, incluir pelo menos os três maiores;
4. continuar até cobrir ≥75% do volume total da máscara candidata;
5. limitar a cinco candidatos;
6. abortar se cinco candidatos não atingirem 75%.

Auditoria cega dessa regra:

- cobertura mínima: 76,92%;
- casos abaixo de 75%: 0;
- média de candidatos nos 80 casos positivos do localizador: 2,775;
- casos que exigem cinco candidatos: 3;
- casos que exigem quatro candidatos: 0.

Nos sete casos sem candidato, será construída uma única pilha fallback centrada no centroide da máscara hepática. O fallback será explicitamente identificado e não será tratado como lesão proposta.

## Gate técnico do bundle

Cada candidato/fallback deverá comprovar:

- T1 venoso válido;
- pelo menos três grupos T1 dinâmicos utilizáveis;
- pelo menos um grupo morfológico utilizável;
- entre 5 e 29 frames reais;
- todos os frames ≤384×384;
- hashes e bytes válidos;
- correspondência entre centro físico e índices de cada grupo;
- janela única por grupo;
- ausência de PHI;
- ausência de máscara de lesão pública/manual;
- origem da máscara candidata exclusivamente no localizador v10;
- `ground_truth_read=false`;
- `holdout_opened=false`.

Qualquer falha invalida o caso antes da inferência.

## Prompt focal

O prompt será único e congelado. Ele orientará o modelo a:

1. analisar somente o candidato central;
2. verificar continuidade tubular nos frames adjacentes;
3. comparar a mesma região entre fases T1;
4. verificar concordância em T2, DWI e ADC;
5. não transformar vaso, variante, perfusão ou artefato em positivo;
6. classificar `POSITIVA` somente se houver evidência focal coerente;
7. usar `INCONCLUSIVA` quando a evidência for insuficiente ou conflitante.

O score continuará sendo obtido pelo contrato restrito de primeiro token em uma única passagem direta:

```text
POSITIVA | NEGATIVA | INCONCLUSIVA
```

## Agregação

Para cada candidato:

```text
candidate_log_odds = log((P(POSITIVA)+1e-8)/(P(NEGATIVA)+1e-8))
```

Score do caso:

```text
case_score = máximo candidate_log_odds
```

A interpretação é determinística: uma lesão focal verdadeira em qualquer candidato deve elevar o score do caso. Nenhum peso será ajustado entre candidatos.

O v16 será avaliado primeiro de forma isolada. Ele não poderá substituir nem combinar-se ao v11 antes de demonstrar valor fora da amostra.

## Tempo

Orçamento inicial conservador:

| Estágio | Teto observado/planejado |
|---|---:|
| Registro de fases | 14,16 s |
| Localizador | 41,92 s |
| Preparação/renderização | 5,00 s |
| MedGemma focal | a medir no piloto |

O piloto deverá medir casos com um, três e cinco candidatos. A execução full87 só será autorizada se o pior caso projetado permanecer ≤180 segundos.

## RAG e GraphRAG

RAG textual e GraphRAG não entrarão na primeira pontuação visual v16, porque não recuperam uma lesão ausente ou mal representada.

Após o piloto visual, eles poderão ser adicionados como contexto congelado e auditável contendo apenas:

- critérios de continuidade vascular;
- mimetizadores de lesão;
- padrões de realce e washout;
- relação entre DWI e ADC;
- limitações por sequência ausente.

Qualquer contexto deverá ter source IDs, hashes e texto fixo antes da inferência. Não haverá recuperação dinâmica baseada em labels ou resultados do caso.

## Etapas

1. implementar gerador/validador do bundle focal;
2. criar testes sintéticos de geometria, seleção, janela, hashes e ausência de vazamento;
3. gerar galeria nos mesmos dez casos tecnicamente aprovados no v10;
4. obter revisão humana da galeria v16;
5. congelar prompt, ordem, agregação e contrato;
6. executar piloto temporal em casos com um, três e cinco candidatos;
7. executar os 87 casos cegos;
8. auditar hashes, completude e tempo;
9. congelar avaliação antes de usar labels;
10. calcular LOOCV e repeated stratified 5-fold;
11. manter o holdout fechado se qualquer gate falhar;
12. se qualificado, empacotar a configuração para reprodução no Mac e posterior comparação com MedGemma 27B.

## Critério de sucesso

- sensibilidade ≥75%;
- especificidade ≥75%;
- `INCONCLUSIVA` como erro na classificação categórica;
- 50/50 repetições atendendo simultaneamente 75%/75%;
- tempo máximo ≤180 segundos;
- revisão humana obrigatória;
- holdout aberto uma única vez e somente após qualificação no desenvolvimento.
