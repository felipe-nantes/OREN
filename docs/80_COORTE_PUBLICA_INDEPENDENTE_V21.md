# Etapa v21 — coorte pública independente

## Estado e propósito

Os protocolos v19 e v20 não atingiram simultaneamente sensibilidade e
especificidade de 75%. O melhor sinal observado nos 87 casos de desenvolvimento
continua sendo o v11, com 74,36% de sensibilidade e 75,00% de especificidade.

Continuar ajustando pesos ou limiares nesses mesmos 87 casos aumentaria o risco
de sobreajuste. A etapa v21 cria uma coorte pública independente para testar se o
pipeline generaliza antes de qualquer abertura do holdout OpenSwissHCC.

O holdout OpenSwissHCC permanece fechado.

## Desenho inicial

O piloto v21 foi definido com:

- LiverHccSeg: casos positivos de HCC em RM multifásica;
- CHAOS MRI: controles anatômicos sem tumor/lesão documentada;
- inclusão de todos os sujeitos elegíveis encontrados nos registries;
- agrupamento de todas as séries do mesmo sujeito antes da inferência;
- mínimo técnico inicial de 14 sujeitos positivos e 15 negativos;
- segmentação e inferência sem acesso a labels ou máscaras de lesão;
- revisão humana obrigatória e uso exclusivo em pesquisa.

Essa composição possui uma limitação metodológica importante: positivos e
negativos vêm de datasets diferentes. O modelo pode explorar diferenças de
scanner, protocolo, resolução ou organização dos dados em vez de patologia. Por
isso, o v21 é um teste externo de generalização/estresse e **não é, sozinho,
evidência final de desempenho publicável**.

## Artefatos implementados

O módulo `dtwin/benchmark/public_independent_cohort.py` produz uma pasta
imutável com:

```text
cohort_protocol.json
inference_manifest.jsonl
operational_source_map.jsonl
protected_ground_truth/
  protected_labels.jsonl
  selection_audit.json
```

### Manifesto cego

`inference_manifest.jsonl` contém apenas `case_id` pseudonimizado, formato,
quantidades, SHA-256 e salvaguardas. Não contém dataset, classe, label, subtipo,
phenotype tag, diagnóstico, anotação ou caminho de máscara.

### Mapa operacional

`operational_source_map.jsonl` mapeia o caso cego para caminhos locais. É
necessário para o executor, mas possui `never_send_to_model=true` e nunca pode ser
incorporado ao prompt ou ao painel. Os roots usam aliases opacos.

### Labels protegidos

`protected_ground_truth/protected_labels.jsonl` contém label, dataset, subtipos e
caminhos de anotações. Só poderá ser interpretado depois que todas as respostas e
hashes estiverem persistidos e o protocolo de avaliação estiver congelado.

### Protocolo

`cohort_protocol.json` vincula por SHA-256 os três manifestos e os registries de
origem. Também registra `holdout_opened=false` e uma assinatura canônica.

## Preflight fail-closed

`verify_public_independent_cohort` verifica antes da inferência:

- assinatura e hashes exatos;
- igualdade e ordem dos casos;
- ausência de campos protegidos no manifesto cego;
- roots e caminhos autorizados;
- SHA-256, contagem e tamanho dos arquivos médicos;
- salvaguardas de pesquisa e revisão humana;
- confirmação de que o holdout não foi aberto.

O preflight calcula o hash em bytes dos labels protegidos, mas não interpreta seu
conteúdo. A saída registra `protected_labels_parsed=false`.

## Preparação dos registries

As imagens LiverHccSeg v1.1 já foram obtidas e verificadas. A planilha pública de
metadados (12,9 kB) teve o MD5 oficial confirmado como
`37806f09955aa198ab8e50e0e2929da7`. A leitura científica contém 17 sujeitos: 14
com tumor segmentado e três sem tumor residual segmentado. Os três últimos não
são assumidos como negativos saudáveis e ficam excluídos, pendentes de eventual
curadoria específica.

Os pacotes oficiais verificados foram:

```text
dicoms.zip
  bytes: 1.654.145.915
  MD5: 1ff9f35e77d2892909dd2c67eea196b3
  SHA-256: ee2e1f6c3d919039e85690344b041c0780475b664b9197fe6a8aab2559437a7e

nifti_and_segms.zip
  bytes: 977.885.191
  MD5: 4382ae1301b68ab60c05de306a1e43ec
  SHA-256: 8b2c20df9b0235d722eba235d2d9803be13326eaf8919a3b27729704a3b9e010
```

O pacote NIfTI foi usado para a preparação cega porque oferece fases registradas
e padronizadas (`art`, `art_pre`, `art_pv`, `art_del`). As máscaras tumorais
permanecem exclusivamente na origem protegida e não são copiadas ou vinculadas.

Para reproduzir o registry DICOM positivo:

```powershell
$env:ARGOS_LIVERHCCSEG_ROOT = 'D:\datasets\LiverHccSeg'
$env:ARGOS_CHAOS_MRI_ROOT = 'D:\datasets\CHAOS_MRI'

.\.venv-win\Scripts\python.exe -m dtwin.datasets.ingest `
  --config configs/datasets/liverhccseg.yaml `
  --root $env:ARGOS_LIVERHCCSEG_ROOT `
  --out data/registry/liverhccseg.jsonl

