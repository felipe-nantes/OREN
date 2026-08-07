# 193 — Fase A: o modelo dedicado NÃO funciona na preparação do LLD (REPROVADO)

## O que a Fase A ia decidir

docs/191 mostrou o `liver_segments_mr` batendo o `total_mr` em 20/20 casos
contra referência humana **no CHAOS** (Dice 0,9256 vs 0,9082). A Fase A
(docs/192) era o teste bloqueante: **esse ganho se transfere para o dado de
produção** — a fase venosa com contraste da coorte LLD? Sem isso, a ressalva
nº 1 de docs/191 (CHAOS é T1 sem contraste) fica em aberto.

Resultado: **não se transfere. Reprovado.** E por um motivo mais básico do que
o contraste.

## Achado 1 — o modelo colapsa no dado do LLD, em TODAS as fases

Rodando `liver_segments_mr_union_segmenter` (o mesmo que deu Dice 0,93 no
CHAOS, sem modificação) na fase venosa do LLD, 5 casos da amostra:

| caso | `total_mr` | `liver_segments_mr` |
|---|---|---|
| 0164881a | 630 mL | **0 mL** |
| 08c7d7e1 | 892 mL | **0 mL** |
| 0c4a7eb1 | 303 mL | **17 mL** |
| 0e87e6c4 | 793 mL | **0 mL** |
| 16f1c817 | 433 mL | **0 mL** |

Não é sensibilidade ao contraste. No **mesmo** caso, em fases **sem** contraste
do próprio LLD, o modelo também colapsa:

| fase | `liver_segments_mr` |
|---|---|
| t1_native (sem contraste) | 0 mL |
| t1_in_phase | 71 mL |
| t1_out_phase | 1 mL |
| t1_venous (com contraste) | 0 mL |

Ou seja: o problema é a **preparação do LLD**, não a fase. O `total_mr` é
robusto a ela; o `liver_segments_mr`, não.

## Achado 2 — a causa é o pré-processamento, mas conserto não é trivial

Comparando a entrada onde o modelo **funcionou** (CHAOS) com a que **falhou**
(LLD):

| | CHAOS (Dice 0,93) | LLD (~0 mL) |
|---|---|---|
| intensidade máx | **1710** (faixa nativa de RM) | **255** (clampado) |
| spacing | 1,70 × 1,70 × 9,0 mm | 0,78 × 0,78 × 3,0 mm |

A preparação do LLD **clampa a intensidade em 0–255**. O nnU-Net do
`liver_segments_mr` normaliza esperando a faixa nativa e produz vazio quando a
recebe quantizada em 256 níveis.

Testei o conserto óbvio — reescalar linearmente a venosa do LLD de 0–255 de
volta para 0–1710 e re-segmentar:

| entrada | `liver_segments_mr` |
|---|---|
| venosa 0–255 (produção) | 0 mL |
| venosa reescalada 0–1710 | **13 mL** (ainda falha; `total_mr` = 630 mL) |

O stretch linear recuperou quase nada (0 → 13 mL). O clamp em 256 níveis
**destrói** a distribuição fina de intensidade que a normalização do modelo
usa, e esticar a faixa não recupera a informação perdida. Recuperar o modelo
exigiria **re-derivar a preparação do LLD a partir das aquisições brutas** (sem
clamp), e re-validar — um trabalho grande, com risco, e sem garantia. Está bem
além de um ajuste de visualização.

## Achado 3 — a âncora de cobertura de lesão não pôde ser usada (dado desalinhado)

O plano da Fase A previa medir acurácia real por **cobertura de lesão anotada**
(fígado deve conter a lesão). Ao montar isso, as máscaras de lesão
(`lesion_masks_cv_v1`, `MR-xxxxxx_C+V.nii.gz`) **não alinham** com a fase
venosa preparada, apesar de headers idênticos (mesma origem/spacing/direção):

- interseção lesão ∩ fígado: **1 voxel** de 18 895.
- a lesão cai em tecido de fígado real (intensidade venosa mediana 228 vs 206
  do fígado; 92% dos voxels acima do p10 do fígado) — então a máscara é boa,
  só está no lugar errado.
- há um **deslocamento sistemático de ~20 fatias em z**: com shift dz=−20 a
  cobertura salta de 0 para **0,963**.

As máscaras de lesão estão numa grade diferente da preparada (consistente com o
alerta de proveniência do `lesion_masks_cv_v1` — nomes clínicos brutos, sem
manifesto de extração). Corrigir isso é um sub-projeto de registro por caso,
fora do escopo desta medição. A âncora forte ficou indisponível; os Achados 1 e
2, porém, já respondem a Fase A sozinhos.

## Veredito

**Gate da Fase A: REPROVADO.** Não por um número apertado, mas porque o modelo
não funciona no dado de produção — produz máscara vazia. As Fases B, C e D do
plano (adoção na visualização) ficam **canceladas**: não há o que adotar.

O resultado do CHAOS (docs/191) continua verdadeiro e não foi retirado — o
`liver_segments_mr` é de fato melhor **quando recebe a faixa de intensidade
nativa**. O que docs/193 acrescenta é a fronteira: esse regime não é o da
produção atual, e a distância entre os dois é grande demais para um stretch
linear cobrir.

## O que isso deixa em aberto (honesto)

- O ganho real existe, mas atrás de uma barreira de pré-processamento. Se algum
  dia a preparação do LLD for reconstruída a partir do bruto (sem clamp em
  0–255), vale re-testar — a alavanca está identificada.
- A sub-segmentação do `total_mr` (docs/190: 7/20 abaixo de 600 mL) **continua
  o problema real e sem solução adotada**. A união de 3 fases (docs/189) segue
  sendo a mitigação em produção.
- Modelos externos não testados aqui (MRSegmentator, MRISegmentator-Abdomen)
  poderiam ser mais robustos ao dado clampado — mas cada um é um novo
  experimento com seu próprio gate.

## Estado

Nenhuma alteração em produção. Teste 100% isolado: `git status` em `dtwin/`,
`webapp/`, `profiles/`, `viewer/`, `configs/` vazio; 102 testes verdes. Tudo
escrito só em `experiments/liver_segments_mr_vs_lld_venous_v1/` (gitignorado).
O ponto de retorno de docs/192 permanece intacto e não precisou ser usado.

## Arquivos

- `tools/measure_liver_segments_mr_vs_total_mr_venous_lld.py` — a medição da
  Fase A (com o gate pré-especificado que não chegou a ser avaliável).
- `tools/liver_segments_mr_worker.py` — worker isolado (docs/191).
- `experiments/liver_segments_mr_vs_lld_venous_v1/` — máscaras e diagnósticos.
