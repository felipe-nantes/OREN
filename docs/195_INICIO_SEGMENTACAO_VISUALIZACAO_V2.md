# 195 — Início seguro da segmentação/visualização v2

## Objetivo desta entrega

Iniciar o plano de melhoria da segmentação hepática sem modificar nenhuma
função atualmente ativa. Esta entrega cobre a Fase 0 e a fundação da Fase 1:

1. congela o baseline atual;
2. formaliza uma configuração experimental desligada;
3. separa a futura entrada nativa do segmentador da entrada do classificador;
4. reserva nomes de artefatos exclusivos para o experimento;
5. impede por código que o experimento sobrescreva a máscara classificada.

## O que permanece exatamente igual

- `mask_organ.nii.gz` continua sendo a máscara de classificação;
- `total_mr` continua sendo o segmentador de produção;
- `mask_organ_union.nii.gz` continua sendo preferida somente pela malha 3-D;
- o MedGemma, o benchmark, o webapp e o visualizador não carregam a nova config;
- nenhum backend MRSegmentator/MRISegmenter foi ligado;
- nenhum exame ou ground truth foi lido.

## Novos artefatos reservados

| Artefato | Finalidade |
|---|---|
| `segmentation_input_manifest_v2.json` | registra hashes e geometria da entrada nativa sem caminho/PHI |
| `mask_organ_visualization_v2.nii.gz` | futura máscara experimental, apenas para visualização |
| `segmentation_quality_manifest_v2.json` | backend, versão, hash, volume, geometria, tempo e revisão |

O contrato recusa explicitamente escrita em `mask_organ.nii.gz`,
`mask_organ_union.nii.gz`, `volume.nii.gz` e `medgemma_report.json`.

## Decisão arquitetural

```text
DICOM bruto
├── preparação/classificação atual (congelada)
└── entrada nativa de segmentação v2 (experimental)
    └── máscara visual v2 na grade do volume classificado
```

A promoção da nova máscara para o classificador não faz parte desta etapa. Se
isso for proposto no futuro, será um candidato separado e exigirá nova validação
de sensibilidade/especificidade.

## Configuração experimental

`configs/segmentation_visualization_v2.yaml` nasce com:

```yaml
enabled: false
status: experimental_shadow_only
```

Ela contém candidatos, fallback e gates planejados, mas não está conectada ao
servidor. Assim, sua presença não altera o comportamento do ARGOS.

## Próximo gate

A próxima etapa deve criar um executor de benchmark isolado — não o webapp —
para comparar, na mesma entrada nativa:

1. `total_mr`;
2. MRSegmentator;
3. MRISegmenter-Abdomen.

Primeiro no CHAOS completo com referência humana; depois em uma coorte LLD fixa
apenas para robustez. O vencedor só poderá entrar em shadow mode após passar os
gates de acurácia, máscara vazia, geometria e tempo.

## Validação executada

- snapshot do baseline gerado e verificado independentemente;
- contrato experimental, proteção de artefatos e geometria: aprovado;
- regressões de preparação, finalização, união multifásica, webapp,
  TotalSegmentator e artefatos do visualizador: aprovadas;
- total da seleção focada: **143 testes aprovados**;
- nenhum arquivo do fluxo ativo (`dtwin/stages.py`, `webapp/server.py`,
  `webapp/seg_worker.py`, `viewer/app.js` ou `profiles/figado.yaml`) foi alterado.
