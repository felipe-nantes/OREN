# Segunda coorte — o que falta e para que será usado

**Data:** 31 de julho de 2026
**Finalidade:** documento de apresentação a parceiro clínico. Todos os números
citados são medidos, com origem no repositório.

---

## 1. O que o sistema faz hoje

Triagem de lesão hepática focal em RM multifásica: dado um exame, responde se há
alteração e, quando há, qual das quatro entidades (FNH, HCC, hemangioma, cisto).

Estado atual, validação cruzada aninhada em 467 exames de duas coortes públicas:

| | Sensibilidade | Especificidade |
|---|---:|---:|
| Agregado | 75,91% | 76,11% |
| `LLD-MMRI` (n=335) | 73,25% | 76,97% |
| `OpenSwissHCC` desenvolvimento (n=88) | 82,05% | 77,55% |
| `OpenSwissHCC` holdout (n=44) | 83,33% | **65,00%** |

Classificação do subtipo: **61,46%** de acurácia balanceada em 4 classes.

Não é desempenho clínico — é validação cruzada em dados de desenvolvimento, com
prevalência artificial. Nada está aprovado para uso.

---

## 2. As três lacunas

### 2.1 Negativos — a mais crítica

O holdout tem **20 exames sem lesão**. Com esse denominador, cada caso vale 5
pontos percentuais e o intervalo de confiança da especificidade tem **38 pontos
de largura**. Não é possível afirmar nada sobre taxa de falso positivo com essa
amostra.

O problema é concreto: o pior alvo do sistema é o **cisto hepático simples**, que
é chamado de positivo em **36%** dos casos. Numa triagem real isso encaminharia
um terço dos cistos para investigação desnecessária. Para medir e corrigir isso é
preciso ter negativos em quantidade.

**Necessário: ~100 exames de fígado sem lesão focal.**

### 2.2 FNH — teto atingido

A hiperplasia nodular focal tem **46 casos**, e essa é a totalidade disponível na
fonte pública utilizada. É a pior classe do sistema em todas as métricas: **52,2%**
de acerto na identificação de subtipo, contra 65% do HCC.

FNH importa clinicamente porque é benigna e não exige intervenção — confundi-la
com HCC gera investigação invasiva desnecessária; o inverso atrasa diagnóstico de
câncer.

Não há como melhorar essa classe com os dados atuais. É um limite de quantidade,
não de método.

**Necessário: ~50 exames com FNH confirmada.**

### 2.3 Origem institucional — confundimento não resolvido

Um classificador treinado para adivinhar **de qual coorte** um exame veio acerta
**100%** das vezes. Isso significa que as duas coortes têm assinatura técnica
distinguível — protocolo de aquisição, scanner, parâmetros — e não é possível
separar o que o sistema aprendeu sobre *doença* do que aprendeu sobre *origem do
exame*.

Uma terceira coorte da mesma origem não resolve. É preciso instituição e
equipamento diferentes.

**Necessário: serviço distinto dos dois já utilizados.**

---

## 3. O que é pedido

Exames **retrospectivos**, já realizados, **anonimizados na origem**.

### Obrigatório por exame

| Item | Especificação |
|---|---|
| Sequências | T1 dinâmico pós-contraste: **arterial, portal/venosa e tardia** |
| Formato | DICOM ou NIfTI |
| Corte | ≤ 5 mm |
| Campo | 1,5 T ou 3,0 T |
| Rótulo | conclusão diagnóstica do laudo |

As três fases dinâmicas são obrigatórias: todo o processamento depende de
compará-las entre si. Exame com apenas uma fase não é utilizável.

### Desejável, não obrigatório

- T2 e difusão, quando existirem no protocolo
- Contorno da lesão marcado por radiologista (permite medir o limite superior do
  componente de localização; sem ele essa análise não é possível)

### Composição alvo

| Categoria | Quantidade |
|---|---:|
| Sem lesão focal | 100 |
| FNH | 50 |
| Hemangioma | 60 |
| Cisto simples | 60 |
| CHC | 60 |
| **Total** | **~330** |

**Se a FNH disponível for menor que 50, convém saber antes de qualquer outra
etapa** — é a lacuna que determina a utilidade da coorte.

---

## 4. Para que será usado

1. **Medir generalização.** Aplicar o sistema, sem retreinar, a exames de origem
   nunca vista. É o único teste que distingue aprendizado real de memorização de
   protocolo de aquisição.

2. **Estabelecer a taxa de falso positivo.** Com ~100 negativos, o intervalo de
   confiança da especificidade cai de 38 para cerca de 16 pontos. Só então é
   possível afirmar algo sobre encaminhamento desnecessário.

3. **Corrigir a classe FNH.** Dobrar a amostra é a única via disponível; as
   alternativas metodológicas foram testadas e reprovadas.

4. **Publicação.** Validação externa multi-institucional é o requisito mínimo
   para submissão em periódico de imagem, e é a etapa que hoje falta.

---

## 5. O que não será feito

- Não haverá contato com pacientes.
- Não serão solicitados dados identificáveis: nome, registro, data de nascimento,
  ou identificadores DICOM de origem. A anonimização ocorre **dentro** da
  instituição, antes da transferência.
- Não haverá uso assistencial. O sistema é de pesquisa; nenhum resultado retorna
  ao prontuário ou influencia conduta.
- Não haverá uso comercial sem acordo específico à parte.
- Não haverá tentativa de reidentificação, sob nenhuma hipótese.

---

## 6. O que é oferecido ao parceiro

- Coautoria nas publicações resultantes.
- Especificação técnica, script de anonimização e suporte à extração, fornecidos
  por nós e executados dentro da instituição.
- Redação da seção metodológica do protocolo de CEP.
- Resultados por coorte compartilhados integralmente, incluindo os desfavoráveis.

---

## 7. Etapas e prazos

| Etapa | Responsável | Prazo |
|---|---|---|
| Contagem de casos elegíveis no PACS | parceiro | 1–2 dias |
| Aprovação no CEP | parceiro, com nosso apoio | 2–4 meses |
| Extração e anonimização | parceiro, com nosso script | 2–4 semanas |
| Rotulagem — 2 leitores e adjudicação | parceiro | ~25 h de radiologista |
| Ingestão e auditoria | nós | 1–2 semanas |

**A primeira etapa é apenas uma consulta ao sistema de laudos e não caracteriza
pesquisa.** Ela define se a colaboração é viável, e por isso deve vir antes de
qualquer submissão.

`research_only: true` · `clinical_use_allowed: false`
