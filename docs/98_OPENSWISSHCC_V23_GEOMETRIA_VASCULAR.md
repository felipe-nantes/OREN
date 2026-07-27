# OpenSwissHCC v23 — geometria vascular dos candidatos

## Motivação

O v22 exact-top5 falhou porque o MedGemma 4B respondeu com frequência a regiões de
realce benigno ou vascular. As 42 features de intensidade dinâmica também não
acrescentaram sinal estável ao v11. A v23 testa uma evidência diferente: a forma física
3D dos componentes candidatos, especialmente sua linearidade, como aproximação
determinística para estruturas tubulares/vasculares.

## Implementação cega

Foi acrescentado um extrator que:

- recebe somente máscaras candidatas automáticas e geometria das imagens;
- calcula autovalores da covariância das coordenadas físicas de cada componente;
- distingue componentes compactos, planares e lineares;
- agrega a linearidade pelo número de voxels de cada componente;
- não possui labels ou máscaras públicas de lesão em sua API;
- falha diante de hashes, schema ou salvaguardas divergentes;
- registra casos sem candidato em vez de excluí-los silenciosamente.

Artefato cego full87:

```text
casos/qualification/openswisshcc_v1/prepared/development_v23_candidate_shape_full87_v1
```

- casos: 87;
- casos com candidato vazio: 1 (`anon-openswiss-40c09ebcf8178f92`);
- SHA-256 de `features.jsonl`:
  `2453501adcdb379b210a8c3d005431d63d76484efc975f6bd9c6685631893e52`;
- labels lidos durante a construção: não;
- máscaras públicas de lesão lidas: não;
- inferência executada: não.

## Hipótese retrospectiva

A hipótese combina:

```text
80% do sinal v11
20% da linearidade ponderada dos componentes candidatos
```

Cada feature é convertida por ECDF usando somente o conjunto de treinamento da divisão.
O limiar também é escolhido somente no treinamento de cada divisão.

Importante: a família geométrica e o peso de 20% foram escolhidos depois que os labels
de desenvolvimento já haviam sido abertos. Portanto, a avaliação é retrospectiva e
pode conter viés de seleção. Ela não qualifica o sistema final.

## Resultado em 87 casos de desenvolvimento

LOOCV:

| Métrica | Resultado |
|---|---:|
| TP | 32 |
| TN | 38 |
| FP | 10 |
| FN | 7 |
| Sensibilidade | 82,05% |
| Especificidade | 79,17% |
| Balanced accuracy | 80,61% |
| IC95% sensibilidade | 67,33%–91,02% |
| IC95% especificidade | 65,74%–88,27% |

Validação estratificada repetida, com 50 repetições de 5 folds:

| Medida | Resultado |
|---|---:|
| Repetições que passaram 75/75 | 49/50 |
| Sensibilidade mediana | 82,05% |
| Especificidade mediana | 79,17% |
| Sensibilidade mínima | 71,79% |
| Especificidade mínima | 75,00% |

O ponto estimado ultrapassou 75/75, mas o gate de robustez integral falhou porque uma
das 50 repetições ficou abaixo de 75% de sensibilidade. Os limites inferiores dos IC95%
também permanecem abaixo de 75%.

## Interpretação

Este é o melhor resultado conjunto observado no desenvolvimento até agora e apoia a
hipótese de que a geometria vascular estava ausente do pipeline. Ele não demonstra que
o ARGOS atingirá 75/75 em uma coorte nova. O holdout v21 já consumido não pode ser
reutilizado para confirmar a v23.

## Próximo gate

1. Manter a v23 congelada, sem reajustar peso ou feature no desenvolvimento atual.
2. Acrescentar testes de integração e executar a suíte completa.
3. Medir o custo temporal do extrator; ele é determinístico e não adiciona chamadas ao
   MedGemma.
4. Validar a regra congelada em uma nova coorte pública balanceada e independente.
5. Somente depois transferir a mesma representação congelada para o Mac/27B.

Artefato de avaliação:

```text
casos/qualification/openswisshcc_v1/evaluations/dev_v23_shape_fusion87_v1
```

O resultado permanece `qualified=false`, `holdout_v21_reuse_forbidden=true` e com
revisão humana obrigatória.

## Calibrador congelado para a próxima coorte

As referências ECDF do desenvolvimento, os pesos e o limiar foram congelados em:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v23/shape_fusion_calibrator_v1.json
```

- limiar: `0.5121839080459771`;
- assinatura: `d0a955178783cf7f2914053c87d3d99d186ab4a56960620068bd118e5ccac475`;
- status: `frozen_for_new_independent_external_validation`;
- qualificação: `false`;
- reutilização do holdout v21: proibida;
- troca do leitor 4B pelo 27B: exige calibração separada.

O scorer externo usa somente os três sinais v11, a linearidade ponderada e as
referências congeladas. Ele não precisa de labels para emitir a predição e recusa
calibrador adulterado.

## Orçamento temporal

A recomputação exata das features nos 87 casos mediu leitura do NIfTI candidato mais
extração geométrica:

```text
máximo por caso = 0,5256 s
```

O limite conservador preparado soma:

```text
limite existente v20             104,4465 s
geração de propostas v22           2,8262 s
extração geométrica v23             0,5256 s
total conservador                 107,7983 s
```

Esse orçamento passa 180 segundos com folga, mesmo declarando possível sobreposição
entre componentes. Ainda não prova o tempo end-to-end desde DICOM bruto, pois
segmentação, preparação e alinhamento completos precisam ser medidos na nova coorte.

Artefato:

```text
casos/qualification/openswisshcc_v1/timing/dev_v23_candidate_shape_full87_v1.json
```
