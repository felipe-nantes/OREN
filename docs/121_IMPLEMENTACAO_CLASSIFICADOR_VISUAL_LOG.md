# Implementação do classificador visual supervisionado — diário técnico

## Estado

```text
Plano: docs/120_PLANO_DE_ACAO_CLASSIFICADOR_VISUAL_SUPERVISIONADO.md
Início: 24 de julho de 2026
Fase atual: Fases 0–9 e Fase 13 concluídas; Fase 5 permanece candidata estável
```

## Fase 0 — Estado-base

### Inventário anterior às alterações deste plano

```text
branch: main
commit-base: 6ee41c58b267f9a6f1f4afb3c8487f4993eeab04
remote: https://github.com/felipe-nantes/argos.git
entradas no git status: 676
arquivos modificados: 34
arquivos não rastreados: 642
arquivos staged: 0
```

O working tree já estava amplamente modificado por todas as etapas anteriores.
Nenhum arquivo existente foi descartado, revertido ou sobrescrito em massa. A
nova linha foi isolada em `dtwin/learning`, `configs/training`, novas ferramentas
e novos testes.

### Proteção local

Foram adicionados ao `.gitignore`:

```text
.codex-tmp/
.pytest-tmp*/
.tmp-*/
/casos/qualification/hybrid_v1/
```

Isso impede que checkpoints temporários e artefatos supervisionados sejam
incluídos acidentalmente no Git. `casos/`, `data/`, DICOM, NIfTI e modelos já
estavam protegidos.

### Regressão antes da implementação

Suíte completa executada sobre o estado recebido:

```text
1147 passed
0 failed
607 warnings
tempo: 117,23 s
```

Os avisos são predominantemente depreciações em SimpleITK, scikit-image, VTK e
Starlette; não impediram a execução.

### Baselines científicos preservados

Referências mantidas:

```text
v23 dev87: 82,05% sensibilidade / 79,17% especificidade
v23 full132: 65,08% / 60,87%
v24 full132: 61,90% / 59,42%
v25 full132: 60,32% / 57,97%
v26 full132: 65,08% / 60,87%
v27 full132: 61,90% / 55,07%
```

O lock do v23 permanece em
`configs/benchmark/openswisshcc_v23_baseline_lock_v1.json`. A nova linha não
altera pesos, limiar ou código histórico do v23.

## Fase 1 — Fundação implementada

### Pacote isolado

Criado:

```text
dtwin/learning/
  __init__.py
  schemas.py
  splits.py
  protocol.py
```

O pacote não carrega modelos de GPU ao ser importado.

### Proteção de labels

`schemas.py` implementa:

- schema protegido de caso;
- validação do endpoint binário;
- validação de subtipos e phenotype tags;
- exclusividade entre subtipos positivos e negativos;
- guarda recursiva que impede labels, ground truth, máscaras de lesão e
  metadados protegidos no caminho de extração/inferência.

### Nested cross-validation

`splits.py` implementa:

- agrupamento por paciente;
- rejeição de labels conflitantes no mesmo paciente;
- folds externos determinísticos;
- folds internos determinísticos por fold externo;
- ausência de labels no artefato de splits;
- validação de cobertura exata;
- garantia de que cada caso aparece exatamente uma vez em teste externo;
- detecção de leakage entre treino, validação e teste.

### Freeze científico

`protocol.py` e `tools/freeze_hybrid_training_protocol.py` implementam:

- leitura explícita de labels públicos já consumidos;
- bloqueio de caminhos fora do workspace;
- bloqueio de arquivos cujo nome indique máscara/lesão;
- hashes SHA-256 das fontes;
- escrita atômica com flush, fsync e substituição;
- assinatura canônica do protocolo;
- verificador independente;
- imutabilidade do primeiro freeze;
- protocolo sem labels individuais;
- split sem labels individuais;
- registro explícito de zero máscaras abertas pelo freeze.

### Coorte inicial declarada

`configs/training/hybrid_v1_protocol.yaml` declara:

```text
OpenSwissHCC development
OpenSwissHCC antigo holdout já consumido
LLD-MMRI
```

Essas coortes são desenvolvimento retrospectivo. O arquivo não as apresenta
como validação externa cega.

### Ambiente

O extra opcional `training` foi criado sem alterar as dependências obrigatórias
do webapp:

```text
joblib
pandas
scikit-learn
```

Dependências pesadas de imagem serão acrescentadas somente na fase que realmente
as consumir.

## Próximo gate

### Testes focados

```text
16 passed
0 failed
3 warnings de bindings externos
```

### Freeze real concluído

O protocolo foi congelado antes da extração supervisionada:

```text
casos totais: 467
positivos: 220
negativos: 247
outer folds: 5
inner folds: 4
seed: 20260724
```

Assinaturas:

```text
protocol_signature:
7754fc80bbdf0de6775f699595059778d0b3cb6a8d22f2e801d3b4b1588f8510

hybrid_v1_protocol.lock.json SHA-256:
1105a80e949f9f81c03492f276ccae0d5a3c813b40dc5503ff25fdc1af46432e

hybrid_v1_nested_splits.json SHA-256:
41c15cc14b89ee80ee8afc7b60eab5637e729057fa3cbe92798cd45115f70fd0
```

O comando independente `verify` aprovou hashes, assinatura, fontes e estrutura
dos folds. Nenhuma máscara de lesão foi aberta.

## Próximo gate

## Fase 2 — Preflight isolado de treinamento

Foi criado um preflight somente leitura:

```text
dtwin/learning/environment.py
tools/check_hybrid_training_environment.py
```

Ele verifica versões, espaço em disco, disponibilidade da GPU e VRAM livre. O
preflight não instala pacotes, baixa modelos nem encerra processos.

Estado encontrado:

```text
Python: 3.13.14
joblib: 1.5.3
pandas: 3.0.3
scikit-learn: 1.9.0
torch: 2.12.1+cu126
transformers: 5.13.0
GPU: NVIDIA GeForce RTX 4060 Laptop, 8188 MiB
VRAM usada durante a vistoria: 7921 MiB
VRAM livre durante a vistoria: 36 MiB
```

Conclusão: dependências leves estão disponíveis, mas a GPU estava ocupada pelo
serviço MedGemma. O treinamento e a extração de embeddings só poderão começar
depois que o gateway for parado e o preflight confirmar ao menos 6144 MiB
livres. Isso é um bloqueio operacional esperado, não uma falha do projeto.

## Próximo gate

1. executar os testes novos e a regressão completa com o freeze presente;
2. parar o MedGemma apenas antes da primeira tarefa que realmente usa GPU;
3. especificar o contrato label-blind do dataset de candidatos;
4. iniciar a materialização somente após os testes de segurança desse contrato.

## Fase 3A — Contrato label-blind de painéis globais

Foi implementado o primeiro estágio do dataset visual:

```text
dtwin/learning/candidate_dataset.py
configs/training/hybrid_v1_candidate_dataset.yaml
tools/build_liver_candidate_dataset.py
tests/test_learning_candidate_dataset.py
```

Este estágio reutiliza apenas painéis liver-enriched já aprovados e sem
contornos. Ele não abre labels nem máscaras. O objetivo é viabilizar primeiro o
baseline MedSigLIP congelado sobre painéis globais; patches candidatos 2.5D
serão acrescentados depois, sem substituir este baseline.

Salvaguardas:

- protocolo e splits verificados sem abrir labels;
- caso fora dos splits é rejeitado;
- campos protegidos em manifesto técnico são rejeitados;
- `lesion_mask_used=false`;
- `ground_truth_used=false`;
- `contour_rendered=false`;
- `phi_metadata_removed=true`;
- hashes de todas as imagens;
- casos sem coleção válida tornam-se falhas técnicas e contam como erro;
- publicação atômica e saída imutável.

