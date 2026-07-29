# Etapa 1 do subtipo — realce relativo: pré-especificação

**Data:** 29 de julho de 2026
**Plano:** [docs/135](135_PLANO_META_SUBTIPO_75.md) §4, Etapa 1
**Status ao escrever:** painéis de realce construídos; nenhum embedding, treino ou métrica
ainda calculado.

---

## 1. A hipótese testada

Os subtipos fracos (cisto 33,33%, hemangioma 47,95%, FNH 51,11%) falham porque o painel
atual funde três fases **pós**-contraste, e nesse espaço "esta lesão realça?" é
inrespondível. Se o déficit é de informação e não de capacidade, dar ao modelo o **realce
verdadeiro** — `(pós − pré)/pré`, com o `C-pre` que já está harmonizado em disco — deve
subir a acurácia balanceada.

---

## 2. O que muda e o que é mantido constante

Ablação de **variável única**. Mantidos idênticos ao pipeline da Etapa C:

- os **splits congelados** (`hybrid_v1_nested_splits.json`, 5×4, por paciente)
- os **rótulos** (`build_multiclass_labels`, mesmas 6 classes)
- o **MedSigLIP congelado** (mesmo `medsiglip_frozen_v1.yaml`)
- a **cabeça** (regressão logística multinomial, `_fit_model`, `class_weight=balanced`)
- os **índices axiais** de cada painel (reusados dos manifestos existentes)

Muda **só o conteúdo dos canais**: de três fases pós para realce relativo ponderado por
confiança (`build_lld_mmri_v23_enhancement_panels.py`, v2). Assim, qualquer diferença de
métrica é atribuível ao realce, não a outra variável.

---

## 3. Método de medição

1. Embutir os 3 painéis de realce de cada caso com o MedSigLIP congelado → matriz
   (n_painéis × 1152), L2-normalizada, igual ao treino.
2. **Nested-OOF** sobre os splits congelados: para cada outer fold, treinar `_fit_model`
   nos casos de treino e prever `predict_proba` (6 classes) nos casos de teste — cada caso
   é avaliado por um modelo que nunca o viu.
3. Agregar painel→caso pela **média** das distribuições (preserva o simplex).
4. `argmax` entre as 4 classes de subtipo, apenas nos casos LLD.

C do classificador: reusa o `selected_c_value = 0.01` do bundle de produção, para não
introduzir uma segunda variável. (Uma varredura de C fica para depois, se o realce passar.)

---

## 4. Gate — fixado antes de qualquer número

Âncoras: acaso 25%, supervisão atual **52,18%** (docs/129).

| Critério | Exigido |
|---|---|
| **Primário** — acurácia balanceada, 4 subtipos, LLD | ≥ **62%** (de 52,18%, +10 pts) |
| **Secundário** — recall de `hepatic_cyst` | ≥ **55%** (de 33,33%) |

**Os dois precisam passar.** O cisto é o teste mais direto da hipótese física: se o realce
verdadeiro não levanta a classe que mais depende de "não realça", a hipótese está errada e
não se deve gastar a Etapa 2 (features por lesão) sobre ela.

### Decisão

| Resultado | Consequência |
|---|---|
| Ambos passam | Hipótese confirmada. Prosseguir: harmonizar `T2WI`/`DWI` e depois Etapa 2. |
| Cisto sobe mas balanceada < 62% | Realce ajuda parcialmente; avaliar combinar realce + fases pós antes da Etapa 2. |
| Cisto não sobe | Hipótese refutada. Revisar antes de investir — provavelmente a resolução/registro do painel de fígado inteiro é grosseira demais e a Etapa 2 (ROI) vira pré-requisito, não sucessora. |

Além do gate, será reportada a **precisão contra prevalência por classe** — o teste que
desmontou o falso "90% de recall no cisto" em docs/131. Recall alto com precisão ≈
prevalência é colapso, não detecção.

Sem iteração sobre o gate após ver o resultado (Etapa B, docs/128, 130, 132).

---

## 5. Fora de escopo aqui

- Não altera produção nem o endpoint binário.
- Não é estimativa de generalização: coorte única, in-sample para o desenvolvimento.
- A sonda de invariância de domínio sobre os embeddings de realce será medida em separado;
  aqui o foco é se o realce carrega **biologia**, a sonda mede se carrega **coorte**.
