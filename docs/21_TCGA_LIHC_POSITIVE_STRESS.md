# Rodada de estresse positiva — TCGA-LIHC

Data: 2026-07-14  
Estado: desenvolvimento; não é benchmark balanceado nem validação final

## Objetivo

Gerar artefatos auditáveis e medir latência nos 12 casos TCGA-LIHC disponíveis
em `D:\lote_positivo_1_real`. O label usado é HCC no nível do paciente. A
visibilidade de uma lesão focal na série selecionada permanece pendente de revisão
humana.

## Dry-run

- 12/12 paths DICOM válidos;
- 60 a 131 arquivos por caso;
- hashes de origem calculados;
- nenhuma inferência chamada;
- ground truth mantido fora do workspace de inferência.

## Run

```text
casos/qualification/fast_dev_runs/
20260714T005634Z_6ee41c58_fast_pathology_tcga_positive_stress_v1
```

Configuração:

```text
configs/medgemma_local_4b_fast_pathology.yaml
```

Hardware/modelo confirmado pelo health check:

- `google/medgemma-1.5-4b-it`;
- NF4;
- CUDA;
- NVIDIA GeForce RTX 4060 Laptop GPU;
- modo pesquisa.

## Resultado técnico

| Medida | Resultado |
|---|---:|
| casos concluídos | 12/12 |
| falhas | 0 |
| timeouts | 0 |
| respostas positivas | 12/12 |
| respostas negativas | 0/12 |
| respostas inconclusivas | 0/12 |
| tempo total médio | 35,29 s |
| maior tempo total | 43,12 s |
| inferência MedGemma média | 2,60 s |

O limite de 180 segundos foi atendido em todos os casos.

## Interpretação correta

A sensibilidade computada pelo runner é 100%, mas não constitui evidência clínica
válida neste momento porque:

- todos os casos pertencem ao grupo positivo;
- não há especificidade mensurável;
- o label é diagnóstico no nível do paciente;
- a série única pode não demonstrar uma lesão focal;
- a configuração já classificou todos os negativos do piloto como positivos.

Portanto, o resultado reforça o colapso da rota rápida em `POSITIVA`; não prova
detecção de HCC.

## Artefatos de revisão local

O run contém:

- `tcga_panels_review_contact_sheet.png`: folha de contato anonimizada com os 12
  painéis;
- `tcga_visual_review.jsonl`: manifesto atômico com case_id, hashes e campos
  clínicos vazios;
- relatórios e painéis individuais do runner.

Campos que exigem revisão humana:

```text
focal_liver_lesion_visible
series_sufficient_for_target
target_label_confirmed
reviewer
reviewed_at
notes
```

O assistente não preencheu esses campos nem transformou impressão visual em
ground truth.

## Decisão

- o objetivo temporal permanece atingido;
- a rota rápida MedGemma 4B permanece não qualificada;
- a rodada não entra na métrica balanceada principal;
- somente casos revisados como lesão focal visível podem compor desenvolvimento;
- o teste final continua exigindo positivos e negativos comparáveis e bloqueados.
