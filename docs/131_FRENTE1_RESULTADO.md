# Frente 1 — Resultado: a representação não carrega subtipo, e nenhum substrato atual é invariante a domínio

**Data:** 29 de julho de 2026
**Pré-especificação:** [docs/130](130_FRENTE1_ZEROSHOT_E_SONDA_DE_DOMINIO.md), commitada em
`636d3f0` **antes** de qualquer número
**Artefatos:** `casos/qualification/hybrid_v1/frente1_zeroshot_v1/`

---

## 1. Conclusão

Dois resultados, e o segundo **refuta uma recomendação que eu mesmo havia feito**.

**H2 confirmada.** O embedding MedSigLIP dos painéis multifásicos não carrega subtipo de
forma recuperável por linguagem: o zero-shot atinge 27,55% de acurácia balanceada contra
acaso de 25% e supervisão de 52,18%. O conserto barato (regularização de domínio sobre a
representação atual) está descartado.

**A sonda de domínio reprovou tudo.** Eu havia proposto o radiomics multifásico como
substrato mais invariante, por ser "medida física". **Está errado.** A coorte é previsível
a partir das features físicas com **98,75%** de acurácia balanceada — praticamente o mesmo
que os embeddings, em **100,00%**. Nenhum dos dois substratos chega perto do critério de
70%.

---

## 2. Validade: o controle de sanidade passou

Sem ele nada abaixo seria interpretável. Nossos painéis são três fases fundidas em RGB, um
composto sintético, e havia risco real de a torre de texto simplesmente não operar sobre
eles.

| Escolha entre 4 descrições grosseiras | Resultado |
|---|---|
| `"an abdominal MRI of the liver"` | **451/451 (100,00%)** IC95 [99,2 – 100,0] |
| `"a chest radiograph"` / `"a brain MRI"` / `"a photograph of a dog"` | 0 |

Critério era ≥ 90%. **Aprovado com folga.** A torre de texto funciona sobre os painéis;
portanto o fracasso no subtipo é sobre subtipo, não sobre entrada fora de distribuição.

---

## 3. Zero-shot de subtipo: 27,55%

**n = 321 · acaso = 25,0% · balanceada = 27,55% · top-1 = 17,13%**

| verdade \ predito | fnh | hcc | hemangioma | hepatic_cyst | recall |
|---|---:|---:|---:|---:|---:|
| **fnh** | **9** | 0 | 0 | 36 | 20,00% |
| **hcc** | 15 | **0** | 0 | 137 | 0,00% |
| **hemangioma** | 14 | 0 | **0** | 59 | 0,00% |
| **hepatic_cyst** | 5 | 0 | 0 | **46** | 90,20% |

### O recall de 90% do cisto é uma armadilha, não um achado

À primeira vista `hepatic_cyst` com 90,20% parece o resultado que buscávamos. Não é. O
classificador **colapsou**: prediz `hepatic_cyst` em 86,6% de todos os casos e **nunca**
prediz `hcc` ou `hemangioma`.

| Classe | Predita em | Precisão | Prevalência | Ganho sobre prevalência |
|---|---:|---:|---:|---:|
| `hepatic_cyst` | 86,6% | 16,5% | 15,9% | **+0,7 pts** |
| `fnh` | 13,4% | 20,9% | 14,0% | +6,9 pts |
| `hcc` | 0,0% | — | 47,4% | — |
| `hemangioma` | 0,0% | — | 22,7% | — |

Um preditor constante que sempre dissesse "cisto" teria recall de 100% nessa classe e
acurácia balanceada de 25,00%. O zero-shot obteve 90,20% e 27,55%. **A precisão do cisto
supera sua prevalência em 0,7 ponto** — ou seja, o acerto é o que se espera de um chute
degenerado, não de detecção.

Se este número fosse reportado como "o modelo identifica cistos com 90% de sensibilidade",
seria uma afirmação falsa construída a partir de um artefato.

---

## 4. Sonda de invariância de domínio: o resultado mais importante

Prever **a coorte** (LLD-MMRI vs OpenSwissHCC) a partir das features, pelos mesmos outer
folds congelados, acurácia balanceada porque as classes são 321 vs 130.

| Substrato | Recall LLD | Recall OpenSwiss | Balanceada | Critério < 70% |
|---|---:|---:|---:|:--|
| Embeddings MedSigLIP (1152-d) | 100,00% | 100,00% | **100,00%** | REPROVADO |
| Radiomics multifásico (145 features) | 99,07% | 98,43% | **98,75%** | REPROVADO |

### Por que a minha hipótese sobre radiomics estava errada

Eu tratei "feature física" como sinônimo de "invariante a domínio". São coisas diferentes.

As 145 features são estatísticas de **fígado inteiro** em valor absoluto: momentos de
distribuição, entropia de 32 bins, magnitude de gradiente, frações acima de limiares de
z robusto. Todas essas quantidades são dominadas por **parâmetros de aquisição** — vendor
do scanner, intensidade de campo, resolução, ruído, reconstrução. Dois hospitais produzem
assinaturas de textura diferentes mesmo fotografando a mesma anatomia. É isso que a sonda
enxerga, e ela enxerga quase perfeitamente.

**A lição de projeto:** invariância a domínio não vem de a feature ser "física". Vem de a
feature ser uma **razão contra uma referência interna à própria imagem**. Realce medido
como `(sinal_da_lesão − sinal_do_parênquima) / sinal_do_parênquima`, dentro da mesma
aquisição, cancela o ganho do scanner por construção. Uma estatística de textura absoluta
não cancela nada.

Nenhuma feature do conjunto atual é construída assim.

---

## 5. Consequências

1. **Frente 1 encerrada.** Não há conserto barato. A regularização de domínio sobre a
   representação atual está descartada, porque a informação não está lá para ser
   resgatada.
2. **A sonda de domínio vira critério obrigatório e é dura.** Nada do que temos hoje passa
   dela. Isso precisa ser sabido *antes* de investir semanas numa frente, não depois.
3. **O requisito de desenho mudou.** Qualquer feature nova para subtipo deve ser razão
   contra referência interna (parênquima, baço ou aorta na mesma aquisição). Intensidade
   absoluta e textura global estão proibidas como entrada, porque a sonda já provou o que
   elas carregam.
4. **`hepatic_cyst` continua sendo o alvo certo** para o primeiro ganho — mas pelo motivo
   correto: cisto tem a assinatura física mais separável que existe (não realça em
   nenhuma fase, é marcadamente hiperintenso em T2, não restringe difusão), e nós
   simplesmente não damos ao modelo nenhuma das três medidas.

---

## 6. Próximo passo recomendado

A Frente 2 (ingerir `C-pre`, `T2WI` e `DWI`, que estão em disco para as 335 casos LLD)
continua sendo o caminho de maior ganho, agora com uma exigência adicional vinda deste
resultado: **as features derivadas dessas sequências devem ser razões internas**, e cada
representação candidata precisa passar pela sonda de domínio antes de qualquer avaliação
de subtipo.

Ordem sugerida:

1. Construir 3 razões internas a partir do que já existe, sem ingerir nada novo, só para
   validar o método da sonda: realce relativo ao parênquima em cada fase pós-contraste.
   Se essas 3 razões já derrubarem a previsibilidade de coorte para perto de 50%, o
   requisito de desenho está confirmado e barato de aplicar.
2. Só então ingerir `C-pre`/`T2WI`/`DWI` e construir o conjunto completo.
3. Avaliar subtipo apenas sobre representações que tenham passado na sonda.
