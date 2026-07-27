# OpenSwissHCC — fallback, congelamento, inferência e avaliação

Data do registro: 2026-07-14.

Este documento continua:

- `docs/24_MEDSIGLIP_E_OPEN_SWISS_QUALIFICATION.md`;
- `docs/25_OPENSWISSHCC_PANEL_REVIEW.md`.

## 1. Fallback para as três falhas de alinhamento

Os três casos que não atingiram Dice 0,80 não foram excluídos. Foi declarado,
antes de qualquer inferência, um fallback de fase venosa única:

```text
candidate_kind: venous_single_phase_fallback
source_phase: t1_venous
fallback_reason: multiphase_alignment_gate_failure
```

Ele usa `configs/medgemma_local_4b_venous_fallback_pathology.yaml`, com:

- `panel.mode=single_grayscale` explícito;
- `uniform_9` e nove cortes;
- crop hepático sem overlay;
- prompt pathology-target;
- timeout interno de 120 segundos;
- zero retry;
- RAG desativado.

Os três painéis foram produzidos somente com `t1_venous` e
`liver_mask_venous`. Nenhum label, máscara de lesão ou inferência foi usado.

Estado resultante:

```text
coorte de desenvolvimento: 88
candidatos multifásicos: 85
fallbacks venosos: 3
painéis prontos para revisão: 88
painéis com aprovação automática: 0
```

## 2. Congelamento experimental

Foi detectado que o hash do YAML filho não cobre sozinho arquivos herdados por
`extends`. Para impedir alteração silenciosa do prompt ou backend, foi criado:

- `dtwin/benchmark/openswisshcc_freeze.py`;
- `tools/freeze_openswisshcc_experiment.py`.

O congelamento assina:

- os 88 SHA-256 dos painéis;
- assinaturas e versões dos candidatos;
- tipo multifásico ou fallback;
- hash do YAML filho;
- hash efetivo depois de resolver toda a cadeia `extends`;
- identidade e endpoint do MedGemma;
- timeout e política de retries;
- salvaguardas research-only.

Artefato real, mantido fora do Git:

```text
casos/qualification/openswisshcc_v1/prepared/
  development_experiment_v1/experiment_freeze.json
```

Resultado:

```text
case_count: 88
experiment_signature: 074b5673c4aa0ccbef0d8cf2bc4ed17fa190c16b2843a1de20cc21983fb7a93c
ground_truth_read: false
inference_executed: false
verified: true
```

Qualquer alteração em painel, candidato, YAML filho ou configuração herdada
invalida a execução.

## 3. Executor MedGemma 1.5 4B

Foram adicionados:

- `dtwin/benchmark/openswisshcc_inference.py`;
- `dtwin/benchmark/openswisshcc_inference_batch.py`;
- `tools/infer_openswisshcc_case.py`;
- `tools/run_openswisshcc_inference.py`.

Gates obrigatórios antes da chamada ao modelo:

1. aprovação visual humana assinada;
2. painel atual idêntico ao painel aprovado;
3. congelamento experimental válido;
4. configuração correta para o tipo de candidato;
5. identidade exata `google/medgemma-1.5-4b-it`;
6. timeout interno máximo de 120 segundos;
7. zero retry de transporte e validação;
8. RAG desativado nesta configuração qualificada.

O lote é sequencial e usa um subprocesso por caso. O timeout externo é 180
segundos incluindo startup, validação, health check e inferência. Timeout ou
falha não produz `medgemma_report.json` parcial. O lote continua para os casos
seguintes e registra a falha no resumo.

Para os três fallbacks, o prompt acrescenta explicitamente que existe somente
fase venosa e proíbe presumir dinâmica arterial ou tardia.

## 4. Avaliação tardia

Foram adicionados:

- `dtwin/benchmark/openswisshcc_evaluation.py`;
- `tools/evaluate_openswisshcc_run.py`.

O avaliador executa esta ordem:

1. revalida congelamento, painéis e configurações;
2. revalida a aprovação visual;
3. exige exatamente 88 registros de inferência;
4. valida hashes dos relatórios e ausência de leitura prévia do ground truth;
5. somente então abre `protected_ground_truth/development_labels.jsonl`;
6. exige exatamente 39 positivos e 49 negativos;
7. calcula métricas e IC95%;
8. calcula média, mediana, p95 e máximo de tempo;
9. publica os artefatos de avaliação atomicamente com retry para locks do
   Windows.

Política da métrica principal:

```text
POSITIVA correta em positivo = TP
NEGATIVA correta em negativo = TN
INCONCLUSIVA = erro do grupo
falha = erro do grupo
timeout = erro do grupo
resposta inválida = erro do grupo
```

O gate combinado somente passa quando:

```text
sensibilidade >= 75%
especificidade >= 75%
zero timeout
tempo máximo por caso <= 180 segundos
```

Passar no desenvolvimento não autoriza alegação final: o holdout continua
lacrado e será executado uma única vez após congelamento definitivo.

## 5. Comandos após a revisão humana

Registrar a aprovação dos 88 painéis:

```powershell
.\.venv-win\Scripts\python.exe -B -m tools.review_openswisshcc_panels `
  --panels casos/qualification/openswisshcc_v1/prepared/development_candidate_v1 `
  --out casos/qualification/openswisshcc_v1/prepared/development_reviews_v1/approved_panels.json `
  --reviewer "IDENTIFICADOR_DO_REVISOR" `
  --all-ready `
  --confirm-no-visible-phi `
  --confirm-alignment `
  --confirm-liver-framing
```

Executar o lote:

```powershell
.\.venv-win\Scripts\python.exe -B -m tools.run_openswisshcc_inference `
  --panels casos/qualification/openswisshcc_v1/prepared/development_candidate_v1 `
  --review casos/qualification/openswisshcc_v1/prepared/development_reviews_v1/approved_panels.json `
  --freeze casos/qualification/openswisshcc_v1/prepared/development_experiment_v1/experiment_freeze.json `
  --out casos/qualification/openswisshcc_v1/runs/development_medgemma_4b_v1 `
  --case-timeout-seconds 180
```

Avaliar somente depois de o lote terminar:

```powershell
.\.venv-win\Scripts\python.exe -B -m tools.evaluate_openswisshcc_run `
  --panels casos/qualification/openswisshcc_v1/prepared/development_candidate_v1 `
  --review casos/qualification/openswisshcc_v1/prepared/development_reviews_v1/approved_panels.json `
  --freeze casos/qualification/openswisshcc_v1/prepared/development_experiment_v1/experiment_freeze.json `
  --inference casos/qualification/openswisshcc_v1/runs/development_medgemma_4b_v1 `
  --protected-labels casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl `
  --out casos/qualification/openswisshcc_v1/evaluations/development_medgemma_4b_v1
```

Nenhum desses comandos de inferência ou avaliação foi executado neste estágio,
pois a revisão visual humana ainda não foi registrada.
