# Fase tardia no localizador — gate reprovado por 2,1 pontos, incluída mesmo assim

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/localizer_delayed_v1/`
**Passo 1** de [docs/144](144_PLANO_FECHAMENTO_META_SUBTIPO.md)
**Veredito do gate:** **REPROVADO** (17,9% vs ≥20% exigido)
**Decisão tomada:** incluir a tardia — por evidência de classe, não por aprovação no gate.

---

## 1. Resultado

Testada nas **67 perdas restantes** após a união venosa+arterial (economia de compute: união
é "venosa ou arterial ou tardia", então acertos anteriores já garantem a união).

Recuperação: **12/67 = 17,9%** das perdas restantes.

| | Recall de localização | IC95 |
|---|---:|---|
| União venosa+arterial (docs/141) | 80,0% | [75,4 – 83,9] |
| **União com tardia** | **83,6%** | **[79,2 – 87,2]** |

| Subtipo | ven+art | +tardia | Δ | Recuperados |
|---|---:|---:|---:|---:|
| **`fnh`** | 63,0% | **73,9%** | **+10,9** | 5 de 17 |
| `hepatic_cyst` | 92,5% | 96,2% | +3,7 | 2 de 4 |
| `hemangioma` | 72,2% | 75,9% | +3,7 | 3 de 22 |
| `hcc` | 84,7% | 86,0% | +1,3 | 2 de 24 |

Efetivo estimado: 63,6% → **66,4%**.

---

## 2. O gate reprovou, e o gate estava mal especificado

Fixei **≥20% de recuperação agregada**. Obtive 17,9%. **Reprovado**, e não é reajustado.

Mas registro o erro de desenho: **usei um critério agregado para uma hipótese que era por
classe.** O plano (docs/144 §2.2) nomeava a FNH como o gargalo — "fraca nas duas metades e
com a menor amostra" — e a hipótese fisiológica da tardia era sobre lesões de realce
progressivo. A tardia entregou **+10,9 pontos exatamente na FNH**, e um agregado de 17,9%
apaga isso, porque é diluído por HCC (+1,3) e hemangioma (+3,7), classes onde a tardia não
tinha por que ajudar.

Dois fatos que não se contradizem:
- o gate, como escrito, **reprovou**;
- a tardia **ajuda substancialmente a classe que mais segura o número**.

---

## 3. Decisão e sua justificativa

**A tardia entra na união**, com a reprovação registrada e o motivo explícito. A decisão é
"incluir por evidência de classe", **não** "aprovado no gate" — a distinção fica no
histórico para quem auditar.

A alternativa seria descartar +10,9 pontos na pior classe por causa de 2,1 pontos num
agregado mal especificado por mim. Não é defensável, e o precedente de docs/141 já registrava
que conclusões agregadas não transferem entre subtipos com fisiologia diferente.

O que **não** foi feito: reescrever o gate para 15% e declarar aprovação. O gate errado fica
no registro como gate errado.

**Lição de método, para os próximos passos:** o gate deve acompanhar a granularidade da
hipótese. Hipótese sobre uma classe exige critério por classe.

---

## 4. O que este resultado fecha

Comparando as duas fases adicionais testadas:

| Fase adicionada | Perdas testadas | Recuperação | Ganho no recall |
|---|---:|---:|---:|
| Arterial (docs/141) | 104 | 35,6% | +11,0 pts |
| **Tardia (este doc)** | **67** | **17,9%** | **+3,6 pts** |

O rendimento **caiu pela metade**. É esperado: os 67 casos restantes são os duplamente
difíceis, que nem a venosa nem a arterial acharam. **Adicionar mais fases ao mesmo localizador
está com rendimento decrescente claro** — uma quarta fase (nativa) renderia menos ainda.

Ganhos futuros de localização exigem **mudar de método**, não mais uma passada do mesmo
modelo: as propostas determinísticas de realce que docs/93 apontou e nunca foram executadas,
agora viáveis com `C-pre` harmonizado.

---

## 5. Estado após o Passo 1

| Métrica | Antes | Agora |
|---|---:|---:|
| Localização (união de 3 fases) | 80,0% | **83,6%** |
| Discriminação (teto, ROI de ground truth) | 79,5% | 79,5% |
| **Efetivo estimado** | 63,6% | **66,4%** |
| Meta | 75% | 75% |

Por classe (localização × discriminação):

| Subtipo | Localiza | Discrimina | Efetivo aprox. |
|---|---:|---:|---:|
| `hepatic_cyst` | 96,2% | 92,5% | ~89% |
| `hcc` | 86,0% | 82,2% | ~71% |
| `hemangioma` | 75,9% | 75,9% | ~58% |
| `fnh` | 73,9% | 67,4% | ~50% |

A FNH saiu de ~42% para ~50%, e agora é limitada por **discriminação** (67,4%), não mais por
localização — inversão causada por este passo.

**Próximo:** Passo 2 de docs/144 — a medição honesta ponta a ponta sobre ROIs **preditas**,
agora usando a união de três fases. O efetivo de 66,4% continua sendo estimativa até lá.

`clinical_use_allowed` permanece `false`.
