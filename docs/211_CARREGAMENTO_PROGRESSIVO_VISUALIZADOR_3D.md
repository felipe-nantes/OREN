# Carregamento progressivo do visualizador 3D

## Objetivo

Reduzir o tempo de tela vazia e o pico de requisições do visualizador sem simplificar malhas, reduzir qualidade ou alterar qualquer resultado do pipeline.

## Estratégia implementada

1. O manifesto é carregado e validado.
2. A malha hepática é localizada deterministicamente e baixada primeiro.
3. O fígado sólido já é renderizado enquanto a anatomia complementar continua carregando.
4. Vasos, vesícula, candidato e lesão têm prioridade sobre camadas de auditoria e segmentos ocultos no padrão.
5. As malhas restantes são baixadas com concorrência limitada a três requisições.
6. A cena completa substitui atomicamente a prévia do fígado.
7. As referências PNG deixaram de ser pré-carregadas em massa: somente o plano 2D atualmente exibido é solicitado ao backend.

Nenhum STL foi simplificado e todos os 14 componentes do caso completo continuam disponíveis.

## Segurança de revisão

- Durante o carregamento parcial, **Concluir revisão técnica** e **Solicitar revisão** ficam desativados.
- O endpoint de aprovação também é protegido pela variável de prontidão, evitando submissão programática antes da cena completa.
- Falha de qualquer malha mantém o caso como não pronto e não permite uma revisão sobre conjunto parcial.
- Arrastar um pacote offline completo continua usando o comportamento local anterior.

## Observabilidade

O painel mostra:

- fase atual;
- estruturas concluídas/total;
- barra de progresso.

O estado técnico exposto para diagnóstico contém fase, total, primeira renderização hepática e conclusão, sem dados clínicos ou PHI.

## Validação real

Caso `c2424a1dd2e1`, com 14 malhas:

- a etapa intermediária mostrou `1/14 estruturas` com o fígado já presente;
- os botões de revisão estavam desabilitados em `1/14`;
- a cena final apresentou Couinaud I–VIII e todas as estruturas autorizadas;
- os botões foram habilitados somente após `14/14`;
- o log HTTP da nova abertura mostrou apenas `mri_reference_axial_027_of_054.png`, em vez de pré-carregar os 54 axiais, o coronal e o sagital;
- padrão sólido e opacidade `1,0` foram preservados.

Captura da etapa intermediária:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_progressive_liver_first_job_c2424a1dd2e1.png`

## Testes

- sintaxe JavaScript aprovada;
- contrato de prioridade hepática, concorrência limitada e referências sob demanda;
- proteção de aprovação durante carregamento parcial;
- suíte integrada: **127 testes aprovados**.

## Correção de responsividade

A primeira implementação ainda reconstruía as 14 malhas simultaneamente ao finalizar o download. Como parsing STL, união de vértices e cálculo de normais ocorriam na thread gráfica, a animação podia aparentar travamento.

A finalização passou a:

- reutilizar a malha hepática já renderizada;
- preparar uma malha complementar por vez;
- liberar um frame de animação antes e depois de cada preparação;
- finalizar controles e metadados sem limpar ou reconstruir a cena;
- evitar uma segunda animação de entrada.

Validação no navegador: a vista **Anterior** respondeu durante o carregamento, enquanto o progresso avançou de `1/14` para `9/14`, completando depois `14/14`, sem erros no console.

Captura da interação durante a montagem:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_nonblocking_animation_progress_job_c2424a1dd2e1.png`

## Escopo metodológico

A mudança atua somente na transferência e apresentação de artefatos já produzidos. Segmentação, classificação, MedGemma, máscaras, relatório e métricas permanecem imutáveis.
