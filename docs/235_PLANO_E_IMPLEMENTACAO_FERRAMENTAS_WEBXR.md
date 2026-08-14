# Plano e implementação — ferramentas WebXR do OREN

## Objetivo

Corrigir e tornar previsíveis, no Meta Quest, as funções de medição, corte,
malha técnica, navegação de estruturas, referências de RM e sincronização
2D/3D. O escopo continua sendo pesquisa com revisão humana; as medidas
descrevem a segmentação e não comprovam acurácia anatômica clínica.

## Sequência executada

1. Congelar o baseline e mapear os contratos entre `viewer/app.js`,
   `viewer/xr.js`, os manifestos do visualizador e a geração das referências.
2. Unificar medições e anotações no sistema LPS em milímetros do modelo.
3. Tornar o plano de corte local ao modelo e transformá-lo para o espaço XR.
4. Limitar a malha técnica ao orçamento seguro do headset.
5. Corrigir a seleção de estruturas visíveis e ocultas.
6. Escolher planos axial, coronal e sagital que intersectem a região candidata
   segmentada, quando ela existir.
7. Tornar a sincronização 2D/3D transacional e restaurar o corte anterior.
8. Validar por testes, sintaxe JavaScript, navegador real e Docker.

## Alterações implementadas

### Medição

- `measurementGroup` passou a ser filho do grupo anatômico. Assim, pontos,
  linhas e rótulos seguem translação, rotação e escala no XR.
- O ponto tocado é convertido do espaço mundial para LPS somente uma vez.
- Interseções ocultadas pelo clipping deixam de ser aceitas como pontos de
  medição.
- As dimensões LR/AP/SI usam `metrics.dimensions_mm`, derivado da máscara
  binária fonte, quando disponível. A caixa da malha é apenas fallback
  explicitamente aproximado.
- A cobertura de interação inclui todas as malhas carregadas e visíveis; uma
  estrutura oculta pode ser selecionada pela aba Estruturas e reativada.

### Planos de corte

- O plano canônico é calculado nas coordenadas LPS locais da anatomia.
- A cada quadro XR, o plano é transformado pela matriz mundial atual do grupo.
  Mover, girar ou redimensionar o fígado não separa mais a anatomia do corte.
- Posições destrutivas são limitadas a 5%/95%, conforme a direção do plano,
  para evitar a remoção visual de 100% da anatomia.
- Alterar coeficientes não recompila materiais; `needsUpdate` é usado somente
  quando o clipping é ligado ou desligado.

### Malha técnica

- No desktop, o comportamento de inspeção global é preservado.
- No XR, somente uma estrutura por vez recebe wireframe: a selecionada ou a
  primeira estrutura visível dentro do orçamento.
- O limite é 75.000 triângulos. Se nenhuma malha segura estiver disponível, a
  função recusa a ativação e apresenta uma explicação, em vez de travar a
  sessão.
- O LOD visual nunca é promovido a autoridade de medição.

### Estruturas

- “Próxima estrutura” usa ordem determinística e sincroniza o cursor com a
  seleção atual.
- Estruturas ocultas podem ser selecionadas sem alterar silenciosamente a
  composição.
- “Enquadrar seleção” torna visível uma estrutura oculta antes de focá-la.
- Visibilidade, opacidade, isolamento, restauração e wireframe são
  reconciliados após cada ação.
- A seleção no XR continua sem recolorir a anatomia.

### RM 2D e região candidata

- Quando existe máscara candidata automática válida, o plano axial padrão é o
  de maior seção candidata.
- Os planos coronal e sagital passam pelo maior corte da mesma região, em vez
  de depender exclusivamente do centroide do fígado.
- Cada frame registra `candidate_visible_in_plane`, base da escolha e índice
  padrão. Se não há candidato, permanece o comportamento seguro de centro do
  fígado, sem inventar lesão.
- O contorno continua sendo evidência auxiliar não confirmada, sem PHI e sem
  uso diagnóstico.

### Sincronização 2D/3D

- Antes de sincronizar, o estado manual do corte é salvo.
- A sincronização valida orientação e posição LPS antes de alterar a cena.
- Ao desligar, eixo, posição, inversão e estado ligado/desligado anteriores são
  restaurados.
- O plano sincronizado usa o mesmo mecanismo transformável do XR; mover o
  modelo não faz o fígado desaparecer.
- Quando um frame fica no extremo destrutivo, o estado informa que o limite
  seguro foi aplicado.

### Inicialização Docker

- `tools/start_argos_docker.ps1 -SkipMedGemmaStart` agora aceita
  `backend=desligado` como estado intencional. Antes, o OREN e o proxy ficavam
  saudáveis, mas o script aguardava inutilmente por até 15 minutos.

## Gates executados

- Baseline anterior: 111 testes relevantes aprovados.
- Após as alterações: 135 testes relevantes aprovados.
- `node --check viewer/app.js`: aprovado.
- `node --check viewer/xr.js`: aprovado.
- Docker: `argos`, `proxy` e `neo4j` saudáveis.
- Artefatos corrigidos servidos pelo container: confirmado por HTTP.
- Caso real `c2424a1dd2e1`: manifesto e malhas carregados no navegador.
- Corte axial/coronal/sagital, inversão e visibilidade de candidato: sem erros
  de console.
- Sincronização: estado anterior restaurado corretamente.
- Limites destrutivos: `0% invertido -> 5%` e `100% normal -> 95%`.
- Dimensões da região candidata exibidas em LR/AP/SI.

## Gate que depende do Meta Quest físico

O navegador desktop não consegue criar uma sessão `immersive-ar`. A aprovação
final no headset deve confirmar:

1. duas pinças em regiões opostas produzem uma distância coerente em mm;
2. mover/girar/escalar o fígado com corte ativo não o faz desaparecer;
3. inverter e mover os três eixos preserva contexto anatômico;
4. malha técnica liga em menos de um segundo e mantém a sessão responsiva;
5. todas as estruturas podem ser percorridas, ocultadas, reexibidas e focadas;
6. axial/coronal/sagital mostram o contorno âmbar quando o candidato intersecta
   o plano;
7. ligar/desligar sincronização não exige sair e entrar novamente no XR;
8. não há perda do fígado ao pausar e retomar a sessão.

## Critério de conclusão

A implementação de software está concluída quando os testes e o smoke Docker
passam. A validação WebXR é concluída somente após o checklist físico acima,
pois fluidez, rastreamento das mãos e sessão imersiva não podem ser certificados
por emulação desktop.
