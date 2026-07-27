# Gd-EOB-DTPA HBP — aquisição e preflight label-blind

## Decisão metodológica

A nova coorte pública foi incorporada somente como candidata a validação
externa de:

```text
HCC versus tumor hepático não-HCC
```

Ela não mede lesão versus fígado saudável. Todos os 220 pacientes possuem tumor
hepático visível. Assim, `NEGATIVE` significa `non_hcc_liver_tumor`, nunca
normalidade clínica.

O contrato anterior
`configs/benchmark/v23_external_validation_contract_v1.json`, cujo alvo é
`focal_liver_lesion_suspicion`, foi preservado sem alteração. O novo contrato é:

```text
configs/benchmark/v23_external_hcc_hbp_contract_v1.json
```

Assinatura:

```text
5fd26d5ffaf8884ef7260492de2ef7da560b2e79e91785b82c296cec6281982b
```

## Fonte fixada

```text
dataset_id: gd_eob_dtpa_phlf_2026
Zenodo record: 18622298, revisão 3
DOI: 10.5281/zenodo.18622298
artigo: 10.1038/s41597-026-07483-x
licença: CC BY 4.0
arquivo: PHLF.zip
bytes: 1.345.046.539
MD5 publicado: 0bd127e0e144b3ed3d75432d70963865
```

O inventário esperado e congelado é:

```text
Center1: 88 imagens HBP
Center2: 94 imagens HBP
Center3: 38 imagens HBP
total: 220
HCC informado pela publicação: 164
não-HCC informado pela publicação: 56
```

## Separação de segurança

O arquivo Zenodo reúne no mesmo ZIP:

- imagens HBP;
- máscaras de fígado;
- segmentos de Couinaud;
- máscaras tumorais;
- outras anotações anatômicas;
- planilhas clinicopatológicas.

O extrator ARGOS aceita exclusivamente:

```text
PHLF/CenterN/Image/<id>.nii.gz
```

Os payloads de `Annotation_*` e das planilhas clinicopatológicas não são
abertos nem extraídos. O resultado local é fisicamente separado:

```text
acquisition_v1/
  image_only/
    collection.json
    image_cases.jsonl
    images/
  protected_source/
    archive_inventory.json
    source_mapping.jsonl
  separation_manifest.json
```

Somente `image_only/` poderá ser entregue às próximas etapas. A pasta
`protected_source/` não contém labels ou máscaras; contém apenas o inventário
e o mapeamento necessário para uma futura vinculação protegida.

Cada caso recebe identificador anônimo determinístico. IDs originais não
aparecem no manifesto destinado à inferência. Cada imagem é verificada por:

- SHA-256 e quantidade de bytes;
- formato NIfTI tridimensional;
- shape, espaçamento e orientação válidos;
- unicidade de caso, caminho e fingerprint;
- correspondência exata com 88/94/38 casos por centro.

## Proteções fail-closed

O fluxo aborta se:

- registro, licença, nome, tamanho ou MD5 do Zenodo divergirem;
- o ZIP possuir caminho absoluto, travessia, duplicação ou membro inesperado;
- não houver exatamente 220 imagens e a distribuição 88/94/38;
- uma imagem estiver ausente, corrompida ou não for volume 3D;
- máscara, anotação, label ou planilha aparecer na raiz `image_only`;
- o baseline v23 ou o novo contrato estiver adulterado;
- houver tentativa de sobrescrever uma coleção já publicada.

O manifesto registra explicitamente:

```text
labels_read=false
lesion_masks_read=false
anatomical_annotations_used=false
protected_payloads_read=false
```

## Limite desta etapa

Concluir a aquisição não libera a inferência dos 220 casos. Ela libera somente
um piloto técnico label-blind. Antes da inferência completa ainda será
necessário provar que a entrada HBP isolada mantém o significado dos sinais da
v23 e congelar o adaptador de representação.

O arquivo de readiness deverá permanecer:

```text
ready_for_technical_pilot=true
ready_for_full_inference=false
blocking_gate=hbp_representation_and_v23_signal_compatibility_not_yet_frozen
```

## Comandos reproduzíveis

Verificar metadados públicos:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_gd_eob_hcc_external.py verify-metadata
```

Congelar/verificar o contrato:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_gd_eob_hcc_external.py `
  freeze-contract `
  --out configs\benchmark\v23_external_hcc_hbp_contract_v1.json
```

Após o download integral e verificável do arquivo público:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_gd_eob_hcc_external.py `
  extract-image-only `
  --contract configs\benchmark\v23_external_hcc_hbp_contract_v1.json `
  --archive data\raw\gd_eob_dtpa_2026\quarantine\PHLF.zip `
  --out casos\qualification\gd_eob_hcc_external_v1\acquisition_v1
```

Verificação independente:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_gd_eob_hcc_external.py `
  verify-image-only `
  --contract configs\benchmark\v23_external_hcc_hbp_contract_v1.json `
  --image-root casos\qualification\gd_eob_hcc_external_v1\acquisition_v1\image_only
```

Nenhum comando desta etapa lê a planilha clinicopatológica ou as máscaras
publicadas.

## Resultado executado

A aquisição real foi concluída e verificada:

```text
PHLF.zip bytes: 1.345.046.539
PHLF.zip MD5: 0bd127e0e144b3ed3d75432d70963865
PHLF.zip SHA-256: f275ecaa71c01aaa7a72a492c9d84a2b9c1f8b9db03f40c7c7d91f96c8947f44
membros totais do ZIP: 1.340
imagens HBP extraídas: 220
membros protegidos não extraídos: 1.098
membros inesperados: 0
Center1/Center2/Center3: 88/94/38
```

Assinaturas:

```text
inventário do arquivo:
ade9920d155e27e6c49387421299b7646e5ce0689be78365e3bbc0c03f6f9de3

coleção image-only:
5cbc71168f409158903694467e872e070ca752bb2b6f2673dfd82b42c0eb876c

manifesto de imagens:
f99d08accfb7ca3875f83e8bf4d40ea5dab045c35aeaaa03006573c0c0cc83c3

readiness do piloto:
d1e233b8eecff57d9383b3eb6148a36ee57c9cf93d1db7be25321e855cf05e63
```

Todos os 220 headers NIfTI foram reabertos por verificação independente e
corresponderam a shape, espaçamento e orientação persistidos. O estado final é:

```text
aquisição pública: concluída
separação image-only: concluída
labels abertos: não
máscaras de lesão abertas: não
anotações anatômicas usadas: não
piloto técnico label-blind: liberado e posteriormente executado
inferência completa: bloqueada
```

O resultado do piloto e o gate de compatibilidade com a v23 estão documentados
em `docs/109_GD_EOB_HBP_PILOTO_COMPATIBILIDADE_V23.md`.

Testes focados do novo fluxo e das proteções v23:

```text
38 passed
```
