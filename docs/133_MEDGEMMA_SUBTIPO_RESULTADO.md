# MedGemma zero-shot para subtipo — Resultado: recusa quase total

**Data:** 29 de julho de 2026
**Pré-especificação:** [docs/132](132_FRENTE_MEDGEMMA_SUBTIPO_PRE_ESPECIFICACAO.md), commitada
em `e6bb9dc` antes de qualquer número
**Artefatos:** `casos/qualification/hybrid_v1/medgemma_subtype_v1/`
**Veredito:** **REPROVADO** nos três critérios

---

## 1. Conclusão

O MedGemma 1.5 4B, olhando os painéis RGB multifásicos, **se recusa a nomear o subtipo em
99,69% dos casos**. Das 321 respostas, 320 foram `INCERTO` e uma foi `HCC` — e essa única
estava errada (o caso era hemangioma).

| Critério | Obtido | Exigido | |
|---|---:|---:|:--|
| Balanceada com `INCERTO` = erro | **0,00%** | ≥ 40% | FALHA |
| Balanceada entre nomeados | **0,00%** | ≥ 50% | FALHA |
| Abstenção | **99,69%** | ≤ 40% | FALHA |

Tempo total: 9,3 min para 321 casos.

---

## 2. Correção de implementação (documentada porque quase produziu um número falso)

A primeira execução gerava texto livre e parseava JSON. Ela processou 136 casos e devolveu
`INCERTO` em **todos**, com os campos `padrao_de_realce` e `confianca` vazios — sinal de que
o JSON nunca foi parseado.

Causa: **o MedGemma 1.5 é um modelo de raciocínio.** A saída crua começa com
`<unused94>thought` e gasta centenas de tokens raciocinando antes de responder. Com
`max_new_tokens=180` o corte acontecia no meio do raciocínio e nenhum JSON chegava a
existir. Aqueles 136 `INCERTO` eram **falha de parsing, não abstenção do modelo**. A rodada
foi interrompida e as predições inválidas foram apagadas.

A versão final usa o **mesmo método do gateway de produção**
(`first_token_restricted_softmax`, [medgemma_server_v14.py:78](../tools/medgemma_server_v14.py)):
prefixa a resposta do assistente com `{"subtipo": "` e faz uma única passada, lendo os
logits do primeiro token de cada classe candidata. Vantagens além de consertar o bug:

- não há geração, portanto não há bloco de raciocínio para atrapalhar;
- **não é possível falhar em parsear** — a saída é uma distribuição de probabilidade;
- primeiros tokens verificados distintos (`HCC`:220665, `HEMANGIOMA`:2808, `CISTO`:236780,
  `FNH`:236811, `INCERTO`:42829), a mesma checagem que a produção faz;
- uma passada por caso em vez de centenas de tokens: 9,3 min em vez de horas.

Prompt, classes e gate permaneceram idênticos ao pré-registrado. O que mudou foi o
mecanismo de leitura da resposta, não o critério — mesma natureza da correção
float32/float64 na Fase 1 (docs/129).

**Portanto o resultado desta rodada não é artefato de parsing.** A abstenção é real.

---

## 3. Matriz

| verdade \ predito | fnh | hcc | hemangioma | hepatic_cyst | INCERTO | recall |
|---|---:|---:|---:|---:|---:|---:|
| **fnh** | 0 | 0 | 0 | 0 | 45 | 0,00% |
| **hcc** | 0 | 0 | 0 | 0 | 152 | 0,00% |
| **hemangioma** | 0 | 1 | 0 | 0 | 72 | 0,00% |
| **hepatic_cyst** | 0 | 0 | 0 | 0 | 51 | 0,00% |

---

## 4. Ressalva importante sobre o alcance desta conclusão

Este resultado **não prova que o MedGemma é incapaz de subtipagem hepática.** Prova que ele
é incapaz *com o que damos a ele hoje*: três fases T1 pós-contraste fundidas nos canais R,
G e B de um composto sintético, sem `C-pre`, sem `T2WI` e sem `DWI`.

A recusa em 99,7% dos casos é, na verdade, **comportamento defensável**: sem pré-contraste
não é possível afirmar se a lesão realça, e sem T2 não é possível separar cisto de
hemangioma com segurança. Um modelo médico que se cala nessas condições está mais correto
do que um que arrisca.

---

## 5. Consequência

Com MedSigLIP zero-shot em 27,55% (docs/131) e MedGemma em abstenção quase total, **as duas
rotas baratas para subtipo estão eliminadas.** Nenhuma delas exigia engenharia de features,
e nenhuma funcionou.

A Frente 2 — ingerir `C-pre`, `T2WI` e `DWI`, que estão em disco para as 335 casos LLD —
passa a ser o caminho justificado, não por preferência, mas por eliminação documentada das
alternativas.

`clinical_use_allowed` permanece `false`. Nada de subtipo é exposto em nenhuma superfície.
