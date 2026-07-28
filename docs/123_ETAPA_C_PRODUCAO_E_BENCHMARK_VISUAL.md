# Etapa C — modelo de produção e benchmark visual em dados novos

**Data:** 26 de julho de 2026
**Objetivo:** consolidar a Etapa C (melhor resultado do projeto) num fluxo
executável de benchmark sobre exames de RM **novos**, gerando resultados reais,
sem afirmar validação que não existe.

---

## 1. Enquadramento honesto

A Etapa C atinge 75,91%/76,11% OOF (AUC 0,853) nos 467 casos multicohort — passa
o gate **agregado**, mas **não** é estável por dataset (LLD falha sensibilidade;
holdout falha especificidade; IC95% cruza 75%). Por isso ela é consolidada como
**modo de pesquisa/benchmark**, explicitamente **retrospectivo e não validado**,
nunca como decisor clínico. O gate de estabilidade do doc 120 §12 continua
bloqueando promoção a produção clínica.

---

## 2. Modelo de produção (bundle)

Os artefatos da Etapa C eram 5 modelos por-fold para avaliação OOF, não um modelo
servível. `train_production_bundle`
(`dtwin/learning/medsiglip_multiclass_classifier.py`) produz UM classificador
servível:

- **Seleção de hiperparâmetros por cross-validation** sobre os outer folds
  congelados: um caso nunca é pontuado, na seleção, por um modelo que viu seu
  rótulo. Selecionados: `C=0.01`, agregação `top2_mean`, threshold `0,475`.
- **Ajuste final** em todos os 467 casos com os hiperparâmetros escolhidos.
- Grava `production_model.joblib` + `bundle_manifest.json` **assinado**,
  registrando `class_names`, `positive_classes`, hiperparâmetros e — chave do
  guard in-sample — o conjunto de `case_ids`/`patient_group_ids` de treino.

> **Distinção metodológica crítica:** a métrica de *seleção* por CV do bundle
> (≈79%/80%) é otimista porque a seleção não é aninhada. A estimativa de
> generalização **honesta** do bundle continua sendo o nested-OOF da Etapa C
> (**75,91%/76,11%**). O manifesto marca isso
> (`generalization_estimate_source: nested_oof_etapa_c`,
> `in_sample_performance_is_not_a_generalization_estimate: true`). Nunca reportar
> a métrica de seleção nem qualquer número in-sample como desempenho do modelo.

Gerar o bundle:

```bash
python -m tools.train_medsiglip_multiclass train-production
```

---

## 3. Contrato de entrada: exame por fase (por que, e a lacuna do DICOM bruto)

A Etapa C foi treinada sobre painéis liver-enriched `multiphase_rgb_fusion`
(arterial+venoso+tardio, 3 painéis/caso). Rodar em single-series daria
descasamento treino/inferência.

**Não existe, no repositório, identificação automática de qual série DICOM é
arterial/venosa/tardia.** LLD e OpenSwiss vieram com as fases já separadas em
NIfTI pelos provedores dos datasets. Classificar dinâmica de fígado por série
DICOM é problema dependente de fabricante/protocolo e fica **fora de escopo**.

Consequência: o benchmark visual exige, por caso, as **fases já identificadas**
+ a máscara hepática grosseira (a `mask_organ.nii.gz` que a segmentação do webapp
já produz). Isso é como toda coorte dinâmica de fígado é curada.

**Passo futuro documentado:** um identificador de fase (heurística de
SeriesDescription/timing de contraste) com confirmação humana, para aceitar
estudos DICOM brutos arbitrários.

---

## 4. Pipeline de inferência (peças novas)

```text
exame (fases NIfTI + máscara)
   │  dtwin/learning/exam_to_panels.build_exam_panels
   ▼  (reusa generate_liver_enriched_panel_set_multiphase; mesma config de painel do treino)
painéis liver-enriched multifásicos (PNG)
   │  dtwin/learning/visual_inference.embed_panels
   ▼  (MedSigLIP pinado, mesma config do treino; carrega/descarrega GPU)
embeddings (n_painéis × 1152)
   │  dtwin/learning/visual_inference.classify_embeddings
   ▼  (bundle de produção: massa de prob. positiva → agregação → threshold)
decisão POSITIVA/NEGATIVA (+ score)
```

Salvaguardas herdadas do gerador: sem máscara de lesão, sem PHI, sem contorno,
máscara usada só para localização.

---

