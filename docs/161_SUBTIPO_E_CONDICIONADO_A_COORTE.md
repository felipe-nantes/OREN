# A capacidade de subtipo é condicionada à coorte, não à lesão

**Data:** 1 de agosto de 2026
**Artefatos novos:** `experiments/massa_classe_real_vs_sintetico_v1/`
**Base:** coorte sintética `synthetic_external_stress_v1_330` e sua avaliação `etapa_c_evaluation_v1`

---

## 1. Objetivo testado

A avaliação da coorte sintética registrou **0% de acerto top-1 nas quatro classes
de subtipo** e predições concentradas em `positive_unspecified` /
`negative_unspecified` (docs/synthetic_external_stress_v1.md §"Frozen-classifier
technical stress result").

Duas explicações levam a ações opostas e a documentação existente não as separa:

- **(a) entrelaçamento de domínio** — a capacidade de subtipo está condicionada à
  assinatura de aquisição do LLD;
- **(b) classes-saco** — as duas `unspecified`, por serem heterogêneas, absorvem
  qualquer coisa fora de distribuição, e o 0% seria artefato de *argmax* sobre
  preferência fraca.

---

## 2. O que foi medido

Massa de probabilidade por classe, não apenas o argmax, usando **os mesmos modelos
por fold** (`outer_fold_*.joblib`) aplicados aos dados reais.

| Coorte | Massa nas 4 classes LLD | Massa nas 2 `unspecified` |
|---|---:|---:|
| `lld_mmri` (real) | **99,32%** | 0,68% |
| `openswisshcc_development` (real) | 1,43% | 98,57% |
| `openswisshcc_consumed_holdout` (real) | 1,47% | 98,53% |
| **sintética** (fundo NIH) | **6,93%** | 93,07% |

**A explicação (b) está refutada.** Não é preferência fraca amplificada pelo
argmax: no LLD real as quatro classes recebem 99,32% da massa. O roteamento é
quase puro nas duas direções.

---

## 3. O detalhe que decide

**As assinaturas de lesão da coorte sintética vieram do LLD** — 219 doadores,
todos casos do nosso protocolo (`donor_library.json`, `source_repo_id:
wanglab/LLD-MMRI-MedSAM2`). Os fundos anatômicos vieram do NIH.

Mesmo com a lesão construída a partir de parâmetros do LLD, o modelo roteia o caso
**para longe** das classes do LLD: 6,93%, mais perto do OpenSwiss (1,4%) do que do
LLD (99,3%).

> O roteamento segue o **fundo anatômico e a aquisição**, não o conteúdo da lesão.

Isso separa as duas coisas de forma limpa, o que o probe de domínio de docs/131
não conseguia fazer: lá se mostrou que a coorte é previsível; aqui se mostra que a
**decisão de classe é determinada por ela**.

---

## 4. Consequência para a meta de subtipo

O número oficial de subtipo — 61,46% — é medido inteiramente dentro do LLD. O
problema não é apenas ausência de validação externa:

> **Numa coorte nova, as quatro classes de subtipo praticamente não seriam
> preditas.** Não é degradação — é não disparar.

Qualquer projeção de desempenho de subtipo fora do LLD, com o modelo atual, é
infundada.

---

## 5. A causa provável, e por que ela é boa notícia

O espaço de rótulos **força** esse comportamento. Os casos do OpenSwiss só podem
receber `positive_unspecified` / `negative_unspecified`, porque seus subtipos não
são documentados na fonte protegida. O modelo aprende então:

> "se parece OpenSwiss → *unspecified*; se parece LLD → uma das quatro."

Isso é **artefato do rótulo**, não necessariamente falha da representação. E se
for o rótulo, é corrigível.

### Consequência direta para a segunda coorte

[docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md) lista o rótulo de subtipo como
parte do pedido. **Este resultado o torna obrigatório, não desejável.** Uma coorte
nova com apenas rótulo binário reproduziria exatamente a mesma patologia: criaria
um terceiro par de classes `unspecified` e o modelo aprenderia a rotear para elas.

---

## 6. Teste que separa rótulo de representação

Ainda não executado, e é o próximo passo natural:

Treinar um classificador de **4 classes apenas** — LLD, sem as `unspecified` — e
aplicá-lo à coorte sintética.

| Resultado | Leitura |
|---|---|
| As 4 classes recebem massa razoável | a patologia é do **espaço de rótulos**; corrigível com rótulo fino na coorte nova |
| Continua colapsando | a patologia é da **representação**; muito mais difícil |

O experimento exige embeddings MedSigLIP dos painéis sintéticos. A avaliação
atual renderizou os painéis mas não persistiu embeddings — seria preciso embutir
os 330 × 3 painéis.

---

## 7. Limitações

- A coorte sintética **não é uma terceira coorte clínica**: fundos NIH, lesões
  construídas de assinaturas LLD, negativos de construção. Nada aqui estima
  sensibilidade, especificidade ou prevalência.
- Não é possível separar "o modelo roteia por domínio" de "imagens sintéticas são
  suficientemente fora de distribuição para qualquer modelo falhar". O contraste
  de 99,32% contra 6,93% mostra que **existe** roteamento por domínio; não prova
  que uma coorte clínica real cairia tanto.
- As massas vêm de predições OOF: cada modelo de fold viu os demais folds. O
  roteamento é consistente entre os cinco.

---

## 8. Verificações executadas

Todas passaram, sem alteração em nenhum arquivo original:

| Comando | Resultado |
|---|---|
| `tools/verify_synthetic_external_stress_v1.py` | assinatura `9e8b81a6…` confere; 330 casos; hashes, geometria e contenção de lesão verificados |
| `tools.verify_synthetic_external_stress_v1_evaluation` | 330 registros, 0 falhas técnicas, métricas recomputadas |
| `pytest tests/test_synthetic_external_stress_v1*.py` | 7 passaram |

`research_only: true` · `clinical_use_allowed: false` · `specificity_estimation_allowed: false`