### Materialização real

```text
casos esperados pelos splits: 467
casos com painéis verificados: 451
falhas técnicas explícitas: 16
registros de painel: 1339
```

As 16 falhas correspondem à ausência de coleção liver-enriched verificada e
permanecem no denominador. Nenhum painel foi fabricado para esses casos.

Assinaturas:

```text
dataset_signature:
739ae746c059f6c10bbd8213ad2007231ab12a190d0714a65973a14208a44613

dataset_manifest.json SHA-256:
2692d72e9964fa8d8b7947341428b6f1b7f43fae44318718ab2556f2a66b22c5

candidate_records.jsonl SHA-256:
0ff2a40f4edcc5e3eddbb06dba95856ee2bf5c5bfa98fa44ba0c05eb4c70fc4f
```

O verificador independente confirmou cobertura exata dos 467 casos, hashes das
1339 imagens, zero labels e zero máscaras de lesão.

## Validação acumulada

```text
testes novos focados: 23 passed, 0 failed
suíte completa após Fases 0–2: 1166 passed, 0 failed
verificador histórico v23: aprovado, 14 arquivos verificados
```

## Próximo gate real

A Fase 4 exige a GPU. Antes da extração de embeddings:

1. parar o gateway MedGemma;
2. executar o preflight com `--require-training-ready`;
3. fixar revisão e processor do MedSigLIP;
4. implementar cache transacional de embeddings;
5. executar um smoke test pequeno antes dos 1339 painéis.

## Fase 4 — Extrator MedSigLIP congelado implementado

Componentes:

```text
dtwin/learning/medsiglip_embeddings.py
configs/training/medsiglip_frozen_v1.yaml
tools/extract_medsiglip_embeddings.py
tests/test_learning_medsiglip_embeddings.py
```

Contrato congelado:

```text
modelo: google/medsiglip-448
revision: 9cea28a1a1195f665105faa6e8544c112fd960a4
entrada: 448x448 RGB
pooling: vision_pooler_output
dimensão: 1152
normalização: L2
saída: float32
inferência interna: float16/CUDA
batch inicial: 4
downloads: desabilitados
```

O extrator:

- recebe apenas registros label-blind;
- valida hash e ausência de metadados PNG;
- grava um `.npy` por painel de forma atômica;
- faz fsync do checkpoint a cada batch;
- retoma uma execução interrompida;
- rejeita NaN, Inf, dimensão ou norma divergente;
- registra revisão e hashes do snapshot;
- descarrega o modelo e libera o cache CUDA ao terminar;
- nunca abre labels ou máscaras.

### Execução real da Fase 4

O gateway MedGemma foi encerrado antes da extração. O preflight confirmou:

```text
VRAM livre: 7956 MiB
blockers: nenhum
training_ready: true
```

Smoke test:

```text
4/4 embeddings válidos
dimensão: 1152
VRAM liberada ao final
embedding_signature:
5222553e5446c78c4b393c137220cbb05c709af70534bedf76e921a13c6b1ddf
```

Execução integral:

```text
1339/1339 embeddings válidos
tempo de extração: 177,5 s
ground_truth_read: false
lesion_masks_read: 0
VRAM usada após encerramento: 0 MiB
```

Assinaturas:

```text
embedding_signature:
4836ef54582a1376e7ad1c8dd3e7f5f3857d8be48cfe3126c03f9c9b5691a0dd

embedding_manifest.json SHA-256:
6922c6288d575dcfe06bf1505f44360cecead0b01dcc703e50b482d9ef743ff3

embedding_records.jsonl SHA-256:
721e983cc9c430c097a96f8e07817dcc5091129d4ebffb87fee83f9c2bf14327
```

O verificador recarregou cada vetor, validou hash, dtype, dimensão, finitude,
normalização e vínculo com o dataset candidato.

## Fase 5 — Classificador nested OOF implementado

Componentes:

```text
dtwin/learning/medsiglip_classifier.py
configs/training/medsiglip_classifier_v1.yaml
tools/train_medsiglip_classifier.py
tests/test_learning_medsiglip_classifier.py
```

Método:

- regressão logística L2 balanceada;
- padronização ajustada somente nos painéis de treino;
- `C = 0.01, 0.1, 1.0`;
- agregação por caso `mean`, `max` ou `top2_mean`;
- seleção do modelo, agregação e threshold exclusivamente por OOF interno;
- predição do paciente externo sem usar seu label;
- um score OOF por caso;
- falhas técnicas contam como FN ou FP conforme o label, somente no avaliador;
- arquivo de predições não contém ground truth;
- métricas gerais e por dataset;
- IC 95% de Wilson;
- saída explicitamente retrospectiva, não externa cega.

### Resultado nested OOF da Fase 5

Execução:

```text
467 predições OOF
451 casos computáveis
16 falhas técnicas contabilizadas como erro
tempo de treinamento/seleção OOF: 60 s
lesion_masks_read: 0
```

Assinaturas:

```text
prediction_signature:
231e7aea111c31d3d4f833853ac863ca1fb5dacc731ee339b5d7d6aa969e29be

oof_predictions.jsonl SHA-256:
378b7772be4f62d102c6b19a0e799afe3c37c8cefc7e050ca559fcb7527ec468

fold_selection.json SHA-256:
4b86b24cd096eb4c72632946ccbf6139126bfc31f88ee442b542aebce2346010

evaluation_signature:
2b75bd07c6f8a0a088588d1886455032bad2742c888e7a2d17a8b666d8441a34
```

Resultado geral:

```text
TP = 159
TN = 181
FP = 66
FN = 61

sensibilidade = 72,27%
especificidade = 73,28%
balanced accuracy = 72,78%
ROC-AUC computável = 0,8014
```

IC 95%:

```text
sensibilidade: 66,01%–77,77%
especificidade: 67,44%–78,41%
```

Por coorte:

| Coorte | Sensibilidade | Especificidade | ROC-AUC |
|---|---:|---:|---:|
| LLD-MMRI | 75,16% | 74,16% | 0,8081 |
| OpenSwissHCC development | 66,67% | 75,51% | 0,8109 |
| OpenSwissHCC antigo holdout consumido | 62,50% | 60,00% | 0,7127 |

### Decisão do gate

O classificador não atingiu 75%/75% e não será promovido ao webapp. Entretanto,
o gate de continuação foi aprovado porque:

- pior eixo geral acima de 60%;
- ROC-AUC geral de 0,8014;
- sinal consideravelmente mais discriminativo do que o MedGemma 4B saturado;
- resultado próximo da meta em LLD-MMRI;
- predições verdadeiramente OOF e sem leakage do paciente externo.

O próximo passo permitido pelo plano é a Fase 6: adicionar atributos radiômicos
e multifásicos e medir ganho incremental OOF. Não é permitido reajustar o
threshold usando estas mesmas predições como se fosse uma validação nova.

## Fase 6 — Radiômica hepática e dinâmica multifásica

### Contrato implementado

Componentes:

```text
dtwin/learning/radiomics_features.py
configs/training/radiomics_v1.yaml
tools/extract_candidate_radiomics.py
tests/test_learning_radiomics_features.py
```

Este primeiro contrato radiômico comum às duas bases usa exclusivamente:

```text
fase arterial
fase venosa
fase tardia
máscara hepática automática
```

Não usa máscara de lesão, label, subtipo clínico ou saída MedGemma.

Famílias de atributos:

- volume e extensões do fígado;
- ocupação da bounding box e cobertura axial;
- distribuição robusta de intensidade por fase;
- assimetria, curtose, entropia e caudas;
- gradiente e resíduo local como medidas de heterogeneidade focal;
- diferenças voxel a voxel arterial–venosa, arterial–tardia e venosa–tardia;
- dominância arterial conjunta;
- razões intrassujeito entre medianas e escalas das fases.

