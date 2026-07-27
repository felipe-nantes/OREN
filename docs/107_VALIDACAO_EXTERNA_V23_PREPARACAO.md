# Preparação da validação externa independente v23

## O que foi congelado

Foi criado um contrato imutável para a próxima validação externa da baseline
v23. Ele preserva:

```text
80% v11 + 20% candidate_weighted_linearity
limiar = 0.5121839080459771
assinatura do calibrador =
d0a955178783cf7f2914053c87d3d99d186ab4a56960620068bd118e5ccac475
```

O contrato está em:

```text
configs/benchmark/v23_external_validation_contract_v1.json
```

Assinatura:

```text
d285095c191afe9faad7e278d697c8719e894e7ce9295f5f4bfbc8fbaf26992e
```

## Gate congelado

A execução somente poderá começar quando uma nova coorte cumprir:

- pelo menos 40 positivos e 40 negativos;
- ambas as classes provenientes da mesma fonte;
- um caso por paciente;
- referência pública especializada ou revisão independente;
- nenhuma utilização prévia no desenvolvimento ou em avaliações;
- ausência de sobreposição por fingerprint;
- imagens e labels protegidos com inventários exatamente correspondentes;
- nenhuma máscara de lesão ou ground truth disponível para inferência.

O sucesso exige simultaneamente:

```text
sensibilidade >= 75%
especificidade >= 75%
tempo end-to-end desde a entrada bruta <= 180 s por caso
```

Falhas técnicas e inconclusivos contam como erros. O limiar não poderá ser
reajustado, nenhum caso poderá ser removido após a inferência e as predições
deverão ser congeladas antes da avaliação dos labels.

## Proteções implementadas

O preflight:

- verifica o lock e os 14 artefatos protegidos da v23;
- recusa OpenSwissHCC, LLD-MMRI, LiverHccSeg, CHAOS MRI e TCGA-LIHC;
- recusa fingerprints já consumidos ou duplicados;
- recusa caminhos fora do workspace;
- recalcula bytes e SHA-256 de cada imagem;
- recusa arquivos com papel de máscara de lesão, tumor ou ground truth;
- exige uma única fonte com as duas classes;
- exige ao menos 40 casos de cada classe;
- publica atomicamente um protocolo `ready_for_inference`;
- falha se labels e imagens não tiverem exatamente os mesmos casos.

CLI:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_v23_external_validation.py `
  preflight `
  --contract configs\benchmark\v23_external_validation_contract_v1.json `
  --images caminho\fresh_external_images.jsonl `
  --protected-labels caminho\protected_labels.jsonl `
  --forbidden-fingerprints caminho\consumed_fingerprints.jsonl `
  --out casos\qualification\v23_external_validation_v1\protocol `
  --allow-protected-label-inventory
```

Os schemas dos dois inventários estão em:

```text
configs/benchmark/v23_external_candidate_manifest.schema.json
configs/benchmark/v23_external_protected_label.schema.json
```

## Auditoria das fontes disponíveis

Nenhuma fonte local atual é elegível:

| Fonte | Motivo |
|---|---|
| OpenSwissHCC | desenvolvimento e holdout já foram abertos |
| LLD-MMRI | labels já foram abertos e usados em avaliações |
| LiverHccSeg | já usado e contém somente o braço positivo |
| CHAOS MRI | já usado e contém somente o braço negativo |
| TCGA-LIHC | já usado como estresse predominantemente positivo |
| exames locais anteriores | já usados durante desenvolvimento e sem referência independente protegida |

Também foram examinadas alternativas públicas. O Duke Liver Dataset fornece
MRI e máscaras hepáticas, mas não oferece um label focal benigno/maligno
adequado para este endpoint. O CirrMRI600+ separa cirrose e controles, o que
mede doença difusa e não a suspeita de lesão focal definida no contrato.

## Estado atual

```text
implementação: pronta
contrato: congelado
baseline: íntegra
inferência externa: não iniciada
coorte externa fresca elegível: ausente
ready_for_external_validation: false
```

O arquivo de estado verificável está em:

```text
casos/qualification/v23_external_validation_v1/readiness.json
```

A validação estará pronta para iniciar assim que for disponibilizada uma coorte
nova, balanceada e com referência protegida que passe integralmente no
preflight. Reutilizar uma base já aberta produziria uma avaliação retrospectiva,
não a confirmação independente necessária para consolidar a alegação 75/75.
