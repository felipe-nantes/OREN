# Qualificação MedGemma 4B — meta 75% / 180 segundos

## Objetivo e política de aceite

Este documento é o diário técnico da execução do plano de qualificação do ARGOS
com `google/medgemma-1.5-4b-it`.

O candidato somente pode ser promovido no webapp quando cumprir simultaneamente:

- sensibilidade maior ou igual a 75%;
- especificidade maior ou igual a 75%;
- falhas, timeouts, respostas inválidas e inconclusivos contados como erro;
- todos os casos do teste bloqueado com `medgemma_report.json` em até 180 segundos;
- zero vazamento de ground truth, máscara de lesão ou PHI para a inferência;
- intervalo de confiança de 95% e matriz de confusão reportados;
- revisão humana obrigatória preservada.

Os lotes já usados durante desenvolvimento não serão apresentados como validação
externa independente. Eles servem para depuração, seleção de configuração e
calibração. A configuração final deve ser congelada antes do teste público
bloqueado.

## Definição do relógio

O tempo principal começa depois que o upload foi recebido e termina quando o
`medgemma_report.json` válido é persistido atomicamente. O carregamento inicial do
servidor MedGemma é medido separadamente. A geração do visualizador 3D detalhado
pode continuar depois do relatório, mas seu estado deve permanecer explícito no
webapp.

Métricas de tempo obrigatórias: `p50`, `p90`, `p95`, máximo, segmentação,
representação visual, fila, geração, validação e total.

## Baseline auditado em 2026-07-13

- commit base: `6ee41c58b267f9a6f1f4afb3c8487f4993eeab04`;
- branch: `main`;
- modelo ativo: `google/medgemma-1.5-4b-it`;
- runtime: Transformers, CUDA, NF4;
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB;
- árvore de trabalho já continha alterações não versionadas antes desta etapa;
- 87 testes diretamente relacionados passaram antes da primeira alteração;
- nenhum arquivo DICOM, NIfTI, máscara ou dado de paciente será versionado.

Telemetria histórica disponível:

- 58 relatórios com tempo de screening;
- mediana: 53,5 segundos;
- P90: 340,4 segundos;
- 16 de 58 acima de 180 segundos;
- caso recente com oito painéis: 866,1 segundos totais, sendo 815,6 segundos de
  MedGemma e 12 gerações por causa de reparos de schema.

O comparativo histórico de 37 casos não é aceito como baseline clínico final por
misturar erro clínico e alta taxa de falha técnica. Ele permanece útil somente
para localizar gargalos.

## Fases de execução

1. Congelar baseline e criar auditoria segura dos datasets.
2. Tornar seleção de séries explícita, reproduzível e consciente de sequência.
3. Unificar e estabilizar webapp, backend e CLI.
4. Criar caminho de classificação curta e estruturada no MedGemma 4B.
5. Avaliar representação volumétrica compacta e segunda passagem condicional.
6. Executar piloto, otimizar apenas no desenvolvimento e congelar o candidato.
7. Executar uma única avaliação no conjunto bloqueado.

## Diário de alterações

### 2026-07-13 — Fundação da qualificação

Motivo:

- o seletor atual privilegia quantidade de cortes, sem provar que a série escolhida
  é a evidência hepática mais informativa;
- positivos e negativos possuem distribuições diferentes de sequências;
- é necessário detectar esse viés antes de atribuir erros ao MedGemma.

Alterações:

- criado `dtwin/benchmark/dataset_audit.py`;
- criado `tools/audit_liver_mri_dataset.py`;
- criados testes em `tests/test_dataset_audit.py`;
- a auditoria lê somente tags técnicas autorizadas;
- UIDs e nomes de diretório são persistidos apenas como SHA-256;
- descrições livres, caminhos, PatientName, PatientID e demais PHI não são
  persistidos;
