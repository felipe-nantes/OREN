# A união de fases recupera fígado real — solução para a visualização

**Data:** 6 de agosto de 2026
**Ferramentas:** `tools/validate_phase_union_against_reference.py`,
`tools/pilot_precontrast_liver_segmentation.py`
**Artefatos:** `experiments/phase_union_validation_v1/`, `experiments/precontrast_segmentation_v1/`
**Continua:** [docs/188](188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md)

---

## 1. A pergunta que abriu esta rodada

Ao ver a galeria de 10 fígados renderizados, a observação foi: *"você acredita
que podemos também estar perdendo essa forma durante a segmentação?"*

A resposta é **sim**, e agora está medida em duas frentes.

---

## 2. As fases perdem pedaços DIFERENTES — medido no LLD

Comparando, nos mesmos 14 pacientes, a máscara da fase venosa (produção) com a
da pré-contraste:

| | Venosa | Pré-contraste | **União** |
|---|---:|---:|---:|
| Volume mediano | 569 mL | 523 mL | **737 mL** |
| Dentro da faixa adulta (900–2400) | 3/14 | 3/14 | **6/14** |
| Ganho sobre a melhor fase isolada | — | — | **1,19×** (máx. 1,44×) |

O número decisivo é a **concordância entre as duas máscaras: Dice mediano de
0,64**. Se ambas vissem o mesmo fígado com uma perda comum, o Dice seria ~0,95.
Em 0,64, cada fase está encontrando regiões substancialmente diferentes do órgão.

> A perda de forma não é um defeito único do segmentador. É **dependente da
> fase**, e por isso parcialmente recuperável.

Caso extremo da amostra: venosa 200 mL, pré-contraste 329 mL, união 456 mL, com
Dice de apenas 0,28 entre as duas.

---

## 3. Mas união sempre cresce — crescer não é acertar

Somar máscaras aumenta o volume por construção. O aumento pode ser fígado
recuperado ou erro de cada fase acumulado. Só há um jeito de decidir: medir
contra referência humana.

O CHAOS tem anotação humana e duas séries T1 do mesmo exame (in-phase e
out-of-phase). Resultado nos 20 casos:

| Dice contra o humano | Mediana |
|---|---:|
| In-phase isolado | 0,9082 |
| Out-phase isolado | 0,8957 |
| **União** | **0,9168** |

| | |
|---|---:|
| União menos a melhor fase isolada | **+0,0085** |
| Casos em que a união **melhorou** | **18/20** |
| Casos em que a união piorou | 2/20 |
| **Precisão do que a união acrescenta** | **0,8194** |

**82% dos voxels que a união soma são confirmados como fígado pela anotação
humana.** A união recupera órgão real; não está invadindo tecido vizinho.

### A limitação que precisa acompanhar esse número

**No CHAOS as duas fases concordam com Dice 0,9544 — no LLD, 0,64.** Ou seja, a
coorte onde existe referência humana quase não apresenta o fenômeno que se quer
corrigir: lá o segmentador já funciona bem e as fases veem o mesmo fígado.

Consequência honesta:

- o **mecanismo** está validado — quando a união acrescenta, ela acerta 82% e
  melhora o Dice em 18/20;
- a **magnitude** não está — o +0,0085 do CHAOS não estima o ganho no regime do
  LLD, onde há muito mais a recuperar.

Não existe coorte pública com referência humana **e** o modo de falha do LLD ao
mesmo tempo. Essa lacuna não se fecha com mais engenharia; ela é a mesma
necessidade de coorte externa que o projeto documenta desde
[docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md).

---

## 4. O que já foi descartado por medição

**Trocar a venosa pela pré-contraste: REPROVADO** (docs/188 §9). Sozinha, a
pré-contraste recupera menos órgão (0,92×) e sai três vezes mais fragmentada.
Ela é **diferente**, não melhor — e é justamente por ser diferente que a união
funciona.

**Reparo topológico: CANCELADO** (docs/188 §7). As malhas já saem 100% estanques
e manifold; o campo contínuo resolve.

---

## 5. A solução

### 5.1 Máscara de visualização pela união das três fases dinâmicas

O webapp já ingere arterial, venosa e tardia harmonizadas na mesma grade. A
união das três não exige dado novo — apenas duas execuções extras do
segmentador. [docs/165](165_QUALIDADE_VISUALIZADOR_3D.md) mediu, no mesmo exame:
venosa 486 mL, tardia 607, união das três 650 mL.

### 5.2 A objeção de rastreabilidade se resolve por contenção

A preocupação registrada em docs/188 §5 era: se o modelo 3-D usa uma máscara e a
decisão usa outra, o revisor audita uma geometria diferente da que classificou.

**Isso deixa de ser um problema quando se percebe que união ⊇ venosa, por
construção.** A máscara de classificação está inteiramente contida na de
visualização. Portanto não são dois modelos concorrentes:

> **Um único modelo anatômico (a união), com a região que a classificação
> examinou marcada dentro dele.**

