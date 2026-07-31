# Passo 1 — Fusão de representações: ganho real, mas o gate não vale

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo1_fusao_v1/`
**Passo 1** de [docs/150](150_PLANO_FINAL_METAS_75.md)

---

## 1. Aviso antes dos números

O script imprimiu **"APROVADO — TODOS OS DATASETS NO GATE 75/75"**. **Essa leitura
é inválida**, por erro de desenho meu, e não deve ser citada.

**Motivo 1 — só existe um dataset na medição.** Os embeddings de recorte só
existem para o LLD, porque o OpenSwiss nunca teve fases harmonizadas. Os dois
datasets OpenSwiss foram **silenciosamente descartados** da avaliação binária.
"Todos os datasets" significa "o único que sobrou" — e o descartado
`openswiss_holdout` era justamente o que falhava em especificidade (65,00%).

**Motivo 2 — o subconjunto é mais fácil.** Os 318 casos são os que têm recorte,
isto é, aqueles em que a localização funcionou. Medindo o **pipeline oficial** nos
mesmos 318:

| Pipeline oficial (Etapa C) no LLD | Sens | Esp |
|---|---:|---:|
| Todos os 335 casos | 73,25% | 76,97% |
| Só os 318 com recorte | **76,00%** | 80,95% |

**+2,75 pontos vêm apenas da seleção de casos.** O baseline do experimento já
parte de um conjunto enviesado.

---

## 2. O que é válido: a comparação interna

Mesmos 318 casos, mesmo treino, variando só a representação:

| Representação | Sens LLD | Esp LLD | Balanceada subtipo |
|---|---:|---:|---:|
| A — fígado inteiro | 78,00% | 79,76% | 51,28% |
| B — recorte por ROI predita | 71,33% | 83,93% | 62,66% |
| **C — fusão concatenada** | **80,67%** | **82,14%** | **63,44%** |
| D — fusão com PCA por bloco | 76,67% | 82,74% | 62,94% |

**A fusão supera as duas representações isoladas nos dois endpoints.** A hipótese
de docs/150 se confirma: fígado inteiro carrega contexto, recorte carrega detalhe
local, e os erros são parcialmente independentes.

Ganho sobre o melhor baseline de cada endpoint:
- binário: **+2,67 pts** de sensibilidade (78,00% → 80,67%)
- subtipo: **+0,78 pt** de balanceada (62,66% → 63,44%)

### Onde a fusão mais rende

No subtipo, o HCC salta de **70,7%** (fígado inteiro) e 67,3% (recorte) para
**80,0%** na fusão — bem acima de qualquer uma isolada. É o comportamento
esperado de fusão útil: o combinado excede os componentes, não fica no meio.

A redução por PCA (braço D) **piorou** em relação à concatenação direta. A
preocupação de que o bloco de 1152 dominasse não se materializou; a regularização
da logística já dá conta.

---

## 3. Consequência estrutural

A fusão **não pode ser validada no endpoint binário completo** com os dados
atuais: exige recorte para OpenSwiss → exige fases harmonizadas → não existem.

É o **segundo** bloqueio pela mesma causa. O primeiro travou o experimento FNH
(sem negativos, especificidade não avaliável). Isso muda o peso do problema:

> Harmonizar as fases dinâmicas do OpenSwiss deixou de ser item de um experimento
> e passou a ser **dependência estrutural de duas linhas de trabalho**.

Enquanto não existir, qualquer ganho medido será sobre um subconjunto do LLD, não
sobre a meta.

---

## 4. Estado das metas

| | Valor | Observação |
|---|---:|---|
| Binário, agregado oficial | 75,91% / 76,11% | inalterado; a fusão não foi validada nele |
| Binário, LLD oficial | 73,25% / 76,97% | inalterado |
| Subtipo, medido oficial | 61,46% | docs/146, com casos sem ROI contando como erro |
| Subtipo, fusão neste subconjunto | 63,44% | **não comparável** com 61,46% — 318 casos, sem-ROI excluídos |

Nada aqui altera os números oficiais das metas. O que se aprendeu é que **a fusão
é o caminho certo de representação**, e isso orienta os Passos 2 e 3.

---

## 5. Nota sobre o endpoint de subtipo

O subtipo é **LLD-only por natureza** — só o LLD tem subtipos anotados. Portanto
os Passos 2 e 3 são plenamente válidos para essa meta sem depender do OpenSwiss.
A dependência é exclusiva do endpoint binário.

`clinical_use_allowed` permanece `false`.
