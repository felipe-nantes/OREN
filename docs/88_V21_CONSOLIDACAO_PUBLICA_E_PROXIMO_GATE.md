# V21 — Consolidação pública e próximo gate

## Objetivo

Consolidar de forma metodologicamente válida os dois braços públicos externos
executados com o calibrador v11 congelado, sem transformar datasets de classe
única em uma falsa avaliação balanceada.

## Evidência positiva — LiverHccSeg

```text
casos: 14
TP: 11
FN: 3
sensibilidade: 78,57%
IC95% Wilson: 52,41%–92,43%
tempo máximo: 51,93 s
```

O ponto estimado supera 75%, mas o limite inferior do IC95% não supera 75%.

## Evidência negativa — CHAOS v1.03

```text
casos: 20
TN: 20
FP: 0
especificidade: 100,00%
IC95% Wilson: 83,89%–100,00%
tempo máximo: 44,46 s
```

O ponto estimado e o limite inferior do IC95% superam 75%. A ressalva humana de
qualidade inferior às galerias anteriores foi preservada; a galeria foi aprovada
tecnicamente pelo revisor `jm` antes da inferência.

## Resultado consolidado correto

```text
sensibilidade pontual >= 75%: PASS, no braço positivo
especificidade pontual >= 75%: PASS, no braço negativo
tempo <= 180 s: PASS, nos dois braços
limites inferiores dos dois IC95% >= 75%: FAIL
qualificação final simultânea: NÃO DEMONSTRADA
```

Não foi calculada matriz de confusão agrupada, acurácia agrupada ou ROC-AUC
agrupada. Em LiverHccSeg todos os casos são positivos e, no braço CHAOS, todos
os casos são negativos. Portanto, classe e dataset estão confundidos; agrupá-los
produziria uma métrica artificialmente otimista e incapaz de medir desempenho no
mesmo domínio.

## Integridade dos artefatos

```text
calibrador compartilhado sha256:
1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971

avaliação LiverHccSeg sha256:
735dda355fd1a6761dc11ccafc1f44fcb06aa6ff78f6024167522699f35ed9b0

avaliação CHAOS sha256:
c4934e1447d84b9d005a11e1f8723bf00b3ee33cfd38dd2c6cffdd5031377976

consolidação sha256:
faf417266e9d0f3ccdd72ae70e213e15a534c739933b9686eebad1ac25189ad2

relatório de consolidação sha256:
bcb3f45459385131a0549fdd2e326e2cad4af83926dd392a264d26d8429032f7
```

## Estado do holdout OpenSwissHCC

O holdout dos sujeitos 045–088 não foi baixado, preparado, inferido ou aberto.
Os labels e máscaras correspondentes permanecem fechados.

## Próximo gate necessário

A conclusão da qualificação exige uma única avaliação congelada e balanceada no
mesmo domínio. O próximo passo é preparar exclusivamente as imagens do holdout
OpenSwissHCC em modo label-blind, mantendo labels e máscaras de lesão fechados.

Sequência obrigatória:

1. baixar e verificar a integridade somente do arquivo de imagens do holdout;
2. preparar casos e painéis sem ler labels ou máscaras de lesão;
3. executar o gate humano de qualidade dos painéis;
4. congelar lista de casos, hashes, calibrador, predições e protocolo;
5. somente então solicitar autorização separada para abrir os labels;
6. calcular sensibilidade, especificidade, matriz de confusão, IC95% e tempo no
   mesmo conjunto.

Até essa avaliação, o estado correto é:

```text
external_single_class_arms_pass_point_gates_not_finally_qualified
```
