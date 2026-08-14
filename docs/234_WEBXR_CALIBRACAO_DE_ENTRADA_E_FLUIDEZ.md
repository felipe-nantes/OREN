# WebXR — calibração de entrada, fonte e fluidez

## Objetivo

Tornar a entrada no visualizador do Meta Quest previsível para pessoas sentadas
ou em pé, clarear a interface Emerald Glass e reduzir trabalho gráfico durante
os primeiros segundos da sessão.

## Decisões implementadas

### Tipografia

A interface espacial utiliza a pilha local `Roboto`, `Noto Sans`,
`Helvetica Neue`, `Arial`, `sans-serif`. Roboto/Noto são apropriadas ao Quest e
a ausência de download de webfont elimina atraso, troca tardia de fonte e uma
dependência de rede. Pesos 600–700 foram mantidos nos controles clínicos.

### Paleta

- vidro base elevado de verde quase preto para esmeralda médio;
- controles inativos e alças receberam luminância adicional;
- textos principais continuam próximos ao branco para contraste;
- bordas verdes preservam distinção entre repouso, hover e seleção;
- o fundo da RM continua preto para não alterar sua leitura visual.

### Calibração pelo headset

Após `renderer.xr.setSession`, o OREN mantém anatomia e painéis ocultos por oito
frames válidos. A posição e a direção horizontal da cabeça são suavizadas e
usadas para posicionar:

- fígado à frente e discretamente abaixo do olhar;
- tablet à esquerda;
- painel RM/RGB à direita;
- saída acima do campo central.

A altura vem do `local-floor`, acomodando uso sentado ou em pé. Um fallback
limitado a 1,5 s impede que uma pose inválida deixe a interface presa.

### Fluidez

- escala das texturas de UI reduzida de 1,50 para 1,25, ainda acima da resolução
  lógica dos painéis;
- entrada começa no perfil de estabilidade e foveação 0,9;
- detalhes auxiliares das mãos ficam reduzidos no aquecimento de 1,4 s;
- o perfil de qualidade só retorna após o p95 de frame time cumprir o gate;
- a calibração aplica transformações diretamente e redesenha o painel grande
  uma única vez;
- persistência síncrona de pose a cada segundo foi removida do loop XR.

## Compatibilidade

Gestos, medição, opacidade, cortes, seleção, RGB, revisão, saída e autoridade da
geometria médica não foram alterados. Poses absolutas antigas não são aplicadas
automaticamente na entrada, pois poderiam posicionar o modelo fora do campo de
visão em outra cadeira, sala ou altura de usuário.

## Validação

- sintaxe dos módulos JavaScript;
- testes estruturais WebXR;
- suíte integrada do visualizador e webapp;
- reconstrução e health check do Docker;
- verificação dos assets versionados por HTTP e HTTPS.
