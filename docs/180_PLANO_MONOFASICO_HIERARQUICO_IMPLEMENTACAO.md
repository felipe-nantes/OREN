# Monofásico hierárquico — implementação e primeiro benchmark

**Data:** 3 de agosto de 2026  
**Estado:** fundação implementada; bundle de pesquisa criado; promoção operacional bloqueada

> Atualização de 2026-08-04: a fusão tardio + axial + ADC chegou a 71,79%/73,47% no desenvolvimento, mas caiu para 54,17%/50,00% na validação retrospectiva dos 44 casos consumidos. Nenhum limiar retrospectivo atingiu 75/75. Consulte `docs/184_VALIDACAO_EXTERNA_MONOFASICA_E_LIMITE_DA_REPRESENTACAO.md`. A configuração não foi promovida ao frontend.

## Objetivo

Separar três perguntas que não podem compartilhar uma resposta implícita:

1. existe evidência de patologia-alvo (HCC)?
2. existe um achado focal benigno ou não alvo?
3. qual subtipo é mais provável: HCC, FNH, hemangioma ou cisto?

## Implementado

- contrato sanitizado por sequência para T1 arterial, venosa, tardia,
  pós-contraste sem timing, T1 químico, T2, DWI, ADC e desconhecida;
- proibição explícita de washout e de comparação dinâmica em série única;
- inventário de uma série real por classe, preservando T2/DWI/ADC disponíveis;
- saída hierárquica que mantém lesão benigna observada sem torná-la HCC positiva;
- discordância binário/subtipo convertida em inconclusiva;
- evidência por painel com probabilidades, painel dominante e agregados
  `mean`, `max` e `top2_mean`, sem alterar a decisão congelada;
- persistência opcional de probabilidades OOF label-blind;
- avaliação protegida de top-1, top-2, recall por subtipo, matriz de confusão e
  acurácia balanceada;
- bundle multiclasse tardio assinado e restrito a pesquisa.

Nenhuma fase foi sintetizada. Nenhuma máscara de lesão foi lida pelo gerador,
encoder ou inferência.

## Primeiro resultado — LLD-MMRI tardio nested OOF

| Endpoint | Resultado | Gate |
|---|---:|---|
| Sensibilidade HCC | 75,80% | passa 75% |
| Especificidade HCC vs benignos | 77,53% | passa 75% |
| ROC-AUC binária | 0,876 | — |
| Subtipo top-1 | 56,42% | falha |
| Subtipo balanceada | 48,88% | falha 75% |
| Subtipo top-2 | 77,91% | diferencial, não top-1 |

Recall de subtipo:

| Subtipo | Recall |
|---|---:|
| HCC | 75,16% |
| FNH | 52,17% |
| Hemangioma | 41,77% |
| Cisto | 26,42% |

As 14 falhas técnicas foram contadas como erro. O resultado é interno ao LLD e
não demonstra generalização.

## Interpretação

A representação tardia global consegue triar HCC contra os três benignos no
LLD, mas perde a caracterização dos benignos. O top-2 acima de 75% permite
registrar um diferencial de pesquisa, porém não autoriza afirmar um diagnóstico
top-1 de subtipo.

Os experimentos anteriores já demonstraram que:

- T2/DWI com descritores medianos acrescentaram apenas 0,23 ponto;
- embedding MedSigLIP de ROI correta atingiu 79,49% balanceada;
- o localizador de união arterial+venosa atingiu 80%, mas essa união não existe
  em um exame verdadeiramente monofásico tardio;
- o caminho 2.5D anterior, treinado em apenas 87 OpenSwiss, falhou claramente.

Portanto, a próxima tentativa válida exige novos candidatos monofásicos de alta
sensibilidade ou dados adicionais; não outro threshold sobre a mesma imagem.

## Artefatos

```text
configs/training/medsiglip_monophase_delayed_subtype_v1.yaml
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_subtype_oof_predictions_v1/
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_subtype_oof_evaluation_v1/
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_subtype_production_bundle_v1/
```

Assinatura da avaliação:

```text
10c8fa894a87603e81000e0e3b4a069f4c6a63d64fd98ad08861ecad9b95e68e
```

Assinatura do bundle:

```text
f21627c5758edd9974422815342360a9d478b9edb2be2afd289a249daa67f8fd
```

## Gate para continuidade

O bundle não será habilitado automaticamente até cumprir:

1. subtipo balanceado ≥75% em avaliação OOF ou externa predefinida;
2. binário ≥75%/75% por domínio, não apenas agregado;
3. validação externa em coorte não usada no desenvolvimento;
4. tempo total ≤180 segundos;
5. nenhuma classe nomeada quando a evidência for `unspecified` ou contraditória.

Enquanto isso, o fallback operacional permanece MedGemma 4B + RAG, com revisão
humana obrigatória e `clinical_use_allowed=false`.

## Experimento pareado de subtipo

Foi pré-especificado e executado um classificador one-vs-one com os seis pares
entre HCC, FNH, hemangioma e cisto. A decisão HCC/benigno permaneceu congelada;
o novo braço atuou somente na caracterização. `C` e agregação foram escolhidos
exclusivamente nos folds internos e as predições OOF foram assinadas antes da
abertura dos subtipos protegidos.

| Métrica | Multinomial | Pareado | Diferença |
|---|---:|---:|---:|
| Subtipo balanceada | 48,88% | 49,53% | +0,65 pp |
| Subtipo top-1 | 56,42% | 57,01% | +0,60 pp |
| Subtipo top-2 | 77,91% | 77,01% | -0,90 pp |

O gate pré-especificado exigia ganho balanceado de pelo menos 5 pontos e top-1
de pelo menos 60%. O braço falhou e não foi promovido. Isso reforça que a
limitação está na representação/localização, não na regra de decisão sobre os
mesmos embeddings globais.

