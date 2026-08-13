# WebXR — seleção sem recoloração e legibilidade

Data: 2026-08-12

## Seleção anatômica

- Durante uma sessão XR, selecionar uma estrutura mantém cor, emissão e acabamento anatômicos originais.
- A estrutura continua selecionada logicamente: foco, isolamento, visibilidade, opacidade e medição permanecem disponíveis.
- Ao encerrar o XR, o realce visual verde do desktop é restaurado para a estrutura ainda selecionada.

## Interface espacial

- Tablet principal ampliado de `0,46 × 0,575 m` para `0,58 × 0,725 m`.
- Abas reorganizadas de uma linha comprimida para grade de quatro colunas e duas linhas.
- Tipografia de status, abas, ações e instruções ampliada e escurecida.
- Fundos inativos ficaram mais opacos para aumentar contraste no passthrough.
- Painel RM/RGB ampliado de `0,38 × 0,443 m` para `0,50 × 0,583 m`.
- Molduras e alças foram redimensionadas proporcionalmente, mantendo interação por toque e pinça.

## Validação

- Sintaxe JavaScript validada com `node --check`.
- Testes focados do viewer, webapp e launcher Quest: **87 aprovados**.
- Build XR: `20260812-44`.
