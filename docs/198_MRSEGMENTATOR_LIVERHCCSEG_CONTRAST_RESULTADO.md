# 198 — MRSegmentator em RM hepática contrastada: resultado LiverHccSeg

## Decisão

O MRSegmentator confirmou ganho consistente sobre o `total_mr` em RM hepática
contrastada e permanece como o candidato principal da segmentação v2. Ele ainda
**não será promovido para produção**: os gates absolutos de Dice mediano e razão
de volume ficaram ligeiramente abaixo do valor pré-especificado.

O fluxo ativo do webapp, benchmark, geração de painéis e visualizador 3-D não foi
alterado por este experimento.

## Protocolo

- coorte pública: LiverHccSeg, 14 casos;
- entrada label-blind: fase venosa registrada;
- comparação: `total_mr` full-resolution versus MRSegmentator
  `fast_single_fold_gpu`;
- inferências concluídas antes da abertura das máscaras humanas de fígado;
- nenhuma máscara de lesão ou label patológico foi lido ou enviado aos modelos;
- GPU: NVIDIA GeForce RTX 4060 Laptop, 8 GB;
- timeout isolado: 180 segundos por caso;
- avaliação espacial feita na geometria física da referência.

## Resultado quantitativo

| métrica mediana, n=14 | `total_mr` | MRSegmentator | diferença |
|---|---:|---:|---:|
| Dice | 0,8977 | **0,9138** | +0,0161 |
| recall | 0,8245 | **0,8617** | +0,0372 |
| precisão | **0,9885** | 0,9781 | -0,0104 |
| razão de volume | 0,8414 | **0,8935** | +0,0520 |
| HD95 | 15,52 mm | **9,19 mm** | -6,33 mm |
| ASSD | 3,20 mm | **2,85 mm** | -0,36 mm |
| Dice mínimo | 0,7597 | **0,8283** | +0,0686 |

O MRSegmentator melhorou o Dice em **14/14 casos**. O teste pareado de Wilcoxon
para Dice resultou em `p=0,000122`. Também houve ganho significativo em recall,
razão de volume e distância de superfície. A queda de precisão é pequena, mas
real, e permanece registrada.

## Desempenho técnico

| execução | concluídos | falhas | mediana | máximo | pico de VRAM |
|---|---:|---:|---:|---:|---:|
| `total_mr` full | 14/14 | 0 | 35,53 s | 40,30 s | 3.371 MB |
| MRSegmentator fast | 14/14 | 0 | 31,82 s | 74,56 s | 3.811 MB |

As duas alternativas cabem no hardware atual. O maior tempo do MRSegmentator
continua abaixo do limite de 180 segundos para a etapa de segmentação.

## Gates pré-especificados

| gate | exigido | obtido pelo MRSegmentator | estado |
|---|---:|---:|---|
| Dice mediano | ≥0,92 | 0,9138 | não passa por 0,0062 |
| ganho de Dice vs baseline | ≥0,01 | +0,0161 | passa |
| Dice mínimo | ≥0,80 | 0,8283 | passa |
| razão de volume mediana | 0,90–1,10 | 0,8935 | não passa por 0,0065 |
| máscaras vazias | 0 | 0 | passa |
| tempo máximo | ≤180 s | 74,56 s | passa |

O candidato passa nos gates de ganho, pior caso, estabilidade e tempo, mas não
passa integralmente no gate absoluto. A diferença pequena não deve ser arredondada
para aprovação.

## Leitura visual

O maior ganho ocorreu em `anon-public-1a75c9f1c6c69df9786f`: o `total_mr`
subsegmentou uma porção extensa, enquanto o MRSegmentator aproximou melhor a
borda humana. Ainda existem lacunas internas na máscara candidata.

O caso de menor Dice do MRSegmentator foi `anon-public-c65717b2246816a69edf`.
Mesmo melhor que o baseline, ele mantém subsegmentação superior/central. Esse
padrão explica a razão de volume mediana ainda inferior a 0,90.

## Artefatos auditáveis

- inferência MRSegmentator:
  `experiments/mrsegmentator_liverhccseg_venous_gpu_fast_v2/`;
- inferência `total_mr`:
  `experiments/total_mr_liverhccseg_venous_gpu_full_v2/`;
- avaliação:
  `experiments/liver_segmentation_benchmark_liverhccseg_venous_v2/`;
- galeria:
  `experiments/liver_segmentation_benchmark_liverhccseg_venous_v2/gallery/index.html`.

## Próximo passo técnico

Antes de qualquer promoção, avaliar uma correção determinística e label-blind da
subsegmentação, priorizando:

1. consenso/fusão das máscaras geradas nas fases registradas;
2. preenchimento controlado de cavidades internas sem expandir livremente a borda;
3. comparação com o candidato MRISegmenter-Abdomen, se pesos e licença estiverem
   disponíveis;
4. repetição dos mesmos gates em CHAOS e LiverHccSeg;
5. somente depois, shadow mode do candidato vencedor no exame individual.

Nenhuma dessas operações pode usar máscara de lesão, label patológico ou
referência humana durante a inferência. A referência humana permanece exclusiva
da avaliação retrospectiva.
