# Fase 1 — O classificador sabe nomear o subtipo? (pré-especificação)

**Data:** 29 de julho de 2026
**Status ao escrever este documento:** nenhum resultado foi calculado ainda.
**Objetivo:** decidir, com critério fixado ANTES de ver qualquer número, se o ARGOS pode
expor o subtipo clínico da lesão além da decisão binária.

---

## 1. Por que esta fase existe

O bundle de produção da Etapa C é internamente **multiclasse**:
`[fnh, hcc, hemangioma, hepatic_cyst, negative_unspecified, positive_unspecified]`.
Ele calcula `predict_proba` sobre as 6 classes a cada painel
([medsiglip_multiclass_classifier.py:315](../dtwin/learning/medsiglip_multiclass_classifier.py)),
soma a massa das classes positivas e descarta o resto uma linha depois, em `_case_scores`.

A informação de subtipo, portanto, **já é calculada e jogada fora**. A pergunta não é se
dá para expô-la — dá, com poucas linhas. A pergunta é se ela **acerta**, e isso nunca foi
medido: `cross_validated_selection_metrics` do bundle só contém TP/TN/FP/FN, e as
predições OOF gravaram apenas o `score` binário colapsado.

Expor um rótulo clínico não validado numa tela médica é pior do que não expor: um nome
como "hemangioma" vira âncora cognitiva mesmo acompanhado de aviso.

---

## 2. O que a estrutura dos rótulos já nos diz

Distribuição das 6 classes nos 467 casos de treino:

| Classe | n | Polaridade | Coorte |
|---|---:|---|---|
| `hcc` | 157 | POSITIVO | lld_mmri |
| `hemangioma` | 79 | negativo | lld_mmri |
| `negative_unspecified` | 69 | negativo | openswisshcc |
| `positive_unspecified` | 63 | POSITIVO | openswisshcc |
| `hepatic_cyst` | 53 | negativo | lld_mmri |
| `fnh` | 46 | negativo | lld_mmri |

Dois fatos estruturais decorrem daqui:

**a) Entre os positivos só existe uma variação nomeada: HCC.** Os outros 63 positivos são
`positive_unspecified`, do OpenSwiss, que não declara subtipo. A pergunta original — "qual
a variação nos fígados positivos" — não tem resposta rica nestes dados. A pergunta que os
dados sustentam é a espelhada: **entre os negativos, qual variante benigna** (hemangioma,
cisto, FNH ou ausência de lesão).

**b) Os 4 subtipos vêm todos de uma única coorte (lld_mmri).** Isso cria um confundimento
sério: um modelo que apenas reconheça "isto é LLD-MMRI" já acerta que o caso pertence ao
grupo dos subtipos nomeados. A ablação da Etapa C mediu exatamente esse efeito e achou
**+0,049 AUC vindos de separação de domínio contra apenas +0,010 dos rótulos finos**.

O desenho abaixo neutraliza (b) medindo o subtipo **apenas dentro do LLD**, onde a coorte
é constante e portanto não pode ser o atalho.

---

## 3. Método

Sem retreino e sem GPU. Os artefatos congelados da Etapa C já contêm tudo:

- os **5 modelos por outer fold** (`outer_fold_{0..4}.joblib`)
- as seleções por fold (C, agregação, limiar) em `fold_selection.json`
- os **splits congelados** (`hybrid_v1_nested_splits.json`, 5 outer × 4 inner, agrupados
  por paciente), `splits_sha256 = 41c15cc1…`
- os **embeddings em cache** (1339 vetores, `embedding_signature = 4836ef5458…`)

Procedimento: para cada outer fold, carregar o modelo daquele fold e rodar `predict_proba`
sobre os embeddings dos seus casos de teste. Isso reproduz a predição out-of-fold original
— cada caso é avaliado por um modelo que nunca o viu — mas preservando o vetor de 6
classes em vez de colapsá-lo.

Agregação painel → caso: **média** das distribuições entre os painéis do caso. A média de
distribuições continua sendo uma distribuição, o que `top2_mean` não garante. A agregação
selecionada em cada fold é usada como verificação de robustez, não como primária.

### Pré-condição de correção (bloqueante)

Somando a massa das classes positivas do vetor extraído e agregando com a agregação
selecionada de cada fold, o resultado tem de reproduzir **exatamente** o `score` já
congelado em `oof_predictions.jsonl`. Se não reproduzir, a extração está lendo outra coisa
e nenhum número seguinte vale. Este teste é o que garante que estamos medindo o modelo
real e não uma re-derivação parecida.

---

## 4. Gate — fixado agora, antes de qualquer resultado

**Primário (controlado para confundimento).** Acurácia balanceada da tarefa de 4 classes
(`hcc`, `hemangioma`, `hepatic_cyst`, `fnh`) restrita aos casos do LLD-MMRI, onde a coorte
é constante:

> **≥ 60%** (acaso = 25%)

**Secundário.** Nenhum dos 4 subtipos com recall < **40%**.

**Diagnóstico (não é gate).** A mesma métrica na tarefa de 6 classes sobre os 467 casos.
Espera-se que seja inflada pelo sinal de coorte, já que as classes `*_unspecified`
coincidem com o OpenSwiss. A **diferença** entre os dois números é a medida direta de
quanto o multiclasse está fazendo geografia em vez de biologia — e será reportada
explicitamente.

### Decisão amarrada ao gate

| Resultado | Consequência |
|---|---|
| Primário ≥ 60% **e** secundário cumprido | Segue para a Fase 2: expor `class_probabilities` como informação lateral, com os ICs medidos aqui. A decisão oficial continua binária. |
| Qualquer um falha | **Não expor.** O caminho passa a ser coletar subtipo numa segunda coorte para quebrar o confundimento com domínio. |

Não haverá iteração sobre o gate depois de ver o resultado. Este é o mesmo compromisso
honrado na Etapa B, quando duas sondas pré-especificadas falharam (AUC 0,486 e 0,554) e o
resultado foi aceito em vez de reajustado.

---

## 5. O que esta fase NÃO decide

- Não altera o modelo, o limiar, nem a decisão binária.
- Não produz estimativa de generalização para coortes novas: os 467 casos são o conjunto
  de desenvolvimento, e o subtipo vive numa única coorte.
- Não valida uso clínico. `clinical_use_allowed` permanece `false`.
