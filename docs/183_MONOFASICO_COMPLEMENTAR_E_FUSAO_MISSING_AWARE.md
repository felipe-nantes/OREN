# Monofásico — sequências complementares e fusão tolerante a ausência

**Data:** 4 de agosto de 2026  
**Estado:** melhor candidato de desenvolvimento melhorou; gate 75/75 ainda reprovado

## Objetivo desta rodada

Investigar por que o classificador monofásico tardio não generalizou para o
OpenSwissHCC e acrescentar evidência real disponível no exame sem sintetizar
fases, usar labels na geração ou expor máscaras de lesão ao MedSigLIP ou ao
MedGemma.

## Auditoria retrospectiva de falsos negativos

Nos 31 falsos negativos de desenvolvimento que podiam usar máscaras públicas
somente depois da inferência:

- 29 tinham lesão intersectando o plano renderizado, mas o classificador ficou
  negativo;
- 2 não possuíam máscara venosa utilizável;
- as máscaras foram usadas apenas nessa auditoria retrospectiva e nunca na
  representação, embedding ou inferência.

Conclusão: o gargalo dominante não era ausência da lesão no painel global, mas
discriminação do achado na representação.

## Cobertura axial exata

Foi criada uma representação com cada corte axial contendo fígado exatamente
uma vez. O gate inteiro confirmou cobertura completa dos voxels hepáticos. O
nested OOF obteve 53,85% de sensibilidade e 63,27% de especificidade, sem ganho
suficiente sobre o painel tardio global.

## Sequências reais complementares

Foram projetadas para o espaço físico da máscara hepática venosa e renderizadas
sem contorno enviado ao modelo:

| Sequência | Casos | Candidatos | Falhas técnicas |
|---|---:|---:|---:|
| T2 HASTE | 82 | 3.455 | 6 |
| DWI trace | 88 | 2.111 | 0 |
| ADC | 88 | 2.112 | 0 |

Total: 7.678 candidatos em 258 combinações caso-sequência. O registro rígido
foi mantido como fallback implementado, mas desabilitado na coorte completa por
latência; a projeção física passou nos gates e na revisão visual.

Resultados nested OOF isolados:

| Sinal | Sensibilidade | Especificidade | AUC | Gate |
|---|---:|---:|---:|---|
| T2 | 41,03% | 48,98% | 0,446 | falha |
| DWI | 48,72% | 59,18% | 0,497 | falha |
| ADC | 61,54% | 65,31% | 0,680 | falha |
| T2+DWI+ADC em uma cabeça | 51,28% | 53,06% | 0,545 | falha |

O ADC foi o único sinal complementar com ganho simultâneo nos dois eixos.

## Hard-negative mining / MIL

Foi acrescentada uma política opcional `iterative_topk_mil`, restrita aos
folds de treino. Ela seleciona os cortes positivos mais suspeitos, os negativos
mais difíceis e uma âncora negativa fácil por caso. O comportamento antigo
continua inalterado quando a opção está ausente.

| Sinal | Sensibilidade | Especificidade | AUC |
|---|---:|---:|---:|
| axial MIL | 51,28% | 53,06% | 0,548 |
| ADC MIL | 64,10% | 61,22% | 0,659 |

O ADC recuperou um positivo, mas perdeu dois negativos. A política não foi
promovida.

## Fusão tardia aninhada

Cada sinal entra como margem `score - threshold`. Pesos, regularização e
threshold são aprendidos exclusivamente dentro dos folds internos.

| Fusão | Sensibilidade | Especificidade | AUC | Falhas |
|---|---:|---:|---:|---:|
| tardio global + ADC | 61,54% | 65,31% | 0,708 | 4 |
| tardio global + axial + ADC | 69,23% | 67,35% | 0,754 | 4 |
| cinco sinais, missing-aware | 66,67% | 69,39% | 0,706 | 0 |
| **tardio global + axial + ADC, missing-aware** | **71,79%** | **73,47%** | **0,779** | **0** |

A política `zero_margin_with_indicator` não descarta o exame quando uma
modalidade complementar está ausente. Ela imputa margem neutra, acrescenta um
indicador explícito de ausência e ainda falha se todos os sinais faltarem. Isso
eliminou quatro falhas técnicas e tornou a ausência auditável.

Matriz do melhor candidato:

```text
TP=28  TN=36  FP=13  FN=11
sensibilidade = 71,79% (IC95% Wilson 56,22%–83,46%)
especificidade = 73,47% (IC95% Wilson 59,74%–83,79%)
ROC-AUC = 0,7792
```

O melhor limiar retrospectivo global também não alcança 75/75: chega a 79,49%
de sensibilidade com 73,47% de especificidade. Logo, recalibrar o limiar sobre
esses mesmos casos não resolve o objetivo e não deve ser usado para declarar
sucesso.

## Assinaturas do melhor candidato

```text
prediction_signature = 6e656ba3fe285a5acf8c59b240b148449320a12063c75935fab1ffaf443f00d4
evaluation_signature = e2af3766a080c874a596372da2c24d1432d71d8f846c1c28e4e991988043b2b3
```

## Segurança e metodologia

- labels foram abertos somente depois de cada freeze OOF;
- nenhuma máscara de lesão entrou na geração, embeddings ou inferência;
- o holdout não foi reutilizado nesta rodada;
- falhas técnicas contam no eixo incorreto da matriz, nunca são excluídas;
- T2/DWI reprovados não foram habilitados no produto;
- os resultados são retrospectivos de desenvolvimento e não comprovam
  generalização clínica.

## Próximo passo permitido

O melhor candidato ficou a dois verdadeiros positivos e um verdadeiro negativo
do gate pontual nessa coorte. Como nenhum threshold atinge 75/75, o próximo
passo deve acrescentar representação nova ou dados externos — por exemplo:

1. validar a fusão em uma coorte monofásica externa não usada no ajuste;
2. treinar um bundle de produção somente após congelar a configuração;
3. usar o segundo leitor MedGemma 4B apenas se seu sinal for derivável do mesmo
   contrato monofásico e demonstrar complementaridade OOF;
4. manter subtipo como diferencial top-2 até top-1 balanceado atingir 75%.

