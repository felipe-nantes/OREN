# Plano — Seleção aprendida de componente

**Data:** 30 de julho de 2026
**Origem:** [docs/148](148_PASSO3C_SELECAO_COMPONENTE.md) — oráculo 82,4% vs critério atual
67,8%; há 14,6 pontos de centro disponíveis, inacessíveis por heurística.
**Objetivo:** capturar o máximo desses 14,6 pontos, que valem ~+8–10 na balanceada.

---

## 1. A tarefa, precisamente

Não é segmentação nem detecção. É **ranqueamento dentro do caso**: dados os componentes
conexos da união das predições (mediana de 3 por caso), escolher qual é a lesão.

Treino como classificação binária por componente — "este componente toca a lesão?" — e em
inferência escolho o de maior probabilidade no caso. Ranqueamento pontual, adequado ao
tamanho do problema.

**Dimensão:** ~1000 componentes, ~28% positivos. Amostra pequena. Isso decide o desenho:
**features boas e modelo simples**, não o contrário.

---

## 2. Uma fonte de sinal descartada de propósito

Concordância entre fases seria a feature mais óbvia — um componente predito pela venosa,
arterial e tardia é mais provável de ser lesão real.

**Não pode ser usada.** Rodei a arterial apenas nas 103 perdas da venosa (docs/141) e a
tardia apenas nas 67 restantes (docs/145). Logo "predito por múltiplas fases" correlaciona
com "a venosa falhou", que é artefato do meu sequenciamento experimental, não propriedade do
pipeline em produção. Um seletor que a usasse aprenderia dificuldade do caso, e o número
seria inflado sem valor real.

Usá-la exigiria rodar as três fases nos 335 casos — ~4h de GPU. Fica registrada como
**melhoria futura de alto valor**, não como parte deste plano.

---

## 3. Features — o que decide o resultado

Todas calculadas sobre a máscara de união, consistentes com o baseline medido.

### 3.1 Rejeição de espúrios (as mais promissoras, não testadas antes)

| Feature | Racional |
|---|---|
| `fracao_dentro_figado` | Componentes fora do fígado são falsos positivos por definição. Trivialmente barata e potencialmente decisiva. |
| `contraste_com_vizinhanca` | Lesão difere do parênquima adjacente; fragmento espúrio de parênquima não difere. Razão contra casca dilatada, referência interna (exigência de docs/131). |
| `dist_borda_figado` | Falsos positivos de nnU-Net concentram-se em bordas de órgão. |

### 3.2 Relativas ao caso (críticas para ranqueamento)

| Feature | Racional |
|---|---|
| `rank_volume` | "É o maior?" vira feature, em vez de regra — o modelo aprende quando volume importa. |
| `fracao_do_volume_total` | Um componente que é 90% do volume predito é diferente de um que é 10%. |
| `n_componentes_no_caso` | Contexto: com 1 componente não há escolha; com 8, o problema é outro. |

### 3.3 Geometria e intensidade

Volume (log), compacidade, alongamento, centralidade; razões lesão/parênquima em pré,
arterial, venosa e tardia; washout, preenchimento, heterogeneidade.

**Todas as intensidades como razão contra parênquima interno**, nunca valor absoluto — o
requisito de invariância de domínio de docs/131, que reprovou features absolutas a 98,75%.

---

## 4. Execução em duas fases

O mesmo padrão que evitou desperdício em docs/148: diagnóstico barato antes de GPU.

### Fase A — CPU, ~20 min

Construir a tabela de componentes, treinar o seletor nos **splits congelados agrupados por
paciente** (OOF; o seletor nunca vê o caso que avalia) e medir **acerto de centro**.

Modelos comparados: regressão logística (interpretável, alinhada ao projeto) e gradient
boosting (captura interações com pouca amostra).

**Gate:** acerto de centro ≥ **73%** (de 67,8%, +5,2 pts, rumo ao oráculo de 82,4%).
Abaixo disso, a Fase B não roda.

### Fase B — GPU, ~15 min

Só se A passar. Recortar pelos componentes selecionados, embutir com MedSigLIP, medir a
balanceada ponta a ponta.

**Variante a testar:** em vez do top-1, recorte cobrindo os **dois** componentes mais bem
ranqueados quando a diferença de probabilidade for pequena. Recupera casos em que o certo
ficou em segundo lugar, ao custo de recorte maior.

**Gate:** balanceada ≥ **66%** (de 61,46%, +4,5 pts).

---

## 5. Aritmética honesta do que se pode esperar

| Cenário de acerto de centro | Balanceada projetada |
|---:|---:|
| 67,8% (hoje) | 61,5% (medido) |
| 73% (gate da Fase A) | ~65% |
| 78% (bom resultado) | ~69% |
| 82,4% (oráculo, inatingível) | ~72% |

**Mesmo capturando todo o oráculo, não se chega a 75%.** O teto do seletor é ~72%, porque a
discriminação com centro correto é 76,5–79,5% e nem todos os casos têm componente certo na
predição.

Isso não desqualifica o trabalho — é o maior ganho isolado ainda disponível sem dados novos.
Mas mantém válida a avaliação de docs/147: **~65–70% é o alvo realista**, e 75% depende da
segunda coorte.

---

## 6. Limitação estrutural a registrar desde já

O seletor é treinado com ground truth de localização do LLD-MMRI. **Sua generalização para
uma coorte nova é desconhecida** e não pode ser medida internamente — mesmo problema de
confundimento de domínio que docs/131 documentou.

Mitigação parcial: features exclusivamente como razões internas (§3.3) reduzem a dependência
de scanner. Mas o requisito de validação externa permanece, e o seletor **não deve ir para
produção** sem ela.

---

## 7. Ordem

```
Fase A (CPU, 20min)  ──→ gate 73% de acerto de centro
       │ reprovou → parar; registrar e ir para a segunda coorte
       ▼
Fase B (GPU, 15min)  ──→ gate 66% de balanceada
       ▼
documentar + commitar (mesmo se reprovar, como em 137/142/147/148)
```

`clinical_use_allowed` permanece `false`.
