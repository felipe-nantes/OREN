# Passo 2 — Medição honesta: 61,46% de ponta a ponta

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo2_medicao_honesta_v1/`
**Passo 2** de [docs/144](144_PLANO_FECHAMENTO_META_SUBTIPO.md)

---

## 1. O número

**61,46%** de acurácia balanceada, medido de ponta a ponta sobre ROI **predita**.

| Margem do recorte | Balanceada |
|---|---:|
| 0,35 | — |
| **0,6** | **61,46%** |
| 1,0 | 60,55% |

| Subtipo | Medido | IC95 |
|---|---:|---|
| `hepatic_cyst` | 67,9% | [55 – 79] |
| `hcc` | 65,0% | [57 – 72] |
| `hemangioma` | 60,8% | [50 – 71] |
| `fnh` | 52,2% | [38 – 66] |

**Este é o número defensável.** As estimativas anteriores — 63,6% (docs/143) e 66,4%
(docs/145) — eram otimistas e **não devem ser reportadas**.

---

## 2. Por que o modelo multiplicativo errou por 5 pontos

A estimativa era `83,6% localização × 79,5% discriminação = 66,4%`. O medido é 61,46%.

O modelo estava **conceitualmente errado**, não apenas impreciso. Ele tratava localização
como binária — achou ou não achou — e assumia que "achou" implicava discriminação no nível do
teto. Mas há uma perda intermediária que a fórmula não representa:

> Uma ROI que **toca** a lesão com IoU de 0,395 produz um recorte que mistura lesão e
> parênquima. O classificador recebe uma imagem degradada e erra — **sem que isso conte como
> falha de localização**.

Essa perda é grande: **18,03 pontos** entre o teto com ROI de ground truth (79,49%) e o
medido com ROI predita (61,46%).

### A queda por classe revela o mecanismo

| Subtipo | ROI ground truth | ROI predita | Queda |
|---|---:|---:|---:|
| `hepatic_cyst` | 92,5% | 67,9% | **−24,6** |
| `hcc` | 82,2% | 65,0% | −17,2 |
| `hemangioma` | 75,9% | 60,8% | −15,1 |
| `fnh` | 67,4% | 52,2% | −15,2 |

O **cisto cai mais**, e é coerente: é a classe cuja identidade depende de conteúdo
homogêneo e sem realce. Um recorte que traz metade de parênquima junto destrói exatamente o
sinal que a define. Quando a ROI é boa, o cisto é a classe mais fácil; quando é ruim, é a que
mais sofre.

---

## 3. A margem maior não compensou — e o motivo importa

docs/144 §2.1 previa que uma margem maior recuperaria a sub-segmentação (predições pegam 57%
do volume real). **Não funcionou:** margem 1,0 ficou 0,9 ponto abaixo de 0,6.

A razão é um defeito do meu desenho: a margem é **proporcional à bbox predita**. Se a bbox
está pequena demais, mesmo dobrá-la continua pequeno em termos absolutos — e a partir de
certo ponto o alargamento só traz parênquima, diluindo a lesão. Proporção não corrige um
viés de escala.

**Correção indicada:** recorte de **tamanho físico fixo** (em mm) centrado no centroide
predito, desacoplando o tamanho do recorte da extensão (sub-estimada) da predição.

---

## 4. Estado real da meta

| | Valor |
|---|---:|
| **Medido ponta a ponta** | **61,46%** |
| Abordagem atual (fígado inteiro) | 52,18% |
| Teto com ROI perfeita | 79,49% |
| **Meta** | **75%** |

Ganho real sobre a abordagem atual: **+9,3 pontos**. Faltam **13,5 pontos** para a meta.

A aritmética de docs/144 §4 previa que os Passos 1–3 levariam a ~69% e não à meta. Com o
valor real em 61,46%, **essa conclusão fica mais forte, não mais fraca**.

---

## 5. O que a medição muda na prioridade

A decomposição útil deixou de ser "localização × discriminação" e passou a ser:

| Perda | Magnitude |
|---|---:|
| Lesão não localizada (16,4% dos casos) | — |
| **Qualidade da ROI (IoU 0,395)** | **18,03 pts** |

**A qualidade da ROI é agora o maior lever isolado**, e não estava no plano original — o plano
media acerto binário de localização, não fidelidade do contorno. Melhorar a taxa de acerto de
83,6% para 90% renderia bem menos do que melhorar o IoU de 0,395 para 0,6.

---

## 6. Nota de execução

O monitor inicial reportou "iniciando" por 20 minutos com o processo já a 49% do trabalho: o
`grep` no pipeline do comando bufferiza a saída, e o log só é escrito quando o buffer enche.
Corrigido passando a contar artefatos em disco. **Para execuções longas, monitorar por
artefato é mais confiável que por log filtrado.**

`clinical_use_allowed` permanece `false`.
