# Padrão visual sólido e transparência controlada

## Decisão

O acabamento realista deixou de existir como modo selecionável. Ele agora é a linguagem visual permanente do visualizador e é aplicado automaticamente a fígado, vasos, vesícula e regiões auxiliares.

O controle **Restaurar padrão** não representa um modo alternativo: ele apenas desfaz ajustes manuais e restaura a composição oficial.

## Comportamento padrão

- fígado com acabamento orgânico e opacidade `1,0`;
- superfície hepática grava corretamente a profundidade da cena;
- vasos, vesícula e candidatos respeitam a oclusão do fígado;
- estruturas situadas atrás ou dentro da superfície não são desenhadas sobre o órgão;
- cores orgânicas permanecem aplicadas às estruturas visíveis externamente;
- controles de anatomia interna, triagem e Couinaud continuam disponíveis para revisão dirigida.

## Transparência

Ao reduzir manualmente a barra **Opacidade de Fígado** abaixo de `1,0`:

- o material hepático passa a ser transparente;
- a escrita de profundidade do fígado é desativada;
- estruturas internas passam a ser visíveis através do parênquima;
- restaurar a opacidade para `1,0`, ou usar **Restaurar padrão**, recupera a oclusão sólida.

Essa regra elimina a visualização interna involuntária que existia porque as estruturas anatômicas usavam `depthTest=false`.

## Compatibilidade

- novos manifestos registram `default_visual_preset: default`;
- manifestos históricos com `realistic` ou `surface` são convertidos internamente para o novo padrão;
- revisões históricas continuam aceitas pelo backend;
- não houve mudança em segmentação, inferência, classificação ou relatório.

## Validação visual

Caso: `c2424a1dd2e1`.

- padrão sólido em opacidade `1,0`:
  `experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_default_solid_occlusion_job_c2424a1dd2e1.png`;
- transparência manual em opacidade `0,35`:
  `experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_manual_transparency_reveals_anatomy_job_c2424a1dd2e1.png`.

## Segurança metodológica

A alteração é exclusivamente visual. O visualizador permanece destinado a pesquisa e revisão humana, e a aparência 3D não comprova acurácia anatômica da máscara.

Validação automatizada: **126 testes aprovados**, além da verificação sintática JavaScript e da inspeção visual nos dois níveis de opacidade.
