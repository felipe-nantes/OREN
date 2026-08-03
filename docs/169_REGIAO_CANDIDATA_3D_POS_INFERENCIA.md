# Região candidata 3D pós-inferência

## Objetivo

O ARGOS pode representar no visualizador uma região focal encontrada
automaticamente pelo `liver_lesions_mr` do TotalSegmentator. A representação é
uma **região candidata não confirmada**, não uma máscara de verdade-terreno e
não um diagnóstico.

## Ordem operacional

1. O DICOM multifásico é ingerido e o fígado é segmentado.
2. Os painéis são produzidos e o classificador visual emite sua decisão.
3. A decisão e o subtipo são congelados.
4. Somente então o localizador recebe a fase venosa e a máscara hepática.
5. A saída é validada, recortada à máscara do fígado e gravada como
   `mask_candidate.nii.gz`.
6. O pipeline 3D gera `figado_candidato.stl` e inclui a região no manifesto.
7. O revisor compara a região âmbar com a RM 2D/3D e aceita a região de
   interesse, rejeita o candidato ou solicita correção.

Esse encadeamento impede vazamento circular: a máscara candidata nunca é usada
para gerar painéis, embeddings, classificação ou subtipo.

## Contrato e gates

`candidate_region.json` usa o schema `argos-candidate-region-v1` e registra:

- modelo/tarefa e tempo;
- hashes da máscara candidata e da máscara hepática;
- voxels dentro e fora do fígado;
- componentes conexos, volume, diâmetro equivalente, bounding box e centroide;
- decisão congelada que motivou a localização;
- `used_by_screening_inference=false`;
- `ground_truth_lesion_mask_used=false`;
- `candidate_is_diagnosis=false`;
- revisão humana obrigatória.

O viewer não publica o candidato se geometria, binariedade, hash ou proveniência
falharem. Uma falha do localizador não altera a classificação já produzida; ela
é reportada como `localization_unavailable` e o modelo anatômico do fígado ainda
pode ser revisado.

## Convenção visual

- amarelo nas referências 2D: contorno da máscara hepática;
- âmbar nas referências e no 3D: região candidata automática não confirmada;
- vermelho: lesão marcada manualmente, quando existe;
- vasos e segmentos de Couinaud mantêm as cores do perfil hepático.

O manifesto fornece também distâncias aproximadas até fígado/vasos e a maior
sobreposição com um segmento de Couinaud. Essas medidas são exploratórias e não
representam margem cirúrgica.

## Revisão e persistência

Se houver candidato, uma aprovação exige:

- inspeção do contorno 3D;
- comparação com as referências 2D;
- comparação específica do candidato âmbar com a RM;
- ciência do uso exclusivo em pesquisa;
- decisão explícita `accepted_as_region_of_interest` ou `rejected`.

Aceitar significa apenas que o contorno é útil como **região de interesse**. Não
confirma HCC, benignidade ou qualquer diagnóstico. A decisão, checklist, estado
do viewer e hashes dos artefatos ficam em `outputs/approval.json`.

## Limitações atuais

- O localizador pode não encontrar lesões reais e pode marcar pseudolesões,
  vasos, artefatos ou variantes benignas.
- A região é gerada na fase venosa usada pelo fluxo atual; alterações visíveis
  somente em outra sequência podem não ser localizadas.
- O resultado depende da qualidade da segmentação hepática e da aquisição.
- Correção voxel a voxel continua sendo feita em ferramenta dedicada; o viewer
  registra aceitação, rejeição ou necessidade de correção, mas não edita a NIfTI.
