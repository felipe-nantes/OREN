# 202 — Smoke real do webapp com 3-D aprimorado

## Resultado

O fluxo individual do webapp foi executado ponta a ponta com um estudo público
multifásico real, usando a opção `Usar segmentação 3-D aprimorada`.

```text
240 DICOMs reais
→ resolução label-blind das fases
→ segmentação baseline para classificação
→ painéis e classificação congelados
→ MRSegmentator arterial shadow
→ validação do recibo e do hash
→ malha 3-D e referências 2-D
```

Nenhum label, ground truth ou máscara pública de lesão foi aberto durante o
teste.

## Identificação segura

- job local: `296732bff897`;
- identificador exibido: `anon-2fa8a821b90e`;
- cenário: `hybrid_supervised`;
- fases: arterial, venosa e tardia;
- método de resolução: `ordered_axial_t1_postcontrast_series`;
- confiança técnica da resolução: `0,8`.

## Segmentação aprimorada

| item | resultado |
|---|---:|
| estado | `APPROVED` |
| backend | MRSegmentator 2.0.0 |
| fase selecionada | arterial |
| fallback | não |
| mesma grade da referência | sim |
| voxels hepáticos | 325.658 |
| volume | 1.526,52 mL |
| tempo do segmentador | 29,38 s |
| ground truth lido | não |
| máscaras de lesão lidas | 0 |
| arquivos de classificação alterados | não |
| hash registrado igual ao arquivo | sim |

A união multifásica anterior foi corretamente omitida após a aprovação do
shadow (`replaced_by_phase_aware_shadow`).

## Resultado operacional

| etapa | tempo |
|---|---:|
| ingestão e segmentação baseline | 43,22 s |
| painéis | 1,62 s |
| classificação | 21,81 s |
| localização pós-inferência | 30,08 s |
| segmentação 3-D aprimorada | 30,07 s |
| construção do modelo 3-D | 23,35 s |
| total | **150,17 s** |

O fluxo ficou abaixo do limite operacional de 180 segundos. O resultado de
triagem foi persistido, mas este smoke valida integração e tempo; não é uma nova
avaliação de sensibilidade ou especificidade.

## Gate da malha

- `viewer_ready=true`;
- volume da máscara refinada: 1.526,01 mL;
- volume da malha: 1.526,82 mL;
- erro de volume: 0,0536%;
- desvio superficial p95: 1,4134 mm;
- 160.000 triângulos;
- superfície fechada e manifold;
- gate de reconstrução aprovado.

O log confirma explicitamente que o estágio 5 refinou o órgão a partir de
`mask_organ_visualization_v2.nii.gz`.

## Capturas

- cena completa:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/webapp_real_multiphase_job_296732bff897_3d.png`;
- fígado isolado e reenquadrado:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/webapp_real_multiphase_job_296732bff897_liver_isolated_final.png`.

## Conclusão

A integração opt-in está funcional no caminho real do webapp. A máscara arterial
aprovada chegou ao visualizador sem alimentar novamente a classificação, o
fallback permaneceu disponível e o tempo total cumpriu o gate de três minutos.
