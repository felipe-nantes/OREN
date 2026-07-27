# OpenSwissHCC v17 — protocolo de auditoria retrospectiva

## Estado

O auditor retrospectivo do atlas axial v17 foi implementado, testado e executado
após autorização explícita. O protocolo real dos 87 casos foi congelado antes
da leitura das máscaras.

```text
atlas_protocol_signature:
0c7627a0fda29fdd1e95bb80213ab62da058a17d8c4283ec5b73a3fc99abd89e

audit_protocol_signature:
2b45a8a7569af4ad5ef3464635b92f9f8de4ab997b232f25483f6f377cc56cd5
```

O holdout permaneceu fechado e o MedGemma não foi chamado.

Assinatura do resultado:

```text
cb5a46615a10a17c1b118430cf4acf42ca4e5709377a043c90c2ffd50591b486
```

## Objetivo

Determinar retrospectivamente se as lesões manuais públicas dos casos de
desenvolvimento realmente aparecem dentro da evidência v17. A auditoria é
isolada da inferência e nunca envia máscara ao modelo.

Para cada lesão serão calculados:

- total de voxels da máscara;
- voxels dentro dos índices axiais e crop efetivamente mostrados;
- presença de ao menos um voxel visível;
- cobertura exata de 100% dos voxels;
- cortes axiais da lesão e cortes visíveis;
- volume em mm³;
- diâmetro esférico equivalente;
- grupo `<10 mm`, `10–<20 mm` ou `≥20 mm`.

Também serão reportadas métricas por caso, por lesão e por tamanho, com intervalo
de Wilson de 95%.

## Congelamento sem máscaras de lesão

O comando executado foi:

```powershell
.\.venv-win\Scripts\python.exe tools/audit_openswisshcc_axial_atlas_v17.py freeze `
  --atlas-root casos/qualification/openswisshcc_v1/prepared/development_candidate_v17_axial_atlas_full87_v1 `
  --source-panel-root casos/qualification/openswisshcc_v1/prepared/development_candidate_v4_volumetric `
  --input-manifest casos/qualification/openswisshcc_v1/prepared/development_v1/manifests/development_inputs.jsonl `
  --input-root casos/qualification/openswisshcc_v1/prepared/development_v1/inputs `
  --out casos/qualification/openswisshcc_v1/prepared/development_audit_v17_axial_atlas_protocol_v1.json
```

Resultado:

```text
casos:                         87
crop vindo do manifesto:      68
crop fallback reconstruído:   19
labels lidos:                   0
máscaras de lesão lidas:        0
holdout aberto:                 0
```

Os 19 painéis fallback antigos não persistiam `crop_bounds_zyx`. O auditor
reconstruiu o crop usando exatamente a máscara hepática, a margem de 30% e o
algoritmo determinístico original. O SHA-256 da máscara hepática precisa
coincidir simultaneamente com o input e o manifesto-fonte. Máscara hepática não
é ground truth de lesão.

## Gates de segurança

- qualquer caminho contendo `holdout` é recusado;
- máscaras e referências devem possuir geometria de índice compatível;
- não é permitido resample da máscara manual;
- hashes do atlas, painel-fonte e referência venosa são revalidados;
- protocolo ou arquivo alterado é recusado;
- saída existente nunca é sobrescrita;
- labels clínicos não fazem parte do protocolo;
- nenhuma função de inferência ou cliente MedGemma é importada.

## Testes

Foram aprovados 40 testes combinados do atlas, auditor v17 e auditor v16. Eles
cobrem cobertura parcial versus total, crops inválidos, índices duplicados,
Wilson 95%, reconstrução fallback, protocolo cego, persistência das métricas,
geometria deslocada sem resample e bloqueio de holdout.

Arquivos:

```text
dtwin/benchmark/openswisshcc_axial_atlas_audit.py
tools/audit_openswisshcc_axial_atlas_v17.py
tests/test_openswisshcc_axial_atlas_audit.py
```

## Autorização e vínculo ao manifesto

A autorização específica v17 foi concedida para o protocolo assinado. O auditor
foi endurecido para aceitar somente o manifesto de extração autorizado: caminho,
bytes e SHA-256 das 74 máscaras precisam coincidir exatamente, e arquivos extras
ou ausentes abortam.

## Resultado da auditoria real

```text
casos com máscara venosa:            37
lesões venosas:                       74
casos com alguma lesão visível:       37/37 = 100%
casos com todas as lesões visíveis:   37/37 = 100%
casos com cobertura total de voxels:  37/37 = 100%
lesões com algum voxel visível:       74/74 = 100%
lesões com todos os voxels visíveis:  74/74 = 100%
fração agregada de voxels visíveis:   100%
```

Intervalos de Wilson de 95%:

```text
por caso:   90,59%–100%
por lesão:  95,07%–100%
```

Por tamanho:

| Diâmetro equivalente | V17 | IC 95% de Wilson |
|---|---:|---:|
| menor que 10 mm | 11/11 = **100%** | 74,12%–100% |
| 10 a menor que 20 mm | 43/43 = **100%** | 91,80%–100% |
| 20 mm ou maior | 20/20 = **100%** | 83,89%–100% |

Na v16, a visibilidade havia sido 23/37 casos e 29/74 lesões; entre as lesões
menores que 10 mm, era 0/11. A v17 removeu esse teto de cobertura no subconjunto
com máscara venosa disponível. Dois positivos públicos continuam sem máscara
manual venosa e não foram transformados artificialmente em sucesso ou falha.

Esse resultado prova presença da evidência no atlas, não reconhecimento pelo
MedGemma. Sensibilidade e especificidade continuam desconhecidas até a execução
cega do leitor 4B e a avaliação posterior.

Artefatos locais:

```text
casos/qualification/openswisshcc_v1/audits/dev_v17_axial_atlas_venous_v1/
  audit_report.json
  case_rows.csv
  lesion_rows.csv
```

Verificação independente:

```text
linhas de caso:          37
linhas de lesão:         74
hashes divergentes:       0
labels lidos:             0
MedGemma chamado:         0
holdout aberto:           0
SHA-256 audit_report: b5c8d9057901dc823fe103f0d5bac411084c36dfbf441923e23aba0437fe80a3
```
