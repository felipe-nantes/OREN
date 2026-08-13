# OREN — evolução da realidade aumentada e interação manual

## Objetivo

Levar ao Meta Quest as funções relevantes do visualizador e do fluxo de revisão
do webapp, preservando o modo desktop, a pesquisa com revisão humana e o mixed
reality já aprovado.

## Execução em partes

### Parte 1 — saída e fundação da interação manual — implementada

- botão espacial permanente `Voltar ao webapp`;
- saída limpa da sessão WebXR antes da navegação para `/`;
- gesto de saída protegido por pinça sustentada durante 900 ms;
- feedback progressivo no próprio botão, evitando saída acidental;
- suavização do raio do indicador para reduzir tremor;
- suavização de translação, rotação e escala do fígado;
- debounce de pinça para impedir ações duplicadas;
- feedback de foco com cores distintas para menu, anatomia e saída;
- controles físicos preservados como alternativa.

#### Refinamento de fidelidade das mãos

- apontamento primário pelo `targetRaySpace` nativo do Quest;
- fallback que combina posição dos olhos e ponta do indicador;
- pinça própria baseada na distância física polegar–indicador;
- limiar adaptado ao tamanho rastreado da mão;
- histerese independente para fechar e soltar a pinça;
- confirmação temporal curta para remover falsos acionamentos;
- fusão com o evento de pinça nativo sem duplicar comandos;
- toque direto no painel quando a mão está próxima;
- estabilidade mínima do foco antes de acionar botões;
- representação dos ossos dos dedos e indicador visual de prontidão da pinça;
- telemetria local da fonte do raio, foco e estado de pinça.

### Parte 2 — tablet virtual espacial — implementada

- o painel de comandos agora possui corpo, moldura e alça próprios, como um
  tablet virtual independente do fígado;
- toque direto com a ponta do indicador aciona abas e botões sem exigir pinça;
- estabilização temporal de 38 ms impede toques acidentais por passagem do dedo;
- cursor circular mostra exatamente o ponto de contato com a tela;
- uma pinça na alça inferior segura o tablet para translação e rotação;
- soltar a pinça mantém o tablet na nova posição sem alterar o fígado;
- pinças fora do tablet preservam a manipulação anatômica anterior;
- botão `Recentrar tablet` recupera a posição segura inicial;
- alça, foco, toque e estado de transporte possuem feedback visual próprio;
- telemetria local informa toque ativo e qual mão está transportando o tablet.

#### Contrato gestual

| Gesto | Região | Resultado |
|---|---|---|
| encostar indicador | tela do tablet | aciona o controle tocado |
| pinça | alça inferior | segura e reposiciona o tablet |
| soltar pinça | durante transporte | fixa o tablet na nova posição |
| pinça | fígado/estrutura | move a anatomia |
| duas pinças | fígado/estrutura | gira e muda a escala anatômica |
| botão `Recentrar tablet` | aba Modelo | restaura o painel no campo de visão |

#### Identidade visual OREN Glass

- linguagem visual alinhada ao site institucional OREN: clara, silenciosa e clínica;
- vidro branco translúcido em camadas, com profundidade preservada no mixed reality;
- tons verdes leves como sinal de estado, sem brilho neon ou excesso de informação;
- núcleo circular OREN simplificado e tipografia limpa, sem retículas decorativas;
- cartões grandes com cantos suaves e feedback distinto para repouso, foco e ativação;
- molduras claras de baixo custo gráfico, sem emissão ou materiais de transmissão;
- cursor verde sólido e discreto, legível sem cobrir o conteúdo selecionado;
- referência de RM e saída segura usam a mesma gramática visual; terracota fica
  reservada exclusivamente para a ação de saída.

#### Perfil de fluidez Meta Quest 3S

- resolução interna WebXR em `0.78`, preservando legibilidade do tablet e
  reduzindo o custo de preenchimento da GPU;
- foveated rendering máximo mantido durante a sessão;
- malhas LOD com gate de fidelidade continuam preferidas automaticamente no Quest;
- juntas das mãos consolidadas em `InstancedMesh`, reduzindo dezenas de draw calls
  para uma chamada por mão;
- esqueleto visual atualizado a 25 Hz, enquanto gesto, toque, pinça e movimento
  continuam sendo processados a cada frame;
- raycast de foco limitado a aproximadamente 31 Hz e interpolado entre consultas;
- raycast anatômico não é executado quando o cursor já atingiu tablet, alça ou saída;
- uploads da textura do tablet só acontecem após estabilidade do foco;
- p95 calculado em janelas espaçadas, eliminando ordenação de métricas em todo frame;
- modo automático `stability` oculta somente detalhes cosméticos das mãos quando o
  p95 ultrapassa 18 ms; toque, pinça, anatomia e tablet permanecem funcionais;
- qualidade completa retorna automaticamente quando o orçamento de quadro se recupera.

#### Estabilidade do fígado e painéis reposicionáveis

- transições desktop de escala, opacidade e visibilidade são consolidadas antes de
  o modelo entrar na árvore WebXR, impedindo que uma animação atrasada o oculte;
- durante a RA, mudanças de visibilidade solicitadas pelo usuário são aplicadas de
  forma atômica, sem quadros intermediários transparentes;
- `frustumCulled` é desativado apenas durante a sessão XR e restaurado na saída;
- câmera imersiva usa `near=0.01 m` e `far=20 m`, evitando que o fígado desapareça
  quando o usuário aproxima a cabeça; os valores desktop são restaurados na saída;
- a alça do tablet de controles foi transferida para a borda inferior;
- o painel de referência RM 2D recebeu moldura, alça inferior e movimento espacial
  independente por pinça;
- o botão `Recentrar painel 2D` restaura sua posição inicial de forma determinística.

### Parte 3 — paridade funcional com o webapp

- resultado da análise e relatório estruturado no ambiente espacial;
- volumetria e qualidade da reconstrução;
- lista completa de estruturas e controles individuais;
- referências 2D sincronizadas;
- medição, clipping, vistas, presets e marcadores;
- revisão humana e decisão técnica, sem automatizar o checklist;
- mensagens de erro e limitações acessíveis dentro da RA.

### Parte 4 — validação final

- testes de regressão desktop, Quest HTTP e WebXR;
- verificação no Meta Quest 3S com mãos, uma e duas pinças;
- avaliação de desempenho e estabilidade de quadros;
- revisão de ergonomia, legibilidade e prevenção de acionamento acidental;
- documentação operacional e aceite humano.

## Salvaguardas

- nenhuma função de RA transforma o resultado em diagnóstico;
- a saída da sessão remove o token da URL ao retornar ao webapp;
- a revisão clínica continua exigindo marcação humana explícita;
- falhas de WebXR não removem o visualizador desktop.
