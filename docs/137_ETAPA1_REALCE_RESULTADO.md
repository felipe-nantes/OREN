# Etapa 1 do subtipo — Resultado: realce global refutado, gargalo é escala espacial

**Data:** 29 de julho de 2026
**Pré-especificação:** [docs/136](136_ETAPA1_REALCE_PRE_ESPECIFICACAO.md), commitada antes de
qualquer número
**Artefatos:** `casos/qualification/hybrid_v1/etapa1_realce_v1/` e `.../etapa1_realce_edgeonly_v1/`
**Veredito:** **REPROVADO** nos dois critérios, em ambas as variantes

---

## 1. Conclusão

Substituir as três fases pós-contraste por realce relativo **piorou** a acurácia de subtipo,
em vez de melhorar. O gate exigia balanceada ≥ 62% e recall do cisto ≥ 55%; o realce
entregou 47–48% e 18–22%. A hipótese de que o gargalo era o **conteúdo espectral** dos
canais está refutada.

| Representação (fígado inteiro) | Balanceada | Recall cisto |
|---|---:|---:|
| Fases pós (Etapa C, atual) | 52,18% | 33,33% |
| Realce relativo v2 (com tissue_weight) | 48,34% | 17,65% |
| Realce relativo edge-only | 47,26% | 21,57% |

---

## 2. Erro de design meu, honestamente reportado

A v2 incluía um `tissue_weight` que atenua o realce onde o sinal venoso é baixo. **Cisto é
conteúdo fluido de sinal T1 baixo** — então esse peso apagou justamente a classe que a
hipótese queria destacar, transformando o cisto num buraco preto.

A variante diagnóstica `edge-only` removeu esse peso. Ela devolveu apenas ~4 pontos ao cisto
(17,65 → 21,57%). Ou seja: meu peso agravou, mas **não foi a causa principal**. A queda real
do cisto — de 33,33% (fases pós) para 21,57% (realce sem meu peso) — vem do próprio realce
puro, que descarta a **morfologia**: forma redonda, homogeneidade, sinal fluido. "Não
realça" sozinho não distingue cisto de qualquer região estável.

O erro do peso está corrigido no builder (flag `--no-tissue-weight`); a conclusão não
depende dele.

---

## 3. A evidência macro é conclusiva

Quatro representações independentes de **fígado inteiro**, todas travadas na mesma faixa:

| Representação | Desempenho |
|---|---:|
| Fases pós | 52,18% balanceada |
| Realce v2 | 48,34% |
| Realce edge-only | 47,26% |
| Radiomics global (binário, docs/131) | 55,4% |

Mudar o conteúdo dos canais **não move o teto**. A causa não é espectral, é **espacial**: a
lesão é pequena, o painel é o fígado inteiro, e o embedding global a dilui. É o mesmo
mecanismo que travou o radiomics global no endpoint binário (docs/131) — a lesão não move a
estatística de 1,5 L de parênquima.

docs/136 previu exatamente este desfecho na linha "cisto não sobe → a Etapa 2 (ROI) vira
pré-requisito, não sucessora".

---

## 4. Consequência

- **Encerrar a exploração de painéis de fígado inteiro para subtipo.** Quatro medições
  concordantes bastam; continuar seria "tentar até passar".
- **A Etapa 2 (localização de lesão + descritores por ROI) é o único caminho restante** para
  o subtipo, e por convergência de evidência, não por preferência.
- Nenhuma iteração sobre o gate: ele permanece 62% / 55% e permanece reprovado. Sem
  produção alterada, `clinical_use_allowed` segue `false`.

---

## 5. Bloqueio descoberto para a Etapa 2

Medir a viabilidade da Etapa 2 exige ground truth de **localização** de lesão no LLD-MMRI
(bounding boxes), que **não está em disco**: o download excluiu deliberadamente todo termo
de lesão/bbox/anotação (`FORBIDDEN_PATH_TERMS`). Sem ele não é possível medir nem o recall
de localização nem o teto de discriminação com ROI perfeita.

Isto é uma decisão de rumo para o usuário (§ próximo passo), porque baixar anotações de
localização — ainda que só para a etapa de avaliação, como docs/93 fez com máscaras venosas
— toca na disciplina label-blind e precisa ser autorizado explicitamente.
