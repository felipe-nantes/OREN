# Por que alguns fígados 3D ficam bons e outros ruins — diagnóstico e plano

**Data:** 5 de agosto de 2026
**Ferramenta:** `tools/audit_liver_mask_geometry_quality.py`
**Artefatos:** `experiments/mask_geometry_quality_v1/`
**Medido em:** 321 máscaras LLD-MMRI (produção) + 20 CHAOS (com referência humana)

---

## 1. A pergunta, e por que ela tem duas respostas possíveis

O visualizador reconstrói uma malha a partir da máscara automática. A qualidade
do que aparece na tela pode falhar em dois lugares, e eles exigem correções
opostas:

| Causa | Significa | Já é medida? |
|---|---|---|
| **(A) Infidelidade de reconstrução** | a malha não representa bem a máscara | **Sim** — `compute_mesh_metrics` |
| **(B) Qualidade da máscara** | a máscara não representa bem o fígado | **Não** — não há referência humana em produção |

`dtwin/viewer_artifacts.compute_mesh_metrics` declara isso no próprio artefato:
`"not_segmentation_accuracy": true`. O sistema sabe se a malha copiou bem a
máscara; **não sabe se a máscara está certa.**

---

## 2. O diagnóstico: é uma síndrome, não quatro defeitos

Medido nas 321 máscaras de produção:

| Atributo | p10 | mediana | p90 |
|---|---:|---:|---:|
| Volume (mL) | 164 | 637 | 1.126 |
| Componentes conexos | 1 | **3** | 8 |
| Característica de Euler | −2 | **2** | 7 |
| Rugosidade (1,0 = esfera) | 1,62 | **1,87** | 2,46 |
| Cortes em z | 27 | 40 | 51 |

| Patologia | Casos |
|---|---:|
| Fragmentadas (mais de um componente) | **240/321 (75%)** |
| Com defeito topológico (Euler ≠ 1) | **271/321 (84%)** |
| Com buracos internos | 9/321 (3%) |
| Encostando na borda em z | 27/321 (8%) |

**As quatro patologias andam juntas, e o volume prediz todas elas:**

| Correlação com o volume | Spearman ρ | p |
|---|---:|---:|
| Rugosidade | **−0,623** | 5,7 × 10⁻³⁶ |
| Fração do maior componente | **+0,484** | 2,9 × 10⁻²⁰ |
| Número de componentes | −0,372 | 5,7 × 10⁻¹² |
| Euler | −0,123 | 0,028 |

> Fígado com volume baixo é **o mesmo** fígado fragmentado, rugoso e com
> topologia quebrada. Não são casos diferentes com problemas diferentes.

### A cadeia causal, fechando com o que já sabíamos

[docs/176](176_TOTAL_MR_VALIDADO_CONTRA_REFERENCIA_HUMANA.md) mediu que o
segmentador atinge **Dice 0,908** contra anotação humana em T1 **sem** contraste,
e degrada na fase venosa **com** contraste — que é a que o pipeline usa.
[docs/165](165_QUALIDADE_VISUALIZADOR_3D.md) isolou isso dentro do mesmo exame:
arterial 122 mL, venosa 486, tardia 607.

Juntando com a medição deste documento:

```text
fase com contraste
   -> segmentador subestima
      -> máscara se parte em pedaços, fica rugosa e ganha alças
         -> o 3D fica ruim
```

**A variação de qualidade do visualizador não é aleatória. É um gradiente com
uma causa a montante.**

### O contraste com o CHAOS confirma

Nos 20 casos CHAOS, onde o segmentador vai bem (Dice mediano 0,908):

| | CHAOS (bom) | LLD (produção) |
|---|---|---|
| Componentes | **1 em 20/20** | mediana 3 |
| Euler = 1 | **20/20** | 16% |
| Rugosidade | 1,23 – 1,62 | mediana 1,87, p90 2,46 |

**Ressalva honesta:** eu tentei usar o CHAOS para descobrir *quais* atributos
predizem baixo Dice, e nenhum deu correlação significativa (todos p > 0,25). Isso
**não** significa que os atributos não importam — significa que o CHAOS não tem
variação neles: todos os 20 são de componente único e topologicamente limpos.
Sem contraste entre casos, não há o que correlacionar. O braço CHAOS serve para
mostrar como é uma máscara boa, não para ranquear preditores.

---

## 3. O defeito concreto no código, e por que é seguro corrigir

