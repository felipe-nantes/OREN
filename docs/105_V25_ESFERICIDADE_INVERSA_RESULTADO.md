# V25 — esfericidade inversa

## Hipótese congelada

Após a rejeição da v24 e antes de calcular as métricas v25, foi congelada uma
única extensão morfológica sobre a baseline v23:

```text
1 - candidate_weighted_sphericity_proxy
```

A direção predefinida foi `higher_is_more_positive`. A extensão foi testada com
pesos de 0%, 5%, 10%, 15% e 20%. O peso e o limiar foram ajustados somente nos
folds de treinamento:

- endpoint primário: LOOCV aninhado;
- robustez: 50 repetições de 5-fold estratificado aninhado;
- seleção interna: maximizar a menor entre sensibilidade e especificidade,
  depois balanced accuracy, sensibilidade e o menor peso;
- falhas e inconclusivos contam como erros;
- holdout v21 e máscaras de lesão permaneceram proibidos.

Protocolo congelado:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v25/
inverse_sphericity_protocol_v1.json
```

Assinatura:

```text
815364923f3984b3924e2d0018841e69efc7b251934c13185a69e8969a30c83f
```

## Resultado

| Configuração | TP | TN | FP | FN | Sensibilidade | Especificidade | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| v23 congelada | 32 | 38 | 10 | 7 | 82,05% | 79,17% | 80,61% |
| v25 aninhada | 32 | 38 | 10 | 7 | 82,05% | 79,17% | 80,61% |

A decisão dos 87 casos foi exatamente igual à v23. A extensão não corrigiu nem
introduziu erros.

No LOOCV externo, a seleção interna escolheu:

```text
peso 0,00: 86/87 folds
peso 0,15: 1/87 folds
demais pesos: 0/87 folds
```

Nas 50 repetições de 5-fold:

```text
execuções passando 75/75: 40/50
sensibilidade mínima: 71,79%
especificidade mínima: 72,92%
```

Isso não supera a robustez da v23, que passou 49/50 execuções e manteve
especificidade mínima de 75%.

## Decisão

A v25 é uma tentativa metodologicamente válida, mas foi reprovada para
promoção:

- não altera nenhuma decisão primária;
- não melhora sensibilidade, especificidade ou balanced accuracy;
- a extensão recebe peso zero em 86/87 folds;
- a robustez cai de 49/50 para 40/50;
- o gate de robustez predefinido não foi atingido.

A baseline v23 permanece inalterada e continua sendo a melhor configuração
fixa.

## Reprodutibilidade

Foram executadas duas avaliações independentes. Os scores por caso foram
idênticos byte a byte:

```text
case_scores.csv:
ee2c513de9791ddb06dda9fa38dc1047a0ace286e70288d68ff539a934387916
```

O conteúdo canônico dos relatórios, excluindo somente o tempo de execução,
também foi idêntico:

```text
evaluation.json canônico:
888816a7d6469093ea98f243cbd02d42e566270033ca885b96d54114fb715ab9

tempos:
432,82 s e 429,38 s
```

A suíte focada terminou com `54 passed`. A compilação dos módulos passou e o
verificador independente confirmou novamente a integridade integral da
baseline v23.

## Próximo passo lógico

Planaridade e esfericidade não acrescentaram sinal estável à linearidade da
v23. O próximo experimento não deve combinar livremente mais descritores
correlacionados. A próxima hipótese isolada deve testar preenchimento da caixa
delimitadora (`candidate_weighted_bbox_fill`) como indicador de candidato
compacto versus estrutura esparsa, com novo protocolo congelado e a mesma
avaliação aninhada.
