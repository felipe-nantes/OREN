# Retirar a saída de escape não resolve — e o experimento não decide o que eu queria

**Data:** 1 de agosto de 2026
**Artefatos:** `experiments/quatro_classes_sintetico_v1/`, `experiments/synthetic_panel_embeddings_v1/`
**Continua** [docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md)

---

## 1. A pergunta

docs/161 mostrou que o modelo oficial manda 93,07% da massa de probabilidade para
`positive_unspecified` / `negative_unspecified` na coorte sintética, contra 0,68%
no LLD real. A hipótese era que o **espaço de rótulos** força isso: casos do
OpenSwiss só podem receber `unspecified`, então o modelo aprende "se não parece
LLD → *unspecified*".

Teste: um classificador de **4 classes apenas**, sem saída de escape, aplicado aos
330 casos sintéticos. 990 painéis embutidos no MedSigLIP.

---

## 2. Resultado

Sobre os 230 casos com lesão de construção. Acaso = 25%.

| Braço | Treino | Top-1 | Balanceada |
|---|---:|---:|---:|
| A — todo o LLD | 321 casos | **26,52%** | 27,67% |
| B — LLD sem doadores | 113 casos | **27,39%** | 26,25% |

**Ambos no acaso.** Retirar a saída de escape não restaura discriminação nenhuma.

O braço A, com todos os 321 casos **e os doadores dentro do treino** — vantagem
máxima possível — despeja quase tudo em `fnh`:

| Verdade | → fnh | → hcc | → hemangioma | → cisto |
|---|---:|---:|---:|---:|
| fnh (50) | 27 | 5 | 13 | 5 |
| hcc (60) | **32** | 6 | 12 | 10 |
| hemangioma (60) | **29** | 1 | 17 | 13 |
| cisto (60) | **32** | 3 | 14 | 11 |

O braço B colapsa em duas classes: `fnh` e `hepatic_cyst` recebem **zero** massa, e
tudo se divide entre `hcc` e `hemangioma` de forma praticamente aleatória.

---

## 3. Por que o experimento não decide

Minha leitura pré-especificada tinha **duas** saídas: espaço de rótulos ou
representação. A realidade tem **três**, e eu não previ a terceira.

### A explicação mais parcimoniosa

A biblioteca de doadores transfere apenas **escalares**:

```
category, volume_ml, extent_mm_zyx, largest_component_voxels,
phases: {arterial, venous, delayed} × {contrast_z, texture_ratio}
```

São cerca de oito números por lesão. **Não transfere a arquitetura interna** —
cicatriz central de FNH, preenchimento centrípeto de hemangioma, *washout* de HCC.
O algoritmo de síntese é `highpass-parenchyma-v2_centroid-motion-implant-v1`: um
implante paramétrico.

> O subtipo se distingue justamente pela morfologia que a síntese não reproduz.

Se as lesões sintéticas **não carregam** o sinal discriminativo, desempenho no
acaso é o esperado — e não diz nada sobre rótulo nem sobre representação.

### As três leituras, todas compatíveis com o dado

1. a representação não transfere entre domínios de aquisição;
2. as imagens sintéticas estão fora de distribuição demais para qualquer
   transferência;
3. **as lesões sintéticas não contêm informação de subtipo**, porque a síntese
   transfere oito escalares e o subtipo mora na morfologia.

A terceira é a mais simples e a mais provável. **Não consigo separá-las com esta
coorte.**

---

## 4. O que fica de pé e o que não fica

**Fica** — docs/161 permanece válido. O contraste 99,32% (LLD real) contra 1,43%
(OpenSwiss real) é medido em **dados reais** e mostra roteamento por coorte de
forma inequívoca. Aquele achado não depende da coorte sintética.

**Não fica** — a hipótese de que o espaço de rótulos causa o colapso **não foi
confirmada nem refutada**. O experimento é inconclusivo para sua própria
pergunta.

**Cai por terra** — o uso da coorte sintética como aumento de treino para FNH,
previsto em [docs/160](160_PLANO_COORTE_SINTETICA.md) §7. Se as lesões sintéticas
não carregam morfologia de subtipo, treinar nelas ensina a associar rótulo a
tamanho e contraste — exatamente o atalho errado. O gate primário daquele plano
(recall de FNH real sobe ≥ 5 pontos) tem chance baixa, e o risco de piorar o
modelo é concreto.

---

## 5. Ressalva sobre o braço B

O braço B exclui os doadores e sobra com **113 casos de treino**, contra 321 do A.
Não é apenas "sem vazamento" — é um terço dos dados e um subconjunto enviesado. O
colapso em duas classes provavelmente reflete isso.

Portanto **o braço A é a leitura limpa aqui**: com dados completos e vantagem de
vazamento, o desempenho é 26,52% contra 25% de acaso.

---

## 6. Consequência prática

A pergunta "o colapso do subtipo é do rótulo ou da representação?" **continua
aberta**, e a coorte sintética não pode respondê-la.

Só uma coorte **real** de outra instituição, **com rótulo fino de subtipo**,
responde — o que reforça, sem alterar, a especificação de
[docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md). E o argumento de docs/161 de que
o rótulo de subtipo é obrigatório permanece: ele vem de dados reais, não deste
experimento.

---

## 7. O que a coorte sintética serve

Confirmado pelo que se viu aqui, e coerente com o limite declarado na sua própria
documentação:

**Serve:** teste de estresse de ingestão multifásica, geometria, robustez a
domínio, comportamento do pipeline fora de distribuição, detecção de falhas
técnicas. Nisso ela funcionou — 330/330 sem falha técnica é informação útil sobre
robustez de execução.

**Não serve:** estimar acurácia, sensibilidade, especificidade ou prevalência;
aumento de treino para subtipo; validação externa; e — como este documento mostra
— nem como substrato para responder perguntas sobre a natureza do colapso de
subtipo.

`construction_labels_only: true` · `clinical_ground_truth: false` ·
`specificity_estimation_allowed: false` · `clinical_use_allowed: false`
