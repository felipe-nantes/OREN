# V23 — auditoria dos 17 erros remanescentes

## Escopo

A auditoria foi executada sobre os 87 casos de desenvolvimento já abertos. O
baseline v23 permaneceu congelado e foi verificado antes da leitura dos
artefatos.

Não foram usadas máscaras de lesão e o holdout v21 não foi aberto nem
reutilizado. Esta análise é retrospectiva, serve para formular a próxima
hipótese e não qualifica o ARGOS final.

## Comparação reproduzida

| Configuração | TP | TN | FP | FN | Sensibilidade | Especificidade |
|---|---:|---:|---:|---:|---:|---:|
| v11 | 29 | 36 | 12 | 10 | 74,36% | 75,00% |
| v23 | 32 | 38 | 10 | 7 | 82,05% | 79,17% |

## Transição caso a caso

Dos 87 casos:

- 65 estavam corretos na v11 e continuaram corretos na v23;
- 5 erros da v11 foram corrigidos pela v23;
- nenhum acerto da v11 foi quebrado pela v23;
- os 17 erros da v23 já eram erros da v11.

As cinco correções foram:

- três casos positivos recuperados;
- dois casos negativos recuperados.

Isso demonstra que a linearidade ponderada acrescentou sinal complementar real
no desenvolvimento. Os erros restantes não são regressões provocadas pela
feature geométrica.

## Distância ao limiar

Foi predefinida como proximidade uma margem absoluta de até `0.025` em relação
ao limiar LOOCV do caso. Nenhum dos 17 erros v23 ficou nessa faixa.

Distribuição dos erros pela posição ECDF da linearidade:

- quartil superior: 6;
- metade central: 7;
- quartil inferior: 4.

Portanto, os erros não se concentram somente junto ao limiar nem em uma única
faixa de linearidade. Um ajuste simples do threshold não é a próxima hipótese
adequada.

## Padrões morfológicos descritivos

Medianas observadas:

| Feature | TP | TN | FP | FN |
|---|---:|---:|---:|---:|
| linearidade ponderada | 0,6078 | 0,5632 | 0,6614 | 0,5070 |
| planaridade ponderada | 0,1976 | 0,2775 | 0,1560 | 0,3024 |
| proxy de esfericidade | 0,1080 | 0,1323 | 0,1425 | 0,1516 |
| preenchimento da bounding box | 0,0566 | 0,0448 | 0,0731 | 0,0496 |
| razão de eixos | 3,2363 | 2,8881 | 3,4248 | 3,3157 |
| voxels candidatos totais | 19.979,5 | 23.887,5 | 12.833,5 | 24.838,0 |

Esses valores são descritivos e não constituem uma regra selecionada. Eles
indicam dois grupos difíceis:

1. falsos positivos com linearidade e preenchimento da bounding box acima dos
   verdadeiros positivos, porém menor volume candidato;
2. falsos negativos com menor linearidade e maior planaridade/esfericidade do
   que os verdadeiros positivos.

## Conclusão para a próxima hipótese

A próxima família a testar deve complementar a linearidade, não substituí-la.
A prioridade é avaliar, uma feature por vez e com validação estritamente
aninhada:

1. planaridade condicionada à linearidade;
2. compactação/esfericidade;
3. relação entre preenchimento espacial e volume candidato.

Nenhuma dessas features está aprovada neste momento. Pesos, direção e limiar
deverão ser selecionados somente dentro dos folds de treinamento.

## Artefatos

Auditoria final:

```text
casos/qualification/openswisshcc_v1/audits/dev_v23_error_audit_v3
```

Conteúdo:

- `summary.json`: métricas, transições e medianas;
- `errors.jsonl`: os 17 erros com sinais e features completas;
- `all_cases.csv`: comparação v11/v23 dos 87 casos;
- `report.md`: resumo auditável.

O gerador recusa sobrescrita, verifica o lock do baseline, valida hashes,
schemas e salvaguardas e não aceita caminhos de holdout para os labels.