`_refine_mask` (`dtwin/stages.py:125`) faz abertura, fechamento e
`remove_small_objects(min_size=300)`. Com voxel de 1,83 mm³, isso remove apenas
ilhas menores que **0,55 mL**. Não isola o maior componente e não preenche
buracos em 3-D.

Efeito medido em 80 casos, comparando estratégias:

| Variante | Componente único | Euler = 1 | Rugosidade | Volume mediano |
|---|---:|---:|---:|---:|
| Máscara bruta | 25% | 18% | 1,87 | 610 mL |
| **Refino atual** | **60%** | **38%** | 1,85 | 609 mL |
| + maior componente | **100%** | 50% | 1,81 | 592 mL |
| + maior + preencher buracos | **100%** | 55% | 1,81 | 592 mL |

Ou seja: **o refino atual deixa 40% dos casos com ilhas flutuando na tela.**

**Isolar o maior componente custa 0,0% de volume na mediana** — as ilhas quase
sempre são detritos. Mas há uma cauda perigosa:

| Fração do maior componente | Casos | Se isolasse cegamente |
|---|---:|---|
| < 0,99 | 62/321 (19,3%) | perderia > 1% |
| < 0,95 | 32/321 (10,0%) | perderia > 5% |
| < 0,90 | 20/321 (6,2%) | perderia > 10% |
| < 0,80 | 13/321 (4,0%) | perderia > 20% (pior caso: **47%**) |

Em 6,2% dos casos o fígado não está "com ilhas" — ele está **partido em dois
pedaços grandes**, e isolar o maior apagaria metade do órgão em silêncio.

**Verificado — a correção é livre de risco para as métricas:** os painéis de
classificação são construídos a partir de `mask_organ.nii.gz` (bruta,
`exam_to_panels.py:169`). `mask_organ_clean.nii.gz` alimenta **apenas** malha,
imagens de referência e resumo de aquisição. Melhorar a limpeza muda o que se vê,
nunca o que se decide.

---

## 4. O limite honesto de "perfeita e fidedigna"

Precisa ser dito antes do plano, porque muda o que se pode prometer:

> **A fidelidade da representação 3-D é limitada pela máscara, não pela malha.**
> Suavizar uma máscara que capturou 40% do fígado produz um fígado bonito e
> errado. Estética e fidelidade são coisas diferentes, e em 76% da coorte de
> produção o volume está abaixo do piso adulto.

Portanto o plano tem duas trilhas, e só a segunda ataca fidelidade de verdade.

---

## 5. Plano

### Trilha A — parar de exibir artefato (barato, seguro, alto impacto visual)

Torna o render fiel **à máscara** e remove o que é claramente artefato de
processamento. Não melhora a fidelidade ao paciente; melhora a honestidade do
que é mostrado.

**A1. Isolar o maior componente, com guarda.**
Quando a fração do maior componente for ≥ 0,90, isolar (resolve 100% da
fragmentação a custo mediano zero). Abaixo de 0,90, **não isolar** — manter tudo
e emitir aviso de que o fígado aparece partido, porque nesse caso a fragmentação
é sintoma de segmentação ruim, não detrito a esconder. O limiar 0,90 já existe no
projeto: `MINIMUM_LARGEST_COMPONENT_FRACTION` em
`dtwin/benchmark/lld_mmri_v23_mask_quality.py`.

**A2. Preencher buracos em 3-D** (`ndimage.binary_fill_holes`). Ganho pequeno
mas gratuito, e elimina cavidades internas que aparecem como transparências.

**A3. Medir a topologia da malha final, não da máscara. — EXECUTADO, ver §7.**

**A4. Reparo topológico — CANCELADO por medição.** A3 mostrou que a patologia
topológica não chega à tela: 100% das malhas saem estanques e manifold. O campo
contínuo já resolve. Ver §7.

**A5. Expor o aviso na interface.** O aviso de volume já existe. Acrescentar
fragmentação e topologia à mesma faixa: quem olha o modelo precisa saber que
aquele fígado está partido, em vez de achar que é anatomia.

### Trilha B — fidelidade real (cara, é onde está o ganho verdadeiro)

**B1. Máscara de visualização pela união de fases.** docs/165 mediu, no mesmo
exame: venosa 486 mL, tardia 607, união das três 650. A união recupera ~34% mais
órgão. Custo: duas execuções extras do TotalSegmentator (~5 min/exame).

