# Adaptador multifásico do benchmark cego interno

## Estado

Implementado e validado sem executar inferência real ou carregar GPU.

O adaptador permite que o fluxo visual da Etapa C use diretamente:

```text
ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1/
  webapp_input/
    ARGOS-BLIND-0001/
      series_001/volume.dcm
      series_002/volume.dcm
      ...
```

Não é necessário copiar, renomear ou reorganizar os DICOMs como
`arterial/venous/delayed`.

## Resolução das fases

Para identificadores no formato `ARGOS-BLIND-####`, o backend consulta somente
o índice autorizado:

```text
ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1/
  private_reference/
    conversion_audit.json
```

As funções aceitam:

```text
t1_arterial ou t1_arterial_ttc_1 → t1_arterial
t1_venous                         → t1_venous
t1_delayed                        → t1_delayed
```

O número da série é transformado deterministicamente em `series_###`. Caminhos
privados presentes no índice nunca são usados como entrada e nunca são
persistidos.

## Gates de segurança

Antes da segmentação ou do MedSigLIP, cada uma das três séries precisa passar:

1. identificador cego autorizado;
2. exatamente uma série por fase;
3. diretório `series_###` único e contido no diretório recebido;
4. presença de `volume.dcm`;
5. SHA-256 idêntico ao índice autorizado;
6. `PatientID` igual ao identificador cego;
7. modalidade DICOM `MR`;
8. `SeriesNumber` idêntico ao índice.

Ausência, ambiguidade ou divergência interrompe somente o caso como falha
técnica. Nenhuma fase é adivinhada.

O preflight label-blind do índice separa previamente os casos elegíveis dos
casos sem o trio obrigatório. Na coleção v1, a estrutura esperada é 100 casos
elegíveis e 20 inelegíveis; os 20 não devem ser iniciados como se fossem falhas
de GPU.

## Isolamento

O navegador não pode enviar o caminho do índice. Ele vem apenas da configuração
server-side `WEBAPP_VISUAL_AUTHORIZED_PHASE_AUDIT`, cujo padrão aponta para a
coleção interna.

O manifesto seguro persistido contém somente:

- caso cego;
- números e hashes das três séries selecionadas;
- hash do índice;
- declaração de que labels e máscaras de lesão não foram lidos;
- declaração de que caminhos e identificadores privados não foram persistidos.

Não chegam aos painéis nem ao MedSigLIP:

- `source_path_private`;
- identificadores originais;
- labels;
- máscaras de lesão;
- justificativas de seleção.

## Compatibilidade

O comportamento anterior continua disponível:

- casos comuns usam `caso/arterial`, `caso/venous` e `caso/delayed`;
- casos `ARGOS-BLIND-####` usam o adaptador autorizado;
- ambos convergem para o mesmo `build_multiphase_case`;
- segmentação venosa, harmonização física, painéis liver-enriched, embeddings e
  classificador permanecem inalterados.

Também foi corrigida a finalização do benchmark visual: ela agora registra
`model_family=MedSigLIP` e não tenta resolver uma configuração MedGemma
inexistente.

## Verificação realizada

Foram usados apenas DICOMs sintéticos nos testes. Nenhum caso real foi
segmentado, harmonizado, renderizado ou enviado ao MedSigLIP nesta etapa.

Cobertura dos testes:

- resolução correta das três fases opacas;
- estrutura adicional preservada pelo upload do webapp;
- índice incompleto;
- fase arterial ambígua;
- hash divergente;
- identidade DICOM divergente;
- identificador não autorizado;
- ausência de caminhos privados no manifesto seguro;
- entrada explícita das fases na ingestão existente;
- regressão das pastas `arterial/venous/delayed`;
- finalização do benchmark visual sem configuração MedGemma.

## Próximo gate

O próximo operador deve executar um único caso elegível com GPU, sem abrir
labels nem máscaras de lesão, e confirmar:

```text
DICOM opaco
→ adaptador autorizado
→ segmentação venosa
→ harmonização arterial/tardia
→ painéis liver-enriched
→ MedSigLIP
→ relatório visual
```

Foi adicionado um launcher label-blind que reutiliza diretamente a
orquestração do webapp:

```powershell
.\.venv-win\Scripts\python.exe -m tools.run_internal_blind_visual_case `
  --preflight-only `
  --dataset-root ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1 `
  --out casos\webapp\internal_blind_multiphase_preflight.json

.\.venv-win\Scripts\python.exe -m tools.run_internal_blind_visual_case `
  --case-id auto `
  --dataset-root ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1 `
  --workspace casos\webapp `
  --out casos\webapp\smoke_internal_blind_0001.json
```

O launcher não recebe label, não abre `blind_labels.csv` e não procura máscara
de lesão. O arquivo de saída é um resultado operacional de um caso, não um
relatório de métricas.

Essa execução real foi intencionalmente deixada pendente para o próximo
operador.
