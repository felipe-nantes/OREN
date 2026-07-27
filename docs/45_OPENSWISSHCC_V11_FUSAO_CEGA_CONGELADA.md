# OpenSwissHCC v11 — fusão cega congelada

## Objetivo desta etapa

A v9 multissequência e a v10 baseada somente no volume do localizador falharam
de forma robusta no gate simultâneo de 75% de sensibilidade e 75% de
especificidade. O tempo, por outro lado, já ficou dentro do teto de 180 segundos.

A v11 muda a hipótese sem repetir ajustes de prompt ou de threshold. Ela combina
três fontes de evidência já persistidas sem ground truth:

1. margem `P(INCONCLUSIVA) - P(NEGATIVA)` do MedGemma 4B balanceado v4;
2. score sagital invertido do MedSigLIP v5;
3. `log1p(volume candidato)` do localizador 3D v10.

Esta etapa criou somente o bundle cego e congelou o protocolo. Nenhum label foi
aberto, nenhuma métrica foi calculada e nenhuma decisão clínica foi emitida.

## Coorte e exclusão técnica

O conjunto contém 87 casos anônimos. Os lotes v4 e v5 continham 88 casos e foram
restringidos exatamente à lista cega v10. A única diferença aceita é:

```text
anon-openswiss-cb2c5c63fc28b8ee
```

Esse é o caso 72, excluído anteriormente por revisão técnica cega devido à
qualidade de imagem severamente prejudicada. O empacotador aborta se surgir
qualquer outra ausência, inclusão ou exclusão.

## Regra pré-declarada

Os pesos foram congelados antes de uma nova abertura dos labels:

| Componente | Peso |
|---|---:|
| MedGemma v4 — margem de incerteza | 0,40 |
| MedSigLIP v5 — sagital invertido | 0,40 |
| Localizador v10 — log do volume | 0,20 |

Cada sinal é transformado por ECDF usando somente as amostras de treinamento do
fold. O score final é a média aritmética ponderada. O limiar também é escolhido
somente no treino, maximizando primeiro o menor valor entre sensibilidade e
especificidade e depois a acurácia balanceada.

O protocolo contém uma única fusão primária. Não há busca de pesos, seleção de
features ou escolha de direção após o acesso aos labels.

## Avaliação congelada

Quando houver autorização separada, a avaliação deverá executar:

- LOOCV com ECDF e threshold recalculados somente nas 86 amostras de treino;
- validação cruzada estratificada 5-fold com 50 repetições;
- transformação e threshold recalculados dentro de cada fold;
- intervalos de Wilson de 95% sobre a matriz LOOCV;
- inconclusivos ou falhas tratados como erro quando houver decisão operacional.

O gate de desenvolvimento exige simultaneamente:

```text
sensibilidade LOOCV >= 75%
especificidade LOOCV >= 75%
50/50 repetições atingindo 75%/75%
tempo <= 180 segundos
```

Mesmo que o desenvolvimento passe, `qualified` continua falso e o holdout não é
aberto automaticamente. Uma etapa adicional deverá congelar o calibrador final
e autorizar explicitamente a avaliação única do holdout.

## Tempo

Foi usada uma estimativa conservadora, somando os maiores tempos observados de
cada componente:

| Componente | Maior tempo observado |
|---|---:|
| MedGemma v4 | 12,4589 s |
| MedSigLIP v5 | 30,9688 s |
| Localizador v10 | 41,9209 s |
| **Soma conservadora** | **85,3486 s** |

O gate de 180 segundos passou com margem de 94,6514 segundos. Essa medida cobre
o benchmark sobre artefatos preparados. A validação operacional DICOM continua
separada e já demonstrou o caminho rápido dentro de 53,32 segundos.

## Artefatos e assinaturas

Bundle cego:

```text
casos/qualification/openswisshcc_v1/runs/dev_v11_blind_fusion87/
```

- `signals.jsonl` SHA-256:
  `34167ef564f2c01cd5c7225e43c91c5a3d392d43c6df6e9f1e2d9e59ff1ac5b5`;
- `summary.json` SHA-256:
  `95177db344109ca46d183c09721c012dcb0a3215b9d8c26bcb06844cc5908dbf`.

Protocolo:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v11/
fusion_protocol.json
```

- assinatura canônica:
  `e161db5eb6e30245d1dd4ac9f5e0ff4662ae6b48a6a880b5b1ddab1f8599393a`;
- SHA-256 do arquivo:
  `60def4536e59786a4b5bbc809debf2c3cc3470dfe8862762a607257402e429dc`.

## Segurança verificada

O bundle e o protocolo registram:

```text
ground_truth_read=false
metrics_calculated=false
final_decision=null
holdout_opened=false
research_only=true
clinical_use_allowed=false
requires_human_review=true
```

Uma busca por `label`, `protected_ground_truth`, ground truth aberto e holdout
aberto não encontrou vazamentos. Uma tentativa real de executar o avaliador sem
`--allow-protected-development-labels` terminou com erro antes de acessar o
caminho de labels e não criou diretório de saída.

## Componentes implementados

```text
dtwin/benchmark/openswisshcc_v11_fusion.py
tools/build_openswisshcc_fusion_v11.py
tools/freeze_openswisshcc_fusion_v11.py
tools/evaluate_openswisshcc_fusion_v11.py
tests/test_openswisshcc_v11_fusion.py
```

O avaliador existe para garantir que a metodologia já esteja imutável, mas não
deve ser executado contra `development_labels.jsonl` sem uma nova autorização
explícita e específica para a v11.

## Validacao de software

- testes exclusivos da v11: 8 aprovados;
- regressao focada v4/v5/v9/v10/v11 e timing: 30 aprovados;
- suite completa do ARGOS: 529 aprovados, zero falhas;
- 328 avisos de deprecacao conhecidos, sem alteracao dos resultados.

## Próximo gate

O próximo passo é exclusivamente a avaliação protegida v11. Se a v11 não
sustentar o gate em LOOCV e nas 50 repetições, deve-se registrar o teto das
abordagens sem treinamento e não continuar procurando combinações no mesmo
desenvolvimento. O holdout deve permanecer fechado nesse cenário.