As intensidades são normalizadas pela mediana e MAD dentro do fígado erodido em
3 mm. Isso reduz diferenças arbitrárias de escala entre aparelhos. O extrator
exige geometria física coincidente, publica checkpoints com fsync, possui
retomada e transforma qualquer falha em registro explícito que conta como erro.

Texturas PyRadiomics de alta dimensionalidade foram deliberadamente adiadas:
aplicá-las ao fígado inteiro aumentaria o risco de aprender scanner/dataset, e
o plano prevê essas texturas preferencialmente sobre candidatos automáticos na
fase 2.5D.

### Execução multicohort da Fase 6

Resultado:

```text
casos esperados: 467
casos com features válidas: 448
LLD-MMRI com features: 321
OpenSwissHCC com features: 127
features por caso: 145
falhas técnicas totais: 19
falhas herdadas: 16
novas falhas por ausência de fonte multifásica comum: 3
valores não finitos: 0
features constantes: 0
```

Novas falhas explícitas:

```text
anon-openswiss-40c09ebcf8178f92
anon-openswiss-7bb936ce9f21d461
anon-openswiss-c83a32179466321d
```

Nenhum volume ou máscara foi fabricado para esses casos. Eles continuarão no
denominador da Fase 7.

Assinaturas:

```text
radiomics_signature:
8e72802fb06225f489080b25ecc701c023334ec45185aec78dd7bbcf10e4551b

radiomics_manifest.json SHA-256:
36d604aa102141afbe43b9ce828d5fe3debc83a73af370bec967497df9d00866

features.jsonl SHA-256:
1fa04cef41e16fb3cfe88561636b49e8a7b0b02cd36d8794e3ba2f7c3f67c0bc
```

O verificador independente confirmou os hashes das quatro fontes de cada caso,
geometria, schema idêntico de 145 atributos, cobertura exata dos 467 casos,
zero labels e zero máscaras de lesão.

### Estado do gate

A Fase 6 está concluída. A extração possui cobertura de 95,93% e fornece um
vetor quantitativo novo, independente das probabilidades do MedGemma e dos
embeddings MedSigLIP. O ganho discriminativo ainda não foi calculado, pois isso
pertence à Fase 7 e deve ocorrer exclusivamente por nested OOF.

Validação final após a Fase 6:

```text
1180 passed
0 failed
616 warnings
tempo: 110,46 s
```

## Fase 7 — Classificador radiômico

### Implementação

Componentes:

```text
dtwin/learning/radiomics_classifier.py
configs/training/radiomics_classifier_v1.yaml
tools/train_radiomics_classifier.py
tests/test_learning_radiomics_classifier.py
```

Foi implementada regressão logística elastic-net com:

- imputação mediana, padronização e seleção univariada ajustadas apenas no
  conjunto de treino de cada fold;
- grade congelada de `C={0.03, 0.1, 0.3}`,
  `l1_ratio={0.0, 0.5, 0.9}` e 32/64 atributos;
- seleção do modelo e do limiar exclusivamente pelas predições OOF dos inner
  folds;
- predição final exclusivamente no outer fold;
- 19 falhas técnicas preservadas no denominador e convertidas em erro do eixo
  correspondente;
- nenhum label ou máscara de lesão persistido no artefato de predição.

### Resultado nested OOF

```text
coorte: 467 casos
TP/TN/FP/FN: 118/141/106/102
falhas técnicas: 19
sensibilidade: 53,64%
especificidade: 57,09%
balanced accuracy: 55,36%
ROC-AUC nos casos computáveis: 0,6182
meta 75/75: não
```

Por dataset:

| Dataset | Sensibilidade | Especificidade | ROC-AUC |
|---|---:|---:|---:|
| LLD-MMRI | 50,32% | 58,99% | 0,6207 |
| OpenSwissHCC development | 64,10% | 51,02% | 0,6131 |
| OpenSwissHCC holdout já consumido | 58,33% | 55,00% | 0,6250 |

Assinaturas:

```text
prediction_signature:
42a9e93fc4ebdeda98613afb002f592a7a14aef742b1d896957d27a7692931e1

evaluation_signature:
d90b6f9e63f7e78aaf6dface94a53e39d3bbfad5658897c5a5491d1294195eec

prediction_freeze.json SHA-256:
1099d59b5a562648cd5cf289514b1dc19775719b680bab7267945b696c2472b5

evaluation.json SHA-256:
9cc95356f25adc7b940338649481bc53837ee406f831095639238ecb48574b4b
```

### Decisão

A Fase 7 foi concluída e rejeitada para fusão. O sinal está acima do acaso, mas
não supera 60% nos dois eixos, não adiciona evidência suficientemente forte ao
MedSigLIP/v23 e permanece semelhante entre datasets em um patamar baixo. Não
será integrado ao webapp. Como o gate falhou, a Fase 8 tornou-se necessária.

## Fase 8 — Localizador e classificador 2.5D

### Estratégia implementada

Para manter compatibilidade com a GPU de 8 GB, a primeira implementação 2.5D
usa o MedSigLIP congelado como backbone médico compacto e treina somente um
classificador linear de candidatos. Isso evita fine-tuning pesado e mantém o
teste isolado do MedGemma.

Componentes:

```text
dtwin/learning/patch25d_dataset.py
dtwin/learning/patch25d_classifier.py
configs/training/patch25d_v1.yaml
configs/training/patch25d_classifier_v1.yaml
tools/build_patch25d_dataset.py
tools/train_patch25d_classifier.py
tests/test_learning_patch25d_dataset.py
tests/test_learning_patch25d_classifier.py
```

O localizador automático congelado é `joint-enhancement t3/top10 por volume`.
Sua geração não lê labels ou máscaras. A auditoria retrospectiva pública já
existente foi validada antes da geração:

```text
recall por caso: 94,59%
recall por lesão: 86,49%
gate mínimo: 85%/85%
gate do localizador: aprovado
```

Foram renderizados cinco cortes adjacentes por candidato. Arterial, venosa e
tardia formam os canais RGB; o crop é de 80 mm, sem contorno de lesão, PHI ou
ground truth. Resultado label-blind:

```text
casos declarados: 87
casos com registro multifásico: 84
falhas técnicas: 3
candidatos automáticos: 839
dataset_signature:
f85733caf1d32df14ac758fd3d7f8b56fdcfde01aad2aadc39b10354454388fb
```

Somente após a publicação e o hash das imagens, as máscaras venosas públicas
autorizadas foram abertas para produzir targets protegidos de treino:

```text
targets totais (incluindo placeholders de falha): 842
targets supervisionados: 819
candidatos positivos: 56
candidatos negativos: 763
positivos sem máscara venosa: 2
target_signature:
e141332045dc25c803a2a280dbd4799881b7b7a98c08177e22ecfacd63217905
```

As máscaras nunca participaram da geração da imagem, embedding ou inferência.
Os 839 embeddings MedSigLIP foram extraídos e verificados:

```text
embedding_signature:
97f8a473a2502f39139c1348880def57bae9649b2431f074232682e25d0e1d90
dimensão: 1152
modelo/revisão:
google/medsiglip-448@9cea28a1a1195f665105faa6e8544c112fd960a4
```

O classificador de candidatos foi ajustado somente com candidatos
supervisionados dos folds de treino. A agregação por exame (`max`,
`top2_mean`, `top3_mean`), regularização e limiar foram escolhidos nos inner
folds; cada caso foi previsto apenas no outer fold.

### Resultado nested OOF

