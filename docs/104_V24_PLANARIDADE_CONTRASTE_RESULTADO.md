# V24 — contraste planaridade-linearidade

## Hipótese congelada

Depois da auditoria dos 17 erros v23 e antes de calcular métricas v24, foi
congelada uma única extensão:

```text
candidate_weighted_planarity - candidate_weighted_linearity
```

A direção predefinida foi `higher_is_more_positive`. A feature foi adicionada
sobre o score v23 com pesos possíveis de 0%, 5%, 10%, 15% e 20%.

Peso e limiar foram selecionados somente dentro dos folds de treinamento:

- endpoint primário: LOOCV aninhado;
- robustez: 50 repetições de 5-fold estratificado aninhado;
- seleção interna: maximizar a menor entre sensibilidade e especificidade,
  depois balanced accuracy, sensibilidade e, por último, o menor peso;
- falhas e inconclusivos: erros;
- holdout v21: proibido;
- máscaras de lesão: proibidas.

Protocolo:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v24/
planarity_contrast_protocol_v1.json
```

Assinatura:

```text
fe67712fdc8b4465af14189b812b621cc8b01b83d75a9750d39080f3e4b427a0
```

## Resultado primário

| Configuração | TP | TN | FP | FN | Sensibilidade | Especificidade | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| v23 congelada | 32 | 38 | 10 | 7 | 82,05% | 79,17% | 80,61% |
| v24 aninhada | 32 | 37 | 11 | 7 | 82,05% | 77,08% | 79,57% |

A v24 manteve a sensibilidade, perdeu um verdadeiro negativo e reduziu a
especificidade em 2,09 pontos percentuais.

O único caso cuja decisão mudou foi:

```text
anon-openswiss-1939ab13ec181c0c
label: NEGATIVE
v23: NEGATIVE
v24: POSITIVE
peso selecionado: 0,05
```

Não houve correção adicional.

## Seleção dos pesos

No LOOCV externo:

```text
peso 0,00: 86/87 folds
peso 0,05: 1/87 folds
pesos 0,10–0,20: 0/87 folds
```

O resultado mostra que, em quase todos os conjuntos de treinamento, a própria
v23 foi preferida à extensão de planaridade.

Nas 50 repetições de 5-fold:

```text
execuções passando 75/75: 36/50
sensibilidade mínima: 71,79%
especificidade mínima: 70,83%
```

Isso é pior que a v23, que passou 49/50 repetições e manteve especificidade
mínima de 75%.

## Decisão

A hipótese v24 é uma tentativa válida, pois foi congelada antes das métricas,
avaliada de forma aninhada, contabilizou todos os casos e não utilizou holdout
ou máscaras de lesão.

Ela está reprovada para promoção porque:

- não melhora a v23;
- introduz um falso positivo;
- reduz a robustez de 49/50 para 36/50;
- a seleção interna escolhe peso zero em 86/87 folds.

Não será ajustada a direção, a fórmula ou a grade de pesos depois deste
resultado. Qualquer nova transformação seria uma nova hipótese e exigiria novo
protocolo.

## Reprodutibilidade e validação técnica

A avaliação foi executada duas vezes de forma independente. Os 87 scores por
caso foram idênticos byte a byte:

```text
case_scores.csv:
000581f4df4219dccd5a131617346a6d424a566e7b90d2087b8bda57ddb1ec97
```

O conteúdo canônico dos dois relatórios, excluindo apenas o tempo de execução,
também foi idêntico:

```text
evaluation.json canônico:
0041341e80504154e959d3a7e00f7218f1d3968fe89cc98f2b256ee3af10cd03

tempos das duas execuções:
442,07 s e 444,76 s
```

A suíte focada terminou com `46 passed`. A compilação dos módulos v24 passou e
o verificador independente confirmou que a baseline v23 permaneceu íntegra. O
`git diff --check` apontou somente linhas em branco finais preexistentes em
`tools/medgemma_server.py` e `webapp/server.py`, fora do escopo desta etapa.

## Próximo passo

A planaridade condicionada à linearidade não acrescentou sinal estável. A
próxima hipótese predefinida deve testar compactação/esfericidade isoladamente
sobre a v23, novamente com peso e limiar escolhidos somente dentro dos folds.
