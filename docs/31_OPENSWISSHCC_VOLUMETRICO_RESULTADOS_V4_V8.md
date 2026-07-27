# OpenSwissHCC — resultados volumétricos v4 a v8

## Estado metodológico

Este documento registra os experimentos de desenvolvimento executados com o
MedGemma 1.5 4B. O uso é exclusivamente de pesquisa, toda saída exige revisão
humana e o conjunto de holdout permanece fechado.

Meta de qualificação:

- sensibilidade >= 75%;
- especificidade >= 75%;
- tempo máximo de 180 segundos por caso;
- nenhum ground truth ou máscara de lesão durante a inferência.

## Painéis v4 aprovados

A revisão humana aprovou os 88 casos e 561 painéis volumétricos. O freeze prova
cobertura axial exata da máscara hepática e vincula cada painel ao SHA-256.

- review signature: `c759ea0d0b045b58e89b196030085e06d20193736d7b1f4220e042074fa6073d`
- experiment signature: `de7959446726aa36c0cce909e47b0566c48700daac75b6f03f8138c0a3e86d27`
- 68 casos multifásicos RGB;
- 19 casos com fallback venoso;
- 1 caso com fallback venoso de alto contraste.

As cores do painel multifásico codificam fases reais registradas. Elas não são
decoração, heatmap, máscara de lesão ou ground truth. Casos sem fases aptas não
devem ser coloridos artificialmente.

## v4 — classificação A/B/C contrabalançada

Execução técnica:

- 88/88 casos;
- 561/561 painéis;
- zero falhas e zero timeouts;
- média de 40,51 s, máximo de 56,28 s.

Resultado:

- sensibilidade: 100%;
- especificidade: 0%;
- todos os casos foram agregados como positivos;
- meta 75/75: reprovada.

As três rodadas do quadrado latino removeram viés de posição, mas produziram
probabilidades próximas de 1/3 e pouca separação semântica.

## v6 — MedSigLIP e fusão

Execução MedSigLIP:

- 88/88 casos e 561 painéis;
- zero falhas;
- média de 4,39 s, máximo de 14,31 s;
- somente scores; nenhuma decisão final.

Melhor fusão MedGemma/MedSigLIP:

- aparente: sensibilidade 61,54%, especificidade 59,18%;
- LOOCV: sensibilidade 58,97%, especificidade 59,18%;
- validação aninhada: mediana 46,15% / 51,02%;
- repetições aprovadas em 75/75: 0/50.

Conclusão: reprovada. O MedSigLIP pode continuar como localizador exploratório,
mas não há evidência para usá-lo como classificador final neste conjunto.

## v7 — frases clínicas pairwise por painel

Foram substituídas as letras A/B/C por duas comparações de frases clínicas
completas e espelhadas. O lote permaneceu cego e não emitiu decisão final.

Execução:

- 88/88 casos e 561/561 painéis;
- zero falhas;
- média de 15,63 s, máximo de 21,95 s;
- pair bank SHA-256: `86e6ca2e579004dadf28e046bee5eb7a8750600c6c096b2b5a90648b6d3c835b`.

Melhor sinal (`pw_focal_lesion_evidence_top2_mean`):

- aparente/LOOCV: sensibilidade 56,41%, especificidade 59,18%;
- validação repetida: mediana 56,41% / 57,14%;
- validação aninhada: mediana 43,59% / 51,02%;
- repetições aprovadas em 75/75: 0/50.

Conclusão: o tempo melhorou, mas a separação clínica continuou insuficiente.

## Auditoria de escala visual

O painel original tem 1536 x 1152 pixels. O processador Gemma 3 o converte para
896 x 896 e usa 256 tokens visuais, aproximadamente uma grade 16 x 16. Como o
painel possui 12 células, cada corte axial recebe somente cerca de 4 x 5 tokens
visuais. Portanto, cobertura volumétrica não equivale a resolução suficiente
para lesões pequenas.

## v8 — um corte axial por imagem

Foi criado um scorer que recorta deterministicamente cada tile axial dos painéis
aprovados, verifica o hash do painel, preserva todos os índices axiais e envia um
corte por vez. Nenhuma imagem foi colorida artificialmente e nenhuma máscara de
lesão foi utilizada.

Piloto técnico de um caso:

- 50 cortes;
- 74,28 s;
- cobertura exata e zero falhas.

Piloto cego exploratório de dez casos:

- 10/10 casos, sendo 5 positivos e 5 negativos após abertura tardia dos labels;
- 533 cortes;
- média de 78,48 s, máximo de 99,0 s;
- zero falhas;
- melhor sinal: média dos scores dos cortes;
- sensibilidade 40%;
- especificidade 100%;
- repetições aprovadas em 75/75: 0/50.

Conclusão: maior escala visual reduziu falsos positivos nesse piloto, mas perdeu
3 de 5 positivos. O resultado não justifica executar a coorte completa v8 sem
uma nova fonte de informação ou um detector/localizador melhor.

## Decisão atual

Não se deve colorir exames monofásicos para tentar melhorar a métrica. Cor só é
válida quando representa fases reais registradas. A evidência acumulada mostra
que o gargalo não é apenas cobertura, prompt, regra de agregação ou escala do
tile. O MedGemma 4B, usando apenas esses painéis T1, ainda não demonstrou sinal
discriminativo suficiente para 75/75.

Próximos caminhos defensáveis:

1. acrescentar sequências originais independentes, principalmente DWI/ADC e T2,
   sem convertê-las em cor decorativa;
2. usar candidato/localizador 3D ou supervisionado para fornecer regiões focais
   de alta resolução ao MedGemma;
3. validar disponibilidade e alinhamento de lesão/fase antes de novo benchmark;
4. manter o holdout fechado até existir candidato que passe de forma robusta no
   desenvolvimento;
5. não declarar 75% nem escolher limiar com base no holdout.

## Artefatos principais

- `casos/qualification/openswisshcc_v1/runs/dev_v4_4b`
- `casos/qualification/openswisshcc_v1/calibration/dev_v6_volumetric_medsiglip`
- `casos/qualification/openswisshcc_v1/evaluation/dev_v6_volumetric_fusion`
- `casos/qualification/openswisshcc_v1/calibration/dev_v7_volumetric_pairwise`
- `casos/qualification/openswisshcc_v1/evaluation/dev_v7_volumetric_pairwise`
- `casos/qualification/openswisshcc_v1/calibration/dev_v8_slice_pairwise_pilot10`
- `casos/qualification/openswisshcc_v1/evaluation/dev_v8_slice_pairwise_pilot10`
