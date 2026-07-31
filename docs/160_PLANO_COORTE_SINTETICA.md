# Plano de uso da coorte sintética

**Data:** 31 de julho de 2026
**Status:** plano, antes de qualquer dado chegar. Gates pré-especificados.

---

## 1. O que dado sintético não pode fazer

Isto precisa estar claro antes de tudo, porque define todo o resto.

A segunda coorte foi pedida em [docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md)
com quatro finalidades. Dado sintético atende **uma**:

| Finalidade | Sintético serve? | Por quê |
|---|---|---|
| Medir generalização para origem nunca vista | **Não** | Se foi gerado a partir das coortes atuais, herda a distribuição delas. Avaliar nele não mede generalização — mede o gerador. |
| Estabelecer taxa de falso positivo | **Não** | A taxa de FP em negativos sintéticos descreve o gerador, não pacientes. |
| Corrigir a classe FNH | **Sim, potencialmente** | Como aumento de dados **no treino**. É o uso legítimo. |
| Validação externa para publicação | **Não** | Não é aceito como validação externa. Revisor rejeita. |

**A busca pela coorte real continua necessária.** O sintético não a substitui; no
melhor caso ele melhora o modelo enquanto a real não chega.

---

## 2. O risco que o plano precisa conter

O pedido foi "garantir a acertividade nas reais". Esse é exatamente o risco certo
a temer, e ele tem quatro formas:

1. **Contaminação da avaliação.** Um caso sintético no conjunto de teste torna
   toda métrica sem sentido.
2. **Deslocamento para o gerador.** Treinar em sintético ensina os artefatos do
   gerador. O probe de domínio já prevê coorte a 100%; sintético seria um quarto
   domínio, provavelmente ainda mais separável.
3. **Vazamento pela origem.** Se o gerador foi treinado sobre imagens do LLD, um
   caso sintético derivado de um caso que está no **teste** carrega informação
   dele. É a falha mais perigosa porque é invisível nas métricas.
4. **Falsa confiança.** Os números sobem, o desempenho real não.

O plano é construído em torno de uma barreira dura contra os quatro.

---

## 3. Princípios inegociáveis

**P1 — Sintético nunca entra na avaliação.** Todas as métricas permanecem sobre
dados reais, nos mesmos splits congelados. Sem exceção.

**P2 — A barreira é mecânica, não uma promessa.** Todo caso sintético recebe
prefixo `synth-`, e a avaliação carrega uma asserção que falha se qualquer id com
esse prefixo aparecer em fold de teste ou no denominador.

**P3 — O gate é a métrica real.** A pergunta é sempre: *adicionar sintético ao
treino melhora o número nos dados reais?* Se não melhorar, descarta-se.

**P4 — Resultado negativo é resultado.** Se o sintético não ajudar, isso fica
documentado com a mesma seriedade, e a linha se encerra.

---

## 4. Fase 0 — Auditoria de procedência (antes de qualquer uso)

**Nada é usado antes desta fase passar.**

### Perguntas que preciso responder

1. **O que gerou os dados?** Modelo, versão, e sobre quais dados foi treinado.
2. **O gerador viu casos dos nossos folds de teste?** Se sim, quais. Esta é a
   pergunta mais importante do plano inteiro.
3. **Cada caso sintético deriva de um caso real identificável?** Se sim, preciso
   do mapeamento — para excluir do treino qualquer sintético cuja origem esteja
   no teste do fold correspondente.
4. **Como os rótulos foram atribuídos?** Condicionados na geração, ou lidos
   depois por alguém?

### Verificação técnica

- fases dinâmicas arterial, venosa e tardia presentes;
- geometria consistente entre fases;
- formato legível pelo pipeline atual;
- ausência de metadados que identifiquem origem.

**Critério de parada:** se não for possível estabelecer que o gerador não viu os
folds de teste, o dado só pode ser usado com os folds refeitos — o que invalida
toda comparação histórica. Nesse caso, é melhor não usar.

---

## 5. Fase 1 — Caracterização (sem treinar nada)

### 1.1 Probe de domínio

Classificador que tenta prever *real vs sintético* a partir dos embeddings.

- **Espero acurácia alta** — sintético costuma ser trivialmente separável.
- Não é motivo para descartar; é a **quantificação do risco**. Quanto mais
  separável, mais o modelo pode aprender "isto é sintético" em vez de "isto é
  FNH".