Artefatos:

```text
configs/training/medsiglip_monophase_delayed_pairwise_subtype_v1.yaml
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_pairwise_subtype_oof_predictions_v1/
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_pairwise_subtype_oof_evaluation_v1/
```

Assinatura da avaliação pareada:

```text
be92eab8e739ae8119ecc92c561faf587c9d359969f143db2f676575e8602c60
```

## Representação axial por instância

Como próxima intervenção, foi implementado um dataset label-blind com um
candidato 448×448 para cada corte axial que contém fígado:

- fase real `t1_delayed`, sem síntese;
- crop hepático fixo por caso com margem de 8%;
- uma única janela p1–p99 calculada no fígado inteiro;
- cada índice axial hepático incluído exatamente uma vez;
- gate inteiro `covered_liver_voxels == total_liver_voxels`;
- máscara automática de fígado somente para crop/cobertura;
- zero máscara de lesão, zero contorno e zero ground truth.

O conjunto completo contém 12.633 cortes de 321 casos. Os 146 casos sem entrada
label-blind utilizável permanecem como falha técnica contada como erro. O
manifesto foi verificado novamente por hash depois da materialização.

```text
casos/qualification/hybrid_v1/medsiglip_monophase_delayed_slice_candidates_full_v1/
dataset_signature = 49a74f580249bd371924f5d50695e3a4d0782b31fc15bed2605e0bd460d6679f
```

Esta representação ainda é experimental. Ela só poderá substituir ou
complementar painéis globais se o nested OOF mostrar ganho pré-especificado e
se a latência completa continuar abaixo de 180 segundos.

### Resultado nested OOF da representação axial

| Endpoint | Painéis globais | Cortes multinomial | Cortes pareado |
|---|---:|---:|---:|
| Sensibilidade HCC | 75,80% | 75,80% | não altera binário |
| Especificidade HCC | 77,53% | 76,40% | não altera binário |
| Subtipo balanceada | 48,88% | 51,08% | 51,05% |
| Subtipo top-1 | 56,42% | 58,21% | 59,10% |
| Subtipo top-2 | 77,91% | 76,42% | 77,91% |

O classificador pareado axial falhou no gate pré-especificado: o ganho de
balanceada foi +2,17 pontos (exigido +5) e o top-1 ficou em 59,10% (exigido
60%). Nenhum dos dois braços axiais foi promovido. A cobertura integral melhora
moderadamente a caracterização, mas ainda dilui a região focal porque todas as
instâncias têm o mesmo peso antes da agregação.

Recall axial pareado por subtipo:

| Subtipo | Recall |
|---|---:|
| HCC | 75,80% |
| FNH | 45,65% |
| Hemangioma | 54,43% |
| Cisto | 28,30% |

Assinaturas:

```text
multinomial axial = 9bd8faf8eb6cdb3dbe0128e70187e7df0ec182ce568861a1028fc60dd12e7238
pairwise axial    = 83ff75c3d46f6cf399e01bfb1bfdebdc9868460354dc991c735a1e1efbd32c83
```

Próximo ramo permitido: selecionar instâncias sem ground truth e fornecer o
diferencial top-2 a um segundo leitor MedGemma 4B/RAG. A saída deve poder ser
`INCONCLUSIVA`, e top-2 jamais pode ser publicado como acerto top-1.

## Segundo leitor top-2 — fundação e smoke 4B

Foi implementado um contrato de adjudicação que reutiliza o endpoint A/B/C
existente, sem mudar o contrato HTTP:

1. MedSigLIP fornece exatamente dois subtipos e probabilidades normalizadas;
2. o mesmo corte é lido duas vezes, invertendo A e B;
3. C significa sempre `INCONCLUSIVA`;
4. as probabilidades são remapeadas aos subtipos e promediadas;
5. exige probabilidade ≥50% e margem ≥15 pontos para nomear subtipo;
6. escolha fora do top-2 é rejeitada;
7. a decisão binária não pode ser promovida pelo segundo leitor;
8. toda discordância HCC/benigno vira inconclusiva e revisão humana.

No smoke real com MedGemma 1.5 4B, o modelo escolheu a letra A nas duas ordens.
Depois do remapeamento, HCC ficou em 43,06% e FNH em 41,10%, margem de apenas
1,97 ponto. O gate respondeu corretamente `subtipo_determinado=false`.

```text
duas leituras = 4,584 s
casos/qualification/hybrid_v1/monophase_subtype_adjudication_smoke_v1.json
```

O smoke valida contrato, execução e latência unitária; não mede acurácia, pois
usou probabilidades técnicas controladas e apenas uma imagem.

## Verificação final desta rodada

```text
1407 testes
0 falhas
0 erros
82,285 s
casos/qualification/hybrid_v1/monophase_hierarchical_full_suite_junit_v3.xml
```

Webapp em `:8080` e MedGemma 4B CUDA em `:8001` permaneceram prontos após os
benchmarks. Nenhum braço reprovado foi habilitado automaticamente no produto.

## Continuação — OpenSwissHCC monofásico e sinais complementares

A auditoria de falhas, cobertura axial exata, T2/DWI/ADC reais, MIL e fusão
tolerante a modalidade ausente estão documentados em
`docs/183_MONOFASICO_COMPLEMENTAR_E_FUSAO_MISSING_AWARE.md`.

O melhor candidato de desenvolvimento atual é a fusão aninhada do painel
tardio global, cobertura axial e ADC, com indicador explícito de sinal ausente:

```text
sensibilidade = 71,79%
especificidade = 73,47%
ROC-AUC = 0,7792
falhas técnicas = 0
```

O gate 75/75 permanece reprovado e nenhum limiar retrospectivo o satisfaz.
