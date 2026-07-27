# OpenSwissHCC v16 — resultado do piloto temporal 4B

Data: 2026-07-16  
Estado: gate temporal projetado aprovado; full87 autorizado pelo protocolo v16  
Modelo: `google/medgemma-1.5-4b-it`  
Holdout: fechado

## 1. Revisão e protocolo

A galeria timing4 v1 foi aprovada pelo revisor `jm`.

- assinatura da revisão: `85f12f168cf39d7c9578e6e7aa2353c1d2fc6a5cdf8a77e0afd81116c1e2d188`;
- assinatura do protocolo de scoring: `92e51cf3c557908ca7ff92d8ab1087539986df6291f576a11338ca565bb4900e`;
- assinatura do plano temporal: `19ee2822d7eff5d5fd0ca0dea33d9f53ae87a898c3611cab83bd67d42c8622cf`.

## 2. Preflight sem inferência

Artefato:

`casos/qualification/openswisshcc_v1/timing/dev_v16_candidate_volume_timing4_preflight_v1/preflight.json`

Resultados:

- 4 casos regenerados;
- 10 stacks;
- hashes dos quatro casos idênticos aos bundles revisados;
- tempo total de preflight: 13,5647 s;
- inferência: não executada;
- ground truth: não lido;
- holdout: fechado.

Tempos de renderização:

| Cenário | Stacks | Renderização |
|---|---:|---:|
| fallback | 1 | 1,4595 s |
| um candidato | 1 | 1,2840 s |
| três candidatos | 3 | 3,6545 s |
| cinco candidatos | 5 | 6,9891 s |

## 3. Backend validado

O backend iniciou com:

- modelo: `google/medgemma-1.5-4b-it`;
- versão: MedGemma 1.5 4B Instruction-Tuned;
- quantização: bitsandbytes NF4;
- dispositivo: CUDA;
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU;
- contrato: `dtwin-medgemma-volume-score-v1`;
- método: `first_token_restricted_softmax_v1`;
- modo pesquisa e revisão humana obrigatória.

## 4. Execução temporal

Artefato:

`casos/qualification/openswisshcc_v1/timing/dev_v16_candidate_volume_timing4_run_v1/timing_report.json`

Foram realizadas exatamente 10 chamadas sequenciais, uma por stack, sem retry automático.

| Cenário | Stacks | Render | Scoring | Caminho fresco | Alinhamento + localizador históricos | Projeção total | Gate 180 s |
|---|---:|---:|---:|---:|---:|---:|---:|
| fallback | 1 | 1,3683 s | 19,7763 s | 21,1451 s | 42,0531 s | 63,1982 s | passou |
| um candidato | 1 | 1,4790 s | 16,3174 s | 17,7970 s | 49,4689 s | 67,2659 s | passou |
| três candidatos | 3 | 4,2091 s | 52,4540 s | 56,6637 s | 54,9910 s | 111,6547 s | passou |
| cinco candidatos | 5 | 8,6395 s | 94,8635 s | 103,5037 s | 50,6743 s | 154,1780 s | passou |

O lote completo levou 199,3585 s. Esse valor não é comparado ao gate, pois o limite é por caso.

O pior caso projetado terminou 25,8220 s abaixo de 180 s.

## 5. Auditoria do backend e das predições

- respostas HTTP 200 em `/score-volume`: 10;
- erros HTTP, traceback ou OOM: 0;
- predições completas: 4;
- resultados parciais publicados: 0;
- backend após o piloto: `ready`;
- hashes frescos dos casos: todos idênticos ao material revisado;
- ground truth lido: não;
- métricas calculadas: não;
- holdout aberto: não.

## 6. Interpretação correta do gate

O gate aprovado usa a fórmula congelada:

```text
tempo_projetado = tempo_historico_de_alinhamento_e_localizador
                + tempo_fresco_de_renderizacao_e_scoring
```

Assim:

- a viabilidade temporal projetada para full87 foi demonstrada;
- o full87 está autorizado pelo protocolo v16;
- o tempo fresco do leitor focal foi medido;
- uma execução completa a partir de DICOM cru ainda não foi medida do início ao fim;
- portanto, `full_pipeline_180_seconds_proven=false` permanece verdadeiro;
- nenhuma acurácia é declarada por este piloto.

## 7. Próxima etapa

1. executar a suíte completa após a implementação do runner;
2. construir o bundle full87 com os 84 casos registrados e os 3 fallbacks aprovados;
3. validar hashes, limites e completude;
4. gerar galeria de auditoria paginada para revisão humana;
5. congelar o protocolo full87 somente após a revisão;
6. executar o 4B sem labels;
7. congelar a avaliação antes de abrir os labels de desenvolvimento;
8. manter o holdout fechado.
