# OpenSwissHCC v17 — score cego e avaliação congelada

## Estado

A galeria full87 do atlas axial v17 foi aprovada para inferência cega 4B pelo
revisor `jm`. O holdout e os labels de desenvolvimento permaneceram fechados
durante toda a geração dos scores.

## Inferência cega 4B

O MedGemma executado foi:

```text
modelo:       google/medgemma-1.5-4b-it
quantização:  bitsandbytes-nf4
dispositivo:  NVIDIA GeForce RTX 4060 Laptop GPU
contrato:     dtwin-medgemma-volume-score-v1
método:       first_token_restricted_softmax_v1
requisições:  87 (uma por caso)
retries:      0
```

Resultado técnico:

```text
casos concluídos: 87/87
falhas técnicas:  0
tempo mínimo:     4,9786 s
tempo mediano:    7,3631 s
tempo médio:      7,5322 s
tempo máximo:     11,1798 s
gate 180 s:       aprovado em 87/87
```

O escopo temporal é `precomputed_atlas_scoring_only`. Logo, o resultado ainda
não prova o tempo end-to-end desde DICOM e preserva
`end_to_end_180_seconds_proven=false`.

Uma segunda passagem validou por SHA-256 e reutilizou 87/87 predições, sem nova
chamada ao modelo. O resumo cego está em:

```text
casos/qualification/openswisshcc_v1/predictions/dev_v17_axial_atlas_full87_v1/summary.json
```

## Observação cega sobre o leitor

O argmax bruto foi `NEGATIVA` nos 87 casos. Isso não foi tratado como falha
técnica nem motivou alteração pós-hoc: as probabilidades e os log-odds são
válidos e variam entre casos. A capacidade discriminativa somente poderá ser
determinada após a abertura autorizada dos labels de desenvolvimento.

Distribuição cega do sinal contínuo:

```text
scores únicos: 77/87
mínimo:        -3,3750
Q1:            -2,6875
mediana:       -2,2500
média:         -2,1703
Q3:            -1,7500
máximo:        -0,1250
```

Portanto, o argmax uniforme não significa score constante. A avaliação
predefinida poderá medir se a ordenação contínua separa positivos e negativos,
sem repetir a inferência ou ajustar o prompt depois de ver os labels.

## Protocolo de avaliação congelado

O avaliador foi implementado antes de abrir qualquer label. Ele valida todos os
hashes e recalcula o score a partir das probabilidades de cada caso.

```text
score protocol:
cedf7dd7a1f6ef6df37e7378c2da203dc712fa7f73bcb89f94a0399bb4228656

blind score vector:
f65f9eeafddd7a4359c308a2962c9aac8f860acad87903454cd628dc4e3b8ae3

evaluation protocol:
3b4a9afafec6c7a90f85f151ffaf088705a27321d8142eab79fd805840067457
```

Arquivo:

```text
casos/qualification/openswisshcc_v1/prepared/development_evaluation_v17_axial_atlas_protocol_v1.json
```

### Métrica primária predefinida

```text
sinal:       log-odds POSITIVA versus NEGATIVA
direção:     maior = mais suspeito
estimador:   leave-one-out
limiar:      ajustado somente nos outros 86 casos de cada fold
seleção:     maximizar min(sensibilidade, especificidade), depois acurácia balanceada
gate:        sensibilidade LOOCV >= 75% e especificidade LOOCV >= 75%
```

Intervalos de confiança de 95% serão calculados por Wilson sobre a matriz de
confusão LOOCV.

### Diagnósticos secundários

- ROC-AUC aparente;
- limiar aparente ajustado nos 87 casos, apenas para eventual congelamento
  futuro;
- argmax bruto, com `INCONCLUSIVA` contado como erro.

Esses diagnósticos não podem substituir a métrica primária.

## Salvaguardas

- o congelamento não recebe caminho de labels;
- a avaliação exige flag explícita de autorização;
- somente `protected_ground_truth/development_labels.jsonl` é aceito;
- qualquer caminho contendo `holdout` é recusado;
- o holdout permanece fechado mesmo depois da avaliação de desenvolvimento;
- aprovação no desenvolvimento não constitui qualificação final;
- revisão humana e uso exclusivamente em pesquisa permanecem obrigatórios.

## Verificação

A suíte completa do ARGOS passou após a implementação:

```text
711 testes aprovados
0 falhas
```

## Próximo gate

É necessária autorização explícita vinculada ao protocolo de avaliação acima
para abrir **somente** os 87 labels de desenvolvimento. Depois disso serão
calculados sensibilidade, especificidade, matriz de confusão, intervalos de
confiança e ROC-AUC. O holdout continuará fechado.

Se o gate de desenvolvimento passar, o passo operacional seguinte será integrar
o atlas v17 ao exame individual e medir em relógio único:

```text
seleção DICOM + segmentação + atlas v17 + inferência + relatório + modelo 3D
```

O máximo de 11,1798 s já prova apenas a parcela de inferência. O histórico do
ARGOS mediu 43–53 s no fluxo DICOM rápido, mas esse valor não pode ser atribuído
ao v17 antes da integração e de um novo smoke end-to-end.