.\.venv-win\Scripts\python.exe tools/filter_liverhccseg_tumor_positive.py `
  --registry data/registry/liverhccseg.jsonl `
  --metadata data/metadata/LiverHccSeg_MetaData_v1.1.xlsx `
  --out data/registry/liverhccseg_tumor_positive.jsonl `
  --audit data/registry/protected/liverhccseg_selection_audit.json

.\.venv-win\Scripts\python.exe -m dtwin.datasets.ingest `
  --config configs/datasets/chaos_mri.yaml `
  --root $env:ARGOS_CHAOS_MRI_ROOT `
  --out data/registry/chaos_mri.jsonl
```

O root deve estar no nível em que o primeiro diretório corresponde ao sujeito.
Assim, `subject_path_components: 1` agrupa todas as séries do participante. Uma
galeria técnica deverá confirmar esse agrupamento antes do freeze definitivo.

### Preparação cega LiverHccSeg

```powershell
.\.venv-win\Scripts\python.exe tools/prepare_liverhccseg_v21.py `
  --source data/raw/LiverHccSeg_v1.1/nifti_and_segms/nifti_and_segms `
  --selection-audit data/registry/protected/liverhccseg_selection_audit.json `
  --out data/prepared/liverhccseg_v21_blind `
  --expected-case-count 14
```

As fases pré, portal/venosa e tardia são reamostradas fisicamente para a grade
arterial. A máscara hepática permanece inalterada. Cada fase precisa cobrir pelo
menos 95% dos voxels hepáticos. O preflight real resultou em:

```text
status: ready_for_blind_panel_generation
casos: 14/14
assinatura: 7356d3bdfea9747bff726781a0694c610d019d0ea0738f502316871162ff250d
hashes: aprovados
geometrias: aprovadas
máscaras de lesão: ausentes
labels patológicos: ausentes
holdout: fechado
```

O CHAOS ainda não foi baixado. O download oficial está sob CC BY-NC-SA 4.0 e
implica aceitação das regras do desafio; essa aceitação precisa ser autorizada
explicitamente pelo responsável do projeto.

## Construção e verificação

```powershell
.\.venv-win\Scripts\python.exe tools/build_public_independent_cohort_v21.py `
  --config configs/benchmark/public_independent_v21.yaml `
  --out data/qualification/public_independent_v21
```

Guardar a assinatura impressa e executar o preflight completo:

```powershell
.\.venv-win\Scripts\python.exe tools/build_public_independent_cohort_v21.py `
  --config configs/benchmark/public_independent_v21.yaml `
  --out data/qualification/public_independent_v21 `
  --verify-only `
  --expected-signature ASSINATURA_GERADA
```

Não usar `--skip-source-rehash` numa rodada qualificatória. Essa opção é apenas
diagnóstica e produz `source_integrity_passed=false`.

## Gates antes da inferência 4B

1. Registries somente com MR e salvaguardas de pesquisa válidas.
2. Cada sujeito exatamente uma vez, contendo todas as séries elegíveis.
3. Exatamente os 14 positivos LiverHccSeg documentados e pelo menos 15 negativos
   CHAOS no piloto inicial.
4. Galeria técnica com fígado visível, orientação correta, crop não destrutivo e
   ausência de PHI visível.
5. Nenhuma máscara tumoral na pasta ou workspace de inferência.
6. Preflight com `ready_for_blind_inference`.
7. Painel, prompt, modelo 4B, agregação e timeout congelados antes da primeira
   resposta.

## Avaliação futura

Somente após a inferência completa e congelada será permitido abrir os labels. O
relatório deverá incluir sensibilidade, especificidade, IC 95%, matriz de
confusão, inconclusivos como erro, tempo por caso/P95, métricas por dataset e
sequência e análise de confusão por domínio. Os pesos não serão ajustados com os
labels v21.

Mesmo se v21 atingir 75%/75%, o holdout OpenSwissHCC só poderá ser aberto depois
de demonstrar que o ganho não decorre apenas da identidade do dataset.

## Correção metodológica após auditoria das sequências

Após materializar o braço LiverHccSeg, a documentação primária dos datasets foi
reavaliada. O CHAOS MRI disponibiliza T1-DUAL em fase/fora de fase e T2-SPIR,
mas não o conjunto DCE pré-contraste, arterial, portal/venoso e tardio usado pelo
LiverHccSeg e pelo protocolo v11. Portanto:

- LiverHccSeg v21 é o braço externo primário de **sensibilidade**;
- CHAOS, se baixado após aceitação explícita dos termos, será apenas um braço
  secundário de estresse de **especificidade sob mudança de domínio**;
- os dois braços não podem ser combinados em uma matriz de confusão primária;
- o Duke Liver Dataset também não resolve a lacuna: possui RM multifásica, mas
  seus labels públicos são de tipo de série e máscaras do fígado, não ground
  truth de presença/ausência de lesão;
- a demonstração final simultânea de sensibilidade e especificidade permanece
  reservada ao holdout OpenSwissHCC, depois de inferência cega e autorização
  explícita para abrir seus labels.

O arquivo `configs/benchmark/public_independent_v21.yaml` foi mantido apenas
como desenho secundário de estresse e agora registra
`combined_primary_metric_allowed: false`.

## Testes desta etapa

Foram cobertos isolamento de labels, agrupamento por sujeito, determinismo,
hashes, adulteração de manifesto/fonte, papéis divergentes, path traversal,
tamanho mínimo, recusa de sobrescrita e preflight sem interpretar labels.

Resultado da suíte completa após esta etapa: `768 passed`.