## 5. Guard in-sample (primeira classe)

Rodar o modelo de produção sobre casos que entraram no treino dá números
**inflados** (in-sample), não estimativa de generalização. Como os dados de
benchmark são definidos pelo usuário e podem, por engano, incluir coortes de
treino, o guard é obrigatório:

- `visual_inference.in_sample_status` / `partition_in_sample`: comparam
  `case_id`/`patient_group_id` do caso com o conjunto de treino do bundle.
- `visual_benchmark.run_visual_benchmark`: o **headline é só o out-of-sample**;
  casos in-sample vão para um bloco separado, explicitamente marcado como
  inflado, e nunca são misturados na métrica limpa.

---

## 6. Rodar um benchmark em dados novos (operacional hoje)

```bash
python -m tools.run_visual_benchmark \
  --manifest data/benchmarks/coorte_nova.json \
  --work-dir casos/webapp/_visual_bench_work \
  --out casos/webapp/_visual_bench_report.json
```

O manifesto lista os casos com as fases identificadas, a máscara hepática e o
rótulo (schema no cabeçalho de `tools/run_visual_benchmark.py`). Falha em
qualquer caso vira falha técnica (conta como erro), nunca decisão fabricada.

---

## 7. Integração no webapp — ingestão multifásica (ENTREGUE)

O cenário `hybrid_supervised` está disponível no benchmark do webapp. Como o
fluxo era single-series (uma pasta → uma série por caso), a ingestão multifásica
foi construída:

**Contrato de upload.** Cada caso envia as fases em subpastas:

```text
caso-001/arterial/*.dcm
caso-001/venous/*.dcm
caso-001/delayed/*.dcm
```

Os aliases aceitos são tolerantes a acento/idioma/separador (`arterial|art|ap`,
`venous|venoso|portal|pv`, `delayed|tardio|late|equilibrio`), e uma pasta
extra de estudo em volta é tolerada. Duas pastas para a mesma fase **falham
fechado** — é erro de curadoria, não algo a resolver silenciosamente.

**Preservação da estrutura.** O upload do benchmark achatava os diretórios
(`Path(filename).name`), destruindo a informação de fase. Agora, *apenas* para o
cenário visual, os `relpaths` são preservados (como o endpoint de exame
individual já fazia). Os cenários MedGemma seguem achatando — para eles a
estrutura é irrelevante, e assim o comportamento existente fica intocado.

**Harmonização de grade (o ponto não óbvio).** O renderizador de painéis exige
que as três fases e a máscara compartilhem uma única grade 3D, mas aquisições
dinâmicas distintas geralmente **não** compartilham. A fase venosa é a
referência (é nela que a segmentação roda, então máscara e fases se alinham por
construção) e arterial/tardia são reamostradas na grade venosa por transformação
física identidade — a mesma convenção usada para construir os dados de treino.
A **cobertura** resultante é medida: abaixo de 50% o caso falha com mensagem
explícita, em vez de produzir silenciosamente uma fase quase vazia.

**Fluxo por caso** (`_run_visual_benchmark_case` em `webapp/server.py`):

```text
subpastas de fase → harmonização + segmentação hepática (venosa, full-res)
  → painéis liver-enriched → embeddings MedSigLIP → bundle → decisão
```

Falha em qualquer etapa vira falha técnica (conta como erro), nunca decisão
fabricada. O cenário **não** depende do gateway MedGemma (não o usa), então o
gate de backend da UI é dispensado para ele.

**Enquadramento na UI.** O botão é rotulado "Classificador visual · Pesquisa" e
exibe aviso de que é o melhor resultado retrospectivo (75,9%/76,1% OOF) porém
**não estável por dataset e não validado clinicamente**. O `model_info` do
relatório carrega `gate_75_75_stable_by_dataset: false` e a referência OOF.

Módulo: `dtwin/learning/multiphase_ingest.py` (testável sem webapp/GPU).

---

## 8. Verificação

- Unitários (GPU/render mockados): `test_learning_visual_inference.py`,
  `test_learning_visual_benchmark.py`, e os novos casos em
  `test_learning_medsiglip_multiclass_classifier.py` (seleção por CV).
- Bundle de produção **treinado de fato** e assinado.
- Reprodutibilidade da assinatura da Etapa C canônica preservada; artefatos
  congelados intactos.
- Ponta a ponta com GPU real + exame multifásico novo: **pendente de dados do
  usuário** (o CLI está pronto para recebê-los).
