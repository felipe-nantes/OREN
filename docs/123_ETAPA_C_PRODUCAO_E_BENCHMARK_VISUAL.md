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

## 7. Estado da integração no webapp (pendência declarada)

O botão de cenário `hybrid_supervised` no benchmark do **webapp** é o único item
não entregue neste incremento. Motivo honesto: `webapp/server.py` está com
alterações **não commitadas e extensas** na exata região do benchmark
(`_benchmark_config`, `_run_benchmark_case`). Editá-lo agora entrelaçaria o
trabalho e violaria a decisão de versionar "só a linha Etapa C". Assim que essas
mudanças assentarem, o handler entra como um edit pequeno e isolado:
`BENCHMARK_SCENARIOS` tipado (`medgemma` | `visual_classifier`) + um ramo em
`_run_benchmark_case` que, para o cenário visual, chama o pipeline dos itens 4–6
em subprocess. O contrato de upload por caso: **subpastas de fase** identificadas
(arterial/venoso/tardio), pela mesma razão da §3.

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
