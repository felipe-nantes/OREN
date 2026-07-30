# Plano de fechamento da meta de subtipo (75%)

**Data:** 30 de julho de 2026
**Estado de partida:** localização 80,0% · discriminação 79,5% · efetivo **estimado** ~63,6%
**Meta:** 75% de acurácia balanceada

---

## 1. Princípio: nada do que foi alcançado é tocado

Todos os passos abaixo são **aditivos sobre artefatos congelados**. Não alteram o bundle de
produção, o endpoint binário, o limiar, nem qualquer arquivo já assinado. Cada experimento
grava em diretório próprio e é reversível por `rm -rf`. O que já está commitado (docs/138 a
143) permanece válido como registro histórico mesmo que os números melhorem.

---

## 2. O que os dados dizem sobre onde investir

### 2.1 As ROIs preditas sub-segmentam — isso é oportunidade, não só problema

| Medida sobre as 228 ROIs preditas que acertaram | Valor |
|---|---:|
| IoU mediano com a lesão real | 0,395 |
| IoU p25 / p75 | 0,170 / 0,548 |
| **Razão de volume predito/real (mediana)** | **0,57** |

A predição **acerta o lugar mas pega pouco mais da metade** do volume da lesão. Como o
recorte é definido por *bounding box + margem*, uma margem maior compensa a
sub-segmentação: o centro está certo, falta extensão. **A margem passa a ser parâmetro a
varrer, não constante.**

### 2.2 O gargalo tem nome: FNH

| Subtipo | Localiza | Discrimina | Efetivo | n |
|---|---:|---:|---:|---:|
| `hepatic_cyst` | 92,5% | 92,5% | ~86% | 53 |
| `hcc` | 84,7% | 82,2% | ~70% | 157 |
| `hemangioma` | 72,2% | 75,9% | ~55% | 79 |
| **`fnh`** | **63,0%** | **67,4%** | **~42%** | **46** |

A FNH é fraca nas duas metades e tem a menor amostra. Cisto já superou a meta; HCC chegou
perto.

### 2.3 Restam 67 perdas de localização após a união

`hemangioma` 22 · `hcc` 24 · `fnh` 17 · `hepatic_cyst` 4

---

## 3. Plano em quatro passos, ordenados por custo/benefício

### Passo 1 — Fase tardia na união do localizador · ~50 min GPU · **executar primeiro**

**Hipótese:** o hemangioma tem preenchimento centrípeto progressivo, mais conspícuo na fase
**tardia**. É o mesmo argumento fisiológico que fez a arterial recuperar 35,6% das perdas
(docs/141), aplicado à classe que a arterial menos ajudou.

**Método:** rodar o localizador na fase tardia apenas nas **67 perdas restantes** — como
união é "venosa ou arterial ou tardia", um acerto anterior já garante a união. Mesma economia
de docs/141.

**Por que primeiro:** define o conjunto final de ROIs. Fazer o Passo 2 antes obrigaria a
refazê-lo depois.

**Gate:** recuperação ≥ 20% das 67 perdas (a arterial recuperou 35,6% de 104). Abaixo disso,
a tardia não entra no pipeline.

### Passo 2 — Medição honesta ponta a ponta, com varredura de margem · ~40 min GPU

**O item mais importante do plano.** Hoje o efetivo de 63,6% é *estimativa*: multiplica
localização por discriminação medida sobre ROI de **ground truth**. Nunca medimos a
discriminação sobre a ROI **predita**.

**Método:** recortar pela ROI **predita** (não a real), embutir com MedSigLIP, rodar o mesmo
nested-OOF. Varrer margens **0,35 / 0,6 / 1,0** — justificado por §2.1: predições
sub-segmentam, então margem maior deve recuperar a lesão.

Casos que o localizador **não** achou contam como **erro**, não são descartados — é o
comportamento de produção.

**Entrega:** o primeiro número de subtipo **medido de ponta a ponta**, sem suposição. É o que
deve ser reportado à equipe; os 63,6% não devem ser citados como resultado.

### Passo 3 — Seleção de C em folds internos · ~10 min CPU

O `C=0,01` da regressão sobre 1152 dimensões foi escolhido por analogia ao bundle, não
medido. Selecionar C nos **folds internos** (aninhado, sem vazamento) é barato e pode render
1–2 pontos. Só vale depois do Passo 2, sobre a representação final.

### Passo 4 — FNH · meses · **iniciar em paralelo, não bloqueia**

n=46 é a menor classe e a mais fraca. Parte do problema pode ser **amostra, não método** —
com 46 casos, o IC95 de um recall de 67% vai de ~53% a ~79%. Uma segunda coorte (Etapa 4 de
docs/135) endereça isso **e** o confundimento de domínio ao mesmo tempo. É o item de maior
prazo e o único que não é técnico.

---

## 4. Aritmética: 75% é alcançável?

Com discriminação em 79,5% e localização em 80,0%, o efetivo estimado é 63,6%. Para 75%:

| Cenário | Localização | Discriminação | Efetivo |
|---|---:|---:|---:|
| Hoje (estimado) | 80,0% | 79,5% | 63,6% |
| Passo 1 otimista (+5 pts loc) | 85,0% | 79,5% | 67,6% |
| Passos 1+3 | 85,0% | 81,5% | 69,3% |
| **Necessário para a meta** | **87%** | **86%** | **75%** |

**Conclusão honesta: os Passos 1–3 provavelmente não bastam.** Levam a ~69%, não a 75%. O
salto restante depende de resolver a FNH, que é limitada por amostra — ou seja, do Passo 4.

Isso não invalida os Passos 1–3: eles são baratos, aditivos, e o Passo 2 é obrigatório para
sabermos onde estamos de verdade. Mas seria desonesto prometer que a meta cai sem dados
novos.

---

## 5. Ordem de execução

```
Passo 1 (tardia, 50min GPU)  ─→ define ROIs finais
        ↓
Passo 2 (medicao honesta + margem, 40min GPU)  ─→ NUMERO REAL
        ↓
Passo 3 (selecao de C, 10min CPU)  ─→ ajuste fino
        ↓
Passo 4 (segunda coorte)  ─→ em paralelo desde ja; unica via para a meta
```

Cada passo tem gate pré-especificado antes de rodar e é registrado com o resultado, mesmo
negativo — como em docs/136, 142 e 143, onde gates reprovados foram mantidos reprovados.

`clinical_use_allowed` permanece `false` em todos os passos.
