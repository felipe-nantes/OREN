# União venosa + arterial no localizador — recall sobe de 69,0% para 80,0%

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/localizer_arterial_v1/`
**Antecedente:** [docs/140](140_LOCALIZADOR_RECALL_COMPLETO.md) — recall venoso 69,0%, com FNH
(45,7%) e hemangioma (53,2%) como gargalo.
**Leitura pré-especificada** no cabeçalho do script, antes de qualquer número.

---

## 1. Resultado

A fase arterial recupera **35,6% (37/104)** das lesões que a venosa perde.

| | Recall | IC95 |
|---|---:|---|
| Venoso (docs/140) | 69,0% | [63,8 – 73,7] |
| **União venosa + arterial** | **80,0%** | **[75,4 – 83,9]** |

| Subtipo | Venoso | União | Δ | Recuperados |
|---|---:|---:|---:|---:|
| `hemangioma` | 53,2% | **72,2%** | **+19,0** | 15 de 37 |
| `fnh` | 45,7% | **63,0%** | **+17,3** | 8 de 25 |
| `hcc` | 76,4% | **84,7%** | +8,3 | 13 de 37 |
| `hepatic_cyst` | 90,6% | 92,5% | +1,9 | 1 de 5 |

O ganho está **concentrado exatamente nas duas classes que eram o gargalo**, como a hipótese
previa: FNH e hemangioma são lesões hipervascularizadas, conspícuas na fase arterial — a
fase onde o pipeline não olhava.

O critério pré-especificado era recuperação ≥ 30% para justificar levar a arterial ao
pipeline. Resultado: **35,6%. Aprovado.**

---

## 2. Por que docs/93 concluiu o oposto, e por que não há contradição

docs/93 testou a união venosa+arterial no OpenSwissHCC e a descartou: *"o ganho de recall
foi insuficiente diante do ruído adicional"*, com apenas 1 de 6 perdas recuperadas.

Não há contradição — há **dependência do alvo**. Aquele estudo era HCC-only. E aqui o HCC é
justamente quem menos ganha proporcionalmente (+8,3 pts, o menor entre as classes sólidas),
porque o HCC já é razoavelmente visível na venosa. Para FNH e hemangioma, cuja assinatura
principal *é* o realce arterial, a conclusão se inverte.

Lição metodológica: uma conclusão negativa medida sobre uma coorte de um único subtipo não
transfere para subtipos com fisiologia diferente. Valeu re-testar em vez de herdar.

---

## 3. Impacto na meta de subtipo

> subtipo efetivo ≈ recall de localização × acerto dado localizado

| Cenário | Recall | Teto (docs/138) | Efetivo |
|---|---:|---:|---:|
| Abordagem atual (fígado inteiro) | — | — | 52,18% |
| Etapa 2 com localizador venoso | 69,0% | 74,5% | 51,4% |
| **Etapa 2 com união venosa+arterial** | **80,0%** | 74,5% | **59,6%** |

A mudança destrava a Etapa 2: de **empate** com a abordagem atual (51,4% vs 52,18%) para
**+7,4 pontos de ganho líquido**. E o custo é baixo — a fase arterial já está harmonizada na
grade venosa em disco; é uma passada adicional do mesmo localizador, sem modelo novo.

### O que ainda falta para 75%

Com recall de união em 80,0%, o teto de discriminação precisaria subir de 74,5% para
**≈ 94%** — o que é irreal. Portanto o alvo continua exigindo avanço nas duas metades:

- **Localização** (80,0% hoje): o teto de recuperação da arterial já foi colhido. Ganhos
  adicionais viriam de propostas determinísticas de realce (docs/93 §final, nunca
  executado), agora viáveis com `C-pre`.
- **Discriminação** (74,5% hoje): descritores de `T2WI`/`DWI` por ROI, que endereçam a maior
  confusão residual, HCC↔FNH (docs/138 §4). As sequências estão em disco.

Combinação plausível para o alvo: 85% × 88% ≈ 75%.

---

## 4. Estado por classe

Cruzando localização de união com discriminação de docs/138:

| Subtipo | Localiza | Discrimina | Efetivo aprox. |
|---|---:|---:|---:|
| `hepatic_cyst` | 92,5% | 90,6% | **~84%** |
| `hcc` | 84,7% | 65,6% | ~56% |
| `hemangioma` | 72,2% | 72,2% | ~52% |
| `fnh` | 63,0% | 69,6% | ~44% |

O cisto segue acima da meta. O HCC passou a ser limitado pela **discriminação**, não pela
localização — inversão em relação a docs/140, e é exatamente o que `T2WI` endereçaria.

---

## 5. Nota de método

Custo reduzido pela metade por construção: como união = venosa **ou** arterial, um acerto
venoso já garante o acerto da união. Bastou rodar a arterial nos 104 casos que a venosa
perdeu, em vez dos 335.

`clinical_use_allowed` permanece `false`. Coorte única; não é estimativa de generalização.