```text
coorte OpenSwissHCC development: 87
TP/TN/FP/FN: 18/22/26/21
falhas técnicas: 3
sensibilidade: 46,15%
especificidade: 45,83%
balanced accuracy: 45,99%
ROC-AUC nos casos computáveis: 0,5208
meta 75/75: não
```

Assinaturas:

```text
prediction_signature:
0e5cae5957650ec57a958e61a79343357ebdbf62eed3600069cc0b29dfa16cb0

evaluation_signature:
ace9fe615070579915a3c978716d31c69a715ffd26b722e33d01e0cfb8e32467

dataset_manifest.json SHA-256:
b3938ffd5f0ed456198286a7021e7b6f40f4273fea5cddb8d66fcf139abb28bc

target_manifest.json SHA-256:
9daba58fdaf982dd045972fbb7152cb1d9686ec4d3c651df26789266e4557cec

embedding_manifest.json SHA-256:
8d032f62c810c9edf81297155850ec03f808e69974de77677adcb1112043c014

prediction_freeze.json SHA-256:
9fdd4539b677ddac6112ece50beb75c065301e54141bdc3167c1d09636314a92

evaluation.json SHA-256:
bd44d3ff7f5660e367fcd192bf3704a625f133b97480373a6297d21df569da9e
```

### Decisão

O gate do localizador passou, mas o classificador 2.5D v1 falhou claramente. A
representação top10 encontra as lesões, porém os embeddings congelados dos
patches não separam candidatos patológicos de estruturas vasculares/realce
benigno. Esta versão não será promovida nem fundida ao v23. A Fase 9 não deve
usar os scores radiômicos ou 2.5D rejeitados; a próxima tentativa válida deve
voltar ao melhor sinal já demonstrado (MedSigLIP global/v23) ou treinar um
backbone 2.5D de fato adaptado, com mais supervisão de candidatos e validação
externa.

Validação final após as Fases 7 e 8:

```text
1189 passed
0 failed
619 warnings
tempo: 105,83 s
```

## Fase 9 — Fusão tardia congelada com o v23

### Implementação

Foram adicionados:

```text
dtwin/learning/late_fusion.py
configs/training/late_fusion_v1.yaml
tools/evaluate_late_fusion.py
tests/test_learning_late_fusion.py
```

A tentativa usou somente scores OOF já congelados e a regra previamente fixa:

```text
80% margem assinada v23 + 20% margem assinada MedSigLIP Fase 5
threshold final: zero
coorte comum: OpenSwissHCC 132
```

Radiômica e 2.5D não foram incluídas porque falharam nos respectivos gates.
Nenhum peso ou threshold foi escolhido a partir dos labels dos 132 casos.

### Resultado

```text
TP/TN/FP/FN: 46/49/20/17
falhas técnicas: 2
sensibilidade: 73,02%
especificidade: 71,01%
balanced accuracy: 72,02%
ROC-AUC: 0,7643
meta 75/75: não
```

Assinaturas:

```text
fusion_signature:
da3b16ec854e26e6a217d40e9e874519cb0d355f1eb2a598d488cee28f2394ed

evaluation_signature:
67df4d6233aa0ae913c27cb2a83b988c9dfce1690f350fb674ec6c09c062de54
```

### Decisão

A fusão foi uma tentativa válida e melhorou substancialmente o v23 full132,
mas não atingiu 75/75. A Fase 5 não foi alterada. Como os embeddings congelados
mantinham sinal real, foi ativada a condição prevista no plano para a Fase 13.

## Fase 13 — Fine-tuning parcial do MedSigLIP

Todos os estágios usaram os mesmos 467 casos, os mesmos outer folds e a mesma
política de falhas da Fase 5. Os artefatos da Fase 5 foram tratados como
imutáveis e seus hashes foram novamente conferidos.

### Estágio 1 — Cabeça não linear, encoder congelado

Componentes:

```text
dtwin/learning/medsiglip_head_classifier.py
configs/training/medsiglip_head_v1.yaml
tools/train_medsiglip_head.py
tests/test_learning_medsiglip_head_classifier.py
```

Uma MLP pequena foi treinada sobre os embeddings congelados, com seleção de
arquitetura, regularização e threshold exclusivamente nos inner folds.

```text
sensibilidade: 70,45%
especificidade: 69,64%
balanced accuracy: 70,05%
ROC-AUC: 0,8018
meta 75/75: não
```

O estágio não superou a cabeça linear congelada da Fase 5 e foi rejeitado.

### Estágio 2 — Último bloco visual completo

Componentes:

```text
dtwin/learning/medsiglip_partial_finetune.py
configs/training/medsiglip_partial_finetune_v1.yaml
tools/train_medsiglip_partial.py
tests/test_learning_medsiglip_partial_finetune.py
```

Foi liberado somente o último bloco do encoder visual. O treino usou batch por
caso, AMP `bfloat16`, acumulação de gradiente, early stopping interno,
checkpoint atômico por fold e um modelo de GPU residente por vez. A GPU RTX
4060 de 8 GB permaneceu dentro do orçamento, com cerca de 2,5 GB observados
durante o treino.

```text
sensibilidade: 57,27%
especificidade: 55,47%
balanced accuracy: 56,37%
ROC-AUC: 0,5897
meta 75/75: não
```

O ajuste completo do bloco degradou fortemente o sinal pré-treinado e foi
rejeitado.

### Estágio 3 — LoRA Q/V no último bloco visual

Foi criada a configuração:

```text
configs/training/medsiglip_lora_v1.yaml
```

O encoder-base permaneceu congelado. Adaptadores LoRA de rank 4 foram
aplicados apenas às projeções Q/V do último bloco. A cabeça foi inicializada
por regressão logística ajustada somente no treino interno sobre os embeddings
congelados, preservando um ponto de partida próximo da Fase 5. As imagens e
embeddings continuaram label-blind; máscaras de lesão lidas: zero.

Resultado multicohort OOF:

```text
TP/TN/FP/FN: 165/174/73/55
falhas técnicas: 16
sensibilidade: 75,00%
especificidade: 70,45%
balanced accuracy: 72,72%
ROC-AUC: 0,8187
meta 75/75: não
```

Por dataset:

```text
LLD-MMRI:       77,07% sensibilidade / 71,91% especificidade
OpenSwiss dev:  69,23% / 69,39%
OpenSwiss hold: 70,83% / 60,00%
```

Assinaturas:

```text
prediction_signature:
b23090d73151226f36bee92a4d4783cb8051482498614d528357cc7129babfc6

evaluation_signature:
71fc3b7c6d405da3cdfe7beff60e8af042b4fd3af4aa273a9969933560b7667c
```

O LoRA recuperou sensibilidade e aumentou a AUC, mas perdeu especificidade e
não foi promovido. Uma ablação fixa, sem ajuste por labels, de 80% Fase 5 +
20% LoRA resultou em 73,64% de sensibilidade e 73,28% de especificidade,
também abaixo da meta.

### Decisão da Fase 13

O gate do plano determina manter o encoder congelado quando o fine-tuning não
supera a alternativa congelada nos dois eixos. Portanto:

```text
Fase 5 preservada como candidata estável: sim
cabeça MLP promovida: não
último bloco completo promovido: não
LoRA promovido: não
QLoRA MedGemma em GPU de 8 GB: não recomendado pelo plano
integração backend/webapp: bloqueada pelo gate 75/75
```

A melhor candidata geral continua sendo a Fase 5:

```text
467 casos
sensibilidade: 72,27%
especificidade: 73,28%
ROC-AUC: 0,8014
```

O melhor avanço de sensibilidade foi LoRA (75,00%), mas sem a especificidade
mínima. Isso confirma que a lacuna atual não é resolvida de forma estável por
maior flexibilidade da cabeça ou por adaptação limitada do encoder neste
hardware/dataset.

### Verificação independente e regressão final

