# Review WebXR — estabilidade, fluidez e identidade OREN

## Escopo

Revisão do caminho WebXR usado no Meta Quest 3S, cobrindo entrada e saída da
sessão, preservação do fígado, mãos, raycast, painéis espaciais e linguagem visual.

## Problemas encontrados

1. A estética anterior acumulava grade, retículas, emissão, ciano e alto contraste.
   O resultado se afastava do site OREN e aumentava a carga visual no mixed reality.
2. Molduras dos painéis usavam `MeshPhysicalMaterial` com propriedades que não
   acrescentavam informação clínica e custavam mais que uma superfície simples.
3. A resolução XR e a frequência dos detalhes cosméticos ainda priorizavam
   acabamento em vez de estabilidade no Quest 3S.
4. O encerramento normal restaurava o desktop, mas uma falha entre
   `requestSession()` e `setSession()` podia deixar o modelo, a câmera ou o orbit
   parcialmente no estado XR.
5. Pausa e retomada da sessão pelo Horizon OS não tinham um tratamento explícito.
6. Transições desktop e frustum culling podiam competir com a apresentação XR.

## Correções aplicadas

- Interface redesenhada com glassmorphism claro, branco quente, cinzas verdes e
  verde OREN usado somente como sinal de estado ou seleção.
- Retirados neon, ciano dominante, grade técnica, cantos HUD e numeração decorativa.
- Tipografia, hierarquia, cartões e espaçamento aproximados da linguagem do site.
- `MeshPhysicalMaterial` das molduras substituído por `MeshStandardMaterial` opaco
  simples, sem emissão, transmissão ou brilho caro.
- Escala do framebuffer ajustada para `0.78`; foveation máxima preservada.
- Gestos continuam a cada frame; esqueleto cosmético roda a 25 Hz e foco a 31 Hz.
- Raycast anatômico é interrompido assim que tablet, alça ou saída são atingidos.
- Juntas das mãos permanecem instanciadas e o perfil adaptativo pode ocultar apenas
  detalhes cosméticos quando o p95 ultrapassa o orçamento.
- Entrada/saída agora usa limpeza idempotente: falha parcial, saída normal ou perda
  da sessão restauram parentes, transforms, câmera, orbit e estado de apresentação.
- `visibilitychange` revalida malhas e estado de apresentação ao voltar para a RA.
- Animações desktop são consolidadas antes da sessão e `frustumCulled` é restaurado
  depois da saída.

## O que permanece deliberadamente inalterado

- Contrato do backend, jobs e aprovação.
- Autoridade das máscaras e métricas de volumetria.
- Presets, clipping, medição, referências 2D e revisão humana.
- LOD protegido por gate de fidelidade.
- WebXR como cliente sem instalação.

## Gate de aceite

- sintaxe JavaScript válida;
- suíte de regressão WebXR, viewer, Quest HTTP e webapp aprovada;
- assets novos servidos com cache versionado;
- entrada e saída restauram o desktop mesmo após falha parcial;
- teste físico no Quest confirma ausência de piscar, p95 estável e legibilidade.

O último item depende de observação no headset; os demais são automatizados.
