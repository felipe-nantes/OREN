# A coorte sintética não carrega nem o sinal de presença de lesão

**Data:** 1 de agosto de 2026
**Artefatos:** `experiments/sinal_no_sintetico_v1/`
**Fecha** a ambiguidade de [docs/162](162_QUATRO_CLASSES_SINTETICO.md)

---

## 1. A pergunta

docs/162 deixou três explicações para o desempenho no acaso do ARGOS sobre a
coorte sintética, sem conseguir separá-las. A terceira, e mais parcimoniosa: **a
síntese transfere ~8 escalares por lesão e não a arquitetura interna onde o
subtipo mora.**

Teste direto: se o sinal não está nas imagens, um modelo treinado **na própria
coorte sintética** também não vai separá-las.

Validação cruzada agrupada respeitando **as duas** dependências declaradas —
`donor_dependency_group` e `background_dependency_group` — unidas por *union-find*,
para que casos que compartilhem doador ou fundo caiam sempre no mesmo fold. 330
casos → 184 grupos.

---

## 2. Resultado

| Tarefa | Balanceada | Acaso |
|---|---:|---:|
| **Controle: lesão × sem-lesão** | **55,22%** | 50% |
| Alvo: 4 subtipos | **25,75%** | 25% |

O subtipo está exatamente no acaso. Mas o que decide é o **controle**: um modelo
treinado na própria coorte sintética mal distingue *tem lesão* de *não tem*
(recall 70,4% para com-lesão, 40,0% para sem-lesão).

---

## 3. Correção de uma regra que eu havia pré-especificado

Minha leitura pré-especificada dizia: *"se o controle falhar, o problema está no
meu pipeline de embedding e nada é interpretável."*

Segui a regra e verifiquei. **O pipeline está correto:** embutindo painéis reais do
LLD pelo meu caminho e comparando ao cache oficial —

| Caso | Δ máximo | Cosseno |
|---|---:|---:|
| `anon-lld-00878b6b34f0cdb4` | 6,74e-04 | 0,999996 |
| `anon-lld-00bc3cd8154e9bb6` | 3,38e-04 | 0,999998 |
| `anon-lld-0164881aa6759a00` | 5,03e-04 | 0,999997 |

Verificado o pipeline, a regra fica sem antecedente e **a conclusão se inverte**:
a falha do controle não é minha, é da coorte. Registro que a regra estava mal
calibrada — ela assumia que só havia uma causa possível para o controle falhar.

---

## 4. Conclusão

> **As lesões sintéticas são quase invisíveis no nível de representação em que o
> ARGOS opera.** Não é que falte informação de *subtipo*: falta informação de
> *presença*.

Isso confirma a explicação 3 de docs/162 numa forma mais forte do que eu havia
formulado, e encerra a ambiguidade: a coorte sintética **não pode dizer nada**
sobre a capacidade de subtipo do ARGOS — nem a favor nem contra. O desempenho no
acaso observado em docs/162 é o esperado para imagens onde o alvo não está
representado.

### Um mecanismo plausível, e uma questão que ele levanta

O volume mediano das lesões doadoras é de ~2–3 mL. Nos painéis de fígado inteiro,
renderizados em campo completo e reduzidos a 448 px, uma lesão desse tamanho ocupa
pouquíssimos pixels.

Isso vale igualmente para os painéis reais do LLD — onde o sistema atinge 73,25%
de sensibilidade. A diferença entre os dois casos merece registro:

> Nos fundos sintéticos, saudáveis por construção, não existem correlatos de
> contexto — parênquima cirrótico, alterações difusas. Nos reais, existem.

Isso é **hipótese, não achado**, e é coerente com [docs/159](159_ANALISE_ERRO_CISTO.md),
onde os erros de cisto não se explicaram por propriedades da lesão. Testá-la
exigiria dados que não temos.

---

## 5. O que muda na prática

**Encerrado:** qualquer uso da coorte sintética para questões sobre capacidade de
subtipo, incluindo o aumento de treino previsto em
[docs/160](160_PLANO_COORTE_SINTETICA.md) §7. O gate primário daquele plano não
tem chance de passar, e treinar nessas lesões ensinaria a associar rótulo a
tamanho e contraste.

**Mantido:** o uso declarado na documentação da própria coorte — estresse de
ingestão multifásica, geometria, robustez de execução, comportamento fora de
distribuição. Os 330/330 sem falha técnica continuam sendo informação útil.

**Intocado:** [docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md). Aquele achado —
99,32% da massa nas 4 classes no LLD real contra 1,43% no OpenSwiss real — é
medido em **dados reais** e não depende em nada da coorte sintética.

**Reforçado:** a coorte real de outra instituição, com rótulo fino de subtipo,
continua sendo a única via. [docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md)
permanece a especificação válida.

---

## 6. Limitação

O controle a 55,22% pode refletir tanto "a lesão sintética é sutil demais" quanto
"os painéis de fígado inteiro têm resolução insuficiente para lesões de 2 mL". Não
os separei. A conclusão operacional é a mesma nos dois casos, mas a causa não está
estabelecida.

`construction_labels_only: true` · `clinical_ground_truth: false` ·
`specificity_estimation_allowed: false` · `clinical_use_allowed: false`
