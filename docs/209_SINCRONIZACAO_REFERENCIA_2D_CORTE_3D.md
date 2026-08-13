# Sincronização da referência 2D com o corte 3D

## Objetivo

Vincular os planos axial, coronal e sagital das referências de RM ao plano de corte ortogonal do visualizador 3D. A mudança é exclusivamente de revisão visual: não altera DICOM, máscaras, segmentação, classificação, MedGemma ou relatório clínico.

## Implementação

- O visualizador mantém o padrão visual sólido e o modelo completo na abertura.
- A opção **Sincronizar plano 2D com corte 3D** fica preparada por padrão, mas o corte só é ativado após interação do revisor.
- Ao mover o seletor da referência 2D, o corte 3D é ativado na mesma coordenada física LPS.
- Ao mudar a orientação, o eixo é convertido deterministicamente:
  - axial → `z`;
  - coronal → `y`;
  - sagital → `x`.
- A posição LPS da imagem é transformada para a translação usada para centralizar o modelo no Three.js. A interface mostra a coordenada LPS original, não a coordenada interna centralizada da cena.
- O controle do corte passou a aceitar passos de `0,01%`, evitando erro de arredondamento visível entre a imagem e o plano 3D.
- Alterar eixo, posição, inversão ou ativação diretamente nos controles do corte pausa a sincronização e passa para ajuste manual.
- Desativar a sincronização remove o corte, retornando à visualização completa.
- Planos sem `position_lps_mm` falham de forma segura e não deslocam o corte.

## Auditoria da revisão

O `approval.json` passa a registrar, dentro de `viewer_state`:

- `reference_sync_enabled`;
- `reference_view`;
- `reference_frame_index`;
- além do estado de clipping já existente.

O backend valida orientação permitida e proíbe índice negativo.

## Validação funcional

Caso usado: `c2424a1dd2e1`.

Resultados observados no navegador:

- axial: eixo Z, `44,8 mm LPS`, corte e referência concordantes;
- coronal: eixo Y, `-3,0 mm LPS`, corte e referência concordantes;
- sagital: eixo X, `-74,3 mm LPS`, corte e referência concordantes;
- padrão visual sólido permaneceu ativo na abertura;
- clipping permaneceu desativado antes da primeira interação.

Captura técnica:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_reference_2d_3d_sync_job_c2424a1dd2e1.png`

## Testes

- contrato JavaScript dos três eixos e da transformação LPS;
- ausência de requisição/inferência dentro da sincronização;
- validação Pydantic do estado persistido;
- persistência dos novos campos no endpoint de aprovação;
- verificação sintática de `viewer/app.js`;
- suíte integrada do visualizador, webapp, finalização, candidato, CLI e gates: **126 testes aprovados**.

## Limites

O plano sincronizado ajuda a correlacionar superfície e RM, mas não transforma o visualizador em estação diagnóstica e não mede a acurácia anatômica da segmentação. Toda aprovação continua exigindo revisão humana.
