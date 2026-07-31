# Passo 3c — Seleção de componente: nenhuma heurística supera "o maior"

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo3c_selecao_v1/`
**Antecedente:** [docs/147](147_PASSO3A_RECORTE_FISICO.md) — a perda de ~16 pontos vem do
centro errado; a única direção barata restante era escolher melhor o componente.
**Veredito:** nenhuma heurística supera o critério atual. **Ganho disponível: +0,0 pontos.**

---

## 1. Resultado

Diagnóstico em CPU sobre os 335 casos: enumerar todos os componentes conexos da união das
predições e medir, para cada critério, com que frequência o componente selecionado **toca a
lesão anotada**.

| Critério | Acerto de centro | IC95 | fnh | hcc | hema | cisto |
|---|---:|---|---:|---:|---:|---:|
| **Oráculo (teto)** | **82,4%** | [77,9 – 86,1] | 74% | 85% | 73% | 94% |
| **Maior — atual** | **67,8%** | [62,6 – 72,5] | 50% | 78% | 52% | 77% |
| volume × compacidade | 66,9% | [61,7 – 71,7] | 52% | 77% | 51% | 74% |
| realce arterial | 44,8% | [39,5 – 50,1] | 57% | 55% | 24% | 36% |
| heterogeneidade | 43,0% | [37,8 – 48,3] | 22% | 38% | 41% | 79% |
| centralidade no fígado | 40,0% | [34,9 – 45,3] | 26% | 49% | 25% | 47% |
| compacidade | 28,1% | [23,5 – 33,1] | 24% | 29% | 18% | 43% |

---

## 2. Por que minhas hipóteses falharam

Propus quatro critérios com justificativa fisiológica ou geométrica. **Todos ficaram abaixo
do volume simples**, e o pior foi justamente o que eu considerava mais promissor.

**Compacidade (28,1%, o pior).** Argumentei que lesões são arredondadas e falsos positivos —
vasos, artefatos de borda — são alongados. O raciocínio ignora um detalhe decisivo:
compacidade favorece o **minúsculo**. Um fragmento de 25 voxels é quase perfeitamente
compacto por construção. O critério seleciona ruído, não lesão.

**Centralidade (40,0%).** Lesões podem estar em qualquer segmento hepático, inclusive
periféricos. Não há razão para o centro geométrico do fígado ser preferencial.

**Realce (44,8%) e heterogeneidade (43,0%).** Ambos medem propriedades reais de lesão, mas
sobre componentes que já são candidatos ruidosos — e vasos realçam intensamente na fase
arterial, competindo diretamente com lesões hipervasculares.

**Volume, apesar de grosseiro, correlaciona melhor com "ser uma lesão de verdade"** do que
qualquer descritor de forma que testei. O nnU-Net produz fragmentos espúrios pequenos e o
componente verdadeiro tende a ser o maior — não sempre, mas com mais frequência que as
alternativas.

---

## 3. O que o oráculo revela

**Em 82,4% dos casos o componente certo existe na predição.** O critério atual o encontra em
67,8%. Há **14,6 pontos de centro** disponíveis — o ganho é real, mas nenhuma regra fixa o
captura.

Traduzindo para a métrica final: recuperar esses 14,6 pontos de acerto de centro renderia
aproximadamente **+8 a 10 pontos de acurácia balanceada**, levando o pipeline de 61,46% para
~70%.

**Isso exige seleção aprendida**, não heurística: um classificador leve que decida "este
componente é lesão ou artefato?" a partir de features do componente e seu contexto. É
factível — as features já estão calculadas neste experimento e o ground truth de localização
está disponível — mas é um projeto de porte médio, não um teste de uma hora.

---

## 4. Fecho do inventário de opções baratas

Este experimento encerra a série de testes rápidos sobre os artefatos existentes. Resumo do
que foi testado e descartado desde docs/146:

| Tentativa | Resultado | Doc |
|---|---|---|
| Recorte físico fixo | refutado; pior que proporcional | 147 |
| Crescimento de região (3b) | **cancelado** sem custo, pelo controle de 147 | 147 |
| Seleção heurística de componente | nenhuma supera "o maior" | este |

O que resta tem custo real:

| Direção | Ganho potencial | Custo |
|---|---|---|
| **Seleção aprendida de componente** | ~+8–10 pts (61,5% → ~70%) | projeto médio |
| Propostas determinísticas de realce (docs/93) | desconhecido | alto — substitui o localizador |
| Segunda coorte | FNH (n=46) e domínio | meses, não técnico |

---

## 5. Estado consolidado da meta de subtipo

| Marco | Valor | Natureza |
|---|---:|---|
| Abordagem inicial (fígado inteiro) | 52,18% | medido |
| **Pipeline atual** | **61,46%** | **medido ponta a ponta** |
| Teto com centro correto | 76,50% | teto |
| Teto com ROI de ground truth | 79,49% | teto |
| **Meta** | **75%** | — |

**Progresso: +9,3 pontos**, todos medidos, com cada passo documentado e cada gate honrado.

**Avaliação honesta do alcance:** a seleção aprendida levaria a ~70%. Chegar a 75% exigiria,
além dela, resolver a FNH — que é limitada por amostra (n=46) e depende da segunda coorte.
Manter a projeção de ~65–70% como alvo realista com os dados atuais, registrada em docs/147,
continua correto.

`clinical_use_allowed` permanece `false`. Coorte única; não é estimativa de generalização.
