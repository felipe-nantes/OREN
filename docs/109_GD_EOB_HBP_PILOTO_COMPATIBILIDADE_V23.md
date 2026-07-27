# Gd-EOB HBP — piloto técnico e compatibilidade com a v23

## Objetivo

Testar, sem abrir labels ou máscaras públicas, se a coorte HBP-only pode:

1. ser segmentada automaticamente;
2. gerar painéis liver-enriched verdadeiramente single-phase;
3. respeitar o orçamento técnico de 180 segundos;
4. fornecer todos os sinais exigidos pela baseline v23 congelada.

O piloto foi congelado antes da segmentação e não autorizou inferência do
MedGemma.

## Protocolo

```text
casos/qualification/gd_eob_hcc_external_v1/hbp_pilot_protocol_v1.json
```

Assinatura:

```text
01a0b4cdaffbebc74189ae32bfa00b31332a44084154cbd55992796e8ce69ba8
```

Seleção:

- nove casos;
- três casos de cada centro;
- ranking determinístico por `case_id`;
- sem uso de label, máscara, imagem ou metadado clínico na seleção.

Representação:

```text
fase disponível: HBP Gd-EOB-DTPA
R=HBP
G=HBP
B=HBP
```

Replicar a mesma fase nos três canais produz grayscale verdadeiro. Nenhuma
diferença de fase é criada. O manifesto registra:

```text
single_phase_replicated_across_rgb=true
dynamic_enhancement_information_present=false
```

As máscaras usadas para localização foram geradas automaticamente pelo
TotalSegmentator `total_mr/liver`, em modo rápido. As máscaras anatômicas
públicas do dataset não foram abertas ou usadas.

## Resultado técnico

```text
casos executados: 9
segmentações válidas: 9
falhas técnicas: 0
painéis gerados: 27
labels lidos: 0
máscaras públicas de lesão lidas: 0
anotações anatômicas públicas usadas: 0
inferências MedGemma executadas: 0
```

Tempos de segmentação mais geração dos painéis:

```text
mínimo: 47,67 s
mediana: 48,51 s
máximo: 60,71 s
mediana da segmentação: 46,67 s
mediana da geração dos painéis: 1,57 s
```

Todos os casos ficaram abaixo de 180 segundos neste escopo. Esse tempo ainda
não inclui MedGemma, MedSigLIP, localizador de lesão e persistência final; não é
uma comprovação do gate end-to-end.

Assinatura da execução:

```text
31879f51dacb46b8d0eae30fe42a9641df89cf0cd98ee689d3add4ce931790db
```

Galeria técnica:

```text
casos/qualification/gd_eob_hcc_external_v1/hbp_pilot_gallery_v1/index.html
```

Assinatura da galeria:

```text
4810f47a4ac786c14b4b6891be75a35191db522d895ce1fc665b605c30be6fba
```

A revisão solicitada na galeria é exclusivamente técnica: presença e cobertura
visual do fígado, ausência de crop excessivo, contorno, PHI ou artefato grave.
Não deve ser feita avaliação diagnóstica.

## Gate de compatibilidade v23

A baseline v23 exige:

```text
80% v11
  40% medgemma_v4_uncertainty_margin
  40% medsiglip_v5_inverse_sagittal
  20% localizer_v10_log_volume

20% candidate_weighted_linearity
```

O HBP fornece pixels suficientes para executar leitores de imagem, mas não
preserva o domínio no qual os três sinais v11 foram congelados:

- o painel MedGemma original era multifásico;
- a entrada sagital do MedSigLIP pertencia à representação congelada;
- o localizador v10 esperava fase venosa, não HBP.

O bloqueio definitivo está em `candidate_weighted_linearity`. Essa feature é
calculada sobre um candidato determinístico de realce que requer:

```text
T1 nativo
T1 arterial
T1 venoso
T1 tardio
```

Uma imagem HBP isolada não permite reconstruir realce arterial ou washout. Usar
HBP como se fosse alguma dessas fases fabricaria evidência e invalidaria a
baseline.

Resultado do gate:

```text
exact_v23_raw_signals_available=false
exact_v23_score_computable=false
direct_external_validation_of_frozen_v23_allowed=false
direct_frozen_v23_validation_decision=REJECTED_INCOMPATIBLE_INPUT_DOMAIN
full_220_case_inference_authorized=false
```

## Decisão

A nova base é tecnicamente utilizável pelo ARGOS, mas não pode validar
diretamente a v23 congelada.

Executar os 220 casos com pesos, ECDFs e limiar da v23 produziria números, porém
eles não representariam a mesma função de decisão avaliada no OpenSwissHCC.
Por integridade científica, essa execução permanece bloqueada.

## Próximo caminho metodologicamente válido

Há duas linhas distintas:

1. Manter a v23 como pipeline multifásico e procurar uma coorte externa fresca
   que possua nativo, arterial, venoso e tardio.
2. Desenvolver um pipeline HBP específico usando parte da nova base como
   desenvolvimento e mantendo um holdout protegido, congelado antes de abrir
   seus labels.

A segunda linha pode aproveitar os painéis HBP já validados tecnicamente, mas
será um novo protocolo, não uma validação direta da v23.

## Testes

Foram executados testes do fluxo Gd-EOB, aquisição, seleção, representação
single-phase, painéis, v11 e v23:

```text
45 passed
```
