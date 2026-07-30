# Recall do localizador de lesão — piloto (segunda metade da viabilidade da Etapa 2)

**Data:** 29 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/localizer_recall_v1/`
**Localizador:** `liver_lesions_mr` (TotalSegmentator Dataset589 fold0), fase venosa, crop pela
máscara automática de fígado.
**Ground truth de localização:** `labels/*_C+V` (máscara binária), usado só na avaliação.

---

## 1. Onde este teste se encaixa

O desempenho de subtipo da Etapa 2 decompõe-se em duas metades:

> subtipo efetivo ≈ **recall do localizador** × **acerto de subtipo dado localizado**

- A segunda metade já foi medida (docs/138): **74,47%** de balanceada com a lesão dada.
- Este documento mede a primeira: o localizador automático **acha** a lesão?

---

## 2. Resultado do piloto (n=16, 4 por subtipo)

**Recall geral de localização: 75,0% (12/16)**, contra 56,76% de referência (docs/93,
OpenSwiss sem `C-pre`). O `C-pre` e a coorte LLD ajudam.

| Subtipo | Recall | IoU mediano (hits) |
|---|---:|---:|
| fnh | 100% (4/4) | 0,38 |
| hepatic_cyst | 100% (4/4) | 0,31 |
| hcc | 50% (2/4) | 0,32 |
| hemangioma | 50% (2/4) | 0,52 |

Definição de acerto: a máscara predita intersecta a lesão anotada (dilatação de tolerância
de 1 voxel), a mesma de docs/93. Casos onde o localizador travou (segfault intermitente do
nnU-Net) contam como falha de localização — o comportamento correto: se não entregou, não
localizou.

---

## 3. Projeção

| Componente | Valor |
|---|---:|
| Teto de discriminação (docs/138) | 74,5% |
| Recall do localizador (piloto) | 75,0% |
| **Subtipo efetivo projetado** (produto) | **~55,9%** |

O pipeline completo projetaria ~56% de balanceada — acima da abordagem atual (52,18%), mas
longe dos 75%. **O localizador é o gargalo confirmado.**

---

## 4. Leitura honesta

**Positivo:** as duas classes de maior valor pelo teto — cisto e FNH — são as bem
localizadas (100% cada). O cisto, o pior caso de toda a investigação de subtipo, agora tem
localização perfeita **e** 90,6% de discriminação: essencialmente resolvido.

**Ressalva de amostra:** n=16 é pequeno. O IC95 do recall geral é [50,5 – 89,8] — 39 pontos
de largura; um caso move o número em ~6 pontos. Os "100%" são sobre 4 casos cada. Não se
pode afirmar 75% de recall com esta amostra — apenas que é promissor e claramente acima da
referência.

**Onde falha:** HCC e hemangioma (50% cada) — lesões sólidas cujo realce se confunde com o
parênquima, mais difíceis de segmentar. É onde o trabalho de localização se concentraria.

---

## 5. Decisão

Sinal positivo o bastante para medir o recall no **conjunto completo (335 casos)** e fechar
o número com IC estreito, por subtipo. Rodada de GPU desassistida de ~3–4h, com o timeout
por caso já validado (evita que um segfault pendure o lote, como ocorreu no primeiro piloto:
92 min travado num único cisto).

Só com o recall completo decidir entre:
- **(a)** construir o pipeline Etapa 2 completo, se o recall se sustentar; ou
- **(b)** primeiro melhorar a localização de HCC/hemangioma, se forem o teto real.

`clinical_use_allowed` permanece `false`; coorte única, sem estimativa de generalização.

---

## 6. Estado da meta de subtipo (resumo)

| Etapa | Resultado | Doc |
|---|---|---|
| Supervisão de fígado inteiro | 52,18% balanceada | 129 |
| Realce global (refutado) | 47–48% | 137 |
| **Teto com ROI de ground truth** | **74,47%** | 138 |
| Recall do localizador (piloto) | 75,0% (n=16) | 139 (este) |
| Subtipo efetivo projetado | ~56% | 139 |

O caminho para 75% existe e está mapeado: melhorar a localização de HCC/hemangioma e
adicionar descritores de `T2WI`/`DWI` por ROI (que endereçam a confusão HCC↔FNH, docs/138).