Foi adicionado `tools/verify_medsiglip_phase13.py`, com hashes da Fase 5
fixados em `configs/training/phase13_verification_v1.yaml`. O verificador não
abre labels nem máscaras e confirmou:

```text
Fase 5 inalterada: sim
casos únicos por candidato: 467
ground truth em predições: 0
labels lidos pelo verificador: 0
máscaras de lesão lidas: 0
status: passed
verification_signature:
ec71cb71976784864dfeb4b4bed59029b771975a10a6939924b33a01a323649a
```

Suíte completa após Fases 9 e 13:

```text
1197 passed
0 failed
620 warnings
tempo: 101,76 s
```

## Encerramento do primeiro ciclo

O primeiro incremento definido no plano, Fases 0–5, foi concluído.

Validação final do código:

```text
1176 passed
0 failed
607 warnings
tempo: 105,81 s
```

Estado:

```text
baseline histórico preservado: sim
protocolo e folds congelados: sim
dataset visual label-blind verificado: sim
embeddings MedSigLIP congelados: sim
predições nested OOF: sim
meta 75%/75% atingida: não
gate para informação complementar: aprovado
integração no webapp: não autorizada pelo gate estatístico
```

## Fase 9B — fusão meta-OOF de Fase 5 + LoRA (nova, distinta da Fase 9)

### Motivação

A Fase 5 (MedSigLIP linear, 467 casos) tem a melhor especificidade
(73,28%); o LoRA da Fase 13 estágio 3 (467 casos) tem a melhor
sensibilidade (75,00%) e a maior AUC (0,8187). Os dois cobrem exatamente a
mesma coorte multicohort. Uma ablação fixa não-OOF-selecionada, citada só no
log da Fase 13 (80% Fase 5 + 20% LoRA), já havia chegado perto da meta
(73,64%/73,28%) sem nenhuma seleção de peso propriamente dita. Esta fase
testa se uma fusão com peso e threshold selecionados corretamente no inner
CV consegue superar isso.

Diferente da Fase 9 (`late_fusion.py`, pesos fixos 80/20, sem seleção), esta
fase treina uma regressão logística L2 sobre a margem assinada
(`score - threshold`) de cada sinal, com `C` e threshold escolhidos **apenas**
nos folds internos dos mesmos splits já congelados
(`hybrid_v1_nested_splits.json`) — nenhum split novo foi gerado.
`late_fusion.py` não foi tocado; o módulo novo é
`dtwin/learning/multi_signal_fusion.py`.

### Diagnóstico prévio — correlação entre sinais

```text
correlação (Pearson) Fase5 x LoRA: 0,894
```

Os dois sinais são fortemente correlacionados — esperado, já que o LoRA foi
inicializado a partir da cabeça linear da Fase 5. Isso já sinalizava um
limite baixo para o ganho possível de qualquer fusão linear dos dois.

### Resultado primário — Fase5 + LoRA, 467 casos multicohort

```text
467 casos, 16 falhas técnicas herdadas
TP=160 TN=180 FP=67 FN=60
sensibilidade = 72,73%
especificidade = 72,87%
balanced accuracy = 72,80%
ROC-AUC = 0,7993
meta 75/75: não
```

Por dataset:

| Dataset | Sensibilidade | Especificidade | AUC |
|---|---:|---:|---:|
| LLD-MMRI | 74,52% | 73,60% | 0,8117 |
| OpenSwissHCC development | 69,23% | 73,47% | 0,7949 |
| OpenSwissHCC holdout já consumido | 66,67% | 65,00% | 0,7061 |

Assinaturas:

```text
prediction_signature:
7721f0b6e2985f24080c5be525dfa4292b057649b006721ac87dbc640f5dcb23

evaluation_signature:
d89fedb3e9e8818d4983caab32dc38aed9bdd65352f8a7b20b6bde813493e5ce
```

### Resultado secundário — v23 + Fase5 + LoRA, 132 casos OpenSwissHCC

Só onde o v23 histórico existe; cohort pequena, já conhecida por não
generalizar (comparação, não resultado principal).

```text
132 casos, 2 falhas técnicas
TP=43 TN=48 FP=21 FN=20
sensibilidade = 68,25%
especificidade = 69,57%
ROC-AUC = 0,7567
meta 75/75: não
```

Assinaturas:

```text
prediction_signature:
1a7c8b151524e216c64186630e5c2e58bcd36e29237a5bc26391c91dd3590853

evaluation_signature:
1404da005b934cb9ecb2785b30c24acdff199e67857518f194de45f9ed430d46
```

### Decisão

**Nenhuma das duas fusões supera os melhores sinais individuais nos dois
eixos simultaneamente.** A fusão primária (72,73%/72,87%) fica entre a Fase
5 (72,27%/73,28%) e o LoRA (75,00%/70,45%) sem superar nenhum dos dois — a
alta correlação (0,894) entre os sinais deixa pouca informação
complementar para uma fusão linear explorar. A fusão secundária com v23
piora em relação à própria Fase 9 original (73,02%/71,01% em 132 casos),
provavelmente porque o sinal mais fraco (v23, 65,08%/60,87%) dilui o
sinal combinado numa cohort pequena. Nenhuma das duas é promovida. A Fase
5 e o LoRA seguem como os dois melhores candidatos individuais, conforme
a Fase 13 já havia estabelecido.

## Fase 10 — robustez multicohort e diagnóstico por subgrupo

### Implementação

```text
dtwin/learning/robustness.py
tools/evaluate_hybrid_robustness.py
tests/test_learning_robustness.py
```

Três diagnósticos, aplicados a quatro candidatos lado a lado (Fase 5, LoRA,
e as duas fusões da Fase 9B): leave-one-dataset-out (usa `dataset_id` já
presente em cada predição, nenhum label novo), bootstrap por
`patient_group_id` (nunca por caso solto) para IC95%, e métricas por
`negative_subtype`/`positive_subtype`/`phenotype_tags`, unidas aos scores
label-blind só nesta etapa de avaliação.

### Achado metodológico: subtipo clínico não populado nesta coorte

As três fontes de label protegido do protocolo `hybrid_v1`
(`development_labels.jsonl`, `holdout_labels.jsonl`, LLD-MMRI `labels.jsonl`)
**não preenchem** `negative_subtype`/`positive_subtype`/`phenotype_tags` —
confirmado por leitura direta: OpenSwissHCC não tem nenhum desses campos;
LLD-MMRI tem um campo `subtype` genérico que não é mapeado por
`ProtectedTrainingCase`. Cobertura real, para todos os quatro candidatos:

```text
negative_subtype: 0,0%
positive_subtype: 0,0%
phenotype_tags: 0,0%
```

`subgroup_metrics` foi implementado para reportar essa cobertura
honestamente em vez de assumir dado presente — não há, hoje, como quebrar o
desempenho por variante anatômica/pseudolesão/HCC dentro do protocolo
`hybrid_v1` sem antes reprocessar as fontes de label com os subtipos
completos (fora do escopo deste incremento).

### Resultado — comparação e leave-one-dataset-out

```text
                          | sens.   | esp.    | AUC    | pior dataset (sens/esp)
medsiglip_phase5          | 72,27%  | 73,28%  | 0,8014 | 62,50% / 60,00%
medsiglip_lora_stage3     | 75,00%  | 70,45%  | 0,8187 | 69,23% / 60,00%
fusion_phase5_lora        | 72,73%  | 72,87%  | 0,7993 | 66,67% / 65,00%
fusion_v23_phase5_lora    | 68,25%  | 69,57%  | 0,7567 | 66,67% / 50,00%
```

