# OpenSwissHCC v17 — scorer 4B e gate temporal

## Estado

O scorer cego do atlas axial v17 foi implementado, testado e submetido ao
piloto temporal cego. A galeria full87 foi aprovada pelo revisor `jm` para
inferência 4B e a revisão foi vinculada aos artefatos por SHA-256.

O holdout e os labels permanecem fechados.

## Contrato do leitor

Cada caso usa:

```text
requisições ao 4B:       1
frames por requisição:   9 a 20 no full87
frames máximos aceitos:  32 no atlas
resolução:               640×640 ou 768×768
retry automático:        0
tempo máximo:            180 segundos
saída:                   probabilidades de POSITIVA/NEGATIVA/INCONCLUSIVA
score contínuo:          log((P(POSITIVA)+1e-8)/(P(NEGATIVA)+1e-8))
```

O endpoint continua sendo `/score-volume`, com o contrato
`dtwin-medgemma-volume-score-v1` e o método
`first_token_restricted_softmax_v1`.

## Prompt

O prompt informa que cada imagem contém uma grade 2×2 de cortes consecutivos,
na ordem:

```text
superior esquerdo → superior direito → inferior esquerdo → inferior direito
```

Também explica:

- quadrantes pretos finais devem ser ignorados;
- RGB significa arterial, portal/venoso e tardio;
- cor isolada não é evidência suficiente de doença;
- grayscale é fallback venoso válido;
- todo frame e quadrante deve ser examinado;
- uma suspeita deve persistir morfologicamente entre cortes;
- vaso tubular, veia calibrosa, variante anatômica, alteração perfusional,
  volume parcial, cisto simples e artefato não são patologia-alvo.

`POSITIVA` é reservada para lesão focal hepática suspeita. O modelo não recebe
label, máscara de lesão ou diagnóstico.

## Ampliação segura do gateway

O endpoint `/score-volume` aceitava somente imagens até 512×512. Os frames v17
preservam nativamente 640×640 ou 768×768, portanto a execução antiga falharia.

O limite individual foi ampliado para 768×768, mantendo:

- limite por arquivo;
- limite total de bytes;
- limite total de pixels;
- máximo de imagens por requisição;
- PNG obrigatório;
- campos extras/PHI proibidos;
- endpoint exclusivamente local.

O `/health` agora deve publicar:

```json
{"volume_score_max_image_edge": 768}
```

O processo MedGemma foi reiniciado antes do piloto temporal. O health confirmou
o modelo `google/medgemma-1.5-4b-it`, CUDA, quantização NF4, contrato de score e
`volume_score_max_image_edge=768`. O scorer continua recusando o backend antigo.

## Reuso e integridade

Uma predição existente só pode ser reutilizada se coincidirem:

- assinatura do protocolo;
- SHA-256 do manifesto do atlas;
- SHA-256 do conjunto de frames;
- quantidade de frames e tiles;
- hash da query derivada;
- probabilidades e argmax;
- log-odds recalculado;
- gate temporal;
- salvaguardas de labels e holdout.

## Escopo do tempo

Inicialmente será medido `precomputed_atlas_scoring_only`. Esse resultado não
prova sozinho o tempo total de 180 segundos do ARGOS. A qualificação final deve
somar ou medir diretamente:

```text
ingestão + segmentação + geração do atlas + inferência + persistência
```

O relatório preserva explicitamente:

```json
{
  "timing_scope": "precomputed_atlas_scoring_only",
  "end_to_end_180_seconds_proven": false,
  "accuracy_claimed": false
}
```

## Gates antes da inferência full87

1. revisar a galeria full87 v17;
2. registrar revisão assinada com escopo `blind_4b_scoring`;
3. reiniciar o MedGemma 4B;
4. confirmar no health o limite de 768 px e o contrato de score;
5. congelar o protocolo do scorer;
6. executar primeiro um piloto temporal cego de casos representativos;
7. somente depois executar o full87.

Os gates 1 a 6 foram concluídos. A inferência cega full87 é o próximo gate.

## Resultado do piloto temporal cego

O plano foi congelado antes da inferência, sem abrir labels ou holdout:

```text
protocolo do scorer: cedf7dd7a1f6ef6df37e7378c2da203dc712fa7f73bcb89f94a0399bb4228656
plano temporal:      af8305aa04aee3948032ee01e2108ac432d87f40ab108d4086c8b3caa9e161c9
casos planejados:    4
casos concluídos:    4
falhas técnicas:     0
```

A seleção cega cobriu o maior volume de pixels RGB, o maior fallback venoso, a
carga mediana e um segundo extremo RGB. Os tempos de requisição ao 4B foram:

| Perfil | Frames | Tempo |
|---|---:|---:|
| maior carga RGB | 18 | 11,6697 s |
| maior fallback venoso | 20 | 13,8166 s |
| carga mediana | 13 | 7,0498 s |
| segundo extremo RGB | 18 | 9,8941 s |

```text
mínimo:  7,0498 s
mediana: 10,7819 s
média:   10,6076 s
máximo:  13,8166 s
gate:    4/4 abaixo de 180 s
```

Este gate aprova o tempo de **inferência sobre o atlas pré-computado**. Ele não
prova ainda o requisito end-to-end desde o DICOM; por isso o artefato mantém
`end_to_end_180_seconds_proven=false` e nenhuma alegação de acurácia.

## Testes

Foram aprovados os testes combinados do atlas, scorer e servidor. Entre eles:

- 640×640 e 768×768 aceitos;
- 769 px rejeitado;
- frame adulterado rejeitado;
- revisão do piloto incapaz de autorizar inferência full87;
- revisão full87 vinculada por hash;
- uma única chamada e nenhum retry;
- resposta probabilística e argmax revalidados;
- log-odds adulterado rejeitado;
- protocolo declara 180 segundos e ausência de ground truth.

Arquivos principais:

```text
dtwin/benchmark/openswisshcc_axial_atlas_score.py
tools/run_openswisshcc_axial_atlas_score_v17.py
tools/medgemma_server_v14.py
tests/test_openswisshcc_axial_atlas_score.py
tests/test_medgemma_volume_score_server.py
```
