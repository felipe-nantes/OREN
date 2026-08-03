# O número honesto de subtipo do caminho que está no ar

**Data:** 3 de agosto de 2026
**Script:** `tools/measure_deployed_subtype_accuracy.py`
**Artefato:** `experiments/subtipo_caminho_producao_v1/results.json` *(não versionado — regerável pelo script)*

---

## 1. Por que este documento existe

Havia três números de subtipo circulando, e **nenhum deles media o caminho que o
webapp usa**:

| Número | O que mede |
|---|---|
| 61,46% ([docs/146](146_PASSO2_MEDICAO_HONESTA.md)) | caminho de **recorte** por ROI predita |
| 64,81% ([docs/156](156_SUBTIPO_HONESTO_FUSAO.md)) | **cascata** de representações |
| 96,43% ([docs/171](171_RESULTADO_BENCHMARK_FRONTEND_PATOLOGIA_VARIACAO.md)) | bundle de produção em 25 casos LLD **que estão no treino dele** |

O webapp usa o bundle de produção sobre painéis de **fígado inteiro**, com
agregação `top2_mean`. Não é nenhum dos três.

Além disso, o número estava sendo citado em [docs/174](174_CONSOLIDADO_ESTADO_ATUAL.md)
sem fonte reproduzível: o artefato não é versionado e o script vivia fora do
repositório. **Um número que ninguém consegue refazer não é defensável**, por mais
correto que esteja. Este documento e o script fecham isso.

---

## 2. Método

Mesmo estimador do bundle de produção — multiclasse de 6 classes, agregação de
painel, `C` e agregação escolhidos **nos folds internos** — avaliado em
**nested-OOF**: cada caso é julgado por um modelo que não o viu.

Denominador honesto: os **335 alvos**, com *sem predição* contando como erro. É a
mesma régua de docs/146 e docs/156, então os três são comparáveis.

A guarda de [docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md) continua ativa: só
nomeia o subtipo quando a massa nas quatro classes nomeadas passa de 50%.

---

## 3. Resultado

| | |
|---|---:|
| **Balanceada, 4 classes** | **52,19%** |
| Top-1 | 58,81% |
| Subtipo determinado | 321 / 335 (95,8%) |

| Classe | Acerto |
|---|---:|
| FNH | 24 / 46 — 52,2% |
| HCC | 117 / 157 — 74,5% |
| Hemangioma | 38 / 79 — 48,1% |
| **Cisto hepático** | **18 / 53 — 34,0%** |

Confusão (linha = verdade):

```text
fnh          -> fnh: 24   hcc:  5   hema: 12   hepa:  4   sem: 1
hcc          -> fnh:  4   hcc:117   hema: 15   hepa: 16   sem: 5
hemangioma   -> fnh: 10   hcc: 11   hema: 38   hepa: 14   sem: 6
hepatic_cyst -> fnh:  4   hcc: 15   hema: 14   hepa: 18   sem: 2
```

---

## 4. O que isso revelou

**O caminho no ar é o pior dos três medidos honestamente.** Pior que o recorte
(61,46%) e pior que a cascata (64,81%).

Comparado à cascata, classe a classe:

| Classe | No ar | Cascata | Δ |
|---|---:|---:|---:|
| FNH | 52,2% | 67,4% | **+15,2** |
| HCC | 74,5% | 74,5% | 0 |
| Hemangioma | 48,1% | 57,0% | +8,9 |
| **Cisto** | **34,0%** | **60,4%** | **+26,4** |
| **Balanceada** | **52,19%** | **64,81%** | **+12,6** |

Isto **corrige uma conclusão de docs/156**, onde a cascata foi recusada por
"regressão no cisto". Aquela comparação era contra o caminho de **recorte** (cisto
71,7%), não contra o que está deployado. Contra o deployado, a cascata **melhora o
cisto em 26 pontos** e não perde em nenhuma classe.

---

## 5. Por que a cascata ainda não subiu

Verificado ao tentar: **não existe modelo de fusão treinado.** A medição de
docs/156 foi nested-OOF com modelos por fold — não há `.joblib` de produção, e o
`results.json` de lá não guarda um. Subir a cascata exigiria treinar um modelo
novo, assiná-lo como bundle de produção e reordenar o pipeline para rodar o
localizador antes do subtipo.

E há um bloqueio que nenhum esforço remove no curto prazo: **não há como validar
esse modelo novo pelo frontend hoje.** Todo caso disponível para teste é LLD, e o
LLD inteiro está no treino. A única evidência seria o número de docs/156 — que
apoia o *método*, não este *build*.

É a próxima entrega, com custo conhecido e ganho medido.

---

`research_only: true` · `clinical_use_allowed: false`
