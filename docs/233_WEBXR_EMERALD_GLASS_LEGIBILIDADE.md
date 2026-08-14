# WebXR — Emerald Glass e legibilidade

## Objetivo

Eliminar as superfícies brancas do visualizador OREN no Meta Quest, preservar
a identidade verde da aplicação e aumentar a leitura dos controles em realidade
mista sem alterar o contrato gestual ou as funções já existentes.

## Alterações

- tablet principal, abas, botões, faixa de estado e alças usam vidro esmeralda
  escuro de alta opacidade;
- títulos e ações usam texto branco-esverdeado de alto contraste;
- estados ativo, hover e pinça usam bordas verdes luminosas distinguíveis;
- painel de referência RM/RGB recebeu o mesmo tratamento visual;
- fundo das imagens permanece preto para preservar o contraste radiológico;
- botão de saída usa verde no estado normal e cobre somente durante a confirmação;
- molduras quadradas foram substituídas por geometria extrudada com cantos e
  chanfros arredondados;
- a URL de `xr.js` foi versionada para impedir cache do tema anterior no Quest.

## Compatibilidade

Nenhuma ação, hitbox, posição, dimensão física, regra de pinça, movimentação,
medição, seleção ou saída foi alterada. A mudança é de apresentação e geometria
decorativa da moldura.

## Validação

- teste estrutural WebXR atualizado para exigir a paleta escura e a moldura
  arredondada;
- sintaxe JavaScript e suíte do visualizador executadas;
- imagem Docker reconstruída para publicar os assets atualizados;
- HTTP desktop e HTTPS Quest verificados após a atualização.
