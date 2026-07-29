# Teto da Etapa 2 — Resultado: com a lesão localizada, o subtipo é separável

**Data:** 29 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/roi_ceiling_v1/` (e `..._nosize_v1/`)
**Ground truth de localização:** `wanglab/LLD-MMRI-MedSAM2` `labels/*_C+V` (máscara binária,
localização pura, sem rótulo de classe), usada **somente na avaliação** — autorizado pelo
usuário, precedente de docs/93.
**Veredito:** **TETO PASSA** — a Etapa 2 é viável; o gargalo vira localização.

---

## 1. Conclusão

Depois de quatro representações de fígado inteiro travadas em ~47–55% (docs/137), este teste
responde a pergunta decisiva: **o problema é falta de informação ou falta de localização?**

A resposta é inequívoca: **localização**. Com a lesão perfeitamente localizada, 16
descritores físicos de realce e uma regressão logística atingem **74,47% de acurácia
balanceada** — contra 52,18% da supervisão global e praticamente no alvo de 75%.

| verdade \ predito | fnh | hcc | heman | cisto | recall | precisão | prevalência |
|---|---:|---:|---:|---:|---:|---:|---:|
| **fnh** | 32 | 9 | 5 | 0 | 69,6% | 50,8% | 13,7% |
| **hcc** | 28 | 103 | 24 | 2 | 65,6% | 82,4% | 46,9% |
| **hemangioma** | 3 | 13 | 57 | 6 | 72,2% | 62,6% | 23,6% |
| **hepatic_cyst** | 0 | 0 | 5 | 48 | **90,6%** | 85,7% | 15,8% |

**n = 335 · top-1 = 71,64% · balanceada = 74,47%**

O cisto — que desabou para 17–22% nos painéis de fígado inteiro (docs/137) — sobe a **90,6%
de recall com 85,7% de precisão**. Precisão muito acima da prevalência (15,8%): é detecção
genuína, o oposto do colapso degenerado que produziu o falso "90%" da Frente 1 (docs/131).

---

## 2. Robustez: não é artefato de tamanho

Tamanho da lesão pode ser confundidor (subtipos têm distribuições de tamanho distintas neste
dataset). Removendo a feature `log_size`:

| Conjunto de descritores | Balanceada | Recall cisto |
|---|---:|---:|
| Realce + tamanho | 74,47% | 90,6% |
| **Realce apenas (sem tamanho)** | **64,97%** | 83,0% |
| Supervisão global (fígado inteiro) | 52,18% | 33,3% |

O realce físico **sozinho** entrega 64,97% — passa o gate (≥62%) e supera a supervisão
global por 13 pontos. O tamanho contribui ~9,5 pontos, mas não é o motor. A separação vem do
comportamento de realce, exatamente o mecanismo clínico esperado.

---

## 3. O que este resultado fecha e o que abre

**Fecha:** a longa investigação sobre representação. A informação de subtipo **está** nos
dados; o que a Etapa 1 provou é que o embedding de fígado inteiro a dilui. Escala espacial
era o gargalo, como docs/137 concluiu.

**Abre:** a Etapa 2 tem meia-parte resolvida (discriminação, 74%) e meia-parte por resolver
(localização). O desempenho de produção será aproximadamente

> recall_do_localizador × acerto_de_subtipo_dado_localizado

O `acerto_dado_localizado` está em 74%. O `recall_do_localizador` é o próximo gargalo e o
risco real: o `liver_lesions_mr` travou em 56,76% no OpenSwiss, sem `C-pre` (docs/93). Se o
localizador achar 70% das lesões, o efetivo cai para ~52%. **Localização é agora o trabalho.**

---

## 4. Onde os descritores ainda erram (rota para passar de 75%)

A maior confusão é **HCC ↔ FNH** (28 HCC preditos como FNH; HCC recall 65,6%, o mais fraco).
Faz sentido clínico: ambos têm realce arterial intenso. As sequências que separam os dois —
`T2WI` (FNH costuma ter cicatriz central em T2) e a fase hepatobiliar — não estão nos
descritores atuais. Isso indica o caminho para elevar o teto de 74% para >75%: adicionar
descritores de `T2WI`/`DWI` por ROI, que já estão em disco.

---

## 5. Disciplina mantida

- A máscara de localização entrou **só na avaliação**; os volumes de realce não a viram para
  gerar features de aparência, e o rótulo de subtipo veio do caminho protegido, não do
  `LLD_MMRI_Annotation.json`.
- Descritores são **razões contra parênquima adjacente** (referência interna), pela
  exigência de invariância de domínio de docs/131. A sonda de domínio sobre eles ainda será
  medida antes de qualquer uso em produção.
- É um teto sobre coorte única; não é estimativa de generalização. `clinical_use_allowed`
  segue `false`.
