# Embedding da lesão recortada — discriminação sobe de 74,5% para 79,5%

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/roi_ceiling_crop_v1/`
**Antecedente:** [docs/142](142_T2WI_DWI_DISCRIMINACAO_RESULTADO.md) — descritores manuais
esgotados; quatro tentativas, teto imóvel em ~74,5%.
**Gate pré-especificado** no cabeçalho do script, antes de qualquer número.

---

## 1. Resultado

| Braço | Representação | dim | Balanceada | HCC | FNH | Hemang. | Cisto |
|---|---|---:|---:|---:|---:|---:|---:|
| **A** | descritores manuais (baseline) | 16 | 74,47% | 65,6% | 69,6% | 72,2% | 90,6% |
| **B** | **embedding do recorte** | 1152 | **79,49%** | **82,2%** | 67,4% | 75,9% | 92,5% |
| **C** | recorte + descritores | 1168 | 78,63% | 80,9% | 65,2% | 75,9% | 92,5% |

| Critério | Exigido | Obtido | |
|---|---:|---:|:--|
| Balanceada | ≥ 80% | 79,49% | **FALHA por 0,51 pt** |
| Recall do HCC | ≥ 75% | **82,17%** | **PASSA** |

**Ganho sobre descritores manuais: +5,02 pontos** — o maior salto de discriminação de toda a
investigação de subtipo.

O gate primário está **reprovado**. Faltou meio ponto, e o critério foi fixado antes de
rodar; não é reajustado nem arredondado para "praticamente passou".

---

## 2. O que confirmou a hipótese

A cadeia de diagnóstico que levou a este teste:

| Descoberta | Doc |
|---|---|
| Embedding MedSigLIP de **fígado inteiro** dilui a lesão (47–52%) | 137 |
| A lesão **localizada** carrega o sinal (74,5% com descritores manuais) | 138 |
| Descritores manuais **esgotados** (T2WI/DWI não movem o teto) | 142 |
| **Embedding da lesão recortada** = representação aprendida na escala certa | este |

O alvo declarado era a confusão **HCC↔FNH**, que resistiu a quatro rodadas de descritores
manuais. Cedeu: **HCC de 65,6% para 82,2%, +16,6 pontos.** Um padrão espacial — realce
heterogêneo, cápsula, cicatriz central — é o que um embedding capta e uma mediana de
intensidade sobre a ROI apaga.

---

## 3. Duas previsões minhas que estavam erradas

**a) Previ que combinar seria melhor.** Argumentei que descritores manuais capturam dinâmica
temporal e o embedding captura padrão espacial, logo seriam complementares. **O braço C
ficou 0,86 ponto ABAIXO de B sozinho.** Somar 16 features a 1152 dimensões só adicionou
ruído; o embedding já captura a dinâmica por conta própria — os três canais RGB são as três
fases.

**b) Previ ganho generalizado.** A **FNH piorou** (69,6% → 67,4%) e é a única classe que os
descritores manuais serviam melhor. Segue sendo a mais fraca, com n=46.

---

## 4. Estado consolidado da meta

| Métrica | Antes | Agora | Fonte |
|---|---:|---:|---|
| Localização (união venosa+arterial) | 80,0% | 80,0% | docs/141 |
| Discriminação (teto) | 74,5% | **79,5%** | este doc |
| **Efetivo estimado** | 59,6% | **~63,6%** | produto |
| Abordagem atual (fígado inteiro) | 52,18% | — | docs/129 |
| **Meta** | 75% | — | — |

Progresso acumulado: **52,18% → ~63,6%**, +11,4 pontos, em quatro passos medidos.

### Por classe (localização × discriminação)

| Subtipo | Localiza | Discrimina | Efetivo aprox. |
|---|---:|---:|---:|
| `hepatic_cyst` | 92,5% | 92,5% | **~86%** |
| `hcc` | 84,7% | 82,2% | **~70%** |
| `hemangioma` | 72,2% | 75,9% | ~55% |
| `fnh` | 63,0% | 67,4% | **~42%** |

O cisto está muito acima da meta. O HCC — 47% da amostra — chegou perto. **A FNH é agora,
isoladamente, o que segura o número**: fraca nas duas metades e com a menor amostra.

---

## 5. Limitação do "efetivo" que precisa ser fechada

O efetivo de 63,6% é **estimativa, não medição**. Ele multiplica a localização pela
discriminação medida sobre a **ROI de ground truth**, assumindo que a discriminação sobre a
**ROI predita** seria igual. É otimista, por dois motivos:

1. A ROI predita tem IoU de apenas ~0,3–0,5 com a real — inclui parênquima e perde parte da
   lesão, o que degrada tanto o recorte quanto os descritores.
2. Essa degradação nunca foi medida.

**Pendência prioritária:** rodar a discriminação sobre as 335 ROIs preditas pelo localizador
(já em disco) e reportar o número de ponta a ponta, sem suposição. É barato e converte
"~63,6% estimado" em desempenho medido — que é o que deve ser reportado à equipe.

---

## 6. Caminho restante para 75%

Com discriminação em 79,5%, a localização precisaria ir a ~94%; com localização em 80%, a
discriminação precisaria ir a ~94%. Nenhuma isolada resolve. Mas o gargalo agora está
nomeado com precisão: **a FNH**, que sozinha puxa a balanceada para baixo nas duas metades.

Direções, na ordem que a evidência sugere:
1. **Fechar a medição honesta** sobre ROIs preditas (§5) — antes de qualquer nova otimização.
2. **FNH**: n=46 é a menor classe; parte do problema pode ser amostra, não método. Uma
   segunda coorte (Etapa 4 de docs/135) endereça isso e o confundimento de domínio ao mesmo
   tempo.
3. **Localização da FNH** (63,0%, a pior): explorar propostas determinísticas de realce,
   o caminho de docs/93 nunca executado.

`clinical_use_allowed` permanece `false`. Coorte única; não é estimativa de generalização.
