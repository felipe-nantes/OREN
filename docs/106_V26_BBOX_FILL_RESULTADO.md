# V26 — preenchimento da caixa delimitadora

## Hipótese congelada

Após as rejeições de planaridade e esfericidade, foi testada isoladamente a
feature:

```text
candidate_weighted_bbox_fill
```

A direção predefinida foi `higher_is_more_positive`, representando a hipótese
de que candidatos que ocupam mais densamente sua caixa delimitadora poderiam
ser mais compatíveis com achado focal que estruturas esparsas.

A feature foi adicionada sobre a baseline v23 com pesos de 0%, 5%, 10%, 15% e
20%. Peso e limiar foram escolhidos somente nos folds de treinamento:

- endpoint primário: LOOCV aninhado;
- robustez: 50 repetições de 5-fold estratificado aninhado;
- falhas e inconclusivos contam como erros;
- holdout v21 e máscaras de lesão permaneceram proibidos;
- o código da hipótese e o núcleo estatístico reutilizado foram incluídos nos
  hashes do protocolo.

Protocolo:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v26/
bbox_fill_protocol_v1.json
```

Assinatura:

```text
243512e6467d6aab9aafb8adbd3cab889e7661d4b8140d7fce0ac53362d89d59
```

## Resultado

| Configuração | TP | TN | FP | FN | Sensibilidade | Especificidade | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| v23 congelada | 32 | 38 | 10 | 7 | 82,05% | 79,17% | 80,61% |
| v26 aninhada | 32 | 38 | 10 | 7 | 82,05% | 79,17% | 80,61% |

Nenhuma decisão mudou. Nos 87 folds externos do LOOCV, a seleção interna
escolheu peso zero em todos:

```text
peso 0,00: 87/87
pesos 0,05–0,20: 0/87
```

Nas 50 repetições de 5-fold:

```text
execuções passando 75/75: 48/50
sensibilidade mínima: 71,79%
especificidade mínima: 75,00%
```

A v26 ficou mais próxima da robustez da v23 que v24 e v25, mas não a superou:
a v23 passou 49/50 execuções e o resultado primário permaneceu exatamente
igual.

## Decisão

A v26 foi reprovada para promoção porque:

- não melhora balanced accuracy, sensibilidade ou especificidade;
- não corrige nenhum dos 17 erros persistentes;
- recebe peso zero em 87/87 folds do endpoint primário;
- não cumpre o gate predefinido de 50/50 execuções robustas;
- não cumpre o gate predefinido de melhora sobre a v23.

A baseline v23 permanece inalterada e continua sendo a melhor configuração
fixa.

## Reprodutibilidade

As duas execuções independentes produziram os mesmos scores byte a byte:

```text
case_scores.csv:
62a1fbc920b8bc0fdc2206c363f3c4e9d5123655cca1aab17944ecefd9a65652
```

Os relatórios canônicos, removendo somente o tempo de execução, também foram
idênticos:

```text
evaluation.json canônico:
89ecfa644123cfb2541538164b49619685d0ceceebf750d3c23bd4973aed4d16

tempos:
432,54 s e 426,59 s
```

A suíte focada terminou com `62 passed`. A compilação dos módulos passou e o
verificador independente confirmou novamente que os 14 artefatos protegidos da
baseline v23 permanecem íntegros.

## Próximo passo lógico

Os três descritores morfológicos adicionais testados após a v23 — planaridade,
esfericidade e preenchimento da bbox — não produziram ganho primário. Continuar
testando transformações correlacionadas nos mesmos 87 casos aumenta o risco de
seleção oportunista.

O próximo passo metodologicamente defensável é encerrar a busca morfológica,
manter a v23 congelada e preparar uma validação externa balanceada,
completamente independente e executada uma única vez. Somente essa validação
poderá consolidar a alegação de sensibilidade e especificidade acima de 75%.
