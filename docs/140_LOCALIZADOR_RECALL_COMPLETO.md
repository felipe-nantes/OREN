# Recall do localizador — conjunto completo (335 casos)

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/localizer_recall_full_v1/`
**Localizador:** `liver_lesions_mr` (TotalSegmentator Dataset589 fold0), fase venosa,
crop pela máscara automática de fígado.
**Ground truth de localização:** `labels/*_C+V` (máscara binária), usado só na avaliação.

---

## 1. Resultado

**Recall de localização: 69,0% (231/335)** · IC95 [63,8 – 73,7]

| Subtipo | Recall | IC95 | n |
|---|---:|---|---:|
| `hepatic_cyst` | **90,6%** | [80 – 96] | 53 |
| `hcc` | **76,4%** | [69 – 82] | 157 |
| `hemangioma` | 53,2% | [42 – 64] | 79 |
| `fnh` | **45,7%** | [32 – 60] | 46 |

Execução: 58,7 min de GPU efetiva. Estados: 311 predições geradas, 16 de cache,
**8 falhas técnicas (2,4%)** — segfault esporádico do nnU-Net, isolado pelo timeout de 180 s
por caso e contado como falha de localização (se não entregou, não localizou).

O piloto de n=16 (docs/139) indicava 75,0%; com 335 casos o valor assenta em **69,0%**, e o
IC estreitou de 39 para 10 pontos. O piloto era otimista, como a ressalva de amostra
antecipava.

---

## 2. A projeção da Etapa 2

> subtipo efetivo ≈ recall do localizador × acerto dado localizado

| Componente | Valor | Fonte |
|---|---:|---|
| Recall do localizador | 69,0% | este doc |
| Teto de discriminação | 74,5% | docs/138 |
| **Subtipo efetivo projetado** | **51,4%** | produto |

**51,4% é praticamente idêntico aos 52,18% da abordagem atual de fígado inteiro**
(docs/129). Ou seja: construir o pipeline Etapa 2 com o localizador **como ele está hoje**
não entregaria ganho líquido.

Este é o achado central deste documento, e ele muda a prioridade.

---

## 3. Onde está o gargalo, com precisão

O produto 69,0% × 74,5% esconde que a perda é **muito desigual por classe**. Combinando com
os recalls de discriminação de docs/138:

| Subtipo | Localização | Discriminação | Efetivo aprox. |
|---|---:|---:|---:|
| `hepatic_cyst` | 90,6% | 90,6% | **~82%** |
| `hcc` | 76,4% | 65,6% | ~50% |
| `hemangioma` | 53,2% | 72,2% | ~38% |
| `fnh` | 45,7% | 69,6% | ~32% |

Duas leituras:

**O cisto está resolvido.** ~82% efetivo, acima da meta de 75%, com as duas metades fortes.
A classe que era o pior caso de toda a investigação (33% na supervisão global, 17-22% com
realce global) é hoje a melhor.

**FNH e hemangioma são o problema, e é de localização, não de discriminação.** Ambas
discriminam bem (70% e 72%) mas localizam mal (46% e 53%). São lesões cuja aparência se
confunde com o parênquima na fase venosa — exatamente onde um localizador treinado
predominantemente em lesões malignas (Dataset589) tende a falhar.

---

## 4. Consequência para a meta de 75%

A meta continua alcançável, mas **o caminho passa obrigatoriamente por melhorar a
localização de FNH e hemangioma** — não por mais trabalho em descritores, que já entregam
74,5% quando a lesão é dada.

Aritmética do alvo: para efetivo de 75% com o teto atual de 74,5% de discriminação, o recall
de localização precisaria ser ≈ **100%**, o que é irreal. Portanto o alvo exige avançar nas
**duas** metades simultaneamente. Por exemplo, recall 85% × discriminação 88% ≈ 75%.

Direções, em ordem de custo/benefício:

1. **Localizar em mais de uma fase.** Hoje só a venosa. FNH e hemangioma são conspícuos na
   **arterial** (realce intenso) — a fase onde justamente não olhamos. A união
   venosa+arterial foi testada no OpenSwiss e descartada por ruído (docs/93), mas naquele
   contexto o alvo era HCC; para FNH/hemangioma a arterial é o sinal principal, então a
   conclusão não transfere.
2. **Propostas determinísticas de realce** como candidatos, em vez de depender só do
   nnU-Net — o caminho que docs/93 apontou e nunca foi executado, agora viável com `C-pre`.
3. **Descritores de `T2WI`/`DWI` por ROI** para elevar a discriminação de 74,5% (endereça a
   confusão HCC↔FNH identificada em docs/138).

---

## 5. Nota operacional

A rodada sofreu **cinco interrupções** de máquina. Nenhuma custou trabalho, graças a três
mecanismos implementados no caminho: checkpoint incremental por caso, timeout de 180 s em
subprocess isolado, e **auto-reparo da config do TotalSegmentator** — que corrompeu pela
quarta vez (bytes NUL) e chegou a produzir 129 falsos negativos em cascata antes de ser
detectada. O guard agora valida e repara a config antes de cada caso.

Recomenda-se levar esse guard para o código de produção; o chip aberto anteriormente
(preflight da config no webapp) cobre o mesmo risco.

`clinical_use_allowed` permanece `false`. Coorte única, sem estimativa de generalização.
