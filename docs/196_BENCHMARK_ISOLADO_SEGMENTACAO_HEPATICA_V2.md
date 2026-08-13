# 196 — Benchmark isolado de segmentação hepática v2

## Escopo

Foi implementado o executor pós-inferência que compara máscaras hepáticas já
congeladas. Ele não chama modelos, não lê ground truth antes da predição e não
escreve dentro das pastas dos casos.

O primeiro uso reaproveitou predições já existentes no CHAOS e depois foi
completado por uma execução GPU integral. O resultado final está consolidado em
`docs/197_MRSEGMENTATOR_CHAOS20_GPU_RESULTADO.md`:

- `total_mr`: 20 casos disponíveis;
- MRSegmentator: 20 casos executados em GPU;
- MRISegmenter-Abdomen: ainda sem pesos/ambiente de inferência local, registrado
  como candidato opcional e não tratado como resultado.

## Métricas

- Dice e Jaccard;
- precisão e recall do fígado;
- razão e erro absoluto de volume;
- HD95 e ASSD em milímetros;
- quantidade de componentes e fração do maior componente;
- indicação de reamostragem para a grade de referência.

Predições multiclasse exigem um `label_value` explícito. MRSegmentator e
MRISegmenter usam rótulo `5` para fígado; tratar simplesmente todo valor maior
que zero como fígado é recusado pelo protocolo porque misturaria todos os órgãos.

## Galeria técnica

Para cada caso são mostradas as vistas axial, coronal e sagital no centroide da
referência humana:

- amarelo: referência humana;
- ciano: `total_mr`;
- magenta: MRSegmentator;
- verde: futuro MRISegmenter-Abdomen.

As vistas respeitam o espaçamento físico de cada eixo. Isso evita achatar as
vistas coronal e sagital de exames com aquisição anisotrópica.

A galeria serve para auditoria; a referência jamais é passada a um segmentador.

## Segurança

- avaliação somente em `experiments/`, que é ignorado pelo Git;
- sobrescrita de uma execução existente é recusada;
- predição obrigatória ausente aborta;
- modelo opcional ausente fica explicitamente `not_available`;
- hashes das fontes, referências e máscaras são persistidos;
- o fluxo de produção continua sem importar este executor.

## Próximo gate

1. validar o executor sobre o piloto já congelado;
2. inspecionar a galeria;
3. executar MRSegmentator nos 20 casos CHAOS em ambiente isolado/GPU;
4. preparar ambiente isolado do MRISegmenter somente após checagem de licença e
   disponibilidade dos pesos;
5. comparar os três modelos na mesma coorte completa.

### Execução GPU durável

O complemento dos 20 casos usa `tools/run_mrsegmentator_chaos_gpu_v2.py` em
`.venv-mrseg`. Cada caso é executado em subprocesso, com timeout de 180 s,
checkpoint com `fsync`, hashes do labelmap e da máscara binária, logs separados
e medição de pico de VRAM. A execução é retomável e nunca abre a referência
humana; a avaliação é outro processo posterior.

## Execução inicial validada

O executor foi aplicado aos 20 casos CHAOS já disponíveis. O `total_mr` possui
predição nos 20; o piloto MRSegmentator possui seis casos. A comparação pareada
correta usa exclusivamente esses mesmos seis casos:

| métrica mediana, mesmos 6 casos | `total_mr` | MRSegmentator |
|---|---:|---:|
| Dice | 0,9055 | **0,9229** |
| recall | 0,8330 | **0,8945** |
| razão de volume | 0,8443 | **0,9567** |
| HD95 | 11,28 mm | **9,00 mm** |

O maior ganho individual de Dice foi `+0,0598`. Isso confirma um sinal visual e
quantitativo relevante, mas **não promove o modelo**: faltam os outros 14 casos,
tempo em GPU e o terceiro candidato.

Durante a primeira execução, o avaliador detectou que as saídas do MRSegmentator
são mapas multiclasse. Uma leitura provisória `valor > 0` misturava todos os
órgãos e produzia números inválidos; essa execução foi preservada como inválida,
o protocolo passou a exigir explicitamente `label_value: 5`, e novos testes
cobrem essa condição. Os resultados acima são da execução corrigida.

Galeria:

`experiments/liver_segmentation_benchmark_chaos_v2/gallery/index.html`
