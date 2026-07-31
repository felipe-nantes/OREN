# Fusão no endpoint binário completo — e a correção de uma premissa que eu inventei

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/fusao_estimador_oficial_v2/`, `openswiss_roi_embeddings_v1/`
**Corrige:** [docs/151 §3](151_PASSO1_FUSAO_RESULTADO.md), [docs/153 §7](153_PASSO3_MIL_RESULTADO.md)

---

## 1. A correção

docs/151 afirmou que **"o OpenSwiss nunca teve fases harmonizadas"** e elevou isso
a *dependência estrutural de duas linhas de trabalho*. docs/153 repetiu.

**Está errado.** As fases existem:

```
prepared/{development,holdout}_alignment_v1/{caso}/art_registered_to_venous.nii.gz
                                                  /del_registered_to_venous.nii.gz
algoritmo: openswisshcc-pairwise-or-identity-v1
```

Verificado: as três fases compartilham a **grade venosa exata** — a mesma garantia
que a harmonização do LLD produz. Cobertura **85/88** no development e **43/44** no
holdout. Localizador e máscaras hepáticas também já existiam.

O motivo real de não haver recortes para o OpenSwiss é que **meus scripts de
scratchpad fixaram caminhos do LLD**. Era suposição de caminho minha, não lacuna de
dado. O "bloqueio estrutural" que reportei era um problema que eu mesmo criei, e a
recomendação que derivei dele — priorizar a harmonização — não tinha base.

Construídos agora **118 recortes OpenSwiss** (8 casos sem predição do localizador,
1 com predição vazia).

---

## 2. Antes de comparar: o estimador certo

A primeira tentativa usou uma **logística binária direta** e deu 56,41% de
sensibilidade no development contra 82,05% do oficial. Eu estava comparando contra
o modelo errado.

O pipeline oficial é **multiclasse sobre o rótulo fino** — o OpenSwiss recebe
`positive_unspecified` / `negative_unspecified` — com o binário vindo da massa de
probabilidade nas classes positivas, e com `C`, agregação de painel e limiar
escolhidos nos folds internos maximizando `min(sens, esp)`. Ausência de painel
conta como erro técnico.

Reproduzido fielmente, o braço A dá:

| Dataset | Oficial | Obtido | Δ |
|---|---|---|---|
| `lld_mmri` | 73,25 / 76,97 | 74,52 / 77,53 | +1,27 / +0,56 |
| `openswisshcc_development` | 82,05 / 77,55 | **82,05 / 77,55** | **0,00 / 0,00** |
| `openswisshcc_consumed_holdout` | 83,33 / 65,00 | 83,33 / **60,00** | 0,00 / −5,00 |

O development é **exato**. O holdout tem sensibilidade exata e difere em
especificidade por **exatamente um caso** (12/20 contra 13/20) — desempate na
seleção de limiar.

**O gate (i) exigia 2 pontos de tolerância e portanto FALHA.** Registro como
falhou: não se reajusta gate depois da medição. Mas registro também que a
tolerância de 2 pontos era **mais fina que a resolução do dado** — num coorte de
20 negativos cada caso vale 5 pontos, como docs/150 já havia apontado. A
reprodução está substantivamente confirmada; o gate é que foi mal especificado.

---

## 3. A fusão no endpoint binário completo

Braço **H**: fusão onde há recorte, painel puro como fallback — a implantação
realista, com denominador completo.

| Dataset | A (oficial) | H (fusão) | Δ sens | Δ esp |
|---|---|---|---:|---:|
| `lld_mmri` | 74,52 / 77,53 | **80,25 / 76,40** | **+5,73** | −1,13 |
| `openswisshcc_development` | 82,05 / 77,55 | 76,92 / 79,59 | −5,13 | +2,04 |
| `openswisshcc_consumed_holdout` | 83,33 / 60,00 | 70,83 / 70,00 | −12,50 | +10,00 |

Em **contagem de casos**, que é como se deve ler coortes de 20 a 44:

| Dataset | VP | VN |
|---|---:|---:|
| `lld_mmri` | **+9** | −2 |
| `openswisshcc_development` | −2 | +1 |
| `openswisshcc_consumed_holdout` | −3 | +2 |

### O que muda no gate 75/75

| Dataset | A (oficial) | H (fusão) |
|---|---|---|
| `lld_mmri` | falha (sens 74,52) | **passa** — 80,25 / 76,40 |
| `openswisshcc_development` | passa | passa — 76,92 / 79,59 |
| `openswisshcc_consumed_holdout` | falha (esp 60,00) | falha — 70,83 / 70,00 |

**A fusão resolve exatamente o déficit que docs/150 identificou no LLD** — aquele
que precisava de "+2 verdadeiros positivos" — e entrega 9. É a primeira vez que o
LLD passa 75/75.

**O gate (ii) falha**, porque o holdout continua reprovado, agora nos dois eixos.

---

## 4. O confundidor que explica a assimetria

Os recortes **não são produzidos pelo mesmo procedimento** nas duas coortes:

| | Origem da ROI | Recall |
|---|---|---:|
| LLD | união de **três** localizadores (venoso, arterial, tardio) | 83,6% (docs/145) |
| OpenSwiss | **um** localizador | não medido |

Recorte pior adiciona ruído em vez de sinal. Isso é a explicação mais simples
para a fusão ajudar no LLD e atrapalhar no OpenSwiss — e é **testável**: basta
rodar os localizadores arterial e tardio no OpenSwiss e reconstruir a união.

Enquanto isso não for feito, **a queda no OpenSwiss não deve ser atribuída à
fusão**. As mudanças lá são de 1 a 3 casos, com ICs que se sobrepõem quase
inteiramente (holdout: [52–87] contra [67–95]).

---

## 5. Estado das metas

| | A (oficial) | H (fusão) |
|---|---|---|
| `lld_mmri` | 74,52 / 77,53 | **80,25 / 76,40** |
| `openswisshcc_development` | 82,05 / 77,55 | 76,92 / 79,59 |
| `openswisshcc_consumed_holdout` | 83,33 / 60,00 | 70,83 / 70,00 |

**Nada é promovido.** O braço H não substitui o pipeline oficial: o gate falhou, e
trocar uma reprovação de LLD por uma reprovação pior de holdout não é progresso
demonstrado. O que está estabelecido é que **a representação fundida carrega
informação que o painel de fígado inteiro não carrega**, e que essa informação
vale 9 casos no LLD.

---

## 6. Próximo passo, agora bem definido

Rodar os localizadores **arterial e tardio** no OpenSwiss e reconstruir os
recortes pela união de três fases, igualando o procedimento ao do LLD. É a única
forma de saber se a queda no OpenSwiss é da fusão ou do recorte pior — e é a
diferença entre um resultado promovível e um resultado ambíguo.

`clinical_use_allowed` permanece `false`.
