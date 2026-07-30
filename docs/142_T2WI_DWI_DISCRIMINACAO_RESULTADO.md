# T2WI e DWI na discriminação — REPROVADO: +0,23 ponto

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/roi_ceiling_t2dwi_v1/`
**Antecedente:** [docs/141](141_LOCALIZADOR_UNIAO_ARTERIAL.md) — HCC passou a ser limitado por
discriminação (localiza 84,7%, discrimina 65,6%); T2WI/DWI eram a aposta para separar
HCC↔FNH.
**Gate pré-especificado** no cabeçalho do script, antes de qualquer número.

---

## 1. Resultado

Ablação de 4 braços, tudo idêntico a docs/138 exceto o conjunto de descritores:

| Braço | Descritores | Balanceada | HCC | FNH | Hemang. | Cisto |
|---|---:|---:|---:|---:|---:|---:|
| **A** T1 apenas (baseline) | 16 | **74,47%** | 65,6% | 69,6% | 72,2% | 90,6% |
| **B** T1 + T2WI | 18 | **74,70%** | 65,6% | 71,7% | 70,9% | 90,6% |
| **C** T1 + DWI | 18 | 74,00% | 65,6% | 69,6% | 72,2% | 88,7% |
| **D** T1 + T2WI + DWI | 20 | 74,00% | 63,7% | 69,6% | 75,9% | 86,8% |

| Critério | Exigido | Obtido | |
|---|---:|---:|:--|
| Balanceada | ≥ 80% | 74,70% | **FALHA** |
| Recall do HCC | ≥ 75% | 65,61% | **FALHA** |

**Ganho do melhor braço sobre o baseline: +0,23 ponto.** Ruído.

O efetivo com a localização de união praticamente não se move: 59,6% → 59,8%.

---

## 2. Não foi problema de cobertura

A preocupação registrada antes de rodar era desalinhamento respiratório entre a ROI (definida
na venosa) e a lesão em T2/DWI, que são aquisições separadas. **Não foi o caso:**

| Sequência | Cobertura mediana da lesão | Casos descartados (<20%) |
|---|---:|---:|
| T2WI | 100% | 2 de 335 |
| DWI | 100% | 2 de 335 |

A reamostragem por transformação física de identidade cobriu as lesões. O problema está em
outro lugar.

---

## 3. Por que falhou — leitura honesta

**O recall do HCC não se moveu um milímetro** (65,6% em A, B e C; piorou para 63,7% em D).
Era o alvo declarado do teste. Isso é informativo: os descritores adicionados não capturam o
que distingue HCC de FNH.

A explicação mais provável é que **meus descritores de T2/DWI são grosseiros demais para o
sinal clínico que eu invoquei**:

- Extraí apenas **razão de intensidade mediana** e **heterogeneidade (IQR relativo)** por
  sequência — 2 features cada.
- Mas o que separa FNH de HCC em T2 não é a intensidade média da lesão: é a **cicatriz
  central**, um padrão *espacial* (foco hiperintenso no centro de uma lesão isointensa). Uma
  mediana global sobre a ROI apaga exatamente isso.
- No DWI, o valor clínico está na **restrição à difusão quantificada (ADC)**, que exige mapa
  de ADC ou múltiplos valores de b. O que temos é uma imagem DWI de b único; sua intensidade
  bruta mistura difusão e ponderação T2 (efeito *T2 shine-through*), então a razão de
  intensidade não mede restrição.

**Portanto o que este resultado refuta é a formulação testada, não a premissa clínica.** Não
posso afirmar "T2WI e DWI não ajudam"; posso afirmar "razões de intensidade mediana em T2WI e
DWI não ajudam".

Registro isso explicitamente porque a distinção importa para a decisão seguinte — e porque a
tentação seria refazer com descritores mais ricos até passar, que é exatamente o padrão de
"tentar até dar certo" evitado em docs/128, 130, 132 e 136. O gate permanece reprovado.

---

## 4. Onde a discriminação está travada

Quatro tentativas de elevar o teto de 74,5%:

| Abordagem | Balanceada |
|---|---:|
| Descritores T1 por ROI (docs/138) | **74,47%** |
| + T2WI | 74,70% |
| + DWI | 74,00% |
| + ambos | 74,00% |

O teto não se move com descritores manuais. A confusão HCC↔FNH persiste intacta.

---

## 5. Estado consolidado da meta de subtipo

| Métrica | Valor | Fonte |
|---|---:|---|
| Localização (união venosa+arterial) | 80,0% | docs/141 |
| Discriminação (teto, descritores manuais) | 74,5% | docs/138, este doc |
| **Acertividade efetiva** | **~59,6%** | produto |
| Abordagem atual (fígado inteiro) | 52,18% | docs/129 |
| **Meta** | **75%** | — |

Faltam ~15 pontos, e **as duas metades resistiram à última rodada de melhorias**: a
localização colheu o ganho da arterial (69% → 80%) e a discriminação não se move com
descritores manuais.

---

## 6. O caminho não testado que eu recomendaria

Toda a linha de descritores manuais está esgotada. Mas há uma opção **nunca testada** que
ataca precisamente o diagnóstico de docs/137:

> docs/137 provou que o embedding MedSigLIP de **fígado inteiro** dilui a lesão.
> docs/138 provou que a lesão localizada carrega o sinal.
> **Nunca testamos o embedding MedSigLIP da lesão RECORTADA.**

Ou seja: em vez de descritores manuais sobre a ROI, recortar a lesão (com margem) e embutir
esse recorte com o MedSigLIP congelado. Isso combina as duas descobertas — representação
aprendida, que é rica, aplicada na escala espacial certa, que era o gargalo. Um padrão
espacial como a cicatriz central da FNH é exatamente o tipo de coisa que um embedding
capta e uma mediana não.

Custo: baixo. As máscaras de ROI já existem, o MedSigLIP está congelado, o pipeline de
embedding e o OOF já estão escritos. É o mesmo tipo de teste barato dos anteriores.

`clinical_use_allowed` permanece `false`.
