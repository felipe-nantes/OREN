# Plano para as metas de 75% — o que resta com os dados atuais

**Data:** 30 de julho de 2026
**Base:** todos os números abaixo são medidos, com origem citada.

---

## 1. Onde estamos

### Meta 1 — endpoint binário (75% sens / 75% esp)

| | Sens | Esp | Gate |
|---|---:|---:|:--|
| Agregado nested-OOF | 75,91% | 76,11% | passa (IC inferior ~70%) |
| `lld_mmri` | **73,25%** | 76,97% | falha |
| `openswiss_development` | 82,05% | 77,55% | OK |
| `openswiss_holdout` | 83,33% | **65,00%** | falha |

**Distância real é pequena:** o LLD precisa de **+2 verdadeiros positivos** e o
holdout de **+2 verdadeiros negativos**. Mas a calibração já foi eliminada
(docs/134): nem o melhor limiar alcança 75/75 no LLD (teto 75,16% / 74,72%).

### Meta 2 — subtipo (75% balanceada)

| | Valor |
|---|---:|
| Medido ponta a ponta | **61,46%** |
| Teto com centro correto | 76,50% |
| Teto com ROI de ground truth | 79,49% |

---

## 2. A aritmética que decide o que é possível

**Subtipo:** o efetivo é `acerto de centro × discriminação`. Com discriminação em
79,49% — o melhor já obtido, e com ROI perfeita — atingir 75% exigiria acerto de
centro de **94%**. O oráculo de seleção de componente é **82,4%**: em 17,6% dos
casos o componente certo **nem existe** na predição. Portanto:

> **75% de subtipo é inalcançável com o localizador e os dados atuais.**
> O teto absoluto, capturando todo o oráculo, é ~65%.

**Binário:** aqui a distância é de 2 casos por dataset. É apertado, mas **não é
aritmeticamente impossível**.

Essa assimetria define o plano: **priorizar o binário**, tratar o subtipo como
melhoria incremental com alvo honesto de 65–70%.

---

## 3. Um achado que orienta tudo

A sensibilidade binária no LLD **é** detecção de HCC — HCC é o único positivo
daquela coorte. E temos três medições do mesmo alvo:

| Representação | Recall de HCC |
|---|---:|
| Painel de fígado inteiro (pipeline binário atual) | 73,25% |
| Recorte por ROI **predita** | 65,0% |
| Recorte por ROI de **ground truth** | 82,2% |

Duas leituras:

1. **Trocar fígado inteiro por recorte piora** (65,0% < 73,25%) — a localização
   atual não é boa o bastante. Substituição está descartada.
2. **As duas representações erram em casos diferentes.** Fígado inteiro captura
   contexto; recorte captura detalhe local. Isso é a condição clássica para
   **fusão** render mais que qualquer uma isolada.

Fusão nunca foi testada entre estas duas. O teste anterior de combinação
(docs/143) somou recorte com **descritores manuais**, que é outra coisa.

---

## 4. Plano — quatro passos, ordenados por custo/benefício

### Passo 1 — Fusão de representações · ~40 min GPU · **maior chance nas duas metas**

Concatenar o embedding de **fígado inteiro** (já em cache, `medsiglip_embeddings_stage_a_v1`)
com o embedding do **recorte por ROI predita** (já em cache,
`predicted_roi_embeddings_v1`). Treinar nos mesmos splits congelados.

Avaliar em **ambos** os endpoints, porque a mesma representação serve aos dois:
- binário: sens/esp por dataset, alvo 75/75
- subtipo: balanceada 4 classes

**Gate:** sensibilidade no LLD ≥ 75% **ou** balanceada de subtipo ≥ 65%.

Custo baixo porque os dois conjuntos de embeddings já existem — é concatenação e
treino, sem re-embutir.

### Passo 2 — Seleção de C e agregação de recortes · ~20 min · ajuste fino

Duas frouxidões nunca corrigidas:

- **C = 0,01 foi herdado**, nunca selecionado. Escolher nos folds internos
  (aninhado, sem vazamento) sobre 1152 dimensões costuma render 1–2 pontos.
- **O recorte usa 3 cortes e uma margem.** Média de embeddings sobre mais cortes e
  duas margens (0,35 e 0,6) é *test-time augmentation* clássica, e reduz a
  variância que a ROI ruidosa introduz.

**Gate:** ganho ≥ 1,5 ponto sobre o Passo 1.

### Passo 3 — Múltiplas instâncias em vez de escolher um componente · ~40 min GPU

Hoje o pipeline **escolhe** um componente e vive com o erro. A seleção aprendida
falhou (+0,9 pt, docs/148) porque o componente certo não é distinguível por
features geométricas.

A alternativa não testada: **não escolher**. Embutir *todos* os componentes do
caso e deixar o classificador pontuar cada um, ficando com a predição mais
confiante. É *multiple instance learning* — a formulação natural para "uma destas
regiões é a lesão", e ela contorna o problema em vez de resolvê-lo.

Teto: o oráculo de 82,4%, não os 67,8% da escolha atual.

**Gate:** balanceada ≥ 66%.

### Passo 4 — Segunda coorte · meses · **iniciar em paralelo, não bloqueia**

O único caminho para 75% de subtipo, e o que também resolveria:
- **FNH** (n=46, pior classe, ~50% efetivo);
- **poder estatístico** do holdout (20 negativos, IC de especificidade com 38
  pontos de largura);
- **confundimento de domínio** (coorte previsível a 100%, docs/131).

Não é trabalho técnico — é aquisição. Por isso deve começar já, em paralelo aos
Passos 1–3.

---

## 5. O que esperar, sem otimismo

| Meta | Hoje | Após Passos 1–3 (estimativa) | Alvo |
|---|---:|---:|---:|
| Binário — sens LLD | 73,25% | 75–78% *(plausível)* | 75% |
| Binário — esp holdout | 65,00% | 68–75% *(incerto, n=20)* | 75% |
| Subtipo — balanceada | 61,46% | 65–68% | 75% |

**Binário 75/75 é alcançável**, com a ressalva de que o holdout tem 20 negativos e
cada caso vale 5 pontos de especificidade — mesmo passando, não estaria
*estabelecido*.

**Subtipo 75% não é alcançável** com os dados atuais. O alvo honesto é 65–70%, e
os 75% dependem do Passo 4.

---

## 6. Compromissos de método

Mantidos de docs/128, 130, 132, 136, 149:

- gate pré-especificado e commitado **antes** de cada medição;
- gate reprovado permanece reprovado, sem reajuste;
- resultado negativo documentado com a mesma seriedade do positivo;
- nada promovido a produção sem validação externa;
- `clinical_use_allowed` permanece `false`.

E um acréscimo, vindo do experimento FNH: **todo protocolo novo é medido também
contra um controle negativo** — o braço "fora do fígado" revelou uma falha de 91%
que nenhuma métrica de acerto teria mostrado.
