# Subtipo com a melhor representação, medido honestamente — gate falha por meio caso

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/subtipo_honesto_fusao_v1/`
**Contexto:** [docs/146](146_PASSO2_MEDICAO_HONESTA.md) (oficial 61,46%), [docs/155](155_REMEDICAO_UNIAO_VEREDITO_FUSAO.md) (fusão encerrada no binário)

**Gate pré-especificado:** balanceada ≥ 65% sobre os 335 alvos (alvo honesto de docs/150).

---

## 1. A lacuna que este documento fecha

O número oficial de subtipo, **61,46%**, foi medido com a representação de
**recorte apenas**. Depois descobrimos que a fusão é melhor — 63,44% (docs/151),
65,25% (docs/152) — mas ambos foram medidos nos **318 casos que têm recorte**, e
docs/151 mostrou que esse subconjunto é enviesado: exclui justamente os casos em
que a localização falhou.

**A configuração conhecida como melhor nunca passou pela medição que vale.**

docs/155 encerrou a fusão no endpoint binário por não generalizar entre coortes.
O subtipo é LLD-only por natureza, então aquele viés não se aplica aqui.

---

## 2. Resultado

Denominador honesto: os 335 alvos, sem predição = erro.

| Braço | Balanceada | Top-1 | Sem predição |
|---|---:|---:|---:|
| R — recorte apenas | 61,65% | 60,90% | 3 |
| A — fígado inteiro | 49,87% | 54,03% | 14 |
| H — fusão, fígado como fallback | 61,20% | 64,18% | 14 |
| **Cascata — melhor representação disponível** | **64,81%** | **67,16%** | **0** |

**Sanidade:** o braço R deu 61,65% contra 61,46% oficial — mesma régua, a
comparação é válida.

A cascata usa fusão nos 318 casos que têm as duas representações, recorte nos 14
sem fígado inteiro e fígado inteiro nos 3 sem recorte. **Cobertura total, nenhum
caso vira erro automático.**

### Gate

> **64,81% contra 65% exigidos. FALHA por 0,19 ponto — menos de meio caso.**

Fica registrado como reprovado. Não se reajusta gate depois de medir, e um gate
perdido por pouco continua perdido.

---

## 3. O padrão que aparece de novo

Acertos absolutos, recorte apenas contra cascata:

| Classe | R | Cascata | Δ |
|---|---:|---:|---:|
| HCC | 95/157 | **117/157** | **+22** |
| FNH | 27/46 | 31/46 | +4 |
| Hemangioma | 44/79 | 45/79 | +1 |
| **Cisto** | 38/53 | **32/53** | **−6** |

**É a mesma assinatura do endpoint binário** (docs/155): a fusão despeja ganho no
HCC e cobra do resto — aqui, do cisto.

Isso é a **terceira confirmação independente** de que a fusão não é uma melhoria
de representação de propósito geral:

1. binário, coortes OpenSwiss: −7 a −8 pontos (docs/154);
2. binário, recorte equiparado: não recuperou (docs/155);
3. subtipo, por classe: HCC +22, cisto −6 (aqui).

> A fusão é, com boa evidência, **um detector de HCC** — não um substrato melhor.

Isso também explica por que a balanceada não sobe tanto quanto o top-1: o top-1
é dominado pelo HCC, que é 47% da coorte, enquanto a balanceada dá o mesmo peso
ao cisto, que regride.

---

## 4. O que é real e o que não é

**Real:** a cascata entrega **+3,35 pontos** sobre o oficial (61,46% → 64,81%) e
elimina os casos sem predição. É a melhor medição honesta de subtipo até aqui.

**Não real:** não é passagem de gate, não é promoção, e não é um ganho limpo — ele
vem acompanhado de regressão no cisto, que já é a classe com pior especificidade
no endpoint binário (64,15%, docs/155 §5 e a avaliação oficial). Piorar o cisto
para melhorar o HCC anda na direção contrária do déficit conhecido do sistema.

**Nada é promovido.** O número oficial de subtipo permanece **61,46%**.

---

## 5. Onde isso deixa a meta de subtipo

| | Valor |
|---|---:|
| Oficial | 61,46% |
| Melhor medição honesta (cascata) | 64,81% |
| Alvo honesto de docs/150 | 65–70% |
| Meta | 75% |

docs/150 §2 já havia demonstrado que 75% é aritmeticamente inalcançável com o
localizador atual: exigiria 94% de acerto de centro, e o oráculo de seleção é
82,4% — fechado por três mecanismos (docs/153).

O que resta é o mesmo de sempre, e não mudou: **melhorar a localização**, que hoje
acerta o centro em 66,87% dos casos, ou adquirir a segunda coorte.

`clinical_use_allowed` permanece `false`.
