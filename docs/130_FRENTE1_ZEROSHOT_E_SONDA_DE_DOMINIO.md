# Frente 1 — Zero-shot de subtipo e sonda de invariância de domínio (pré-especificação)

**Data:** 29 de julho de 2026
**Status ao escrever:** nenhum resultado calculado.
**Antecedente:** [docs/129](129_FASE1_SUBTIPO_RESULTADO.md) — a cabeça supervisionada
atinge 52,18% de acurácia balanceada em 4 subtipos dentro do LLD, enquanto separa coorte
a 99,78%.

---

## 1. A pergunta que esta frente responde

Depois do resultado da Fase 1, há duas explicações concorrentes, e elas levam a
investimentos muito diferentes:

| Hipótese | Se for verdade | Custo do conserto |
|---|---|---|
| **H1 — Informação presente, atenção sequestrada.** O subtipo está codificado no embedding, mas a cabeça supervisionada aprende domínio porque é o atalho de menor perda. | Regularização de domínio, reponderação, adversarial debiasing | Baixo |
| **H2 — Informação ausente.** O embedding de painel multifásico simplesmente não carrega o que distingue cisto de hemangioma. | Novas sequências (`C-pre`, `T2WI`, `DWI`) e/ou features de realce por lesão | Alto |

Um classificador supervisionado **não consegue separar as duas**, porque qualquer resultado
seu já vem contaminado pelo mesmo atalho. Por isso a sonda tem de ser **zero-shot**: sem
nenhum treino nos nossos rótulos, não há como o resultado vir de reconhecer a coorte.

---

## 2. O ativo que torna isso quase gratuito

O MedSigLIP é carregado com `AutoModel`, que instancia o `SiglipModel` **inteiro** — as
duas torres. O pipeline chama apenas `get_image_features`
([medsiglip_embeddings.py:119](../dtwin/learning/medsiglip_embeddings.py)). Verificado:

- `get_text_features` disponível, `SiglipTokenizer` presente
- dimensão do texto = **1152**, idêntica à dos embeddings de imagem
- os **1339 embeddings de imagem já estão em cache** e L2-normalizados

Ou seja: falta apenas embutir texto e calcular cosseno. Nenhuma GPU-hora de imagem,
nenhum retreino.

---

## 3. Os três experimentos

### 3A — Controle de sanidade (bloqueante)

**Sem este controle, os outros dois são ininterpretáveis.** Nossos painéis são
`multiphase_rgb_fusion`: três fases temporais fundidas nos canais R, G e B. Isso **não é
uma imagem radiológica natural** — é um composto sintético. O alinhamento imagem-texto do
MedSigLIP foi treinado em imagens reais.

Se a torre de texto não conseguir nem uma tarefa trivial sobre esses painéis, um fracasso
no subtipo seria ambíguo: falta de informação ou entrada fora de distribuição?

**Tarefa:** escolher entre descrições grosseiramente distintas —
`"an abdominal MRI of the liver"` contra `"a chest radiograph"`, `"a brain MRI"` e
`"a photograph of a dog"`.

**Critério de aprovação:** a descrição correta escolhida em **≥ 90%** dos casos.
Se reprovar, 3B é declarado **inconclusivo** e a decisão vai direto para as Frentes 2 e 3.

### 3B — Zero-shot de subtipo

Quatro classes (`hcc`, `hemangioma`, `hepatic_cyst`, `fnh`), apenas casos LLD, onde a
coorte é constante — mesmo recorte do gate primário de docs/128, para ser diretamente
comparável.

**Prompts pré-registrados** (ensemble de 4 por classe, média dos embeddings de texto).
Fixados agora para que não possam ser ajustados depois de ver o resultado:

- **hepatic_cyst:** `"a simple hepatic cyst"` · `"MRI of the liver showing a simple cyst with no enhancement"` · `"well-defined non-enhancing fluid-filled liver lesion"` · `"benign hepatic cyst"`
- **hemangioma:** `"a hepatic hemangioma"` · `"MRI of the liver showing a hemangioma with peripheral nodular enhancement"` · `"benign vascular liver lesion with progressive centripetal filling"` · `"cavernous hemangioma of the liver"`
- **fnh:** `"focal nodular hyperplasia of the liver"` · `"MRI of the liver showing focal nodular hyperplasia with a central scar"` · `"homogeneously arterially enhancing benign liver lesion"` · `"hepatic focal nodular hyperplasia"`
- **hcc:** `"hepatocellular carcinoma"` · `"MRI of the liver showing hepatocellular carcinoma with arterial hyperenhancement and washout"` · `"malignant primary liver tumor"` · `"HCC in a cirrhotic liver"`

Agregação painel → caso: **média** do cosseno, igual à Fase 1. Decisão por `argmax`
(monotônico, portanto `logit_scale`/`logit_bias` não alteram a escolha).

**Âncora de comparação: 52,18%**, a supervisionada.

| Resultado | Leitura | Consequência |
|---|---|---|
| ZS **≥ 52,18%** | H1 confirmada — a informação está lá e a supervisão a desperdiça | Investir em regularização de domínio (barato) |
| 25% < ZS < 52,18% | Informação parcial; a supervisão ainda é melhor | Frente 2 continua sendo o caminho |
| ZS ≈ 25% **e** 3A aprovado | H2 confirmada — a representação não carrega subtipo | Frentes 2 e 3, sem hesitar |
| ZS ≈ 25% **e** 3A reprovado | Inconclusivo (entrada fora de distribuição) | Nada se conclui sobre H1/H2 aqui |

### 3C — Sonda de invariância de domínio

Treinar um classificador para prever **a coorte** (`lld_mmri` vs `openswisshcc`) a partir
das features, usando os **mesmos outer folds congelados** agrupados por paciente, para não
haver vazamento. Métrica: **acurácia balanceada** — as classes são desbalanceadas
(335 vs 132), então acurácia bruta teria linha de base de 71,7%.

Rodada sobre dois substratos:
1. **Embeddings MedSigLIP** — estabelece o número de referência
2. **Features de radiomics multifásico** (145 features físicas, 448 casos) — responde se
   medida física é um substrato melhor que representação aprendida

**Critério adotado daqui em diante:** nenhuma representação nova entra em produção para
subtipo se a sonda de coorte passar de **70%** de acurácia balanceada. Este vira o segundo
critério de aceitação, ao lado do gate de subtipo.

Esta é a medida que **prevê comportamento em coorte nova sem precisar de coorte nova** —
exatamente o que interessa para os dados cegos futuros.

---

## 4. O que esta frente não faz

- Não altera o modelo de produção, o limiar nem a decisão binária.
- Não expõe subtipo em lugar nenhum — docs/129 permanece valendo.
- Não substitui a necessidade de uma segunda coorte com subtipo anotado; apenas informa
  onde investir enquanto ela não existe.
