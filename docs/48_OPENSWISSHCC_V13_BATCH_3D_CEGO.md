# OpenSwissHCC v13 — batch cego com entrada 3D nativa

## Objetivo da etapa

Transformar o piloto high-dimensional v12 em um benchmark de desenvolvimento
reproduzível para os 87 casos cegos, mantendo:

- MedGemma 1.5 4B;
- uma chamada determinística por caso;
- máximo de 180 segundos por chamada;
- nenhum label durante preparação ou inferência;
- holdout fechado;
- uso exclusivo em pesquisa e revisão humana obrigatória.

## Teto temporal de 50 cortes

O piloto v12 com 50 imagens levou 148,50 segundos e usou 7.943 MiB da GPU de
8 GB. Por isso o gerador passou a aceitar um teto configurável. O protocolo v13
foi preparado com:

```text
mínimo: 5 cortes
máximo do endpoint: 85 cortes
máximo congelado para esta GPU: 50 cortes
amostragem: equidistante no intervalo axial hepático
```

O teto de 50 é uma restrição operacional predeclarada, não um parâmetro escolhido
após observar labels.

## Preparação das 87 pilhas

Origem dos IDs:

```text
casos/qualification/openswisshcc_v1/runs/dev_v11_blind_fusion87/summary.json
```

Entradas permitidas por caso:

```text
t1_venous
liver_mask_venous
```

Resultado:

```text
casos preparados: 87/87
slice_count mínimo: 35
slice_count mediano: 50
slice_count máximo: 50
casos com 50 cortes: 58

cobertura hepática mínima nos planos selecionados: 64,02%
cobertura mediana: 96,49%
cobertura média: 92,32%
cobertura máxima: 100%
casos com cobertura de 100%: 34

hashes de manifesto divergentes: 0
ground_truth_read: false
holdout_opened: false
```

O percentual de cobertura mede voxels da máscara hepática situados nos planos
selecionados. Quando há mais de 50 planos hepáticos, alguns planos são omitidos
pela amostragem equidistante; não há alegação de cobertura volumétrica de 100%
nesse cenário high-dimensional.

Bundle:

```text
assinatura:
0e647375dd48d11c30f28e63f7fd55cf2a07510f2ce0f6cee642d2b2b7bc2f2e

SHA-256 do bundle.json:
5d91db775d5691e192986dcf30fb678b529bb5c9850d80814af2975ccd68e480
```

## Falhas técnicas encontradas e corrigidas

### Lock transitório do Windows

Durante a publicação atômica de uma pilha, o Windows retornou `WinError 5` no
`rename`. A publicação agora repete somente `PermissionError` transitório, com
backoff limitado a oito tentativas. Outros erros continuam abortando. Um teste
simula dois locks e confirma que a terceira publicação ocorre sem duplicação.

### Ruído numérico após orientação LPS

O caso `anon-openswiss-64b60879e2e812a9` possuía diferenças já aceitas pelo gate
original:

```text
spacing: 1,1920929e-7
direction: 3,0840992e-10
```

Ao inverter o eixo para LPS, a diferença de spacing acumulada por 319 pixels
produziu diferença de origem de `3,8009416e-5 mm`. Os arrays continuavam
voxel-a-voxel alinhados.

A correção:

1. mantém o gate de geometria original em `1e-5`;
2. orienta volume e máscara com a mesma operação LPS;
3. exige dimensões idênticas;
4. harmoniza apenas os metadados da máscara após a orientação;
5. registra todos os deltas no manifesto;
6. não reamostra nem desloca voxels.

Três casos precisaram dessa harmonização numérica:

```text
anon-openswiss-64b60879e2e812a9
anon-openswiss-9ae9714397cade3e
anon-openswiss-e002736d3e9589fa
```

## Protocolo congelado

```text
casos: 87
máximo de cortes: 50
requisições por caso: 1
retries automáticos: 0
timeout por caso: 180 s

assinatura:
11616f927c361f13852607395e3861060b1cf957ffe7a9ffc45ace013dffe9e3

SHA-256 do arquivo:
2a7dcb33f5e4ab5061cb43e2949a9441f082d0fc48841d3b25d15505340b0e26
```

O protocolo está em:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v13/
highdimensional_batch_protocol.json
```

## Runner resumível

O runner:

- valida os 87 manifests antes de iniciar;
- confirma health, modelo, versão e contrato;
- grava uma predição atômica após cada caso;
- recusa reuso com protocolo ou hash divergente;
- nunca repete automaticamente um caso concluído;
- permite limitar o número de novos casos por execução;
- produz `progress.json` sem ground truth;
- só produz `summary.json` quando os 87 casos estiverem completos.

## Primeiro bloco cego

Foram executados três casos, sem abrir labels:

| Caso | Classe retornada | Tempo da chamada |
|---|---:|---:|
| `anon-openswiss-04031ea54343b8db` | NEGATIVA | 148,5798 s |
| `anon-openswiss-0994a99dfb80e244` | POSITIVA | 147,9036 s |
| `anon-openswiss-0b899ac38ea25c6d` | INCONCLUSIVA | 123,4864 s |

Estado:

```text
concluídos: 3
pendentes: 84
gates temporais aprovados: 3/3
ground_truth_read: false
metrics_calculated: false
holdout_opened: false
```

As classes acima não são acertos ou erros até a abertura autorizada dos labels de
desenvolvimento após a conclusão das 87 predições.

## Testes

Após todas as alterações desta etapa:

```text
testes focados high-dimensional: 33 aprovados
suíte completa ARGOS: 555 aprovados
falhas: 0
avisos: 334 depreciações de dependências
```

## Próximo passo

Continuar o runner resumível até 87/87. Se qualquer caso exceder 180 segundos,
tiver saída inválida ou falhar tecnicamente, o batch deve parar e o protocolo não
pode ser avaliado parcialmente. Somente com todas as predições persistidas será
solicitada autorização específica para abrir os labels de desenvolvimento v13.
O holdout permanece fechado até que sensibilidade e especificidade de
desenvolvimento atinjam pelo menos 75% com estabilidade adequada.
