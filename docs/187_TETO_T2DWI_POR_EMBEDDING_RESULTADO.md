# T2/DWI por embedding no mesmo recorte — REPROVADO: −1,96 ponto

**Data:** 5 de agosto de 2026
**Artefatos:** `casos/qualification/hybrid_v1/roi_ceiling_t2dwi_embedding_v1/`
**Script:** `tools/build_lld_mmri_v23_roi_ceiling_t2dwi_embedding_pilot.py`
**Gate pré-especificado** no docstring do script e em constante, antes de qualquer número.

---

## 1. A lacuna que este piloto fechou

[docs/142](142_T2WI_DWI_DISCRIMINACAO_RESULTADO.md) testou T2/DWI no mesmo local
físico da lesão e falhou (+0,23 ponto, ruído) — mas com **descritores
artesanais** (razão de intensidade mediana e IQR). [docs/143](143_RECORTE_MEDSIGLIP_DISCRIMINACAO.md),
logo depois, trocou descritores artesanais por **embedding MedSigLIP** para a
dinâmica e saltou de 74,47% para 79,49% (+5,02).

Ninguém havia testado a combinação: **T2/DWI por embedding aprendido**. Um
padrão espacial — cicatriz central de FNH, textura de restrição à difusão — é
exatamente o que um embedding capta e uma mediana de intensidade apaga. Era
também o item 5 da lista de próximos passos válidos de
[docs/184](184_VALIDACAO_EXTERNA_MONOFASICA_E_LIMITE_DA_REPRESENTACAO.md).

---

## 2. Método

Idêntico ao braço B de docs/143 em tudo — mesma ROI de ground truth, mesma
margem (0,35), mesmos cortes axiais (3), mesmo tile (448), mesmos splits
congelados, mesmo estimador. **A única variável é o conteúdo dos canais RGB.**
É isso que torna a comparação contra 79,49% legítima.

T2 e DWI vivem em grades nativas diferentes (7 mm de corte contra 3 mm da
dinâmica) e foram reamostrados na grade venosa por transformação de identidade
em coordenadas físicas — a mesma técnica de produção. Canais: R=T2, G=DWI,
B=DWI (o LLD-MMRI **não possui mapa ADC**; há dois sinais reais para três
canais, e duplicar o DWI concentra capacidade no sinal de restrição).

Cobertura verificada: **312/335 casos** com cobertura ≥90% da caixa de recorte.
Os 23 restantes entraram com vetor zerado e indicador explícito de ausência —
nunca removidos do denominador.

---

## 3. Resultado

| Braço | Representação | dim | n | Balanceada | Top-1 |
|---|---|---:|---:|---:|---:|
| **B** dinâmico (referência) | R=art G=ven B=del | 1152 | 335 | **79,49%** | 80,30% |
| **T** T2/DWI sozinho (diagnóstico) | R=T2 G=DWI B=DWI | 1152 | 312 | 56,57% | 58,33% |
| **E** fundido (hipótese) | B + T + indicador | 2305 | 335 | **77,53%** | 79,40% |

| Critério | Exigido | Obtido | |
|---|---:|---:|:--|
| Balanceada do braço E | ≥ 81,49% | 77,53% | **FALHA** |

> **O braço B reproduziu 79,49% exatamente**, o mesmo número de docs/143. A
> reprodução exata é o que valida o arranjo: a comparação é contra a mesma
> régua, não contra um número aproximado.

**Acrescentar T2/DWI piorou o resultado em 1,96 ponto.**

Recall por classe:

| Classe | B | E | Δ |
|---|---:|---:|---:|
| FNH | 67,4% | 65,2% | −2,2 |
| HCC | 82,2% | 84,1% | **+1,9** |
| Hemangioma | 75,9% | 72,2% | −3,7 |
| Cisto hepático | 92,5% | 88,7% | −3,8 |

---

## 4. Não é artefato de regularização — verificado

O piloto usou `C=0,01` fixo nos três braços, herdado da escolha de docs/143. Mas
o braço E tem o dobro da dimensão, e regularização fixa poderia penalizá-lo por
construção — o que seria erro de implementação, não resultado sobre T2/DWI.
Varredura diagnóstica:

| C | B (dinâmica) | E (fundido) |
|---:|---:|---:|
| 0,001 | 77,13% | 75,24% |
| 0,003 | 76,97% | 76,03% |
| **0,01** | **79,49%** | 77,53% |
| 0,03 | 79,01% | 77,38% |
| 0,1 | 76,90% | 77,38% |
| 0,3 | 75,95% | 77,22% |
| 1,0 | 75,41% | **77,53%** |

**O braço E não supera o braço B em nenhum valor de C**, e seu máximo (77,53%)
fica 3,96 pontos abaixo do gate. O resultado negativo é robusto à
regularização.

Esta varredura é **diagnóstica e post-hoc**. Ela não reabre o gate — o gate
falhou como pré-especificado. Ela apenas descarta a explicação de que a falha
fosse um defeito do meu arranjo em vez de um fato sobre a representação.

---

## 5. O que aprendemos — leitura honesta

**T2/DWI carrega sinal de subtipo, e isso é novo.** O braço T sozinho atinge
56,57% contra 25,00% de acaso. Descritores artesanais em docs/142 não
conseguiram demonstrar isso; o embedding consegue. A hipótese "embedding capta
o que a mediana apaga" **estava certa sobre a existência do sinal**.

**Mas o sinal é redundante, não complementar.** Tudo que T2/DWI sabe sobre
subtipo, a dinâmica já sabe — e melhor (79,49% contra 56,57%). Acrescentar 1152
dimensões de um sinal mais fraco sobre 335 casos custa mais em variância do que
adiciona em informação. O padrão por classe confirma: o HCC melhora 1,9 ponto,
mas FNH, hemangioma e cisto pioram entre 2,2 e 3,8.

**A confusão que importa não se moveu.** O gargalo nomeado desde docs/141 é
HCC↔FNH, e a FNH — a pior classe do sistema — **piorou** com T2/DWI. Se havia
uma classe que a difusão e o T2 deveriam ajudar a separar, era essa.

---

## 6. Consequência para o plano

O piloto foi desenhado justamente para ser a decisão barata antes da construção
cara: localizador do LLD (que não existe no repositório e precisaria ser
reconstruído), geometria de candidato, renderização de segunda vista, supervisão
multiclasse por candidato, hard negatives. **Todo esse trabalho está agora
descartado por evidência**, a um custo de 4,7 minutos de GPU e um script.

Se o piloto tivesse sido pulado, a mesma conclusão viria depois de semanas de
engenharia — e com uma variável a mais (localização imperfeita) contaminando a
leitura.

**A hipótese de que "T2/DWI no mesmo local espacial melhora o subtipo" está
encerrada em duas formulações independentes:** descritores artesanais (docs/142,
+0,23) e embedding aprendido (este documento, −1,96). Não deve ser retomada sem
uma razão nova e específica — mais uma variação sobre os mesmos dois sinais nos
mesmos 335 casos não é razão.

---

## 7. O que isto não diz

- Não diz que T2/DWI é clinicamente irrelevante. Diz que, **nesta
  representação, nesta coorte e para este endpoint**, ele não adiciona sobre a
  dinâmica.
- Não diz nada sobre o endpoint binário (HCC contra benignos). O teste foi
  sobre subtipo de 4 classes.
- ROI de ground truth é **teto, não desempenho**. O efetivo exige multiplicar
  pelo recall do localizador (~80%, docs/141). Nenhum número aqui é desempenho
  de sistema.
- Máscara de lesão usada **apenas** para definir o recorte, na avaliação, nunca
  como entrada do modelo e nunca em inferência.

---

## 8. O que continua valendo como próximo passo

O diagnóstico convergente de quatro linhas independentes (docs/121, 131, 161,
182+184) permanece intocado por este resultado: **o gargalo do projeto é
heterogeneidade de domínio entre instituições, não discriminação entre lesões.**
Este piloto é a quinta confirmação por um quinto caminho — desta vez mostrando
que nem uma modalidade adicional no local espacial correto move o teto.

A recomendação segue sendo a coorte real adicional, de instituição distinta,
com rótulo fino de subtipo ([docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md)).

`research_only: true` · `clinical_use_allowed: false`