**Decisão que precisa ser sua, não minha:** isso cria duas máscaras — a que
classifica (venosa, congelada) e a que se vê (união). Um revisor que audita o
modelo 3-D estaria auditando uma geometria diferente da que gerou a decisão.
Opções:

- **(i)** manter uma máscara só, a de classificação — rastreável, porém
  incompleta na tela;
- **(ii)** duas máscaras, com rótulo explícito de qual é qual e sobreposição da
  de classificação sobre o modelo anatômico;
- **(iii)** trocar as duas pela união — o mais fiel, mas **invalida as métricas
  congeladas** e exige remedição completa.

Minha recomendação é **(ii)**: ganha-se anatomia sem perder rastreabilidade, e
nada congelado é tocado. Mas é escolha de projeto, não técnica.

**B2. Segmentar numa série sem contraste, quando existir.** É a intervenção que
ataca a causa medida em docs/176 — o segmentador é validado justamente em T1 sem
contraste. Exige registrar a máscara de volta para a grade venosa. Mesmo trade-off
de rastreabilidade de B1.

**B3. O que não resolve, já medido:** aumentar cobertura, trocar limiar, ou
suavizar mais. docs/165 já mostrou que a união chega a 650 mL contra os ~1.230
esperados — mesmo a melhor combinação de fases não recupera o órgão inteiro.

---

## 6. Ordem recomendada

1. **A3** primeiro (medir a malha final) — é barato e pode tornar A4 desnecessário.
2. **A1 + A2 + A5** — resolvem fragmentação com guarda e tornam visível o que hoje é silencioso.
3. **Decidir B1** entre (i)/(ii)/(iii) — é a escolha que destrava a fidelidade real.
4. **B2** como trabalho maior, dependente da decisão anterior.

Nada da Trilha A toca classificação. A Trilha B exige decisão explícita sobre
rastreabilidade antes de qualquer linha de código.

`research_only: true` · `clinical_use_allowed: false`

---

## 7. Passo 1 executado — o que chega de fato à tela

**Ferramenta:** `tools/audit_mesh_topology_quality.py`
**Artefatos:** `experiments/mesh_topology_quality_v1/`
**Amostra:** 30 casos LLD, reconstrução idêntica à de produção (isotrópico
0,8 mm, σ 2,0 mm, Taubin 30×, decimação para 160k triângulos)

| | Máscara binária (§2) | **Malha final** |
|---|---:|---:|
| Estanque e manifold | Euler ≠ 1 em 84% | **100%** |
| Rugosidade | 1,85 | **1,36** |
| Corpo único | 60% | 57% |

### O que isso decide

**A patologia topológica não sobrevive à reconstrução.** Todas as 30 malhas saem
estanques e manifold — o campo contínuo com σ 2,0 mm fecha os túneis e alças que
existiam na máscara binária. A rugosidade cai de 1,85 para 1,36, dentro da faixa
observada nas máscaras boas do CHAOS (1,23–1,62).

> **A4 (reparo topológico) está cancelado por medição.** Teria sido esforço
> gasto num problema que a reconstrução atual já resolve. Foi exatamente para
> isso que A3 veio antes de A4.

**A fragmentação, ao contrário, sobrevive inteira** — e é o que aparece como
ilhas flutuando ao lado do órgão.

### Efeito da limpeza proposta (A1 + A2)

Medido só nos casos onde a limpeza tem o que fazer, para não diluir o resultado
com máscaras que já eram limpas:

| Situação | Casos | Corpo único antes | Corpo único depois |
|---|---:|---:|---:|
| Já era componente único | 17/30 | — | — |
| **Guarda permitiu isolar** | **12/30** | **0%** | **100%** |
| Guarda bloqueou (fígado partido) | 1/30 | 0% | 0% (correto) |

**Nos 12 casos em que agiu, a limpeza resolveu 12.** No caso bloqueado
(`anon-lld-d64c9d7fc09e19c4`, fração 0,805) nada mudou — que é o comportamento
desejado: ali o fígado está partido em dois pedaços grandes e isolar apagaria
cerca de 20% do órgão em silêncio.

### Correção de um erro de relatório

A primeira versão deste auditor imprimiu *"a guarda impediu isolar em 18/30
casos (fígado partido)"*. **Estava errado** e teria alarmado sem razão: o
contador somava máscaras de componente único — onde não havia nada a isolar e a
guarda nem chegou a agir — com fígados de fato partidos. O número correto de
fígados partidos na amostra é **1/30**, não 18. O auditor foi corrigido para
separar as três situações.
