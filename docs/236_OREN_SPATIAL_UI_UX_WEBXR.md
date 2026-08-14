# OREN Spatial — atualização UI/UX WebXR

## Estado

Implementado em 2026-08-14 como apresentação padrão do visualizador WebXR. A mudança é somente de interface, organização espacial e orçamento de renderização. Não altera segmentação, volumetria, medições, coordenadas LPS, malhas anatômicas, sincronização 2D/3D nem o contrato de revisão humana.

## Referências analisadas

A pasta local `C:\Users\profurg\Desktop\loucurasdamadrugada\uixvr viewer` continha três imagens e três vídeos. Foram absorvidos apenas princípios de design:

- modelo tridimensional como foco principal;
- painéis espaciais arredondados e reposicionáveis;
- separação clara entre imagem MPR e anatomia 3D;
- controles compactos próximos do contexto;
- transições discretas e manipulação direta pelas mãos.

Nenhum ativo visual externo foi copiado para o OREN.

## Implementação

### Linguagem visual

- tokens locais `XR_SPATIAL_THEME` para superfícies, bordas, texto e estados;
- superfícies grafite/esmeralda opacas o suficiente para leitura em mixed reality;
- tipografia local Roboto/Noto Sans, sem dependência de rede;
- cards contextuais, estados ativos e microcopy curta;
- `OREN SPATIAL` como identificação da nova organização.

### Tablet principal

- `createSpatialPanelV2()` é a implementação utilizada por padrão;
- as sete páginas continuam sendo `model`, `views`, `tools`, `structures`, `reference`, `rgb` e `review`;
- todos os identificadores de ação de `PANEL_PAGES` foram preservados;
- estrutura selecionada mostra nome, categoria e visibilidade no card contextual;
- ações exibem rótulo primário e dica operacional curta;
- perfil do paciente continua sem ações clínicas restritas.

### RM 2D e RGB

- continuam em painel independente e reposicionável;
- identificação MPR/RGB com contraste alto;
- imagem permanece dominante, sem efeitos sobre os pixels médicos;
- metadados e orientação operacional ficam em superfície separada;
- navegação, sincronização e recentralização mantêm os métodos existentes.

## Preservação funcional

O teste `test_uxvr_spatial_v2_preserves_every_existing_action_contract` protege todas as ações existentes:

- composições e volumetria;
- vistas e bookmarks;
- medição por dois pontos e dimensões 3D;
- malha técnica;
- ativação, posição, eixo e inversão de corte;
- seleção, foco, isolamento, visibilidade e opacidade de estruturas;
- RM axial, coronal e sagital;
- painéis RGB;
- checklist, decisão do candidato, aprovação e solicitação de revisão.

## Fluidez e orçamento do Quest 3S

- orçamento preservado em `13,9 ms` por frame;
- texturas de interface usam filtro linear sem mipmaps;
- o painel ignora redraws quando seu estado visual não mudou;
- o progresso do botão de saída é quantizado para evitar upload por microvariação;
- handles do tablet e do painel RM/RGB também possuem cache de estado;
- molduras tridimensionais usam material opaco, evitando blending desnecessário;
- não são usados `MeshPhysicalMaterial`, transmission, refração ou blur em tempo real;
- contadores de uploads são expostos em `window.__argosXR.getPerformance()`;
- no tier `stability`, somente bordas decorativas e detalhes auxiliares das mãos são ocultados;
- anatomia, painéis, medições, cortes e funções clínicas permanecem ativos;
- ao sair da sessão, a qualidade visual é restaurada para a próxima entrada.

## Cache busting

- módulo XR: `oren-20260814-spatial-v2-2`;
- link da sessão: `xr_build=20260814-spatial-v2-2`.

Isso impede o Meta Quest de reutilizar a versão anterior do JavaScript.

## Validação automatizada

Comando executado:

```powershell
.venv-win\Scripts\python.exe -m pytest -q `
  tests\test_viewer_xr.py `
  tests\test_viewer_presets.py `
  tests\test_viewer_artifacts.py `
  tests\test_webapp.py `
  tests\test_docker_integration.py `
  tests\test_segmentation_contract.py
```

Resultado: **138 testes aprovados**.

`node --check` também foi aprovado para `viewer/app.js` e `viewer/xr.js`.

A imagem `argos-runtime:local` foi reconstruída e os containers `argos`, `proxy` e `neo4j` ficaram saudáveis. A rota HTTPS do Quest respondeu `200`, e uma sessão real de teste retornou o IP LAN e o build `20260814-spatial-v2-2` corretamente.

## Refinamento glassmorphism neutro

A identidade visual foi amadurecida para uso clínico e institucional:

- superfícies de vidro grafite e cinza-neutro substituem grandes áreas verdes;
- o verde OREN fica restrito a seleção, confirmação, foco e estado ativo;
- bordas claras discretas definem a hierarquia sem aparência de painel de jogo;
- textos usam branco suave e cinza de alto contraste, com menos brilho emissivo;
- molduras físicas dos painéis usam acabamento grafite fosco;
- o efeito de vidro continua desenhado nas texturas Canvas, sem blur, refração ou materiais físicos caros em tempo real.

Esse refinamento é apenas visual: ações, gestos, medição, planos de corte, estruturas, RM 2D, painéis RGB e revisão permanecem com o mesmo contrato funcional.

## Gate físico no Meta Quest

Antes de considerar a interface visual definitivamente aprovada, verificar:

1. entrada calibrada e fígado estável no campo de visão;
2. leitura do tablet a aproximadamente 60–80 cm;
3. toque direto, pinça e movimentação pela barra inferior;
4. todas as sete páginas e seus estados ativos;
5. seleção de estrutura sem alteração indevida de cor;
6. medição, dimensões, corte e malha técnica;
7. RM 2D, RGB e sincronização 2D/3D;
8. perfil médico e perfil paciente;
9. fluidez com mãos, segmentos e painel 2D simultâneos;
10. saída e reentrada na sessão sem perda do modelo.

Durante o teste, `window.__argosXR.getPerformance()` permite consultar `p95_ms`, tier adaptativo e número de uploads das texturas dos painéis.
