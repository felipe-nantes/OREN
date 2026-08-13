# WebXR — estabilidade do fígado e painéis RGB

Data: 2026-08-12

## Mudanças

- A sessão XR congela transições pendentes e mantém um estado explícito de visibilidade por estrutura.
- Um verificador leve, executado a cada 180 ms, restaura somente alterações involuntárias de `visible`, `material.visible`, opacidade e frustum culling. Comandos manuais de exibir/ocultar continuam autorizados e atualizam o estado esperado.
- Planos de corte residuais do visualizador desktop são desativados ao entrar em XR e restaurados ao sair.
- A resolução efetiva dos canvases do tablet e do painel 2D foi aumentada em 1,5×.
- O framebuffer XR passou de 0,78 para 0,86. A foveação usa 0,55 no modo de qualidade e volta a 1 somente quando o monitor de desempenho aciona o modo de estabilidade.
- Foi adicionada a aba **Painéis RGB**, com navegação anterior, seguinte, primeiro painel e reposicionamento do painel espacial.
- Os PNGs são publicados por uma rota restrita ao padrão determinístico do caso; caminhos arbitrários e arquivos não autorizados retornam 404.

## Segurança e compatibilidade

- Nenhuma alteração foi feita na segmentação, volumetria ou inferência.
- O visualizador desktop mantém o comportamento existente.
- A rota RGB somente lê `case/panels/medgemma_liver_screening_panel_???_of_???.png`.
- O catálogo inclui SHA-256 para auditoria.

## Validação

- `node --check viewer/xr.js`
- `node --check viewer/app.js`
- `pytest tests/test_viewer_xr.py tests/test_webapp.py -q`: **85 passed**.

Ainda é necessária a verificação visual final no Meta Quest 3S, pois estabilidade de tracking, composição do navegador e qualidade óptica não podem ser reproduzidas integralmente pelos testes desktop.

## Correção de redirecionamento HTTP

Após o primeiro deploy, o atalho HTTP `:8082/quest` criava a sessão, mas o backend gerava por padrão um destino HTTPS em `:8443`. Como esse listener não fazia parte do fluxo sem certificado, a tela de abertura aparecia e em seguida o navegador informava que o site estava indisponível.

O backend agora conserva a origem não local que efetivamente recebeu a criação da sessão. Assim, uma chamada originada em `http://192.168.15.8:8082` gera um visualizador nessa mesma origem; HTTPS continua sendo preservado quando a chamada realmente chega por HTTPS. A variável `OREN_QUEST_BASE_URL` permanece com precedência quando configurada explicitamente.
