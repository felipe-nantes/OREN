# 201 — Integração opt-in da segmentação 3-D aprimorada

## Estado

Implementada no fluxo de exame individual como opção experimental, desmarcada
por padrão. A integração promove somente a saída de visualização do adaptador
shadow. Classificação, painéis enviados ao MedGemma, relatório clínico e arquivos
legados permanecem imutáveis.

## Candidato promovido

```text
MRSegmentator 2.0.0 na arterial registrada e aprovada
→ fallback label-blind para o volume representativo quando necessário
→ fallback operacional para mask_organ_union.nii.gz ou mask_organ.nii.gz
```

A escolha foi sustentada pelo benchmark LiverHccSeg de 14 casos: Dice mediano
0,9417, recall 0,9170, precisão 0,9705, Dice mínimo 0,8334 e tempo máximo de
75,45 segundos. A fusão de quatro fases não foi promovida porque excedeu 180
segundos em 3/14 casos.

## Contrato de segurança

O visualizador somente aceita `mask_organ_visualization_v2.nii.gz` quando o
recibo versionado comprova simultaneamente:

- estado aprovado;
- finalidade `visualization_only`;
- classificação imutável;
- zero leitura de ground truth;
- zero leitura de máscara de lesão;
- zero escrita em arquivos de produção;
- SHA-256 da máscara igual ao registrado no recibo.

Recibo ausente, parcial, inconsistente ou com hash inválido é ignorado. O fluxo
continua com a máscara ativa anterior, sem interromper o exame.

## Integração no webapp

- endpoint de capacidade fail-closed: `/api/segmentation-visualization`;
- checkbox no exame individual: `Usar segmentação 3-D aprimorada`;
- disponível somente quando a configuração autorizada e o ambiente isolado do
  MRSegmentator existem localmente;
- aceita apenas o valor booleano estrito enviado pelo formulário;
- o navegador nunca escolhe executável, configuração, fase ou caminho;
- execução inserida depois da classificação e antes da construção da malha;
- opção aplicável ao fluxo multifásico e desmarcada por padrão;
- falha do candidato gera fallback explícito, sem perder a análise.

## Seleção da fonte da malha

Ordem determinística:

1. shadow v2 aprovado e com hash válido;
2. máscara de união multifásica existente;
3. máscara hepática baseline.

O gate de geometria física do volume permanece obrigatório antes da geração da
malha 3-D.

## Evidência visual e smoke test

- comparação de malhas:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/mesh_comparison/shadow_mesh_comparison.png`;
- opção validada no webapp:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/webapp_enhanced_3d_option_viewport.png`;
- smoke real do adaptador: 19,94 segundos, mesma grade da referência, 419.641
  voxels hepáticos, zero leitura de ground truth ou máscara de lesão.

No caso auditado, o Dice retrospectivo melhorou de 0,7597 (`total_mr`) para
0,9330 (MRSegmentator arterial). Esse dado sustenta a melhora anatômica daquele
caso, mas não altera nem representa a acurácia de classificação do ARGOS.

## Critério para uso

Esta opção é experimental e exige revisão humana. Ela melhora a anatomia exibida
no visualizador, não autoriza uso clínico e não deve ser apresentada como ganho
de sensibilidade ou especificidade do MedGemma.
