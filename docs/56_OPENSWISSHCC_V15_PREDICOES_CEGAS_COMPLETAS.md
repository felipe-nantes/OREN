# OpenSwissHCC v15 — predições cegas completas

Data da execução: 16 de julho de 2026.

## Objetivo desta etapa

Executar o protocolo v15 congelado nos 87 casos de desenvolvimento sem ler o ground truth, sem calcular métricas e sem abrir o holdout. O v15 mantém o mesmo MedGemma 1.5 4B e o mesmo método de score contínuo do v14, mas limita a entrada volumétrica a 32 cortes equidistantes por caso para cumprir o teto operacional de 180 segundos.

## Artefatos autoritativos

- Bundle cego: `casos/qualification/openswisshcc_v1/runs/dev_v15_highdimensional_blind87/bundle.json`
- Protocolo congelado: `casos/qualification/openswisshcc_v1/prepared/development_freezes_v15/volume_score_protocol.json`
- Predições: `casos/qualification/openswisshcc_v1/runs/dev_v15_volume_score_blind87/predictions/`
- Progresso final: `casos/qualification/openswisshcc_v1/runs/dev_v15_volume_score_blind87/progress.json`
- Resumo cego: `casos/qualification/openswisshcc_v1/runs/dev_v15_volume_score_blind87/summary.json`

## Integridade e cegamento

A auditoria pós-execução verificou:

- 87 casos concluídos e 87 `case_id` únicos;
- correspondência exata entre os casos do bundle e das predições;
- existência e SHA-256 correto de cada uma das 87 predições;
- assinatura do protocolo idêntica em todos os resultados;
- probabilidades restritas no intervalo de 0 a 1 e com soma igual a 1 dentro da tolerância numérica;
- `ground_truth_read=false`;
- `metrics_calculated=false`;
- `holdout_opened=false`;
- `research_only=true`;
- `clinical_use_allowed=false`;
- `requires_human_review=true`.

Resultado da auditoria: **aprovada, sem erros**.

## Identificadores criptográficos

- Assinatura do protocolo: `d7f40621f6a224d51e4499bbddb4da1d170141ff830a082991c0a7f969388eb1`
- SHA-256 do arquivo de protocolo: `C5A14D4E2CB09AFC7EAA881CA4E9BE69D82D26AFE0855B183B703E7357FAF8A1`
- SHA-256 do bundle: `FF0933155F3A10B949B2CDAAB553A0406783041C351667C930A669F9A692D897`
- SHA-256 do progresso final: `72D99696BA262CFF7016ADC1ECBDC462ECCA662DF2AB8B8C5F780AE76052E8C3`
- SHA-256 do resumo cego: `3F1C2D2695E8446FF7E7692D89890716BE597CB1FE9D889906934C5336D358E0`

## Resultado operacional

| Medida | Resultado |
|---|---:|
| Casos concluídos | 87/87 |
| Tempo mínimo | 16,6903 s |
| Tempo mediano | 16,8469 s |
| Tempo médio | 16,8472 s |
| P95 | 16,9582 s |
| Tempo máximo | 17,0126 s |
| Casos acima de 180 s | 0 |

O v15 cumpriu o gate técnico de tempo nos 87 casos de desenvolvimento. Isso resolve o gargalo operacional observado no v14, no qual um caso excedeu 180 segundos.

## Distribuição cega das saídas

Sem usar o ground truth, a distribuição bruta foi:

- `POSITIVA`: 8;
- `NEGATIVA`: 35;
- `INCONCLUSIVA`: 44.

Essa distribuição **não é uma métrica de desempenho**. Ela apenas descreve as saídas do score restrito antes da calibração/avaliação. Sensibilidade, especificidade e acurácia ainda não foram calculadas.

## Limitações preservadas

- A amostragem de 32 cortes reduz a cobertura volumétrica em relação ao v14; a cobertura do volume preparado varia aproximadamente de 41,04% a 92,88%, com mediana de 62,85%.
- O score contínuo é um sinal experimental derivado da distribuição restrita do primeiro token entre três classes; não é uma probabilidade clínica calibrada.
- O alto número de classificações brutas inconclusivas reforça que a regra categórica direta não deve ser aceita sem avaliação estatística aninhada.
- Nenhum ganho de acurácia pode ser declarado nesta etapa.

## Próxima etapa autorizável

Antes de abrir `development_labels.jsonl`, deve ser criado e assinado um protocolo de avaliação v15 que fixe:

1. os sinais contínuos candidatos permitidos;
2. o tratamento de `INCONCLUSIVA` como erro na métrica principal;
3. o procedimento de seleção/calibração exclusivamente dentro dos folds de treino;
4. a validação externa por nested cross-validation e repeated stratified 5-fold;
5. os critérios de aceite de sensibilidade e especificidade maiores ou iguais a 75%;
6. a proibição de abrir o holdout.

Somente depois desse congelamento deve ser solicitada autorização específica para ler os labels de desenvolvimento na avaliação v15.