**Nenhum candidato passa 75/75 em nenhum dos três datasets isoladamente.**
O padrão é consistente nos quatro candidatos: `openswisshcc_consumed_holdout`
(44 casos, o antigo holdout do v21 já consumido) é sistematicamente o pior
subgrupo — especificidade de 60% (Fase 5, LoRA) a 50% (fusão com v23).
LLD-MMRI (335 casos) é onde todos os candidatos mais se aproximam da meta
(sensibilidade 74–77%, especificidade 72–74%). O bootstrap por paciente
(2000 resamples, `patient_group_count=467`, um grupo por caso nesta coorte)
reproduz o IC95% de Wilson pontual dentro de margem estreita — a estimativa
é internamente estável, só está abaixo da meta.

Assinaturas dos relatórios (`report_signature`, `casos/qualification/hybrid_v1/robustness_v1/`):

```text
medsiglip_phase5:       5f6b0a8c80dcdd33305ae60a0c997e2b0c0f3afe39e588275bcce4052d1ce6e6
medsiglip_lora_stage3:  5ee8e65380dc9394150d46f2dfa88627ebe2ce7c96b391e5321a6a054a35e8db
fusion_phase5_lora:     644edde66bc4f02978908d7a2568145d0bb328791175e78e81a550fad7360587
fusion_v23_phase5_lora: 5f236acdb083a115ac346bf95f0ae70cfc0fda485d4083b1245bc993d06ab8ae
```

### Decisão do gate

Nenhum candidato estabiliza 75/75 por dataset — a instabilidade concentrada
no holdout OpenSwissHCC antigo (44 casos) é o mesmo padrão de "cohort
pequena não generaliza" já documentado na linha histórica v23 dev87→full132.
Por regra da matriz de decisão (doc 120 §7, "Fusão atinge 75/75 mas colapsa
por dataset → declarar resultado retrospectivo instável" — aqui nem sequer
atinge 75/75 no agregado), nenhum candidato é promovido ao webapp. A Fase 5
e o LoRA seguem como candidatas estáveis de referência; a Fase 9B não altera
essa conclusão.

## Fase — preparação da transferência MedGemma 27B (não executada)

Conforme panorama (`docs/119_PANORAMA_GERAL_ATUAL_ARGOS.md` §15, "Etapa 1"),
foi congelado `configs/training/medgemma_27b_transfer_protocol_v1.yaml`,
referenciando o mesmo protocolo/splits já usados pela linha supervisionada e
os configs pathology-target já existentes para 4B (Windows) e 27B
(Mac/Ollama). `comparison_status: not_yet_executed` — a execução real
(Etapa 2 do panorama) depende do Mac e fica fora do escopo deste
incremento.

## Etapa A — diagnóstico por mimetizador clínico

### Motivação

A Fase 10 mostrou que nenhum candidato passa 75/75, mas não conseguia dizer
**onde** o erro se concentra: o vocabulário canônico de subtipo
(`NEGATIVE_SUBTYPES`/`POSITIVE_SUBTYPES`) tem cobertura 0% neste protocolo.
Sem isso, qualquer decisão sobre o próximo passo seria no escuro.

### Achado de dado

O campo `subtype` do LLD-MMRI **existe e está 100% preenchido** nas 335
linhas da fonte protegida:

```text
hcc:           157  (POSITIVE)
hemangioma:     79  (NEGATIVE)
hepatic_cyst:   53  (NEGATIVE)
fnh:            46  (NEGATIVE)
```

Ele era simplesmente descartado por `ProtectedTrainingCase.from_mapping`,
que só aceita o vocabulário fechado. Mapear hemangioma/cisto/FNH para o
vocabulário canônico os colapsaria todos em `benign_non_target_finding` —
destruindo exatamente a granularidade necessária. Optou-se por carregar o
subtipo clínico bruto como **dimensão separada de avaliação**
(`load_protected_label_rows` + `clinical_subtype_metrics`), sem alterar a
taxonomia compartilhada com o benchmark clínico.

### Resultado — desempenho por mimetizador (LLD-MMRI, 335 casos)

| Subtipo | Classe | Casos | Eixo | Fase 5 | LoRA |
|---|---|---:|---|---:|---:|
| hcc | POSITIVE | 157 | sensibilidade | 75,16% | 77,07% |
| fnh | NEGATIVE | 46 | especificidade | 82,61% | 84,78% |
| hemangioma | NEGATIVE | 79 | especificidade | 79,75% | 74,68% |
| **hepatic_cyst** | NEGATIVE | 53 | especificidade | **58,49%** | **56,60%** |

Cobertura: 335/467 casos (71,7%). Os 132 casos OpenSwissHCC não declaram
subtipo clínico em nenhuma fonte — reportado como cobertura 0 em vez de
assumido.

### Interpretação

O erro **não** está distribuído entre os mimetizadores. HCC, FNH e
hemangioma já estão em patamar aceitável (74–85%); praticamente todo o
déficit de especificidade vem de um único bucket: **cisto hepático**, onde
~42% dos casos são chamados de positivos.

Isso é clinicamente contraintuitivo — um cisto simples é o achado mais fácil
de descartar em RM (não realça em nenhuma fase, é marcadamente
hiperintenso em T2, homogêneo e bem delimitado). O padrão observado é
consistente com um classificador que responde a **conspicuidade**, não a
caracterização: o desempenho piora conforme a lesão fica mais conspícua
(FNH, a mais sutil, é a melhor; cisto, a mais chamativa, é a pior).

### Projeção quantificada

Corrigindo apenas o bucket de cisto, mantendo todo o resto inalterado:

```text
Fase 5  (sens 72,27%): cisto->80% => esp 77,73% | cisto->90% => esp 80,16%
LoRA    (sens 75,00%): cisto->80% => esp 75,30% | cisto->90% => esp 77,73%
```

O LoRA, que já tem 75,00% de sensibilidade agregada, **passaria o gate
75/75 na coorte completa de 467 casos** se a especificidade em cisto subir
de 56,60% para 80% — um alvo plausível para uma lesão que não realça.

Esta é a primeira via quantificada e concreta para a meta em todo o
histórico do projeto. Não é garantia: o ganho precisa ser conquistado com
sinal novo e medido em nested OOF, não assumido.

### Consequência para a Etapa B

A hipótese da assinatura dinâmica por candidato é sustentada, mas
**redirecionada**: a feature de maior retorno não é a curva sutil de
washout, e sim a mais trivial de todas — **magnitude de realce do candidato
relativa ao parênquima, através das fases**. Um cisto tende a zero (ou
negativo) nessa medida em todas as fases. É barata, robusta e ataca
diretamente o maior bucket de erro.

Assinaturas dos relatórios (`casos/qualification/hybrid_v1/robustness_v2_clinical_subtypes/`):

```text
medsiglip_phase5:       5a7715131e42d9a7fb16cfdd2f572963b5bca0dfd38d1cdd9e7ab3270b9602ef
medsiglip_lora_stage3:  649e92bbfc61004f717ee121613a0f301d060bf62a7cadaeb69782ff88e72553
fusion_phase5_lora:     a43c740e30b74e83444b97186ce609b75b924315a4d5c092d61499fd8c6fe7a5
fusion_v23_phase5_lora: 4c7e6706b0a32829e2b74a7c3b0e92c2cf5eaf4c3ea75581a66fd064328ca497
```

## Etapa B — assinatura dinâmica por candidato (hipótese NÃO sustentada)

### Hipótese

A Etapa A mostrou que quase todo o déficit de especificidade vem de um único
bucket (cisto hepático, ~42% chamados positivos). Como um cisto simples não
realça em nenhuma fase pós-contraste, a hipótese era que uma medida de
**realce por candidato relativa ao parênquima local** separaria cisto de HCC,
onde a radiômica da Fase 6/7 falhou por medir o **fígado inteiro** (uma lesão
de 2 cm é ~0,1% dos voxels do órgão).

