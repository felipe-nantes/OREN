# V21 — preparação real do LiverHccSeg

## Resultado desta etapa

O braço positivo da coorte pública independente foi materializado e está pronto
para geração cega de painéis. Nenhuma inferência foi executada e nenhum label do
holdout OpenSwissHCC foi aberto.

```text
sujeitos documentados: 17
sujeitos com tumor segmentado: 14
sujeitos sem tumor segmentado: 3
séries DICOM MR no registry bruto: 285
séries DICOM dos 14 positivos: 247
casos NIfTI cegos preparados: 14
```

Os três sujeitos sem tumor segmentado foram excluídos. Eles não foram chamados de
negativos, pois incluem histórico de HCC/tratamento e alterações pós-terapêuticas.

## Integridade dos downloads

Fonte oficial: `https://zenodo.org/records/8179129`, versão 1.1, CC BY 4.0.

```text
dicoms.zip
MD5 oficial/observado: 1ff9f35e77d2892909dd2c67eea196b3
SHA-256: ee2e1f6c3d919039e85690344b041c0780475b664b9197fe6a8aab2559437a7e

nifti_and_segms.zip
MD5 oficial/observado: 4382ae1301b68ab60c05de306a1e43ec
SHA-256: 8b2c20df9b0235d722eba235d2d9803be13326eaf8919a3b27729704a3b9e010

LiverHccSeg_MetaData_v1.1.xlsx
MD5 oficial/observado: 37806f09955aa198ab8e50e0e2929da7
SHA-256: c8e7ae9ca77e1c58f72f0da841b7ac0ba1a9dc88ce47fe454e1aa3715e2e0dc4
```

Todos os ZIPs foram verificados contra path traversal antes da extração. Os dados
e artefatos derivados permanecem sob `data/`, fora do Git.

## Filtro protegido

`dtwin/datasets/liverhccseg_labels.py` lê a planilha oficial sem dependência de
Excel/openpyxl. Ele exige os hashes e contagens congelados e produz:

- `data/registry/liverhccseg_tumor_positive.jsonl`;
- `data/registry/protected/liverhccseg_selection_audit.json`.

O audit contém apenas hashes dos identificadores públicos e registra:

```text
included_tumor_subject_count: 14
excluded_non_tumor_subject_count: 3
excluded_subjects_not_assumed_negative: true
ground_truth_available_to_inference: false
filtered_registry_sha256: b4cc9791d9e9fef173ebcba9d04d8b028bf6645559a399bd451a07dc1afb099f
```

## Escolha DICOM versus NIfTI

O DICOM bruto foi auditado, mas suas descrições são heterogêneas: apenas duas
séries foram classificadas explicitamente como arteriais e duas como portais;
grande parte ficou como T1 pós-contraste ou não especificada. Selecionar fases
apenas pelo texto DICOM criaria erro sistemático.

O pacote NIfTI v1.1 possui quatro fases registradas e padronizadas. A preparação
usa:

```text
t1_native   <- art_pre.nii.gz
t1_arterial <- art.nii.gz
t1_venous   <- art_pv.nii.gz
t1_delayed  <- art_del.nii.gz
liver_mask  <- rater1_liver.nii.gz
```

Nenhum arquivo `tumor*` ou `lesion*` é copiado ou vinculado.

## Correção geométrica

Nos 14 sujeitos, arterial e máscara hepática compartilham a mesma grade. As
demais fases registradas possuem direção/origem NIfTI diferentes. A preparação:

1. usa a arterial como referência;
2. reamostra pré, venosa e tardia por coordenadas físicas;
3. usa interpolação linear somente nas intensidades;
4. não reamostra a máscara hepática;
5. exige cobertura de pelo menos 95% dos voxels hepáticos em cada fase;
6. publica atomicamente somente se todos os 14 casos passarem.

## Preflight real

```text
cohort_signature:
7356d3bdfea9747bff726781a0694c610d019d0ea0738f502316871162ff250d

status: ready_for_blind_panel_generation
all_file_hashes_passed: true
all_geometries_passed: true
minimum_liver_support_passed: true
lesion_masks_present: false
pathology_labels_present: false
holdout_opened: false
```

## Próximo gate

O protocolo v11 combina três sinais: MedGemma, MedSigLIP e volume do localizador.
Não deve ser reduzido a uma única configuração MedGemma. Para reproduzi-lo de
forma independente ainda é necessário:

1. aceitar explicitamente as regras/licença CHAOS e baixar o treino oficial;
2. preparar pelo menos 15 controles MRI CHAOS sem lesão;
3. unir os casos positivos e negativos mantendo dataset/label fora do modelo;
4. gerar e revisar uma galeria técnica cega;
5. congelar os três sinais e o tempo máximo de 180 segundos;
6. executar a inferência 4B sem abrir labels;
7. abrir labels somente após todas as respostas e hashes estarem congelados.

O v21 continuará sendo teste de generalização/estresse. A correlação entre
dataset e classe deverá ser reportada e impede que o resultado isolado seja
tratado como validação clínica definitiva.

## Atualização: calibrador e painéis reais

O próximo gate foi parcialmente concluído sem abrir novos labels:

```text
calibrador externo v11:
  assinatura: cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181
  limiar congelado: 0,5241379310344827
  pesos: MedGemma 0,40; MedSigLIP 0,40; localizador 0,20
  holdout aberto: não

painéis LiverHccSeg:
  casos: 14
  representação: multiphase RGB uniform_9
  assinatura: c60473f82cb5aecae88ee1e1b7916f9ab7697aca3235b7806e77d38da64c6b5d
  máscaras de lesão usadas: não
  labels usados: não
  elegíveis para inferência: não, pendentes de revisão humana
```

O CHAOS deixou de ser requisito para executar o braço positivo. Ele não possui
as mesmas fases DCE e, caso seja usado futuramente, será reportado apenas como
estresse secundário de especificidade sob mudança de domínio.