O revisor vê o órgão e vê, destacada, a parte que o classificador olhou. Isso é
*mais* rastreável que hoje, não menos — hoje ele vê só a região classificada e
não tem como saber quanto do fígado ficou de fora.

### 5.3 O custo cabe, porque a união não entra no caminho da decisão

Duas segmentações extras acrescentariam ~60 a 100 s, o que estouraria o
orçamento de 180 s se estivessem no caminho crítico. **Elas não estão.**

A região candidata já é localizada **depois** da decisão congelada
([docs/169](169_REGIAO_CANDIDATA_3D_POS_INFERENCIA.md)), e o modelo 3-D é
construído no mesmo estágio. A união serve exclusivamente ao visualizador, então
roda depois de a decisão ter sido devolvida — sem tocar a latência da triagem
nem o resultado.

### 5.4 O que fica igual, e é essencial que fique

- A máscara de classificação continua sendo a venosa, **congelada**.
- Os painéis continuam vindo de `mask_organ.nii.gz`.
- Nenhuma métrica do protocolo é afetada.
- O aviso de volume passa a reportar o volume da união, com o da venosa ao lado.

---

## 6. Execução

### 6.1 Passo 1 — gate: a união das TRÊS fases de produção, medida

`tools/measure_three_phase_union_gain.py`, 19 casos LLD, arterial+venosa+tardia
já harmonizadas (verificado: mesma grade, união é OR direto, sem registro):

| | Venosa | União |
|---|---:|---:|
| Volume mediano | 590 mL | **758 mL** |
| Dentro da faixa adulta | 1/19 | **6/19** |

Razão mediana **1,23×** (min 1,03, máx 17,47 — um caso em que venosa e tardia
quase falharam sozinhas e a arterial resgatou o órgão). **Gate passa.**

### 6.2 Passo 2 — implementado

- `dtwin/core.py`: `Case.mask_organ_union`, arquivo novo, nunca escrito por
  classificação.
- `dtwin/stages.py`: `_fonte_da_malha_do_orgao(case)` — o estágio de malha
  prefere a união quando o arquivo existe, com verificação de geometria contra
  a venosa (referência garantida) antes de aceitar; geometria divergente
  descarta a união e cai para a venosa, com aviso no log.
- `webapp/server.py`: `_build_union_liver_mask(case_dir, phase_paths)` — roda
  **depois** de `classify_embeddings` (garantido por teste estrutural que lê o
  código-fonte). Cada fase extra tem timeout próprio
  (`WEBAPP_UNION_PHASE_TIMEOUT`, padrão 240 s) e uma falha nela só a exclui da
  união, nunca falha o exame. Atrás de um interruptor
  (`WEBAPP_UNION_MASK_ENABLED`, ligado por padrão).
- `_aviso_volume_figado` passou a receber o volume da união quando disponível,
  e a mensagem nomeia a origem ("a união das fases..." vs. "a fase venosa").
- Interface: quando a união é construída, mostra os dois volumes lado a lado —
  o classificado (venosa) e o exibido no modelo 3D (união).

**O que ficou de fora desta implementação, registrado para não ser esquecido:**
a marcação visual da região de classificação *dentro* da malha da união (§5.2,
"destacada, a parte que o classificador olhou") não foi construída — hoje só o
**dado** (`classification_region_fraction_of_union`) é exposto, não um overlay
renderizado no visualizador 3D. A infraestrutura para isso já existe (o mesmo
mecanismo que desenha `mesh_candidate.vtp` sobre o órgão), mas construir o
segundo mesh e o suporte no `viewer/app.js` é trabalho novo, não feito aqui.

### 6.3 Verificação

- 8 testes novos (1472 → **1480**): a garantia central — hash byte-a-byte de
  `mask_organ.nii.gz` antes e depois de construir a união — está travada por
  teste e **passou**; também: geometria divergente é descartada, degradação
  quando todas as fases falham, fonte da malha prefere a união quando presente,
  estágio 5 descarta união com geometria errada, aviso de volume com/sem união,
  ordem estrutural (união depois de classificar).
- **Smoke de ponta a ponta com dado real** (`anon-lld-00878b6b34f0cdb4`, fora da
  suíte automatizada): venosa 816,0 mL → união 1220,3 mL, três fases
  contribuíram sem falha, `mask_organ.nii.gz` confirmado **idêntico voxel a
  voxel** ao original depois da chamada, malha final saiu de
  `mask_organ_union.nii.gz` (log do estágio 5), componente único, 160 000
  triângulos.
- Suíte completa: **1480/1480**.

Passos 3 (regerar a galeria) e a marcação visual do §6.2 continuam como
trabalho seguinte, não feito nesta rodada.

---

## 7. O que isto ainda não resolve

Mesmo com a união, o volume mediano projetado fica em torno de 737 mL contra os
~1.230 mL esperados para um adulto. **A união melhora, não resolve.** Uma parte
do fígado não é encontrada por nenhuma das fases, e recuperá-la exige um
segmentador adaptado ao domínio — não outra combinação das mesmas máscaras.

`research_only: true` · `clinical_use_allowed: false`