Compromisso metodológico assumido antes de rodar: **duas** operacionalizações
pré-especificadas; se ambas falhassem, encerrar a hipótese em vez de iterar
parâmetros contra os dados.

### Sonda 1 — hipointensidade persistente por valor extremo

Feature: mínimo, sobre os voxels do fígado, do mínimo entre fases do z-score
relativo ao parênquima (suavizado 3 mm). Cisto deveria ser o mais negativo.

```text
hcc           -6.51   <- menos hipointenso
hepatic_cyst  -8.23
hemangioma    -9.01   <- MAIS hipointenso que o cisto
fnh           -7.64

AUC cisto vs resto: 0,4861  (aleatório)
```

Diagnóstico: estatística de valor extremo mede "quão escura é a coisa mais
escura do fígado". Todo fígado tem estruturas persistentemente escuras
(ductos biliares, fissuras, fluido fisiológico, artefatos), presentes em
**todos** os casos — não "existe uma lesão focal que não realça".

### Sonda 2 — volume de lesão compacta persistentemente não-realçante

Correção mecanística (não ajuste a rótulo): conjunção por voxel exigindo
hipointensidade em **todas** as fases (exclui HCC que realça na arterial,
hemangioma que preenche na tardia, FNH), abertura morfológica para remover
estruturas tubulares finas, e **volume** de componentes sobreviventes em vez
de valor extremo.

```text
                 volume total (mL), mediana
hcc                     0,00
hepatic_cyst            0,00
hemangioma              0,00
fnh                     0,00

AUC cisto vs resto: 0,5543 (total) / 0,5475 (maior componente)
```

O detector encontrou volume ~zero em **todos** os subtipos, inclusive cistos:
a operacionalização é restritiva demais. O spacing do LLD é anisotrópico
(0,76 × 0,76 × 3,0 mm), então a abertura de 3 mm exige ~9 mm de extensão
através dos cortes — agressiva para cistos pequenos.

### Diagnóstico de registro — hipótese própria refutada

Antes de concluir, testei a explicação mais plausível para a falha: aritmética
voxel-a-voxel entre fases exige registro **anatômico**, e grade coincidente
(o que a Fase 6 verifica com `_same_geometry`) não é o mesmo que anatomia
alinhada, já que fases dinâmicas são aquisições separadas e a respiração
desloca o fígado.

Deslocamento rígido ótimo por correlação de fase, contra o controle
OpenSwissHCC (cujas fases passaram por registro explícito):

```text
LLD-MMRI    arterial vs venosa:  mediana 0,00 mm, max 1,48 mm
LLD-MMRI    tardia  vs venosa:   mediana 0,00 mm, max 1,48 mm
OpenSwiss   arterial registrada: mediana 0,00 mm, max 1,19 mm  (controle)
OpenSwiss   tardia   registrada: mediana 0,00 mm, max 0,00 mm  (controle)
```

As fases do LLD **já estão bem registradas**, indistinguíveis do controle que
passou por registro formal. **Misregistro não é a causa** — a hipótese
explicativa foi refutada, não confirmada. Registrar isso evita que o projeto
invista numa infraestrutura de registro que não é o gargalo.

### Decisão

A hipótese **não está refutada** (a física continua verdadeira: cisto não
realça), mas **não é sustentada** por duas operacionalizações
pré-especificadas. Fazê-la funcionar exigiria iterar parâmetros de
processamento de imagem contra os rótulos — exatamente a armadilha de
sobreajuste que o doc 120 §3.2 proíbe e que o compromisso desta etapa
antecipou. A linha é encerrada aqui, sem código de produção promovido.

Nenhuma config órfã foi deixada: `candidate_enhancement_v1.yaml`, escrita
durante a etapa, foi removida por não corresponder a um contrato validado.

### Padrão acumulado — sinal para a estratégia

Três tentativas de feature manualmente engenheirada já falharam
(Fase 7 radiômica, Fase 8 patches 2.5D, Etapa B realce por candidato),
enquanto os três melhores sinais do projeto são todos derivados de
**representação aprendida** (MedSigLIP congelado, LoRA, e a fusão dos dois).
Isso é evidência empírica acumulada de onde está o valor neste problema, e
deve orientar a próxima etapa.

Uma oportunidade concreta permanece **não explorada**: a Fase 8 treinou
classificador de candidato em apenas 87 casos OpenSwissHCC com 56 candidatos
positivos — gravemente subdimensionado — e nunca no LLD-MMRI, que tem 335
casos cujos negativos são exatamente os mimetizadores em questão. Além disso,
os rótulos de subtipo descobertos na Etapa A (hcc/hemangioma/cisto/fnh)
permitem supervisão **multiclasse** sobre os embeddings MedSigLIP **já
extraídos**, em vez de binária — forçando o modelo a aprender por que as
lesões diferem, não apenas "anormal ou não". Isso não requer GPU nova nem
processamento de imagem novo.

## Etapa C — supervisão multiclasse (primeiro candidato a passar o gate agregado)

### Hipótese e desenho

A Etapa B mostrou que injetar uma *feature* manualmente engenheirada falha. Esta
etapa muda o lever: **rótulo mais fino em vez de feature mais fina**, sobre a
MESMA representação. Os subtipos descobertos na Etapa A permitem treinar a
cabeça para dizer QUAL lesão vê, e derivar a decisão binária como a massa de
probabilidade nas classes positivas.

Ablação apples-to-apples contra a Fase 5: mesmos embeddings
(`embedding_signature` 4836ef54…), mesmos splits (`splits_sha256` 41c15cc1…),
mesma família de modelo, mesmas agregações, mesma seleção de threshold no inner
CV, mesma política de falhas. **A única diferença é a granularidade do rótulo
no ajuste.** Artefatos da Fase 5 não foram modificados.

Espaço de rótulos (nenhuma informação fabricada — o endpoint binário é
inalterado, e a polaridade de cada classe é validada contra os labels
protegidos, falhando fechado em caso de contradição):

```text
LLD-MMRI      hcc 157 | hemangioma 79 | hepatic_cyst 53 | fnh 46
OpenSwissHCC  positive_unspecified 63 | negative_unspecified 69
```

Os positivos do OpenSwissHCC **não** estão documentados como especificamente
HCC na fonte protegida, então recebem classe explicitamente não especificada em
vez de um subtipo inventado.

### Resultado — 467 casos multicohort

```text
TP 167 | TN 188 | FP 59 | FN 53 | falhas técnicas 16
sensibilidade    = 75,91%   (IC95% Wilson 69,84–81,08%)
especificidade   = 76,11%   (IC95% Wilson 70,42–81,01%)
bootstrap por paciente: sens 70,25–81,82% | esp 70,99–81,47%
ROC-AUC          = 0,8534
gate 75/75 (estimativa pontual): APROVADO
```

Comparação direta contra os melhores candidatos anteriores:

| Candidato | Sensibilidade | Especificidade | AUC |
|---|---:|---:|---:|
| Fase 5 (binário, mesma representação) | 72,27% | 73,28% | 0,8014 |
| Fase 13-3 LoRA | 75,00% | 70,45% | 0,8187 |
| **Etapa C multiclasse** | **75,91%** | **76,11%** | **0,8534** |

O ganho de AUC (+0,053 sobre o melhor anterior) indica melhoria em nível de
**representação/ordenação**, não apenas deslocamento de threshold.

Assinaturas:

```text
prediction_signature:
01d8f7017c93141ad04b35c1cfa943419e363b80b96acb7082dcc0120bd7c630

evaluation_signature:
744456cfa1d8f2ae60cac22a7799aca4f3023b461002e25d35f8cd9fda1619f5

robustness report_signature:
6a4dd3b3d4f3a0999f1769a6594f483cea8a702778a864813044fb41e72b7afd
```

