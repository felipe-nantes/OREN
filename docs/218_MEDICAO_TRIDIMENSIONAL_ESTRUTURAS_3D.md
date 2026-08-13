# Medição tridimensional de estruturas no visualizador

## Objetivo

Permitir a mensuração tridimensional de uma estrutura segmentada, incluindo a
profundidade anterior–posterior de uma região candidata ou lesão disponível no
manifesto.

## Uso

1. selecionar diretamente uma estrutura no modelo 3D;
2. clicar em **Medir em 3D**;
3. revisar as três guias coloridas e os valores no painel;
4. usar **Limpar medidas** para remover as anotações.

## Dimensões

As medidas seguem o sistema de coordenadas LPS:

- **LR** (`x`): largura esquerda–direita;
- **AP** (`y`): profundidade anterior–posterior;
- **SI** (`z`): extensão superior–inferior.

O cálculo usa a caixa envolvente alinhada aos eixos LPS da malha completa:

```text
method = axis_aligned_lps_bounding_box
source = selected_segmentation_mesh
approximate = true
```

O plano de corte pode ocultar parte da visualização, mas não altera as dimensões
da malha fonte.

## Visualização

O visualizador cria três linhas com marcadores e rótulos em milímetros. A câmera
é reenquadrada com margem adicional para incluir as anotações. O painel mostra
os mesmos valores e esclarece que a medida é aproximada e deriva da segmentação
automática.

## Auditoria

Cada medição é persistida em `viewer_state.structure_dimensions_3d` com:

- papel e rótulo da estrutura;
- LR, AP e SI em milímetros;
- método, coordenadas e fonte;
- declaração obrigatória `approximate=true`.

O backend aceita no máximo 16 estruturas, rejeita papéis ausentes do manifesto,
duplicações, valores não finitos, dimensões nulas e dimensões acima de 5000 mm.

## Validação real

No caso `c2424a1dd2e1`, a região candidata automática apresentou:

```text
LR = 35,3 mm
AP = 38,5 mm (profundidade)
SI = 35,5 mm
```

As três guias foram renderizadas corretamente e nenhum erro apareceu no console
do navegador.

Validação automatizada:

```text
testes focados: 91 passed
suíte completa: 1529 passed, 3 skipped
```

Evidência visual:

```text
experiments/couinaud_diagnostic_c2424a1dd2e1_v3/
viewer_candidate_3d_dimensions_job_c2424a1dd2e1.png
```

## Limitação metodológica

Essa dimensão mede a extensão da **malha segmentada**, não a extensão clínica
confirmada da lesão. Erros na segmentação propagam-se para a medida. O recurso
continua em modo pesquisa e requer comparação humana com a RM 2D.
