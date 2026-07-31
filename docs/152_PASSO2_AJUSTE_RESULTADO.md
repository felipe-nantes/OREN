# Passo 2 — Seleção de C e agregação de recortes: o gate passa, o efeito não se estabelece

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo2_ajuste_v1/`
**Passo 2** de [docs/150](150_PLANO_FINAL_METAS_75.md) · continua [docs/151](151_PASSO1_FUSAO_RESULTADO.md)

**Gate pré-especificado:** ganho ≥ 1,5 ponto sobre o Passo 1 (63,44%).

---

## 1. Resultado bruto

Endpoint de subtipo, 318 casos do LLD, splits congelados:

| Configuração | Balanceada | FNH | HCC | Hemang. | Cisto |
|---|---:|---:|---:|---:|---:|
| fusão + margem única + C=0,01 *(Passo 1)* | 63,44% | 64,4% | 80,0% | 58,3% | 51,0% |
| fusão + TTA de margens + C=0,01 | 64,38% | 64,4% | 80,7% | 55,6% | 56,9% |
| **fusão + margem única + C aninhado** | **65,25%** | 64,4% | 78,0% | 59,7% | 58,8% |
| fusão + TTA + C aninhado | 63,60% | 64,4% | 78,7% | 58,3% | 52,9% |

Ganho da melhor configuração: **+1,81 ponto**. **O gate, na sua letra, passa.**

---

## 2. Por que não aceitei isso de imediato

Um padrão incoerente: **cada ajuste ajuda sozinho e juntos pioram.** TTA sozinho
+0,94; C aninhado sozinho +1,81; os dois juntos **+0,16**. Efeitos reais e
independentes deveriam somar, não cancelar. Isso é assinatura de ruído.

Segundo sinal: no braço combinado, o C escolhido oscila de **0,001 a 1,0** entre
folds — isso é instabilidade de seleção, não aprendizado.

Terceiro: o "melhor" foi escolhido entre 4 braços olhando o próprio OOF.

---

## 3. Verificação pareada

### (A) O ganho em número de casos

| | |
|---|---:|
| predições alteradas | 22 de 318 |
| erradas → certas | 11 |
| certas → erradas | 9 |
| **saldo líquido** | **2 casos** |

**+1,81 ponto = 2 casos de 318.**

### (B) Bootstrap pareado por caso (4000 reamostragens)

| | |
|---|---:|
| diferença média | +1,87 pts |
| **IC 95%** | **[−1,28, +5,12] pts** |
| P(diferença ≤ 0) | 0,128 |

**O intervalo cruza zero.** O ganho não é distinguível de ruído.

### (C) A seleção aninhada faz trabalho?

| C fixo | Balanceada |
|---:|---:|
| 0,001 | 64,42% |
| **0,003** | **65,64%** |
| 0,01 *(herdado)* | 63,44% |
| 0,03 | 63,95% |
| 0,1 | 62,97% |
| 0,3 | 61,72% |
| 1,0 | 61,93% |

A curva é **suave e unimodal**, com pico em 0,003 e queda monotônica depois —
formato de estrutura real, não de ruído. **C = 0,01 estava do lado errado do
pico.**

Mas a seleção aninhada rende **−0,39 ponto** em relação a simplesmente fixar
C = 0,003. Toda a maquinaria de seleção interna não entrega nada além de "o C
herdado era grande demais".

---

## 4. Veredito

> **O gate passa mecanicamente. Não conto isso como progresso.**

O efeito são 2 casos líquidos, com IC de 95% cruzando zero. Registro o gate como
cumprido na sua letra — a disciplina do projeto é não reajustar gate depois da
medição, e isso vale nos dois sentidos — mas **o resultado não sustenta a
afirmação de que a acurácia subiu**.

O que é sólido e aproveitável: **a curva de C**. Adotar C = 0,003 em vez de 0,01 é
gratuito, coerente e sem contraindicação. Não é ganho de meta; é remover uma
frouxidão herdada.

**TTA de margens está descartado** — não ajuda isoladamente de forma confiável e
desestabiliza a seleção de C.

---

## 5. Binário (referência interna, apenas LLD)

Mantida a ressalva de docs/151 §1: o OpenSwiss está ausente e o subconjunto é
enviesado. **Não são números de meta.**

| Configuração | Sens | Esp |
|---|---:|---:|
| fusão margem única + C=0,01 | 80,67% | 82,14% |
| fusão margem única + C aninhado | 81,33% | 81,55% |
| fusão TTA + C=0,01 | 80,67% | **84,52%** |
| fusão TTA + C aninhado | 80,67% | 81,55% |

---

## 6. Estado das metas

Inalterado. Subtipo oficial permanece **61,46%** (docs/146); binário permanece
**75,91% / 76,11%** agregado.

O que os Passos 1 e 2 estabeleceram é de **representação**, não de acurácia
demonstrada: a fusão é o substrato certo, e o C herdado era grande demais. O
ganho medível segue dentro do ruído de 318 casos.

Restam o Passo 3 (múltiplas instâncias, teto no oráculo de 82,4%) e o Passo 4
(segunda coorte).

`clinical_use_allowed` permanece `false`.
