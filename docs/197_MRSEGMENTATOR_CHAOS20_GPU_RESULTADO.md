# 197 — MRSegmentator no CHAOS completo: resultado GPU

## Decisão

O MRSegmentator passou o gate quantitativo da Fase 2 e avança como candidato à
avaliação de robustez no domínio do ARGOS. Ele **não foi ligado ao webapp** e
não substitui `total_mr` nesta etapa.

## Protocolo

- coorte: CHAOS T1 in-phase, 20 casos com máscara humana;
- inferência executada antes da leitura das referências;
- modo: `fast_single_fold_gpu`;
- fígado: rótulo multiclasse `5`, extraído para máscara binária;
- GPU: NVIDIA GeForce RTX 4060 Laptop, 8 GB;
- ambiente isolado: `.venv-mrseg`;
- PyTorch isolado corrigido de CPU para `2.6.0+cu124`;
- nenhum arquivo de produção escrito;
- zero máscaras de lesão lidas.

## Resultado

| métrica mediana, n=20 | `total_mr` | MRSegmentator | leitura |
|---|---:|---:|---|
| Dice | 0,9082 | **0,9244** | ganho de 0,0162 |
| recall | 0,8375 | **0,8979** | recupera mais fígado |
| precisão | **0,9899** | 0,9508 | perde 3,9 pontos de precisão |
| razão de volume | 0,8513 | **0,9444** | muito mais próximo da referência |
| HD95 | 13,04 mm | **9,00 mm** | borda mais próxima |
| ASSD | 3,04 mm | **2,02 mm** | superfície mais próxima |
| Dice mínimo | 0,8650 | **0,9009** | nenhum caso catastrófico |

O Dice melhorou em 18/20 casos e piorou levemente em 2/20. O maior ganho foi
`+0,0598`; a maior perda foi `-0,0096`. O teste pareado de Wilcoxon para Dice
deu `p=0,000019`, confirmando que o ganho observado nos 20 casos não é apenas
um caso extremo isolado.

A redução de precisão é real e não deve ser escondida: o MRSegmentator expande
mais a máscara. Contra a referência humana, porém, essa expansão melhora Dice,
volume, HD95 e ASSD, portanto o balanço foi favorável nesta coorte.

## Desempenho

| indicador | resultado |
|---|---:|
| casos concluídos | 20/20 |
| falhas técnicas | 0 |
| tempo mediano | 28,00 s |
| tempo máximo | 32,56 s |
| pico máximo de VRAM | 4.349 MB |
| timeout por caso | 180 s |

O candidato cabe com margem na RTX 4060 de 8 GB e deixa espaço temporal para o
restante do pipeline. Isso mede apenas a segmentação, não o tempo completo do
ARGOS.

## Gates

| gate pré-especificado | exigido | obtido | estado |
|---|---:|---:|---|
| Dice mediano | ≥0,92 | 0,9244 | PASSA |
| ganho de Dice vs baseline | ≥0,01 | +0,0162 | PASSA |
| Dice mínimo | ≥0,80 | 0,9009 | PASSA |
| razão de volume mediana | 0,90–1,10 | 0,9444 | PASSA |
| máscaras vazias | 0 | 0 | PASSA |
| tempo máximo da segmentação | ≤180 s | 32,56 s | PASSA |

## Artefatos

- execução cega: `experiments/mrsegmentator_chaos_gpu_fast_v2/`;
- avaliação: `experiments/liver_segmentation_benchmark_chaos_v2/`;
- galeria: `experiments/liver_segmentation_benchmark_chaos_v2/gallery/index.html`.

## Limite da conclusão

O CHAOS é T1 sem contraste. O próximo gate precisa verificar robustez em fases
contrastadas e nos casos difíceis do ARGOS sem usar rótulos de lesão. Somente
depois disso o modelo poderá entrar em shadow mode, ainda restrito ao 3-D.
