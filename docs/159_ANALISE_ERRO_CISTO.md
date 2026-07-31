# O maior modo de erro do ARGOS não tem explicação física

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/analise_cisto_v1/`

---

## 1. O alvo

O cisto hepático simples é o maior modo de erro isolado do sistema: **36% são
chamados de positivo** (64,15% de acerto como negativo, a pior classe do endpoint
binário). É também, fisicamente, a lesão mais fácil de distinguir — é líquido,
logo não realça em fase nenhuma.

Dos 53 cistos: **17 chamados POSITIVO**, 34 corretos, 2 falhas técnicas.

Três hipóteses pré-especificadas, com ações diferentes:

- **H1 — confiança marginal:** os erros estão logo acima do limiar.
- **H2 — cisto atípico:** os errados são fisicamente diferentes dos acertados.
- **H3 — o painel não mostra:** são iguais, e o problema é a representação.

---

## 2. H1 — refutada

| Margem acima do limiar | |
|---|---:|
| mínima | +0,019 |
| **mediana** | **+0,194** |
| máxima | +0,481 |
| dentro de 0,05 do limiar | **3 de 17** |

O sistema não está hesitando: está **confiantemente errado** em 14 dos 17.
Recalibrar não resolve — coerente com docs/134, que já mostrou teto de calibração
de 75,16/74,72 no LLD.

> Nota: o script imprimiu "possível" para H1 porque minha condição de veredito
> exigia maioria acima de 0,20. Os números refutam mais do que o rótulo indicava;
> vale o número.

---

## 3. H2 — refutada

Propriedades da lesão, medidas na máscara de ground truth (uso diagnóstico
apenas):

| Propriedade | FP mediana | Corretos mediana | p |
|---|---:|---:|---:|
| volume (mL) | 1,727 | 2,470 | 0,617 |
| nº de lesões | 1,000 | 1,000 | 1,000 |
| razão de sinal arterial | 0,667 | 0,821 | 0,069 |
| razão de sinal venosa | 0,580 | 0,687 | 0,484 |
| razão de sinal tardia | 0,642 | 0,714 | 0,299 |
| realce arterial→venosa | −0,103 | −0,122 | 0,058 |
| realce venosa→tardia | 0,036 | 0,031 | 0,968 |
| amplitude de realce | 0,106 | 0,138 | 0,201 |
| heterogeneidade | 0,413 | 0,377 | 0,472 |

**Nenhuma separa.** Os dois mais próximos indicam que os falsos positivos são
levemente mais escuros na arterial, mas com n=17 é indício, não achado.

---

## 4. Exploratório — nem o contexto separa

Um fato de docs/156 apertou o diagnóstico: a fusão com recorte, que **amplia a
lesão**, piorou o cisto de 38 para 32 acertos. Se ampliar piora e a lesão não
separa, o sinal poderia estar no parênquima ao redor.

Medido o fígado **excluindo** a lesão — volume, coeficiente de variação e razão
p95/p50 nas três fases, realce do parênquima:

**Nenhuma propriedade separa** (p entre 0,162 e 0,984).

Esta análise é **pós-hoc** e serviria apenas para gerar hipótese. Não gerou.

---

## 5. Conclusão

> **Os 17 cistos que o sistema erra são indistinguíveis dos 34 que acerta — na
> lesão e no parênquima — e o erro é confiante, não marginal.**

Isso fecha uma família inteira de abordagens: **não existe regra baseada em física
da lesão que corrija este modo de erro**, porque não há sinal físico separando os
dois grupos. E explica retrospectivamente por que docs/136–137 falharam ao injetar
realce relativo como feature — não havia o que injetar.

O erro está na representação. E as duas mudanças de representação já testadas
pioraram o cisto:

| | Cisto correto |
|---|---:|
| Recorte apenas | 38/53 |
| Fusão (docs/156) | 32/53 |

---

## 6. Limitações

- **n=17 contra 34** é pouco poder. Um efeito real mas modesto passaria
  despercebido.
- Os descritores são **estatísticas de intensidade**. Textura e forma não foram
  medidas, e são exatamente o tipo de coisa que o MedSigLIP pode codificar sem
  correspondência nos meus descritores.
- As medidas usam a **máscara de ground truth**, ou seja, o melhor caso possível.
  Se nem ali há separação, com ROI predita haveria menos ainda.

---

## 7. O que isto muda na fila

**Remove** da fila: regra de rejeição de cisto por realce, feature de
não-enhancement, ajuste de limiar dirigido a cisto.

**Mantém**: o déficit de especificidade do cisto é real, custa ~19 casos no LLD, e
depende de uma representação melhor — não de uma regra. Sem hipótese testável no
momento.

Reforça a leitura de [docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md): a coorte com
100 negativos é o que permitiria estudar este modo de erro com poder estatístico
suficiente para concluir algo.

`clinical_use_allowed` permanece `false`.
