# OpenSwissHCC v10 — avaliação autorizada do localizador em 87 casos

Data: 15/07/2026.

## Escopo e autorização

Foi autorizada explicitamente a abertura de `development_labels.jsonl`
exclusivamente para avaliar os 87 casos de desenvolvimento pelo protocolo v10
congelado. O holdout permaneceu fechado.

Antes da autorização, o mesmo CLI foi executado sem a flag de acesso e abortou
com `PipelineError`, código 1, sem criar diretório de saída. Depois da
autorização, foi usada a flag explícita:

```text
--allow-protected-development-labels
```

Nenhuma busca de limiar adicional, combinação pós-hoc ou leitura do holdout foi
realizada.

## Protocolo congelado

Feature primária única:

```text
candidate_total_volume_log1p = log1p(total_candidate_volume_mm3)
```

Assinatura do protocolo:

```text
e94b1bb1bc43cbb2a643515945948a5cb238e9b66473c50f365545ff8c778bbe
```

SHA-256 do run cego de origem:

```text
81826b1d5471170e89a86e1e826ca10cc55028f4f04a489428e110dfa87f6a61
```

SHA-256 dos labels protegidos de desenvolvimento:

```text
406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020
```

Coorte avaliada:

- 87 casos primários;
- 39 positivos;
- 48 negativos;
- caso 72 já excluído tecnicamente antes da inferência e da avaliação.

## Resultado aparente no desenvolvimento

O limiar aparente escolhido exclusivamente no desenvolvimento foi:

```text
6.613559097172975
```

| Medida | Resultado |
|---|---:|
| TP | 23 |
| FN | 16 |
| TN | 26 |
| FP | 22 |
| Sensibilidade | 58,97% |
| Especificidade | 54,17% |
| Acurácia balanceada | 56,57% |
| Gate simultâneo 75%/75% | reprovado |

Nem mesmo a métrica aparente atingiu os dois objetivos. Portanto, o fracasso
não pode ser atribuído somente ao procedimento de validação cruzada.

## Resultado primário LOOCV

| Medida | Resultado |
|---|---:|
| TP | 21 |
| FN | 18 |
| TN | 26 |
| FP | 22 |
| Sensibilidade | **53,85%** |
| Especificidade | **54,17%** |
| Acurácia balanceada | 54,01% |
| Menor métrica do gate | 53,85% |
| Gate simultâneo 75%/75% | **reprovado** |

Intervalos de confiança Wilson de 95%:

- sensibilidade: 38,57% a 68,43%;
- especificidade: 40,29% a 67,42%.

## Estabilidade

Validação cruzada estratificada 5-fold, 50 repetições:

| Medida | Resultado |
|---|---:|
| Repetições que atingiram 75%/75% | **0/50** |
| Sensibilidade mediana | 53,85% |
| Especificidade mediana | 56,25% |
| Menor sensibilidade | 48,72% |
| Menor especificidade | 52,08% |

O resultado do piloto de dez casos — 75,00% de sensibilidade e 83,33% de
especificidade — não se reproduziu na coorte completa. A diferença é compatível
com a elevada incerteza do piloto pequeno, cujos intervalos de confiança já
eram amplos.

## Segurança e estado metodológico

O artefato final registra:

```text
ground_truth_read=true
metrics_calculated=true
holdout_opened=false
qualified=false
research_only=true
clinical_use_allowed=false
requires_human_review=true
```

Status oficial:

```text
development_calibration_not_holdout_qualified
```

SHA-256 de `evaluation.json`:

```text
1c957bcf4dc8d3386c45f9c692496326e3a1852b10f162bf60a8791ffd5064f4
```

Artefatos locais:

```text
casos/qualification/openswisshcc_v1/evaluation/
dev_v10_lesion_localizer_full87/evaluation.json

casos/qualification/openswisshcc_v1/evaluation/
dev_v10_lesion_localizer_full87/case_features.csv
```

## Relação com o limite de tempo

A reprovação é de acurácia, não de latência. O localizador cego já havia
demonstrado média de 28,35 s e máximo de 41,92 s. O fluxo DICOM rápido com
MedGemma 4B demonstrou 43,36–51,28 s até o relatório e 45,17–53,32 s incluindo
o modelo 3D. O teto de 180 s permanece tecnicamente viável.

## Decisão

1. Não promover `candidate_total_volume_log1p` como classificador principal.
2. Não abrir o holdout, pois nenhuma configuração de desenvolvimento está
   qualificada e estável.
3. Não executar MedGemma 4B indiscriminadamente em todos os 87 casos: o caminho
   rápido já demonstrou colapso para `POSITIVA`, e as perguntas do piloto v10
   não superaram o sinal determinístico.
4. Considerar encerrado o caminho de feature única baseada apenas no volume
   candidato.
5. Se houver uma etapa v11, congelar antes um protocolo de fusão simples entre
   sinais cegos já existentes e usar validação aninhada. A reutilização dos
   labels para esse novo objetivo exige autorização separada.
6. Se a fusão v11 também não sustentar 75%/75%, registrar formalmente o teto das
   abordagens sem treinamento, sem procurar sucessivamente novas regras no
   desenvolvimento.

## Validação de software

Após a avaliação, 17 testes focados passaram, cobrindo:

- protocolo e avaliador full87;
- integridade e merge dos chunks cegos;
- gate e persistência do timing operacional;
- regressão de `WORKSPACE` relativo.

Nenhuma falha foi observada. A suíte completa anterior continha 521 testes
aprovados e zero falhas.
