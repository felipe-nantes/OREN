# Fase 2 — Extensão realista para estruturas anatômicas

Data: 2026-08-10
Estado: implementada e validada no caso real `c2424a1dd2e1`

## Composição visual

O preset **Tecido realista** passou a preservar uma linguagem de cores por estrutura:

- fígado: vermelho-acastanhado com variação tonal discreta;
- veia porta/esplênica: ciano;
- veia cava inferior: azul;
- vesícula biliar: verde;
- região candidata automática: âmbar;
- região que alimentou a classificação: ciano, disponível sob demanda;
- lesão, quando existir no manifesto: cor própria da lesão.

As estruturas internas usam sobreposição anatômica controlada para continuarem visíveis através do fígado. Isso é uma ferramenta de revisão, não uma simulação de tecido exposto.

## Decisão de legibilidade

A região classificada pode ocupar quase todo o fígado. Exibi-la automaticamente cobriu a superfície realista e prejudicou a leitura das demais estruturas durante a primeira validação visual. Por isso:

- seu material e sua cor foram atualizados;
- ela permanece disponível pelo controle individual e pelo preset Triagem;
- ela fica desmarcada na abertura do modo Tecido realista.

Assim, a cena inicial mantém fígado, vasos, vesícula e candidato legíveis sem perder a camada de auditoria.

## Segurança e validação

- Materiais originais, profundidade e ordem de renderização são restaurados ao trocar de preset.
- Nenhuma máscara, classificação ou inferência foi modificada.
- 81 testes de webapp/presets aprovados e 4/4 testes focados após o refinamento visual.
- Captura aprovada tecnicamente:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_realistic_anatomical_overlays_job_c2424a1dd2e1_v2.png`.
