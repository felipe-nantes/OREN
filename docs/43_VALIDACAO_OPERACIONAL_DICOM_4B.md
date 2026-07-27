# Validação operacional DICOM do MedGemma 1.5 4B

Data da execução: 15/07/2026.

## Objetivo

Medir o fluxo real do exame individual, do início do worker após o upload até:

1. a disponibilidade de um `medgemma_report.json` validado;
2. a conclusão da tentativa de gerar o modelo 3D para revisão humana.

O limite pré-declarado é de 180 segundos por exame. Esta auditoria mede latência;
ela não substitui o benchmark de sensibilidade e especificidade.

## Diagnóstico dos benchmarks anteriores

| Execução | Coorte | Configuração | Resultado operacional |
|---|---:|---|---|
| `5839948e861b` | 5 negativos | `medgemma_local_4b.yaml` | 5 relatórios decisivos; média 129,97 s; máximo 150,29 s |
| `a68eaa274d05` | 5 negativos | `medgemma_local_4b.yaml` | 5 relatórios decisivos; média 117,90 s; máximo 127,10 s |
| `5cf8b271185c` | 20 casos | `medgemma_local_4b.yaml` | 20 falhas, principalmente segmentação; um timeout de 901,80 s |
| `62613fa9c74f` | 17 casos | `medgemma_local_4b.yaml` | 17 falhas de segmentação ou análise |
| `ac214f0838d3` | 1 positivo | `medgemma_local_4b_volumetric_rag.yaml` | relatório decisivo em 866,06 s; 815,55 s na inferência |

As execuções antigas demonstram que o 4B simples podia ficar abaixo de 180 s em
negativos, mas não provavam sensibilidade. O cenário volumétrico com RAG produziu
relatório, porém ultrapassou o limite por causa das múltiplas inferências.

## Instrumentação implementada

Cada exame individual passa a gerar atomicamente:

```text
case/outputs/operational_timing.json
```

Schema: `argos-operational-dicom-timing-v1`.

O manifesto registra:

- seleção e cópia da série;
- preparação e segmentação;
- espera e execução do subprocesso de screening;
- geração do painel, RAG e inferência informados pelo envelope MedGemma;
- tempo até relatório validado;
- geração do modelo 3D;
- tempo total;
- configuração e SHA-256;
- dispositivo de segmentação;
- etapa da falha, quando aplicável;
- gate exato de 180 segundos, sem decidir por valor arredondado.

Escopo do relógio:

- inicia no começo do worker, depois do upload;
- não inclui espera anterior ao início do worker;
- inclui espera pela trava serial do gateway MedGemma;
- `time_to_report` termina no JSON validado;
- `total_with_3d` termina após a tentativa do visualizador.

O artefato declara `ground_truth_read=false`, `raw_paths_persisted=false`,
`raw_uids_persisted=false`, uso exclusivo em pesquisa e revisão humana obrigatória.

## Smoke test real

Foi usado um único caso de `D:\rm_normais`, copiado para uma área temporária do
ARGOS. O diretório original não foi modificado. A configuração foi:

```text
configs/medgemma_local_4b_fast_pathology.yaml
SHA-256: 7631f5830761015021ea11f36187a7761f97b0398a485afa6695939962607541
```

Ela usa um painel `uniform_9`, recorte hepático, sem RAG e saída compacta. O
gateway confirmado foi `google/medgemma-1.5-4b-it`, NF4, CUDA, em uma RTX 4060.

| Medida | Execução 1 | Execução 2 |
|---|---:|---:|
| Seleção/cópia da série | 0,57 s | 0,67 s |
| Segmentação full-resolution | 45,18 s | 37,51 s |
| Geração do painel | 0,37 s | 0,36 s |
| Inferência MedGemma | 3,85 s | 3,43 s |
| Tempo até relatório | 51,28 s | 43,36 s |
| Modelo 3D | 2,04 s | 1,80 s |
| Total com 3D | 53,32 s | 45,17 s |
| Gate de relatório ≤180 s | passou | passou |
| Gate total com 3D ≤180 s | passou | passou |

Hashes dos manifestos de timing:

```text
execução 1: 0696586bb17faff3295e190610cb2a70e2f07bebfaf33078ccd606399a637ee5
execução 2: 2963dc3ff2854e6d2d34e8dee57d04c17c7cdcfa74ddcf7f9d9c91e810a9078f
```

## Resultado clínico experimental do smoke

Nas duas execuções, o MedGemma classificou o caso negativo como `POSITIVA`, com
confiança moderada. Isso é um falso positivo repetido e impede usar o cenário
rápido atual como configuração final, apesar do excelente tempo.

O caso isolado não fornece uma porcentagem de especificidade. Ele serve como
hard negative operacional e demonstra que a próxima alteração deve melhorar a
separação entre variante/estrutura vascular e lesão focal sem retornar às
múltiplas chamadas do modo volumétrico.

## Testes

Foram acrescentados testes para:

- limite exato em 180,0000 s e falha em 180,0001 s;
- relatório ausente sem aprovação do gate;
- durações negativas, infinitas ou `NaN` rejeitadas;
- persistência atômica;
- sucesso completo do worker DICOM;
- falha antes da segmentação;
- `WORKSPACE` relativo com artefato absoluto, regressão encontrada no primeiro smoke.

Antes da correção final, a suíte completa passou com 520 testes. Após a correção
do caminho relativo, os 37 testes focados passaram. A suíte completa final passou
com **521 testes**, zero falhas e 328 avisos de depreciação já conhecidos.

## Próximo gate

1. Executar um piloto balanceado de desenvolvimento com casos positivos e
   negativos, sem tocar no holdout público.
2. Comparar o cenário rápido atual com uma regra determinística/localizador já
   congelada, preservando uma única chamada 4B.
3. Só promover uma configuração se sensibilidade e especificidade forem ambas
   pelo menos 75%, com inconclusivos e falhas contados como erro.
4. Avaliar os 87 casos públicos apenas após autorização explícita para abrir os
   labels protegidos de desenvolvimento. O holdout permanece fechado.

