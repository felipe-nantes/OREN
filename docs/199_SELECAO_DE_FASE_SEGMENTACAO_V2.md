# 199 — Seleção de fase para a segmentação hepática v2

## Decisão

O candidato recomendado para o próximo shadow mode é:

```text
MRSegmentator em fase arterial, quando a fase arterial confiável estiver disponível
→ caso contrário, MRSegmentator no volume nativo/representativo
→ manter total_mr como baseline ativo até terminar o shadow mode
```

A fusão de quatro fases não será promovida, apesar do melhor Dice, porque viola o
orçamento temporal em parte da coorte. Nenhuma alteração foi feita no webapp, no
classificador, nos painéis ou no visualizador 3-D ativo.

## Comparação de fases — LiverHccSeg, n=14

| candidato | Dice mediano | recall | precisão | razão de volume | HD95 | Dice mínimo |
|---|---:|---:|---:|---:|---:|---:|
| `total_mr` venoso | 0,8977 | 0,8245 | **0,9885** | 0,8414 | 15,52 mm | 0,7597 |
| MRSegmentator venoso | 0,9138 | 0,8617 | 0,9781 | 0,8935 | 9,19 mm | 0,8283 |
| MRSegmentator tardio | 0,9213 | 0,8709 | 0,9747 | 0,9116 | 8,71 mm | 0,8137 |
| MRSegmentator nativo | 0,9375 | **0,9177** | 0,9606 | 0,9452 | **7,10 mm** | **0,8655** |
| MRSegmentator arterial | **0,9417** | 0,9170 | 0,9705 | **0,9461** | 7,38 mm | 0,8334 |
| fusão protegida 4 fases | 0,9444 | 0,9436 | 0,9482 | 0,9995 | 7,37 mm | 0,8709 |

Todos os candidatos foram gerados antes da avaliação e sem leitura de label
patológico ou máscara de lesão.

## Por que a arterial foi escolhida

A fase arterial passa todos os gates absolutos pré-especificados:

| gate | exigido | arterial | estado |
|---|---:|---:|---|
| Dice mediano | ≥0,92 | 0,9417 | passa |
| ganho de Dice vs `total_mr` | ≥0,01 | +0,0440 | passa |
| Dice mínimo | ≥0,80 | 0,8334 | passa |
| razão de volume mediana | 0,90–1,10 | 0,9461 | passa |
| máscaras vazias | 0 | 0 | passa |
| tempo máximo de segmentação | ≤180 s | 75,45 s | passa |

O tempo mediano foi 32,89 segundos. Isso preserva margem muito maior para o
restante do ARGOS do que a fusão multifásica.

## Por que a fusão de quatro fases não foi escolhida

A fusão protegida melhorou o Dice mediano para 0,9444 e a razão de volume para
0,9995, mas exige quatro inferências sequenciais. O tempo combinado observado foi:

- mediana: 137,87 segundos;
- máximo: 304,45 segundos;
- casos acima de 180 segundos apenas na segmentação: 3/14.

Ela é útil como evidência de que as fases contêm informação complementar, mas não
atende ao requisito operacional de análise rápida. O preenchimento de cavidades
na máscara venosa isolada não reproduziu o ganho (`0,913828` versus `0,913822`),
confirmando que a melhora não veio de pós-processamento artificial.

## Evidência em outro domínio

No CHAOS T1 sem contraste, o MRSegmentator já havia obtido Dice mediano 0,9244,
razão de volume 0,9444, Dice mínimo 0,9009 e tempo máximo 32,56 segundos. Assim,
o volume nativo/representativo é um fallback tecnicamente sustentado quando não
houver fase arterial confiável.

## Política para o shadow mode

1. Usar a classificação de fase já produzida pelo pipeline; não inferir fase pelo
   nome da pasta.
2. Aceitar arterial apenas quando os gates de geometria, registro e qualidade
   estiverem aprovados.
3. Se arterial estiver ausente ou reprovada, usar o volume nativo/representativo.
4. Gerar somente `mask_organ_visualization_v2.nii.gz`; nunca sobrescrever
   `mask_organ.nii.gz`, `mask_organ_union.nii.gz` ou entradas do MedGemma.
5. Registrar backend, versão, fase, hashes, geometria, tempo e motivo do fallback.
6. Comparar lado a lado com a máscara atual no visualizador de auditoria.
7. Manter `total_mr` como fonte ativa até a aprovação humana e técnica do shadow.

## Artefatos

- comparação das fases:
  `experiments/liver_segmentation_benchmark_liverhccseg_single_phases_v2/`;
- galeria:
  `experiments/liver_segmentation_benchmark_liverhccseg_single_phases_v2/gallery/index.html`;
- comparação da fusão:
  `experiments/liver_segmentation_benchmark_liverhccseg_phase_fusion_v2/`;
- inferências por fase:
  `experiments/mrsegmentator_liverhccseg_{native,arterial,venous,delayed}_gpu_fast_v2/`.

## Próximo gate

Implementar o shadow adapter phase-aware dentro do contrato experimental v2 e
testá-lo em exame individual real, sem alterar o comportamento de produção. A
promoção só poderá ser discutida após:

- regressão integral aprovada;
- auditoria visual dos contornos e da malha 3-D;
- ausência de PHI e de máscara de lesão;
- prova de que classificações/painéis permanecem byte a byte inalterados;
- tempo end-to-end dentro do requisito do ARGOS.
