# Fase 2 — Modo de tecido hepático realista

Data: 2026-08-10
Estado: implementado como modo reversível e validado visualmente

## Objetivo

Fazer a superfície do fígado virtual se aproximar visualmente de tecido hepático, sem modificar a máscara, a geometria aprovada, a classificação ou qualquer etapa de inferência.

## Implementação

Foi acrescentado o preset **Tecido realista**. Ele utiliza somente a malha hepática já presente no manifesto e aplica:

- paleta vermelho-acastanhada compatível com a leitura visual macroscópica do fígado;
- variação tonal procedural, determinística e discreta entre vértices;
- material fisicamente baseado com maior rugosidade;
- brilho superficial úmido moderado, sem aparência de plástico;
- iluminação ambiental reduzida para preservar relevo e profundidade;
- opacidade quase sólida;
- ocultação das sobreposições de triagem nesse modo.

A textura é estritamente de apresentação. Ela não representa perfusão, fibrose, gordura, tumor ou característica histológica específica do paciente.

## Segurança e reversibilidade

- O material original de cada estrutura é armazenado quando a malha é carregada.
- Ao selecionar outro preset, cor, rugosidade, brilho, emissão e cores de vértice são restaurados.
- O modo não contém `fetch`, não acessa máscaras e não cria estruturas anatômicas.
- O backend autoriza somente o identificador `realistic` e registra o modo na revisão humana.
- O comportamento anterior continua disponível nos presets Superfície, Anatomia interna e Triagem.

## Validação

- suíte combinada: **102 testes aprovados**;
- ajuste visual final: 4/4 testes focados aprovados;
- sintaxe JavaScript validada;
- caso multifásico real `296732bff897` renderizado sem falhas;
- contorno shadow aprovado permaneceu inalterado;
- captura final:
  `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_preset_realistic_liver_job_296732bff897_v2.png`.

## Decisão sobre tornar o modo fixo

O modo permanece selecionável nesta fase. Torná-lo padrão deve ocorrer somente depois da aprovação visual humana em mais de um formato de fígado, pois uma aparência agradável não pode esconder irregularidades de segmentação. A recomendação é revisar uma pequena galeria heterogênea e, se aprovada, definir `realistic` como preset inicial sem remover os demais modos de auditoria.
