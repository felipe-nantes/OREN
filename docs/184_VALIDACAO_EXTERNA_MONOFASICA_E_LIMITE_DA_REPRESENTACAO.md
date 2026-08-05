# Validação externa monofásica e limite da representação — 2026-08-04

## Objetivo desta rodada

Testar, sem reutilizar labels durante a inferência, se a combinação tardio/global + cobertura axial + ADC consegue aproximar o OREN da meta binária de sensibilidade e especificidade de 75% no fluxo monofásico.

Os 44 casos do antigo holdout OpenSwissHCC já haviam sido consumidos por protocolos anteriores. Nesta rodada eles foram usados como **validação retrospectiva de generalização**, nunca como um holdout virgem ou prospectivo. Nenhuma máscara de lesão foi aberta ou enviada aos modelos.

## Implementações concluídas

1. Cobertura axial completa e sinal ADC complementar, ambos label-blind.
2. MIL iterativo para instâncias positivas e hard negatives, avaliado e rejeitado.
3. Fusão missing-aware com margem zero e indicador explícito de sinal ausente.
4. Bundles de produção independentes para tardio/global, axial e ADC, treinados apenas nos 88 casos OpenSwiss de desenvolvimento.
5. Bundle de produção da fusão, com seleção exclusivamente em desenvolvimento.
6. Inferência externa amarrada à lista SHA-256 exata dos 44 casos label-blind.
7. Verificador genérico para datasets candidatos derivados e assinados.
8. Correção do `dataset_id` do gerador complementar. O artefato antigo tinha imagens corretas, mas metadado de coorte incorreto e foi rejeitado para métricas.
9. Publicação segura no Windows com manifesto publicado por último.
10. Reuso de embeddings somente após identidade exata de `candidate_id` e SHA-256 da imagem, seguido de novo vínculo e nova assinatura.
11. Diagnóstico retrospectivo de distribuições, correlações e limiar-oráculo, explicitamente não utilizável para implantação.
12. Ponderação experimental por dataset, classe e caso, evitando que número de casos ou cortes domine o treino.

## Melhor resultado antes da validação externa

Nos 88 casos de desenvolvimento, a fusão tardio + axial + ADC missing-aware obteve:

- sensibilidade: **71,79%**;
- especificidade: **73,47%**;
- ROC-AUC: **0,779**;
- falhas técnicas: **0**.

Esse resultado ficou próximo, mas abaixo, da meta 75/75. Ele nunca foi apresentado como validação externa.

## Resultado nos 44 casos externos retrospectivos

| Leitor congelado | Sensibilidade | Especificidade | ROC-AUC | Falhas |
|---|---:|---:|---:|---:|
| Tardio/global | 79,17% | 45,00% | 0,590 | 1 |
| Axial completo | 25,00% | 95,00% | 0,571 | 0 |
| ADC | 41,67% | 65,00% | 0,517 | 0 |
| Fusão missing-aware | 54,17% | 50,00% | 0,588 | 0 |

Matriz de confusão da fusão: TP=13, TN=10, FP=10, FN=11.

O resultado final não atingiu a meta e a fusão não foi promovida ao frontend.

## Por que não é apenas calibração

Foi feita uma varredura retrospectiva de todos os limiares possíveis, somente para diagnóstico. Nenhum dos quatro sinais possui qualquer limiar que alcance simultaneamente 75% de sensibilidade e 75% de especificidade nos 44 casos.

Isso impede a solução artificial de alterar o threshold depois de observar os labels. O problema principal é de ordenação/separabilidade do sinal, confirmado pelas AUCs próximas de 0,5.

O tardio tende a chamar muitos casos de positivos. O axial completo tende a chamar quase todos de negativos. A fusão aprende uma relação útil em desenvolvimento, mas essa relação muda na coorte externa.

## Experimentos adicionais feitos sem reabrir o holdout para seleção

### Ponderação por domínio

A regressão foi ponderada para que cada combinação dataset × classe e cada caso contribuísse igualmente, independentemente do número de cortes.

- OpenSwiss desenvolvimento: 58,97% / 61,22%;
- agregado LLD + OpenSwiss: 73,47% / 70,04%.

Foi rejeitada porque não atingiu 75/75 e piorou o agregado.

### Redesenvolvimento com todos os 132 OpenSwiss

Depois de o antigo holdout já estar consumido, os 132 casos foram explicitamente tratados como desenvolvimento e avaliados por OOF interno:

- sensibilidade: 53,97%;
- especificidade: 55,07%;
- ROC-AUC: 0,611;
- falhas técnicas: 5.

Esse resultado também foi rejeitado. Ele demonstra que adicionar mais labels à mesma representação tardia não basta.

## Interpretação técnica

O teto observado não está na cobertura: o conjunto axial representa todos os cortes hepáticos e o ADC possui cobertura exata nos casos materializados. O gargalo está na representação e na localização da evidência:

- pooling de embeddings de cortes inteiros dilui lesões pequenas;
- o encoder congelado separa bem algumas coortes, mas não preserva a mesma fronteira entre aquisições;
- tardio isolado perde informação dinâmica arterial/washout;
- ADC sem harmonização física e sem localização pode responder a ruído, vasos e artefatos;
- uma regressão linear sobre escores globais não corrige um ranking externo próximo do acaso.

## Próximo caminho válido

1. Não retestar thresholds no mesmo holdout consumido.
2. Construir candidatos 3D/localizados gerados sem máscara de lesão em inferência.
3. Usar as máscaras públicas de lesão apenas no desenvolvimento para medir recall do localizador e para supervisão permitida, nunca como entrada.
4. Treinar um classificador de candidatos com hard negatives anatômicos, preservando decisão por exame.
5. Incorporar T2, DWI e ADC no mesmo candidato espacial registrado, em vez de agregar scores globais independentes.
6. Validar externamente em coorte pública separada; os 132 OpenSwiss agora são desenvolvimento.
7. Manter subtipo como endpoint separado. O resultado anterior de subtipo top-1 (~56%) continua abaixo de 75%; top-2 não substitui a meta top-1.

## Estado metodológico

- Meta binária 75/75 no monofásico geral: **não atingida**.
- Meta de subtipo top-1 75%: **não atingida**.
- Tempo por caso: continua compatível com o teto de 180 segundos nas rotas avaliadas.
- Frontend: nenhuma configuração experimental desta rodada foi ativada.
- Segurança: ground truth não entrou nas predições; máscaras de lesão lidas na inferência = 0; revisão humana permanece obrigatória.

## Artefatos principais

- Bundle de fusão: `casos/qualification/hybrid_v1/medsiglip_monophase_missing_aware_fusion_production_bundle_v1`
- Predições externas finais: `casos/qualification/hybrid_v1/medsiglip_openswiss_holdout_missing_aware_fusion_predictions_v1`
- Avaliação externa: `casos/qualification/hybrid_v1/medsiglip_openswiss_holdout_missing_aware_fusion_evaluation_v1/evaluation.json`
- Diagnóstico: `casos/qualification/hybrid_v1/medsiglip_openswiss_holdout_monophase_signal_diagnostics_v1.json`

Esses artefatos são de pesquisa, assinados, imutáveis e não autorizam uso clínico.
