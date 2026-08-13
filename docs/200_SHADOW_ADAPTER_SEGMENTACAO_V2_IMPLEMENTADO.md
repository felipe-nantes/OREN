# 200 — Adaptador phase-aware da segmentação v2

> Atualização: a revisão humana foi aprovada e o adaptador passou a ter integração
> opt-in no exame individual. O contrato e os gates da promoção estão documentados
> em `docs/201_INTEGRACAO_OPT_IN_3D_APRIMORADO.md`.

## Estado

Implementado e validado em modo **experimental shadow-only**. O adaptador ainda
não é carregado pelo webapp e não substitui nenhuma máscara ativa.

## O que foi implementado

- seleção determinística `arterial registrada → volume representativo`;
- validação de geometria física antes de aceitar a arterial;
- execução isolada do MRSegmentator 2.0.0;
- saída restrita a:
  - `segmentation_input_manifest_v2.json`;
  - `mask_organ_visualization_v2.nii.gz`;
  - `segmentation_quality_manifest_v2.json`;
- recusa de sobrescrita de uma execução shadow existente;
- remoção de candidato parcial em falha;
- manifesto sem caminho da fonte, metadados DICOM ou identificadores;
- hashes, backend, versão, fase selecionada, fallback e tempo persistidos;
- zero uso de ground truth ou máscara de lesão;
- tolerância a handles transitórios do Windows na publicação de runs GPU.

Arquivos principais:

- `dtwin/segmentation_shadow.py`;
- `tools/run_segmentation_visualization_shadow_v2.py`;
- `tests/test_segmentation_shadow.py`;
- `configs/segmentation_visualization_v2.yaml`.

## Smoke test real

Caso público isolado: `anon-public-1a75c9f1c6c69df9786f`.

| item | resultado |
|---|---:|
| fase selecionada | arterial registrada |
| fallback | não |
| tempo | 19,94 s |
| voxels de fígado | 419.641 |
| volume | 1.850,53 mL |
| mesma grade da referência | sim |
| ground truth lido | não |
| máscaras de lesão lidas | 0 |
| arquivos de produção escritos | não |

O smoke foi executado em
`experiments/segmentation_shadow_smoke_liverhccseg_v2/`, fora do caso original.
As cópias-sentinela de `volume.nii.gz`, `mask_organ.nii.gz` e
`medgemma_report.json` permaneceram intactas. A máscara repetida diferiu em 32
voxels de aproximadamente 420 mil em relação à execução arterial anterior, sem
mudança de geometria; essa pequena não-deterministicidade de GPU deve continuar
registrada em futuras auditorias.

## Comparação 3-D isolada

O mesmo algoritmo de malha usado pelo ARGOS foi executado sobre a máscara atual
e sobre o shadow, sem publicar artefatos no viewer:

- máscara atual `total_mr`: 1.284,54 mL;
- máscara shadow arterial: 1.850,52 mL;
- ambas as malhas: 160.000 triângulos;
- imagem: `experiments/segmentation_shadow_smoke_liverhccseg_v2/mesh_comparison/shadow_mesh_comparison.png`;
- manifesto e hashes: `shadow_mesh_comparison.json` na mesma pasta.

Neste caso, a referência humana retrospectiva deu Dice 0,7597 ao `total_mr` e
0,9330 ao MRSegmentator arterial. Portanto, o aumento visual de volume representa
recuperação de fígado real neste exemplo auditado, não apenas expansão estética.

## Validação automatizada

- testes específicos da fundação, comparação, fusão e shadow: 27 aprovados;
- regressão de motor, webapp, ingestão, artefatos do viewer e runtime: 135
  aprovados;
- snapshot do baseline: verificado separadamente;
- produção: configuração v2 continua com `enabled: false`.

## Próximo passo

Submeter a galeria de contornos e a comparação 3-D à revisão humana. Depois,
considerar uma integração opt-in no exame individual. Classificação, painéis e
relatório MedGemma devem permanecer imutáveis durante todo esse gate.
