# 220 — Contrato e motor central de volumetria v1

## Estado

As Fases 1 e 2 do plano de volumetria foram implementadas sem trocar o
segmentador, a máscara de classificação, o MedGemma ou a origem das malhas.

## Contrato

O contrato versionado é `oren-hepatic-volumetry-contract-v1`, persistido no
manifesto `oren-volumetry-manifest-v1`.

O valor autoritativo é sempre:

```text
volume_mL = voxels positivos da máscara × spacing_x × spacing_y × spacing_z / 1000
```

A medida usa a geometria física da própria máscara, validada contra o volume de
referência. O volume da malha STL não substitui essa medida. Ele continua sendo
um controle separado de fidelidade da reconstrução.

### Fígado total

O volume hepático representa tudo que a máscara hepática refinada contém:

- parênquima;
- lesões incluídas no órgão;
- vasos intra-hepáticos incluídos pela máscara.

Não deve incluir:

- vesícula;
- veia porta extra-hepática;
- veia cava inferior;
- tecido vizinho;
- fragmentos removidos pelo refino.

### Região candidata

O papel `candidato` recebe obrigatoriamente a classe
`automatic_unconfirmed_candidate`. Seu volume é medida de uma região automática
não confirmada e nunca é denominado volume tumoral.

### Segmentos de Couinaud

Os volumes segmentares somente são marcados como utilizáveis quando:

- os oito segmentos I–VIII estão presentes;
- não há sobreposição entre segmentos;
- a união cobre exatamente o fígado;
- não há voxels segmentares fora da máscara hepática.

Uma falha nesse gate não apaga as malhas existentes, mas impede que os valores
segmentares sejam apresentados como uma partição volumétrica válida.

## Motor

Arquivo central:

```text
dtwin/volumetry.py
```

Para cada máscara o motor registra:

- volume em mL;
- quantidade de voxels;
- volume físico do voxel;
- espaçamento XYZ;
- dimensões LR/AP/SI em LPS;
- área superficial aproximada;
- quantidade de componentes conectados;
- fração do maior componente;
- contato com cada face do campo de visão;
- percentual do volume hepático;
- SHA-256 da máscara;
- avisos e validade técnica.

## Artefatos

O estágio final gera atomicamente:

```text
outputs/volumetry_summary.csv
outputs/volumetry_manifest.json
```

O CSV é publicado primeiro e seu SHA-256 entra no JSON. O JSON é publicado por
último e funciona como marcador de conclusão do par de artefatos.

O mesmo manifesto é incluído em `viewer_manifest.json`, preparando a futura
apresentação visual sem exigir uma segunda fórmula no navegador.

## Segurança metodológica

- não há leitura de ground truth;
- não há alteração de máscara;
- não há reamostragem para calcular o volume;
- não há arredondamento antes do cálculo;
- a geometria divergente aborta a publicação;
- a medida descreve a máscara e não afirma acurácia anatômica;
- revisão humana continua obrigatória;
- uso permanece restrito a pesquisa.

## Testes

Os testes cobrem:

- volume físico exato com spacing anisotrópico;
- dimensões em coordenadas LPS;
- rejeição de geometria divergente;
- candidato automático explicitamente não confirmado;
- partição Couinaud exata;
- reprovação de partição Couinaud incompleta;
- persistência JSON/CSV;
- integração com `finalize` e `viewer_manifest.json`.

## Limite desta etapa

As Fases 1 e 2 tornam a medição única, correta e auditável **para a máscara que o
pipeline produziu**. O ganho de acurácia anatômica depende da Fase 3, que deverá
melhorar e validar a própria segmentação antes de promover uma nova máscara como
fonte volumétrica padrão.
