# ARGOS v21 — execução cega do braço negativo CHAOS

Data da execução: 2026-07-18.

## Escopo e limitação

Foram processados 20 controles públicos CHAOS v1.03 como braço secundário de
especificidade e estresse de mudança de domínio. Este braço não pode ser
combinado como matriz de confusão primária com os positivos LiverHccSeg porque
classe, dataset e protocolo de aquisição estão confundidos.

O holdout OpenSwissHCC permaneceu fechado. Nenhum label protegido foi lido na
preparação, revisão, inferência, montagem, calibração ou freeze.

## Revisão humana

A galeria foi aprovada tecnicamente pelo revisor `jm`, com a ressalva explícita:

> A qualidade está inferior às galerias anteriores, mas está aprovado.

Essa limitação foi preservada no artefato assinado e não deve ser omitida na
interpretação do resultado.

```text
review_signature:
1c468f45d48eee7945339ff681f0c4d661e7f82ea777122844084730fb00e995

panel_cohort_signature:
c07132616654ac50444d95ca134cf180817b8ce35a8d969a7e2c83a0071cc79d

gallery_signature:
9b0abbbac64e253cbe1512de320ccadc2fa01908309182526f46ca67a440dc94
```

A revisão foi somente técnica, não diagnóstica.

## Tentativa parcial descartada

Na primeira chamada do localizador, o PowerShell não entregou o progresso
incremental. O silêncio foi inicialmente interpretado como possível estouro do
primeiro caso e a execução foi cancelada preventivamente. A inspeção posterior
mostrou que sete casos haviam terminado, todos abaixo de 36 segundos.

Esse staging parcial não foi reutilizado. A execução válida começou novamente
do zero e foi publicada apenas após os 20 casos concluírem, preservando a regra
atômica do protocolo.

## Localizador 3D

O TotalSegmentator 2.15.0, task `liver_lesions_mr`, Dataset589 fold 0,
processou T2-SPIR usando somente a máscara hepática pública como crop.

O T2-SPIR é uma mudança de domínio em relação à entrada venosa usada no
desenvolvimento. Ele não foi chamado de T1 venoso nos manifestos.

```text
casos completos: 20/20
média por caso: 23,12 s
máximo por caso: 28,13 s
casos abaixo de 90 s: 20/20
candidato derivado presente: 16
candidato derivado ausente: 4
ground truth de lesão usado: não
decisão emitida: não
runtime guard: pyarrow_blocked_for_windows_spawn_v1
```

A alta taxa de candidatos no T2-SPIR não foi interpretada isoladamente nem
usada para ajustar o limiar.

## MedSigLIP

O MedSigLIP 448 foi executado sem decisão autônoma, usando a configuração
`medsiglip_liver_volumetric_mimic_aware.yaml`.

```text
casos completos: 20/20
média por caso: 1,13 s
máximo por caso: 9,98 s
scores sha256:
bbacb286594b9e4729ae9a55fad93612ec4c3a22df71d715f025d7d73e17250d
ground truth lido: não
decisão emitida: não
```

Os avisos `bos_token_id/eos_token_id` foram emitidos pelo Transformers ao
carregar a configuração oficial. O modelo carregou, os 20 casos foram
processados e os scores passaram pelo schema e pelos gates de finitude.

## MedGemma 1.5 4B

O gateway confirmou:

```text
contrato: dtwin-medgemma-v1
modelo: google/medgemma-1.5-4b-it
quantização: bitsandbytes-nf4
dispositivo: cuda
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
load_error: null
```

Foram usadas as sequências corretas do CHAOS na fusão:

```text
R = T1 in-phase
G = T1 out-phase
B = T2-SPIR
```

```text
casos completos: 20/20
respostas HTTP 200: 20/20
retries: 0
média por caso: 6,24 s
máximo por caso: 6,88 s
scores sha256:
02d8a05a6f2e5f7008a4c7227d9c0587ee58446fb182bf07c7e702e86517f915
ground truth lido: não
decisão emitida pelo componente: não
```

O gateway foi encerrado depois da rodada para liberar a GPU.

## Montagem e gate temporal

Os três sinais v11 foram montados sem labels:

```text
P(INCONCLUSIVA) - P(NEGATIVA)
-P_MedSigLIP_positiva_na_vista_sagital
log1p(volume_candidato_mm3)
```

```text
raw signals sha256:
5e8749c2be7371e43cdf7083f0b6083ccf9d5ad14949426d558432b86804ff05

tempo operacional médio: 30,49 s
tempo operacional máximo: 44,46 s
casos <= 180 s: 20/20
gate temporal: PASS
```

## Calibrador v11 congelado

O mesmo calibrador externo congelado antes do LiverHccSeg foi aplicado sem
reajuste no CHAOS:

```text
calibrator signature:
cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181

calibrator sha256:
1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971
```

## Predições ainda cegas

Antes de qualquer abertura do ground truth:

```text
predições NEGATIVE: 20
predições POSITIVE: 0
scores sha256:
8e98145ea0113b8bf23211427ed011236eac0914526fe48e27a866aed6313eb6
```

Essas contagens ainda não são chamadas de TN/FP nem de especificidade.

## Protocolo protegido de avaliação

As predições e todos os artefatos foram congelados. A próxima operação exige
autorização explícita para abrir exclusivamente os labels públicos dos 20 casos
CHAOS vinculados ao protocolo abaixo:

```text
evaluation protocol signature:
0b5952302fa95e572503d31bdf3f1b3daeccef2b2f75e7a72e37444675d30738

protected labels sha256:
63c0f98eb027fb20241e6f763e123424d8252d6097b0054cfebba357425ff3aa

public cohort protocol signature:
75d63e46e89cb043dd5b7bc09e997bd6b9302de116692b5634c83f8f55644237
```

O avaliador deverá reportar especificidade, TN, FP, FPR, IC95% Wilson e tempo.
Sensibilidade e ROC-AUC permanecerão nulos por ser um braço de classe única.
`qualified` permanecerá falso porque este estresse secundário não comprova
sozinho a meta simultânea de 75%/75%.

## Avaliação protegida autorizada

O usuário autorizou a abertura exclusiva dos labels públicos dos 20 casos CHAOS
vinculados ao protocolo assinado. O holdout OpenSwissHCC permaneceu fechado.

```text
TN: 20
FP: 0
especificidade: 100,00%
IC95% Wilson: 83,89%–100,00%
FPR: 0,00%
tempo médio: 30,49 s
tempo máximo: 44,46 s
gate pontual de especificidade >= 75%: PASS
gate de tempo <= 180 s: PASS
```

```text
evaluation sha256:
c4934e1447d84b9d005a11e1f8723bf00b3ee33cfd38dd2c6cffdd5031377976
```

Como o CHAOS é um braço externo somente negativo, sensibilidade e ROC-AUC
permaneceram nulos e `qualified=false`. Nenhuma métrica combinada com o braço
positivo deve ser apresentada como validação balanceada.