- séries com o mesmo UID e ecos diferentes são separadas;
- são calculados orientação, matriz, spacing, duplicações, não uniformidade,
  sequência provável, elegibilidade e score técnico;
- o relatório compara a distribuição de sequências entre labels e emite alerta de
  possível confusão por protocolo.

Comando planejado para os lotes locais:

```powershell
python -m tools.audit_liver_mri_dataset `
  --positive-root "D:\lote_positivo_1_real" `
  --negative-root "D:\rm_normais" `
  --out "casos\qualification\dataset_audit_v1.json"
```

O arquivo gerado permanece fora do Git por estar sob `casos/`.

Testes e resultado desta alteração serão registrados após a execução.

Resultado intermediário:

- o primeiro ciclo executou três testes sintéticos;
- dois passaram;
- um revelou que o score técnico, isoladamente, ainda permitia uma série CT axial
  com muitos cortes;
- corrigido o gate para exigir explicitamente `Modality == MR`, além do score e
  da quantidade mínima de cortes;
- o teste foi mantido como regressão permanente.

Resultado final da fundação:

- `3 passed` em `tests/test_dataset_audit.py`;
- auditoria real concluída em 33 casos: 17 positivos e 16 negativos;
- todos os casos possuem ao menos uma série tecnicamente elegível;
- o scanner de segurança não encontrou caminho de drive, identificador TCGA,
  campo PatientName/PatientID ou UID DICOM bruto no JSON sanitizado;
- relatório local: `casos/qualification/dataset_audit_v1.json` (ignorado pelo Git).

Distribuição observada:

| Label protegido | Sequência normalizada | Séries elegíveis |
|---|---|---:|
| positivo | T1 inespecífico | 8 |
| positivo | T1 pós-contraste | 6 |
| positivo | T1 tardio | 2 |
| positivo | T1 portal | 1 |
| negativo | T1 in-phase | 16 |
| negativo | T1 out-phase | 16 |
| negativo | T2 | 16 |

Decisão metodológica:

- confirmado `sequence_distribution_differs_between_labels`;
- a diferença é um confundidor forte: um classificador pode aprender origem e
  protocolo em vez de patologia;
- os 33 casos serão usados para desenvolvimento e análise estratificada;
- não serão usados isoladamente como prova externa dos 75%;
- a seleção de série passará a ser explícita no manifesto, nunca apenas “a maior
  série”.

### 2026-07-13 — Seletor de séries v1

Alterações:

- adicionado `select_best_mr_series` ao módulo de auditoria;
- a seleção separa ecos diferentes mesmo quando compartilham SeriesInstanceUID;
- modalidade MR é requisito absoluto;
- o desempate usa score técnico, prioridade de sequência, quantidade de frames e
  hash da série;
- o webapp deixou de escolher automaticamente apenas a série com mais arquivos;
- exame individual e benchmark web persistem `outputs/series_selection.json`;
- o sidecar contém somente categorias, hashes e geometria sanitizada;
- caminhos locais, UIDs e descrições livres não são persistidos.

Compatibilidade:

- a função pública `find_best_series` mantém o retorno legado `(files, slices)`;
- DICOM multiframe continua suportado pelo contador `NumberOfFrames`;
- CT continua rejeitado para o perfil hepático de RM.

Teste de integração:

- o primeiro ciclo encontrou incompatibilidade com séries sintéticas mínimas de
  cinco cortes usadas pelos testes legados;
- mantido o gate rígido de 16 cortes na auditoria de qualificação;
- o seletor operacional passou a respeitar o `MIN_SLICES` do chamador, preservando
  compatibilidade, enquanto modalidade MR permanece obrigatória;
- gates posteriores de ingestão e segmentação continuam responsáveis por rejeitar
  volume tridimensional inviável.
- um segundo ciclo encontrou SeriesInstanceUID reutilizado entre CT e MR no gerador
  sintético; modalidade foi adicionada à chave de agrupamento, impedindo que um
  export defeituoso misture modalidades numa única série lógica.

Validação:

- `33 passed` em `tests/test_dataset_audit.py` + `tests/test_webapp.py`;
- auditoria real regenerada com 33 casos e o mesmo alerta de distribuição;
- nenhum caso real perdeu elegibilidade após o endurecimento;
- o novo seletor ainda não altera labels, pixels, segmentação ou prompt.

### 2026-07-13 — Gate de regressão antes da otimização

Validação:

- executada a suíte completa antes de alterar o formato de resposta do modelo;
- resultado: `316 passed`, nenhuma falha, em 7,48 segundos;
- os avisos observados são de depreciações já existentes em SimpleITK, scikit-image,
  VTK e Starlette e não alteraram o resultado dos testes;
- este resultado passa a ser o ponto de comparação funcional da etapa de latência.

### 2026-07-13 — Caminho rápido experimental v1

Problema atacado:

- o modo volumétrico chegou a executar oito painéis e doze gerações completas em
  um único caso devido a reparos de schema;
- o relatório solicitado ao modelo continha treze campos e texto livre extenso;
- uma falha de JSON repetia toda a inferência, tornando impossível sustentar o
  limite de três minutos.

Alterações:

- adicionado `response_mode`, com padrão retrocompatível `full_report`;
- criado o modo isolado `compact_classification`;
- nesse modo o MedGemma retorna somente classe, confiança, três flags clínicas,
  tipo de alteração não alvo e uma evidência visual curta;
- os campos legados administrativos são expandidos deterministicamente, sem
  inventar localização, diagnóstico ou síntese clínica;
- o relatório expandido atravessa novamente o validador clínico e as regras de
  segurança já existentes;
- `POSITIVA` sem `ha_lesao_focal_suspeita=true` é rejeitada;
- `NEGATIVA` com `ha_lesao_focal_suspeita=true` é rejeitada;
- a auditoria registra `response_mode` e `deterministic_report_expansion`;
- criada `configs/medgemma_local_4b_fast_pathology.yaml` com um painel `uniform_9`,
  sem RAG, 256 tokens, timeout de 120 segundos e zero retry de validação;
- `fast_pathology` foi autorizado somente no benchmark. O modo ainda não foi
  exposto no exame individual porque não foi qualificado;
- configs e cenários anteriores permaneceram inalterados e selecionáveis.

Validação:

- `85 passed` em cliente MedGemma, orquestração e webapp;
- incluídos testes de expansão determinística, contradição clínica, limites da
  configuração e autorização explícita do cenário;
- ainda não há alegação de ganho de tempo ou acurácia: isso depende do piloto real.

### 2026-07-13 — Runner DICOM unificado

Problema atacado:

- o webapp já isolava uma série antes da segmentação, mas o runner CLI/backend
  entregava a pasta DICOM inteira ao `Engine`;
- em estudos com múltiplas séries, os dois caminhos podiam segmentar volumes
  diferentes e produzir resultados incomparáveis.

Alterações:

- `prepare_inference_case` passou a usar o mesmo `select_best_mr_series` do webapp;
- somente a série MR selecionada é materializada em diretório temporário;
- os DICOMs temporários são apagados mesmo quando a preparação falha;
- nenhum DICOM bruto é copiado para o diretório final do benchmark;
- o manifesto sanitizado do runner recebe `series_selection`, com hashes,
  geometria, classe de sequência e score, sem caminhos, UID bruto ou PHI;
- seleção continua independente de label e ground truth.

Falha encontrada durante os testes:

- o primeiro teste consultava `modality` diretamente na raiz do sidecar, mas o
  schema versionado contém a lista `selected_series`;
- a asserção foi corrigida para verificar o contrato real sem alterar o código de
  produção.

Validação:

- `53 passed` nos importadores, runner, CLI, auditoria e webapp;
- o teste DICOM confirma a seleção MR, seis arquivos e remoção do staging temporário.
