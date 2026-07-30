# Passo 3a — Recorte físico fixo: hipótese refutada, gargalo identificado

**Data:** 30 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/passo3a_recorte_fisico_v1/`
**Passo 3a** de [docs/146](146_PASSO2_MEDICAO_HONESTA.md) §5
**Veredito:** hipótese **refutada** — mas o braço de controle identificou o gargalo real.

---

## 1. Resultado

| Centro | 30 mm | 40 mm | 50 mm | 60 mm |
|---|---:|---:|---:|---:|
| **Predito** | **60,91%** | 56,27% | 55,80% | 52,44% |
| **Ground truth** | 75,88% | **76,50%** | 69,93% | 65,30% |

Baseline (margem proporcional 0,6, docs/146): **61,46%**.

**Nenhum tamanho fixo superou o baseline.** O melhor (30 mm) ficou 0,55 ponto abaixo, e o
desempenho **cai monotonicamente** com o tamanho.

---

## 2. Por que minha hipótese estava errada

Argumentei em docs/146 §3 que a margem proporcional herdava o viés de escala da predição
(que sub-segmenta), e que um tamanho físico fixo corrigiria isso.

O erro: tratei o tamanho das lesões como aproximadamente constante. **Não é.** Um recorte
fixo é grande demais para lesão pequena — que fica diluída em parênquima — e apertado demais
para lesão grande, que é cortada. O recorte proporcional, apesar de herdar a sub-segmentação,
ao menos **se adapta à escala de cada lesão**.

A monotonicidade confirma: quanto maior o recorte fixo, mais parênquima entra, pior fica. O
mesmo padrão aparece nos braços de ground truth (76,50% em 40 mm → 65,30% em 60 mm).

---

## 3. O braço de controle: o achado que justifica o experimento

Este era um teste desenhado para não sair de mãos vazias mesmo falhando, e foi o que
aconteceu. Com **método de recorte idêntico**, trocando apenas o centro:

| | 40 mm |
|---|---:|
| Centro predito | 56,27% |
| **Centro de ground truth** | **76,50%** |
| **Diferença** | **20,2 pontos** |

Considerando os melhores de cada lado: **15,59 pontos** de perda atribuíveis exclusivamente
ao centro.

**Conclusão: a degradação de 18 pontos identificada em docs/146 vem da qualidade da
localização — de onde o localizador aponta — e não do enquadramento do recorte.** Nenhuma
engenharia de recorte contorna isso.

---

## 4. Consequência imediata: o Passo 3b está cancelado

docs/146 §5 propunha crescimento de região a partir da semente predita como plano B. **Está
cancelado antes de custar tempo.**

O motivo é direto: crescimento de região parte da mesma semente. Se o centro está errado,
crescer a partir dele produz uma região errada e maior — não melhor. O braço de controle
mostra que o problema não é a extensão da ROI, é sua posição.

Este é o valor do controle: um resultado negativo que **elimina** o próximo passo planejado,
em vez de deixá-lo como incerteza a testar.

---

## 5. Onde a meta está

| | Valor |
|---|---:|
| Abordagem atual (fígado inteiro) | 52,18% |
| **Pipeline medido (melhor configuração)** | **61,46%** |
| Teto com centro correto, recorte fixo | 76,50% |
| Teto com ROI de ground truth completa | 79,49% |
| **Meta** | **75%** |

O caminho para 75% tem agora **um nome único: precisão de localização.** Não o recall
binário — 83,6% já é razoável — mas *acertar o centro da lesão certa*.

### Por que recall binário e precisão de centro são coisas diferentes

O recall de 83,6% (docs/145) conta como acerto qualquer predição que **toque** a lesão. Mas
o pipeline usa o **maior componente conexo** da união, e seu centroide pode estar deslocado —
seja porque o componente pega só uma borda da lesão, seja porque um falso positivo em outro
lugar é maior que o verdadeiro. Nos dois casos o recorte sai do lugar errado, e o
classificador recebe tecido que não é a lesão.

---

## 6. Direções restantes, com custo/benefício honesto

| Direção | Ataca | Custo | Avaliação |
|---|---|---|---|
| **Selecionar melhor o componente** (não o maior, mas o mais provável como lesão) | precisão de centro | baixo | O único item barato que ataca o gargalo real |
| Propostas determinísticas de realce (docs/93) | precisão de centro | alto | Substituir o localizador; nunca executado |
| Segunda coorte | FNH (n=46) e domínio | meses | Inalterado; não bloqueia |
| ~~Crescimento de região (3b)~~ | — | — | **Cancelado por este experimento** |
| ~~Recorte fixo (3a)~~ | — | — | **Refutado por este experimento** |

O primeiro item merece teste: hoje escolho o maior componente por simplicidade. Critérios
alternativos — componente mais central no fígado, mais compacto, ou com maior realce relativo
— podem acertar o centro com mais frequência sem trocar o localizador.

**Avaliação honesta:** mesmo com centro perfeito o teto é 76,50–79,49%, então a meta de 75%
exigiria localização quase perfeita. Com os dados atuais, considero **~65–70% o alvo
realista**, e 75% dependente de dados adicionais.

`clinical_use_allowed` permanece `false`.
