# OpenSwissHCC v18 — atlas axial em blocos

## Hipótese

O v17 mostrou todas as 9–20 imagens do atlas em uma única chamada e produziu
argmax negativo nos 87 casos. O v18 testa se contextos menores reduzem a diluição
de uma lesão focal pequena.

Não há treinamento, nova segmentação ou uso de máscara de lesão na inferência.
Os frames são exatamente os mesmos que já passaram pela revisão humana v17.

## Protocolo

O atlas é dividido em blocos sequenciais balanceados:

```text
blocos por caso: 1 a 4
frames por bloco: pelo menos 5
padding: nenhum
duplicação: nenhuma
cobertura: cada frame exatamente uma vez
retry: 0
agregação: maior log-odds POSITIVA/NEGATIVA entre blocos
gate por caso: 180 segundos
```

O protocolo válido v18-v2 foi congelado com assinatura:

```text
f84fe44d0cb26f20620dc81092702485eb571d70eb7e567b0889a4df3c05ac6b
```

O primeiro protocolo v18-v1, de quatro frames por bloco, foi abortado no
preflight real porque o gateway exige no mínimo cinco imagens por chamada. Não
houve predição v18-v1. O v18-v2 corrigiu o particionamento sem relaxar o gateway,
duplicar imagens ou introduzir padding.

## Execução

```text
casos: 87/87
requisições: 207
falhas técnicas: 0
predições reutilizadas por hash na segunda passagem: 87/87
ground truth lido pela inferência: não
holdout aberto: não
```

Distribuição categórica cega:

```text
POSITIVA:     25
NEGATIVA:     61
INCONCLUSIVA:  1
```

Tempos sobre atlas pré-computado:

```text
mínimo:  4,8696 s
mediana: 7,5227 s
média:   7,6448 s
máximo: 11,1118 s
gate:   87/87 abaixo de 180 s
```

## Avaliação predefinida

O protocolo declarou antes da inferência:

- sinal primário: máximo log-odds dos blocos;
- direção: maior significa mais suspeito;
- estimador: LOOCV;
- limiar ajustado somente nos outros 86 casos;
- meta simultânea: sensibilidade e especificidade de pelo menos 75%;
- argmax e ROC-AUC apenas como diagnósticos secundários;
- aprovação no desenvolvimento não equivale a qualificação final.

O avaliador recalcula probabilidades, argmax, log-odds, cobertura, agregação,
hashes e tempos antes de aceitar os scores.

## Próximo gate

A autorização anterior nomeava exclusivamente o protocolo v17. A avaliação v18
somente poderá abrir novamente `development_labels.jsonl` após autorização
explícita vinculada à assinatura v18-v2 acima. O holdout deve permanecer fechado.
