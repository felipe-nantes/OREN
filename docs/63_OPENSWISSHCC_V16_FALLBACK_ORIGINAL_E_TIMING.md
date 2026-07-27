# OpenSwissHCC v16 — fallback de fases originais e plano temporal

Data: 2026-07-16  
Estado: implementação técnica concluída; revisão humana da galeria fallback v2 pendente  
Uso: pesquisa, com revisão humana obrigatória  
Holdout: fechado

## 1. Ponto de partida

A galeria principal v16 de stacks focais foi aprovada pelo revisor `jm`. A revisão assinada está em:

`casos/qualification/openswisshcc_v1/prepared/development_reviews_v16/candidate_volume_pilot10_review.json`

Assinatura da revisão: `7400280c660f927b9ce001de5240b8204ba98424142aa107e0c173ea6d46cff9`.

Três dos 87 casos de desenvolvimento não possuíam alinhamento arterial/tardio publicado porque o gate cego de Dice mínimo 0,80 foi reprovado:

- `anon-openswiss-40c09ebcf8178f92`;
- `anon-openswiss-7bb936ce9f21d461`;
- `anon-openswiss-c83a32179466321d`.

O limiar não foi reduzido e nenhum alinhamento reprovado foi reaproveitado.

## 2. Endurecimento do scorer

O scorer v16 agora:

- vincula cada diretório de saída a um único protocolo e bundle por `run_context.json`;
- recusa misturar predições de protocolos diferentes;
- revalida, ao reutilizar cache, o número do candidato, hash do manifesto, quantidade de frames, flag de fallback, hash da consulta, schema da resposta, probabilidades e log-odds;
- recalcula a agregação antes de aceitar resultado reutilizado;
- declara que o gate de 180 segundos do scorer cobre apenas o scoring de stacks previamente preparados;
- mantém `end_to_end_180_seconds_proven=false` até o piloto ponta a ponta.

Testes focados: 10 aprovados.

## 3. Plano temporal congelado

Artefato:

`casos/qualification/openswisshcc_v1/protocols/v16_candidate_volume_timing_selection.json`

Assinatura: `19ee2822d7eff5d5fd0ca0dea33d9f53ae87a898c3611cab83bd67d42c8622cf`.

O plano registra:

- 87 casos técnicos de origem;
- 84 casos com alinhamento publicado;
- 3 casos sem alinhamento, preservados na auditoria e nunca excluídos silenciosamente;
- seleção determinística do pior tempo técnico conhecido para os cenários fallback, 1, 3 e 5 candidatos;
- seleção sem uso de labels;
- desenvolvimento classificado como exploratório devido ao incidente de visibilidade de labels já descrito em `docs/62_OPENSWISSHCC_V16_INCIDENTE_DE_LABELS_E_GATE_DE_ALINHAMENTO.md`;
- holdout fechado.

Testes focados: 4 aprovados.

## 4. Fallback de fases originais

Quando não existe registro publicado, o gerador usa:

- T1 venoso como geometria de referência;
- centro físico LPS do candidato do localizador ou do centro hepático no fallback;
- T1 arterial original e T1 tardio original amostrados nesse mesmo centro físico;
- T1 nativo, T2, DWI trace e ADC nas geometrias originais;
- nenhuma máscara de lesão do dataset;
- nenhum contorno nos frames enviados ao modelo.

A fase arterial é escolhida deterministicamente:

1. `t1_arterial`, quando disponível;
2. `t1_arterial_ttc_3`, quando disponível;
3. maior índice `t1_arterial_ttc_N` válido.

O manifesto diferencia explicitamente:

- `registered_to_venous`;
- `original_unregistered_physical_center`.

O fallback não é acionado quando existe diretório de registro parcial ou manifesto/arquivo adulterado. Nesses casos, o pipeline aborta.

O baseline registrado permaneceu reproduzível: mesmos papéis e 29 frames no cenário completo.

Testes focados do gerador/fallback/scorer: 27 aprovados. Suíte integrada v16 anterior à correção de caminho: 31 aprovados.

## 5. Incidente de limite de caminho no Windows

A primeira publicação da galeria fallback produziu nomes longos como `t1_arterial_original_unregistered`. O caminho absoluto chegou a 261 caracteres. O Windows listava os PNGs, mas o `pathlib` usado pelo scorer não os reconhecia de forma confiável.

O validador independente bloqueou a galeria antes de qualquer aprovação ou inferência. O artefato foi preservado, renomeado como:

`development_review_gallery_v16_candidate_volume_unregistered_fallback3_v1_INVALID_windows_path_length`

Correção:

- o papel do frame foi encurtado para `t1_arterial_original` e `t1_delayed_original`;
- a condição não registrada permanece explícita em `alignment_mode=original_unregistered_physical_center`;
- foi acrescentado teste que limita o nome de frame fallback a 48 caracteres;
- a galeria foi regenerada do zero como v2.

## 6. Galeria fallback v2 válida

Diretório:

`casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v16_candidate_volume_unregistered_fallback3_v2`

Resultados técnicos:

- casos: 3;
- stacks: 6;
- frames: 174;
- 29 frames por stack;
- arquivos totais: 185;
- maior caminho absoluto: 248 caracteres;
- assinatura da galeria: `a952a53964fd931a08ef824cb0f095946f1664679dd6e14eccf0121136a61445`;
- SHA-256 do manifesto da coorte: `d4ecdf7980d46be8e59625aeaeb9b6c4f097379f757fc2bf2b222bd42ae5b5cd`;
- todos os stacks passaram pelo validador que será usado pelo scorer;
- inferência não executada;
- labels não lidos pelo processo;
- holdout fechado;
- revisão técnica: pendente.

Distribuição:

- `anon-openswiss-40c09ebcf8178f92`: 1 stack;
- `anon-openswiss-7bb936ce9f21d461`: 2 stacks;
- `anon-openswiss-c83a32179466321d`: 3 stacks.

## 7. Gate humano pendente

O revisor deve verificar, em cada candidato:

1. se o fígado e o ROI permanecem visíveis em todos os grupos;
2. se início, centro e fim mostram continuidade plausível;
3. se arterial e tardio originais ainda representam região anatômica comparável ao centro venoso;
4. se não há corte abrupto, estrutura fora do FOV ou crop deslocado;
5. se contraste de T1, T2, DWI e ADC permite leitura;
6. se não há PHI, texto clínico, contorno de candidato ou máscara de lesão.

O revisor não deve julgar diagnóstico nem tentar inferir o ground truth nesta galeria. A pergunta é exclusivamente se os stacks são tecnicamente utilizáveis como entrada do leitor focal.

## 8. Próximos passos após aprovação

1. registrar revisão humana assinada da galeria fallback v2;
2. congelar o protocolo de scoring dos 84 casos registrados mais os 3 fallback, sem misturar hashes;
3. executar piloto temporal fresco nos cenários fallback, 1, 3 e 5 candidatos;
4. medir renderização, scoring e tempo ponta a ponta;
5. exigir no máximo 180 segundos por caso sem resultado parcial;
6. somente depois executar os 87 casos de desenvolvimento;
7. avaliar desenvolvimento como exploratório;
8. manter o holdout fechado até a configuração final.

Nenhum ganho de acurácia é declarado nesta etapa.

## 9. Validação final de código

A suíte completa do ARGOS foi executada após a correção da galeria v2:

- `632 passed`;
- `0 failed`;
- `389 warnings` de depreciação em dependências já existentes;
- duração reportada pelo pytest: `35.75 s`.

Os seis backups temporários autorizados foram mantidos durante toda a implementação e removidos somente depois dessa aprovação integral.