### O mecanismo NÃO foi o previsto

A Etapa A previu que o ganho viria da especificidade em cisto. Os números
refutam parcialmente essa previsão:

| Subgrupo | Eixo | Fase 5 | Multiclasse | Δ |
|---|---|---:|---:|---:|
| hepatic_cyst | especificidade | 58,49% | 64,15% | +5,7 pp |
| fnh | especificidade | 82,61% | 89,13% | +6,5 pp |
| hemangioma | especificidade | 79,75% | 78,48% | −1,3 pp |
| hcc (LLD) | sensibilidade | 75,16% | 73,25% | **−1,9 pp** |
| OpenSwiss dev | sensibilidade | 66,67% | 82,05% | **+15,4 pp** |
| OpenSwiss holdout | sensibilidade | 62,50% | 83,33% | **+20,8 pp** |

O cisto melhorou, mas continua o pior bucket. **O ganho dominante veio da
sensibilidade no OpenSwissHCC**, não da discriminação de mimetizadores. Registrar
isso importa: a previsão mecanística da Etapa A estava em grande parte errada,
mesmo que a intervenção tenha funcionado.

### Ressalvas obrigatórias — o gate agregado passou, a generalização não

1. **Os IC95% cruzam 75%** em ambos os eixos (limites inferiores ~70%). A
   estimativa pontual passa, mas não se pode afirmar ≥75% com 95% de confiança.
2. **Não é estável por dataset.** Só `openswisshcc_development` passa 75/75
   isoladamente:

```text
lld_mmri                       73,25% / 76,97%   FALHA (sensibilidade)
openswisshcc_development       82,05% / 77,55%   OK
openswisshcc_consumed_holdout  83,33% / 65,00%   FALHA (especificidade)
```

   Pela matriz de decisão do doc 120 §7 ("atinge 75/75 mas colapsa por
   dataset → declarar resultado retrospectivo instável"), este é um resultado
   **retrospectivo promissor, não generalização consolidada**. Não autoriza
   promoção ao webapp.
3. **Classes específicas de coorte.** `positive_unspecified`/
   `negative_unspecified` existem por coorte, então o modelo pode aplicar
   calibração condicionada ao domínio. Isso **não** é atalho de dataset para a
   classe — saber a coorte praticamente não informa o rótulo (OpenSwiss 63/132
   ≈ 48% positivo; LLD 157/335 ≈ 47%) — e não há vazamento de label do fold de
   teste. Mas o ganho pode não transferir para uma terceira coorte inédita. A
   ablação natural (mapear OpenSwiss para as classes finas, sem classes
   específicas de coorte) é o próximo teste indicado.

### Decisão

Primeiro candidato do projeto a passar o gate 75/75 na coorte agregada de 467
casos, com melhoria real de AUC e sob metodologia nested OOF idêntica à da
Fase 5. Permanece **não promovido** ao webapp: o gate exige estabilidade, e a
análise por dataset mostra que ela ainda não existe. A Fase 5 segue como
referência congelada; nada foi alterado nela.

## Etapa C — ablação: o ganho é biologia ou calibração de domínio?

### Pergunta

O resultado da Etapa C passou o gate agregado com classes específicas de coorte
(`positive_unspecified`/`negative_unspecified`), que permitem ao modelo
condicionar a calibração ao domínio. Antes de qualquer afirmação, era preciso
saber se o ganho vem da **biologia** (o rótulo fino ajuda a separar
mimetizadores) ou da **calibração de domínio** (as classes de coorte agem como
indicador de dataset). O desenho que isola isso: restringir ao **LLD-MMRI**
(única coorte com rótulos finos reais), onde não existe classe de coorte por
construção, e comparar dois braços que diferem **só** na granularidade do
rótulo. Mesmo módulo, mesmos embeddings, mesmos splits congelados (apenas
intersectados com o universo LLD, sem reatribuir folds), mesma agregação, mesma
seleção de threshold.

### Resultado — LLD-MMRI, 335 casos

```text
braço              sens     esp      AUC      gate
binário          76,43%   75,84%   0,8567    OK
multiclasse      75,16%   76,97%   0,8664    OK

Δ (multi − binário):  sens −1,27 pp | esp +1,12 pp | AUC +0,0098
```

Na decisão binária o rótulo fino é praticamente um empate (troca 1,3 pp de
sensibilidade por 1,1 pp de especificidade); no AUC, adiciona apenas +0,010.

### Decomposição do ganho da Etapa C

Reconciliando o AUC **dentro do LLD** entre as quatro configurações:

```text
Fase 5 binário, treino nos 467 (subset LLD):   AUC 0,8081   (baseline)
binário, treino SÓ no LLD (335):               AUC 0,8567   (+0,049)
multiclasse, treino SÓ no LLD (335):           AUC 0,8664   (+0,058)
multiclasse, treino nos 467 c/ classes coorte: AUC 0,8630
```

O salto de AUC da Etapa C (~+0,055 sobre a Fase 5 no LLD) decompõe-se em:

- **separação de domínio** (parar de misturar OpenSwissHCC no treino):
  **+0,049** — o efeito dominante;
- **granularidade de rótulo fino**, por cima disso: **+0,010** — marginal.

O AUC do run completo multiclasse (0,8630) é essencialmente reproduzido pelo
binário treinado só no LLD (0,8567): as classes específicas de coorte, no run
completo, faziam **o mesmo trabalho** que restringir fisicamente ao LLD — separar
domínios. A biologia dos subtipos (hcc/hemangioma/cisto/fnh) contribui pouco.

### Interpretação — reformulação do teto

O gargalo não é "o modelo não sabe distinguir cisto de HCC". É **heterogeneidade
de domínio**: misturar OpenSwissHCC e LLD-MMRI no treino piora o desempenho em
cada coorte, e um classificador binário simples treinado por coorte já passa o
gate na sua própria coorte (LLD: 76,43%/75,84%). Isso é o mesmo problema de
domain shift que o histórico documentou (v23 dev87 → full132), agora medido de
forma limpa.

Consequências:

1. A supervisão multiclasse "funcionou" no run completo majoritariamente porque
   as classes de coorte agiram como indicador de domínio, não porque o modelo
   aprendeu a caracterizar melhor as lesões. O ganho é **~85% domínio, ~15%
   rótulo fino**.
2. Treino por coorte **não é candidato promovível**: uma coorte nova não tem
   rótulos in-domain para calibrar. É diagnóstico, não solução de produção.
3. Perseguir rótulos de subtipo melhores tem retorno marginal (+0,010 AUC). O
   valor está em **generalização entre domínios** — que é o que uma coorte
   independente ou um backbone mais forte (27B) endereçam, não mais engenharia
   de feature/rótulo sobre estes dois datasets.

### Decisão

A Etapa C permanece como está: primeiro candidato a passar o gate agregado,
**não promovido** por não ser estável por dataset. A ablação não muda essa
conclusão — refina o entendimento de **por que**: o teto atual é dominado por
domain shift, não por discriminação de mimetizadores. Nada foi alterado nos
artefatos congelados (Fase 5 e o próprio run canônico da Etapa C reproduzem suas
assinaturas; as opções de ablação só entram no freeze quando não-padrão).

## Estado após Fase 9B e Fase 10

```text
suíte completa: ver validação abaixo
candidato de referência inalterado: Fase 5 (MedSigLIP linear congelado)
fusão OOF própria (Fase 9B): tentada, não supera os sinais individuais
robustez multicohort (Fase 10): implementada, nenhum candidato estável em 75/75
protocolo de transferência 27B: congelado, execução pendente (Mac)
integração no webapp: continua não autorizada pelo gate estatístico
```