### 1.2 Comparação de distribuições

Os mesmos descritores de [docs/159](159_ANALISE_ERRO_CISTO.md) — volume, razão de
sinal por fase, realce entre fases, heterogeneidade — comparados entre FNH real e
FNH sintética. Diz se o gerador reproduz a física ou só a aparência.

### 1.3 Revisão visual

Uma amostra vista por radiologista, sem rótulo. A pergunta é simples: **isto
parece um exame de verdade?** Se um humano treinado descarta na hora, o modelo
provavelmente também.

---

## 6. Fase 2 — Controles negativos (antes de acreditar em qualquer ganho)

Executados **antes** do experimento principal, porque definem como interpretá-lo.

### Controle A — treinar só em sintético, avaliar em real

| Resultado | Leitura |
|---|---|
| Desempenho ruim | Esperado. O sintético sozinho não carrega sinal transferível. |
| Desempenho bom | **Suspeito.** Investigar vazamento antes de comemorar. |
| Desempenho igual ao real | Sinal forte de vazamento pela origem. **Parar.** |

### Controle B — sintético com rótulo embaralhado

Adicionar sintético ao treino com rótulos aleatórios. Se o desempenho real
**melhorar** mesmo assim, o ganho não vem do rótulo — vem de regularização por
ruído, e o dado sintético não está fazendo o que se pensa.

---

## 7. Fase 3 — Experimento principal

### Desenho

- sintético entra **apenas nos folds de treino**, nunca em validação ou teste;
- os splits congelados dos casos reais permanecem **intocados**;
- avaliação idêntica à oficial: multiclasse sobre o rótulo fino, binário pela
  massa nas classes positivas, `C`/agregação/limiar escolhidos nos folds internos;
- denominador: os mesmos 467 casos reais.

### Braços

| Braço | Treino |
|---|---|
| Base | só real *(reproduz o oficial)* |
| S1 | real + sintético de FNH |
| S2 | real + sintético de todas as classes |
| S3 | real + sintético com peso amostral reduzido |

### Gates pré-especificados

**Primário — a classe alvo:**
> recall de FNH em dados reais sobe **≥ 5 pontos** sem que nenhuma outra classe
> caia mais de 2 pontos.

**Secundário — o endpoint binário:**
> nenhum dataset piora mais de 1 ponto em sensibilidade ou especificidade.

**Verificação de sanidade:**
> o braço Base reproduz o oficial dentro de 1 ponto. Sem isso, nada é
> interpretável.

**Se o gate primário falhar, a linha se encerra.** Sem reajuste, sem "quase lá".

---

## 8. Fase 4 — O que pode e o que não pode ser dito depois

Mesmo com todos os gates passando:

**Pode:** "adicionar dados sintéticos ao treino melhorou o recall de FNH em dados
reais de X para Y, medido nos mesmos splits congelados, sem degradar as demais
classes."

**Não pode:** chamar isso de validação externa; reportar qualquer métrica medida
sobre sintético; usar como evidência de generalização; dispensar a coorte real.

Todo artefato gerado carrega `synthetic_data_used_in_training: true`, e qualquer
número derivado dele carrega essa marca junto.

---

## 9. Custo e ordem

| Fase | Esforço | Bloqueia? |
|---|---|---|
| 0 — auditoria de procedência | horas | **sim, tudo** |
| 1 — caracterização | ~1 h de compute | não |
| 2 — controles negativos | ~2 h | **sim, a fase 3** |
| 3 — experimento | ~3 h | — |

**A Fase 0 é a que decide.** Se o gerador viu os folds de teste, nada do resto se
sustenta — e é melhor saber disso antes de gastar as outras seis horas.

---

## 10. O que preciso de você junto com os dados

1. **Como foram gerados** — modelo, e sobre quais dados foi treinado.
2. **Se o gerador viu LLD ou OpenSwiss**, e quais casos.
3. **Mapeamento caso sintético → caso real de origem**, se existir.
4. **Como os rótulos foram definidos.**
5. **Quantos casos por classe**, incluindo negativos.

Sem os itens 1 e 2 eu não consigo garantir a barreira contra vazamento, e aí o
uso honesto do dado fica limitado a exploração — não a nada que entre em número
reportado.

`research_only: true` · `clinical_use_allowed: false`
