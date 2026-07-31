# Passo 3 — Múltiplas instâncias: REPROVADO, e o oráculo é inacessível

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo3_mil_v1/`, `mil_component_embeddings_v1/`
**Passo 3** de [docs/150](150_PLANO_FINAL_METAS_75.md) · continua [docs/152](152_PASSO2_AJUSTE_RESULTADO.md)

**Gate pré-especificado:** balanceada ≥ 66%.

---

## 1. A hipótese

Hoje o pipeline **escolhe** o maior componente conexo e vive com o erro. A ideia
era **não escolher**: embutir todos os componentes preditos e deixar o
classificador pontuar cada um, agregando depois.

Teto: o **oráculo de 83,3%** — a fração de casos em que existe, entre os
componentes preditos, ao menos um que toca a lesão. Contra ~67,8% da escolha
atual, seriam ~15 pontos disponíveis.

**1217 componentes** de 318 casos foram embutidos no MedSigLIP (3,83 por caso,
até 8 maiores por caso, margem 0,6).

---

## 2. Desenho

| | |
|---|---|
| treino `hit` | usa o componente que **toca a lesão** — ground truth como supervisão, legítimo porque no treino as máscaras existem |
| treino `maior` | usa o maior componente, como o pipeline atual |
| teste | **nenhum** ground truth; pontua-se todo componente e agrega-se |

Três agregações: **máxima confiança**, **média** das probabilidades, **média
ponderada por volume**.

Substrato: fusão (Passo 1) com C = 0,003 (pico de docs/152). Denominador honesto:
os 335 alvos, caso sem predição contando como erro — mesmo critério dos 61,46%
oficiais.

---

## 3. Resultado

| Treino | Agregação | Honesta (335) | Sub-318 |
|---|---|---:|---:|
| maior | máx. confiança | 57,62% | 60,40% |
| maior | média | 56,56% | 59,32% |
| **maior** | **média ponderada** | **61,11%** | 64,12% |
| hit | máx. confiança | 57,45% | 60,37% |
| hit | média | 54,37% | 57,20% |
| hit | média ponderada | 60,68% | 63,75% |

**Melhor: 61,11%. Gate de 66%: FALHA.** E **−0,35 ponto** abaixo do oficial de
61,46% — nenhum braço superou o pipeline que já existe.

---

## 4. O que o resultado diz

**A regra que menos perde é a que menos usa a ideia.** A média ponderada por
volume devolve o peso ao maior componente — ou seja, o melhor braço é aquele que
mais se aproxima de *reproduzir a escolha atual*. Quanto mais o método realmente
distribui atenção entre componentes (média simples: 56,56%), pior fica.

**Máxima confiança falha do jeito previsível:** com ~4 componentes por caso, o
mais confiante costuma ser um componente errado sobre o qual o classificador está
espúriamente certo. Confiança não é evidência de ser a lesão.

**Treinar no componente correto não ajudou** — `hit` empata ou perde para
`maior` em todas as agregações. Mesmo mostrando ao classificador exatamente qual
região é a lesão durante o treino, ele não aprende a reconhecê-la entre
distratores no teste.

---

## 5. O achado que vale mais que o passo

O oráculo de 83,3% **já foi atacado por três mecanismos independentes**:

| Tentativa | Mecanismo | Resultado |
|---|---|---:|
| docs/148 | heurísticas geométricas | +0,0 |
| docs/149 | seleção aprendida | +0,9, gate falhou |
| **docs/153** | **não selecionar (MIL)** | **−0,35, gate falhou** |

Geometria, seleção supervisionada e ausência de seleção falharam sobre o mesmo
oráculo. A conclusão não é sobre nenhum dos três métodos:

> **O componente que contém a lesão não é distinguível dos demais por nada que a
> representação atual codifique.** O oráculo de 83,3% existe no papel e não é
> acessível.

Isso encerra uma família inteira de abordagens. Os ~15 pontos entre a escolha
atual e o oráculo **não estão disponíveis por seleção, aprendida ou não** — e o
caminho para eles é melhorar a *localização* (produzir menos distratores), não
escolher melhor entre os que existem.

---

## 6. Estado das metas após os Passos 1–3

| Meta | Antes | Depois | Alvo |
|---|---:|---:|---:|
| Subtipo, medido honesto | 61,46% | **61,46%** | 75% |
| Binário, agregado | 75,91% / 76,11% | **inalterado** | 75/75 |

**Nenhum dos três passos moveu o número oficial.** O que produziram foi
conhecimento negativo de boa qualidade:

- **Passo 1:** a fusão é o substrato certo de representação (+12 pts sobre
  fígado inteiro isolado no subtipo), mas não pôde ser validada no binário
  completo — falta harmonizar o OpenSwiss.
- **Passo 2:** o C herdado estava mal escolhido; corrigi-lo rende ~2 casos, dentro
  do ruído.
- **Passo 3:** o oráculo de seleção está fechado.

A estimativa de docs/150 §5 — "65–68% após os Passos 1–3" — **não se
concretizou**. Ela supunha que os passos somariam; os ganhos ficaram dentro do
ruído de 318 casos e o Passo 3 não rendeu nada.

---

## 7. O que resta

1. **Harmonizar as fases do OpenSwiss.** Dependência estrutural de duas linhas
   (docs/151 §3): sem isso, nem a fusão no binário nem a especificidade do
   experimento FNH podem ser medidas.
2. **Passo 4 — segunda coorte.** Aquisição, não engenharia. Continua sendo o
   único caminho para 75% de subtipo, e agora com um argumento a mais: o teto
   por seleção está demonstrado como fechado.
3. **Melhorar a localização**, não a seleção — é onde os pontos restantes estão.

`clinical_use_allowed` permanece `false`.
