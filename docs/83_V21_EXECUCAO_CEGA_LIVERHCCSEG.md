# V21 — execução cega externa LiverHccSeg

Data da execução: 2026-07-18.

## Escopo metodológico

Esta rodada usa 14 sujeitos tumor-positivos do LiverHccSeg v1.1 como braço
externo de sensibilidade. Os três sujeitos restantes do dataset, sem tumor
documentado no registry, foram excluídos e não foram reinterpretados como
negativos.

O braço é de classe única. Portanto, ele pode estimar sensibilidade externa,
mas não pode estimar especificidade, ROC-AUC nem comprovar sozinho a meta
simultânea de sensibilidade e especificidade de 75%.

Durante toda a preparação e inferência:

- nenhuma máscara pública de tumor/lesão foi copiada ou enviada aos modelos;
- nenhum label foi lido pelos componentes de inferência;
- o holdout OpenSwissHCC permaneceu fechado;
- uso clínico permaneceu desabilitado e a revisão humana obrigatória.

## Gate humano

A galeria `liverhccseg_v21_uniform9_gallery` foi aprovada integralmente pelo
revisor `jm`, exclusivamente quanto à qualidade técnica da representação.

```text
review_signature:
ae6df9f5a8adf93d2fcb8373c25c72b67608672ce38d140f1d18538f5c769419

panel_cohort_signature:
c60473f82cb5aecae88ee1e1b7916f9ab7697aca3235b7806e77d38da64c6b5d

gallery_signature:
3bc6d6021f657dd247227cceaaeb6c223dbfe9f035b1e552288855a47dcc22e6
```

A aprovação não foi uma revisão diagnóstica e não abriu o ground truth.

## Execução cega

### Localizador 3D

O `TotalSegmentator 2.15.0`, task `liver_lesions_mr`, Dataset589 fold 0,
processou a fase venosa usando somente a máscara hepática como recorte.

```text
casos completos: 14/14
média por caso: 25,30 s
máximo por caso: 35,68 s
casos abaixo de 90 s: 14/14
ground truth lido: não
decisão emitida: não
```

O primeiro lançamento falhou em um worker `spawn` do nnU-Net porque
`pyarrow 24` com Python 3.13 no Windows recebeu `WinError 6714`. O pacote
opcional `pyarrow`, que não participa do algoritmo, foi ocultado somente
durante a execução e restaurado obrigatoriamente em `finally`. A rodada válida
começou do zero e nenhuma saída parcial da tentativa falha foi reutilizada.

### MedSigLIP

O cache local inicialmente continha apenas configurações; faltavam
`spiece.model` e `model.safetensors`. Os dois artefatos oficiais de
`google/medsiglip-448` foram completados no cache Hugging Face. Nenhum dado do
projeto foi enviado no download.

```text
casos completos: 14/14
média por caso: 1,26 s
máximo por caso: 8,75 s
scores_sha256:
c0fe46cf63cb7a2f26811cdc382d2c07d2f345a22a30279d2914fd9dbcc4e1c0
ground truth lido: não
decisão emitida: não
```

### MedGemma 1.5 4B

O gateway local foi validado como `dtwin-medgemma-v1`, NF4, CUDA, GPU RTX
4060 de 8 GB. Foram solicitadas probabilidades de escolha, sem relatório
narrativo e sem RAG.

```text
casos completos: 14/14
média por caso: 6,57 s
máximo por caso: 7,50 s
scores_sha256:
acdd41274411340e6401a2a5bbfa7670ac0c00267e56b1dc604e7f27ca437535
ground truth lido: não
decisão emitida pelo componente: não
```

O gateway foi desligado após a rodada para liberar a GPU.

## Montagem e calibrador congelado

Os sinais foram montados exatamente como no protocolo v11:

```text
P(INCONCLUSIVA) - P(NEGATIVA)
-P_MedSigLIP_positiva_na_vista_sagital
log1p(volume_candidato_mm3)
```

```text
raw signals sha256:
6295238fb198cfdca59b717239edb39c8f8462ec108bd6eded0e74a71c6095c2

calibrator signature:
cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181

calibrator sha256:
1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971

limiar congelado:
0.5241379310344827
```

O limiar e as ECDFs não foram reajustados no LiverHccSeg.

## Predições ainda cegas

Antes de qualquer leitura do artefato protegido:

```text
predições POSITIVE: 11
predições NEGATIVE: 3
score mínimo: 0.37931034482758624
score máximo: 0.8505747126436782
scores sha256:
e88580e542ca8e42552d8e3ba637c9f68a6254530ade26a69e5d105b2f0b6d00
```

Essas contagens não são apresentadas como TP/FN enquanto o ground truth
protegido não for aberto pelo avaliador autorizado.

## Gate de tempo

O tempo operacional por caso soma localizador, MedSigLIP e MedGemma:

```text
média: 33,13 s
máximo: 51,93 s
casos <= 180 s: 14/14
gate temporal: PASS
```

O tempo total de parede do lote não substitui a métrica operacional por caso,
pois os três modelos são carregados uma vez e executados em estágios separados
para respeitar a GPU de 8 GB.

## Protocolo de avaliação protegido

As predições foram congeladas. A próxima operação possível é abrir somente
`data/registry/protected/liverhccseg_selection_audit.json`, depois dos gates,
para comprovar a classe positiva e calcular TP, FN, sensibilidade e IC 95%.

```text
evaluation authorization protocol signature:
54cbca7db12d8c4dd32d9319b54320098b4d5ee14928fa93270e7837f2955022

score summary sha256:
8cd48d987cfa93972b40a294778d72b082e78782538ca746ab96ba98c97b59e0

prepared cohort sha256:
7b37690f12bc6c4cb4dd8392edfb0c75a977b435488bc6dc7ff78e0f4a274107

protected selection audit expected sha256:
7eafc841f8ebaa603741d6019e5a8ac24ba4cbd576ffddd4849997c0d0c68083
```

O avaliador deve continuar reportando `specificity=null`, `roc_auc=null` e
`qualified=false`. O holdout OpenSwissHCC deve permanecer fechado.

## Validação de software

Após a rodada:

```text
791 passed após o gate assinado e a avaliação protegida
396 warnings conhecidos
0 failures
```

Os warnings são depreciações conhecidas de SimpleITK, scikit-image, VTK e
Starlette e não representam falha funcional nesta execução.
