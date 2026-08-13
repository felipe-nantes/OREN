# Oclusão sólida dos segmentos de Couinaud

## Problema

No preset **Segmentos**, Couinaud I–VIII usavam opacidade `0,95`. Além disso, a regra genérica de materiais tratava segmentos como sobreposições transparentes e desativava a escrita no buffer de profundidade.

Consequências visuais:

- vasos internos apareciam através do parênquima segmentar;
- segmentos posteriores podiam ser vistos através dos anteriores;
- a composição parecia translúcida mesmo sem ajuste manual do revisor.

## Correção

- Segmentos passaram a ser superfícies sólidas, assim como o fígado completo.
- A opacidade padrão no preset Segmentos passou para `1,0`.
- Com opacidade total, `depthWrite` permanece ativo e estruturas posteriores são ocluídas.
- `depthTest` continua ativo em vasos e demais estruturas.
- A transparência segmentar somente é habilitada quando o revisor reduz manualmente a barra de opacidade do segmento.

## Compatibilidade

- Cores próprias de Couinaud I–VIII foram preservadas.
- Veias externamente visíveis continuam aparecendo.
- Seleção, sincronização 2D/3D, corte e régua permanecem funcionais.
- Nenhuma máscara ou segmentação foi modificada.

## Validação

Caso `c2424a1dd2e1`:

- preset Segmentos ativado com I–VIII em opacidade `1,0`;
- ausência de erros no console;
- oclusão visual confirmada;
- **130 testes aprovados**.

Captura:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_segments_solid_occlusion_job_c2424a1dd2e1.png`
