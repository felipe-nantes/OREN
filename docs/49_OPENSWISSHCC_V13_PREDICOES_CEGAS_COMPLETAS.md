# OpenSwissHCC v13 — predições 3D cegas completas

Data da conclusão: 2026-07-15

## Objetivo desta etapa

Executar o MedGemma 1.5 4B sobre os 87 casos de desenvolvimento do
OpenSwissHCC usando a entrada 3D nativa congelada no protocolo v13, antes de
qualquer leitura dos rótulos protegidos.

Esta etapa mede somente validade técnica, reprodutibilidade, segurança e tempo.
Ela não mede sensibilidade, especificidade ou acurácia.

## Protocolo congelado

- modelo: `google/medgemma-1.5-4b-it`;
- hardware observado: CUDA, GPU local;
- contrato HTTP: `dtwin-medgemma-volume-v1`;
- schema persistido: `argos-openswisshcc-highdimensional-batch-prediction-v1`;
- protocolo: `development_freezes_v13/highdimensional_batch_protocol.json`;
- assinatura do protocolo:
  `11616f927c361f13852607395e3861060b1cf957ffe7a9ffc45ace013dffe9e3`;
- uma requisição por caso;
- zero retries automáticos;
- geração determinística;
- entre 35 e 50 cortes axiais ordenados por caso;
- limite de tempo: 180 segundos por requisição;
- labels de desenvolvimento fechados durante toda a inferência;
- holdout fechado.

## Resultado técnico

| Item | Resultado |
|---|---:|
| Casos previstos | 87/87 |
| IDs únicos | 87 |
| IDs duplicados | 0 |
| Casos tecnicamente aprovados | 87/87 |
| Respostas com schema válido | 87/87 |
| Casos dentro de 180 segundos | 87/87 |
| Tempo mínimo | 91,2307 s |
| Tempo mediano | 145,3736 s |
| Tempo médio auxiliar | 139,4026 s |
| Tempo máximo | 149,4518 s |

A margem observada no pior caso foi de 30,5482 segundos em relação ao limite
de 180 segundos.

## Distribuição cega das saídas

Esta distribuição não pode ser interpretada como desempenho clínico porque os
rótulos ainda não foram abertos.

| Saída | Casos |
|---|---:|
| `POSITIVA` | 44 |
| `NEGATIVA` | 24 |
| `INCONCLUSIVA` | 19 |

## Auditoria de segurança e integridade

Os 87 artefatos individuais registram:

- `research_only=true`;
- `clinical_use_allowed=false`;
- `requires_human_review=true`;
- `ground_truth_read=false`;
- `holdout_opened=false`;
- `metrics_calculated=false`;
- `output_schema_valid=true`;
- `time_gate_passed=true`.

Também foram confirmados:

- uma única assinatura de protocolo em toda a coorte;
- 87 hashes distintos de manifestos de stack;
- nenhum UID bruto, PHI ou máscara de lesão na inferência;
- gravação atômica e retomável de cada previsão;
- nenhum ajuste de prompt, amostragem ou regra entre os casos.

## Artefatos autoritativos

- resultados individuais:
  `casos/qualification/openswisshcc_v1/runs/dev_v13_highdimensional_blind87/inference/predictions/`;
- progresso final:
  `casos/qualification/openswisshcc_v1/runs/dev_v13_highdimensional_blind87/inference/progress.json`;
- SHA-256 do progresso:
  `2cd3e5dac3c3b54b8b994cea73d74dfc4eec3b2809d2433c794b17c5254998ba`;
- resumo cego:
  `casos/qualification/openswisshcc_v1/runs/dev_v13_highdimensional_blind87/inference/summary.json`;
- SHA-256 do resumo:
  `82d6c307acc8f6008eab49f6c04d3c74a4fae12a6a1e07c81ed0a9fc5863893e`.

## Próxima etapa autorizável

Somente após autorização explícita e específica para o protocolo v13:

1. validar novamente hashes do bundle, protocolo, progresso e previsões;
2. abrir exclusivamente `development_labels.jsonl`;
3. unir por `case_id` sem modificar previsões;
4. tratar `INCONCLUSIVA` como erro na métrica principal;
5. calcular matriz de confusão, sensibilidade, especificidade, acurácia
   balanceada e intervalos de confiança de 95%;
6. documentar a avaliação e fechar novamente a etapa de desenvolvimento;
7. manter o holdout fechado, a menos que sensibilidade e especificidade atinjam
   pelo menos 75% e os critérios de estabilidade também sejam satisfeitos.

