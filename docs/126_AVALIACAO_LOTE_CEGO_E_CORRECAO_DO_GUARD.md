# Avaliação do lote cego de 100 casos + correção do guard in-sample

**Data:** 28 de julho de 2026
**Predições:** congeladas em `casos/webapp/internal_blind_batch_v1/` (doc 125)
**Rótulos:** abertos **apenas nesta etapa**, com todas as predições já em disco —
o mesmo padrão de avaliação usado em todo o projeto.

---

## 1. Resposta curta

**Acurácia = 86,00%** (sensibilidade 84,00% / especificidade 88,00%), medida sob
o endpoint para o qual a Etapa C foi treinada.

E esse número **não é validação**: 86 dos 100 casos estavam no conjunto de treino
do bundle.

---

## 2. Dois achados que precedem qualquer número

### 2.1 A coleção cega usa um endpoint diferente do treino

A coleção rotula **hemangioma, cisto hepático e FNH como POSITIVE** — ela pergunta
*"existe lesão focal?"*. A Etapa C foi treinada com o endpoint do doc 120:
*"existe patologia-alvo (HCC) suspeita?"*, onde esses três são **NEGATIVOS**
(mimetizadores benignos).

| Subtipo | Coleção cega | Treino Etapa C | n |
|---|---|---|---:|
| hepatic_cyst | POSITIVE | NEGATIVE | 7 |
| hemangioma | POSITIVE | NEGATIVE | 7 |
| fnh | POSITIVE | NEGATIVE | 6 |

O modelo classificou **20/20** desses casos como NEGATIVA — exatamente o
comportamento treinado. Sob o endpoint da coleção, cada acerto vira falso
negativo.

Por isso há dois números, e apenas um deles mede o modelo:

| Endpoint | Sens. | Espec. | **Acurácia** | O que mede |
|---|---:|---:|---:|---|
| Coleção (*"lesão focal?"*) | 60,00% | 80,00% | **66,00%** | desacordo de definição |
| Treino Etapa C (*"patologia-alvo?"*) | 84,00% | 88,00% | **86,00%** | o modelo |

Reportar 66% como desempenho seria incorreto: penaliza o modelo por acertar.

### 2.2 O guard in-sample dava falso negativo — defeito real, agora corrigido

Os 100 relatórios declararam `in_sample=false`. A proveniência real
(`original_case_id`/`patient_group_id` contra o treino do bundle) mostra
**86 in-sample e 14 out-of-sample**.

Causa: o guard comparava identificadores cegos (`ARGOS-BLIND-0001`) com ids de
treino (`anon-lld-*`, `anon-openswiss-*`). Namespaces distintos nunca casam, e o
código binário traduzia "não encontrei" como "não estava no treino" —
**certificando como limpo um lote majoritariamente in-sample**. É a falha mais
perigosa possível num guard: silenciosa e na direção que valida números
inflados.

---

## 3. Resultado sob o endpoint do treino

```text
n=100   TP=42  TN=44  FP=6  FN=8   (2 falhas técnicas contadas como erro)
sensibilidade  = 84,00%   IC95% [71,5–91,7]
especificidade = 88,00%   IC95% [76,2–94,4]
ACURÁCIA       = 86,00%
```

Estratificado pela sobreposição real com o treino:

| Recorte | n | Sens. | Espec. | Acurácia |
|---|---:|---:|---:|---:|
| **In-sample (inflado)** | 86 | 86,11% | 88,00% | 87,21% |
| **Out-of-sample** | 14 | 78,57% | n/a | 78,57% |

O recorte out-of-sample tem 14 casos, **todos positivos** — sem negativos, não há
especificidade, e a sensibilidade tem IC95% [52,4–92,4]. Amostra insuficiente
para qualquer conclusão.

Por subtipo (endpoint do treino):

| Subtipo | n | Eixo | Valor |
|---|---:|---|---:|
| hcc | 50 | sensibilidade | 84,00% |
| hcc_absent_chronic_liver_control | 30 | especificidade | 80,00% |
| hemangioma | 7 | especificidade | 100,00% |
| hepatic_cyst | 7 | especificidade | 100,00% |
| fnh | 6 | especificidade | 100,00% |

O cisto atingiu 100% aqui, o oposto do gargalo de 58% que a Etapa A mediu no
LLD-MMRI. Com n=7 e in-sample, isso não sustenta conclusão.

---

## 4. A correção do guard

`dtwin/learning/visual_inference.py` passa a emitir **três estados** em vez de
dois, porque *"não encontrado no treino"* e *"não comparável ao treino"* são
fatos diferentes:

```text
in_sample      -> comprovadamente visto no treino
out_of_sample  -> comprovadamente NÃO visto (namespace comparável, sem match)
unknown        -> não é possível decidir (namespace estranho ao treino)
```

- `in_sample` só é `True` quando comprovado; nunca em `unknown`.
- Novo campo `provably_out_of_sample` — os chamadores não podem mais ler
  `not in_sample` como "out-of-sample".
- Novo parâmetro `provenance`: um mapa identificador→id original (vindo de um
  índice autorizado) torna o veredito definitivo.
- `partition_in_sample` e `run_visual_benchmark` ganham o bucket `unknown`, que
  **nunca entra no headline** e dispara aviso explícito.

Comportamento verificado contra o lote real:

```text
sem proveniência : in_sample=0   out_of_sample=0    unknown=100
com proveniência : in_sample=86  out_of_sample=14   unknown=0
```

Ou seja: sem informação o guard **se recusa a afirmar** (antes afirmava
"100 out-of-sample", que era falso); com o índice autorizado, recupera a verdade.

Regressão: `test_foreign_namespace_is_unknown_not_out_of_sample` reproduz
exatamente o cenário que falhou.

---

## 5. O que pode e o que não pode ser afirmado

**Pode:**
- O fluxo visual roda de ponta a ponta e produz decisões em 98/100 casos.
- Sob o endpoint para o qual foi treinado, acertou 86% deste lote.
- O modelo respeita a distinção patologia-alvo vs. mimetizador benigno: 20/20
  hemangiomas/cistos/FNH classificados como NEGATIVA.

**Não pode:**
- Chamar 86% de acurácia validada, generalização ou desempenho externo — 86% dos
  casos estavam no treino e o próprio README da coleção declara
  *"Not External Validation — Retrospective Multicohort"*.
- Usar o recorte out-of-sample (n=14, sem negativos) como estimativa.
- Comparar 86% com os 75,91%/76,11% do nested-OOF da Etapa C: são populações e
  condições diferentes; o OOF continua sendo a estimativa honesta de
  generalização.

---

## 6. Consequência prática

Toda avaliação futura sobre coleções renomeadas precisa **fornecer o mapa de
proveniência**; sem ele o relatório agora acusa `unknown` e recusa headline, que
é o comportamento correto. E qualquer coorte candidata a validação real precisa,
antes de mais nada, de **endpoint idêntico ao do treino** — caso contrário mede
desacordo de definição, não qualidade.
