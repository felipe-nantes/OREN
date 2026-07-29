# Plano para atingir 75% na identificação do subtipo

**Data:** 29 de julho de 2026
**Meta pedida:** o ARGOS deve acertar **qual é a alteração** de cada caso, com 75% de
acerto.

---

## 1. Antes de tudo: duas definições que precisam ficar explícitas

### 1.1 O que conta como "75% de acerto"

A escolha muda materialmente o tamanho do trabalho, porque as classes são desbalanceadas
(HCC é 47% dos casos com subtipo):

| Definição | Valor hoje | Comentário |
|---|---:|---|
| Top-1 bruta | 59,50% | Inflada pela prevalência do HCC — um modelo que só dissesse "HCC" acertaria 47% |
| **Acurácia balanceada** (média do recall por classe) | **52,18%** | Não é gameável por prevalência |
| Recall ≥ 75% em **toda** classe | falha em 3 de 4 | O mais duro |

**Este plano adota acurácia balanceada ≥ 75%, com piso de 60% por classe**, porque é o
análogo consistente da meta binária do projeto: 75/75 é sensibilidade **e** especificidade
justamente para não ser satisfeita por prevalência. Se a intenção era a top-1 bruta, o alvo
fica bem mais perto e o plano encurta — mas é uma meta mais fraca do que parece.

### 1.2 "Qual é a alteração" — o que os rótulos permitem

Entre os casos **positivos** só existe uma alteração nomeada: **HCC**. Os outros 63
positivos são `positive_unspecified` (OpenSwiss, que não declara subtipo). As outras três
classes — hemangioma, cisto, FNH — são **negativas** no endpoint binário.

Então a tarefa realizável é de **4 classes**, cobrindo as duas polaridades:

| Classe | n | Polaridade | Recall hoje |
|---|---:|---|---:|
| `hcc` | 157 | POSITIVO | 76,32% |
| `hemangioma` | 79 | negativo | 47,95% |
| `hepatic_cyst` | 53 | negativo | 33,33% |
| `fnh` | 46 | negativo | 51,11% |

Todas as 335 vêm de **uma única coorte** (`lld_mmri`). Isso cria dois marcos distintos, e
misturá-los seria repetir o problema de enquadramento do último benchmark:

- **Marco 1 — 75% medido OOF dentro do LLD.** Alcançável internamente. É o que este plano
  entrega.
- **Marco 2 — 75% que transfere para um hospital novo.** **Não é alcançável internamente.**
  Enquanto os subtipos existirem em uma coorte só, nenhum experimento distingue "aprendeu a
  doença" de "reconheceu o hospital" — a sonda de domínio já mediu coorte previsível a
  100% (docs/131).

---

## 2. O que já está eliminado por evidência

| Caminho | Resultado | Doc |
|---|---|---|
| Cabeça supervisionada atual, 4 classes | 52,18% balanceada | 129 |
| Zero-shot MedSigLIP (torre de texto) | 27,55% (acaso 25%) | 131 |
| Radiomics de fígado inteiro como substrato | coorte previsível a 98,75% | 131 |
| Zero-shot MedGemma 4B nos painéis RGB | 99,69% de abstenção | 133 |
| Localizador `liver_lesions_mr` venoso | recall 56,76% | 93 |

Nenhuma rota barata sobrou. O caminho restante é dar ao modelo a informação que hoje não
recebe.

---

## 3. O diagnóstico: mostramos 3 de 8 sequências

Cada um dos 335 casos tem **8 sequências em disco** e o pipeline usa 3
(`C+A`, `C+V`, `C+Delay`). As descartadas são exatamente as que definem clinicamente as
classes em que falhamos:

| Sequência | Estado | Por que importa |
|---|---|---|
| `C-pre` | **não usada** | Realce = pós − pré. Sem pré-contraste, "esta lesão realça?" é inrespondível. Hoje só comparamos fases pós entre si, e nesse espaço um cisto (não realça) e uma FNH (virou isointensa) parecem igualmente planos |
| `T2WI` | **não usada** | Cisto é marcadamente hiperintenso ("sinal da lâmpada"). É o discriminador clássico cisto × hemangioma |
| `DWI` | **não usada** | Cisto não restringe difusão; lesão sólida restringe. Separa cístico de sólido |
| `InPhase` / `OutPhase` | **não usadas** | Dixon; quantificação de gordura. Relevante para adenoma/esteatose focal |

**Base para otimismo, distinta de otimismo:** um radiologista com `C-pre` + dinâmica T1 +
`T2WI` distingue cisto simples com acurácia próxima de 100% — a lesão é praticamente
inconfundível. A informação **está** na aquisição. Não estamos pedindo ao modelo algo que a
imagem não contém; estamos escondendo dele a imagem que contém.

O que os 75% exigem por classe:

| Classe | Hoje | Falta | Caminho físico |
|---|---:|---:|---|
| `hcc` | 76,32% | já passa | manter |
| `fnh` | 51,11% | +24 pts | realce arterial homogêneo → isointenso, cicatriz central |
| `hemangioma` | 47,95% | +27 pts | realce nodular periférico → preenchimento centrípeto |
| `hepatic_cyst` | 33,33% | **+42 pts** | ausência de realce + T2 muito hiperintenso |

O cisto é o maior déficit **e** o de assinatura mais separável. É onde o ganho começa.

---

## 4. Plano em quatro etapas, com gate em cada uma

### Etapa 1 — Ingerir `C-pre`, `T2WI` e `DWI` mantendo painéis de fígado inteiro
**Custo:** dias · GPU para re-renderizar e re-embutir os 335 casos

A mudança mais barata que ataca o maior déficit. Não exige localização de lesão.

Trabalho:
- estender `multiphase_ingest` para carregar os três papéis novos, harmonizados na grade
  venosa que já usamos (a infraestrutura de harmonização existe:
  `lld_mmri_v23_harmonization.py`)
- decidir a representação: o painel atual é `multiphase_rgb_fusion`, com os 3 canais RGB
  ocupados pelas 3 fases. Duas opções, a testar como ablação:
  **(a)** um segundo conjunto de painéis com `(C-pre, T2WI, DWI)` → 6 painéis por caso;
  **(b)** um canal de **realce verdadeiro** (`pós − pré`) substituindo um canal atual
- re-embutir com o MedSigLIP congelado e retreinar a cabeça multiclasse nos mesmos splits

**Gate 1:** balanceada ≥ **62%** (de 52,18%, ou seja +10 pts) **e** recall do cisto ≥ 55%
(de 33,33%). Se o cisto não subir com `T2WI` disponível, a hipótese física está errada e o
plano precisa ser revisto antes de gastar a Etapa 2.

### Etapa 2 — Assinatura de realce **por lesão**, com referência interna
**Custo:** semanas · o núcleo técnico

Hemangioma × FNH não se resolve com estatística de fígado inteiro: a diferença é o
**padrão espacial-temporal dentro da lesão** (periférico nodular com preenchimento
centrípeto vs homogêneo que vira isointenso). Isso exige ROI.

O localizador `liver_lesions_mr` trava em 56,76% de recall e a união arterial foi
descartada por ruído. O próprio docs/93 apontou o próximo passo, nunca executado:
*propostas determinísticas de realce sobre todo o fígado*. Com `C-pre` disponível essa
proposta passa a ser bem-posta — candidatos são voxels onde `pós − pré` desvia do
parênquima.

Descritores por candidato, **todos como razão contra referência interna** (exigência herdada
de docs/131, onde features físicas absolutas reprovaram na sonda de domínio a 98,75%):
- amplitude de realce relativa ao parênquima, por fase
- washout (`arterial − tardia`) e preenchimento (`tardia − arterial`)
- perifericidade do realce (anel nodular vs homogêneo)
- razão T2 lesão/parênquima e razão de difusão

**Gate 2:** balanceada ≥ **75%**, piso de 60% por classe, **e** a sonda de domínio abaixo
de 70% sobre os novos descritores.

### Etapa 3 — Camada de decisão fisiológica antes do classificador
**Custo:** dias · depende da Etapa 2

Os casos clinicamente inequívocos não deveriam depender de aprendizado estatístico:
amplitude de realce ≈ 0 em todas as fases + T2 muito alto → cisto. Uma camada de regras
sobre os descritores da Etapa 2 resolve esses, e o classificador fica só com o resíduo
ambíguo. Ganho esperado em cisto e em interpretabilidade — cada decisão passa a ter
justificativa física citável, o que importa num contexto de revisão médica obrigatória.

### Etapa 4 — Segunda coorte com subtipo anotado
**Custo:** meses · aquisição · **INICIAR EM PARALELO JÁ**

Necessária para o Marco 2 e para poder estatístico. Hoje `fnh` tem n=46 e `hepatic_cyst`
n=53: mesmo alcançando 75% de recall, o IC95 Wilson em n=46 fica em torno de
[61 – 85] — o ponto é atingível, a **demonstração** não. E sem segunda coorte a
transferência para hospital novo permanece indemonstrável por construção.

---

## 5. Sequenciamento

```
agora        Etapa 1  (dias, GPU)      ─→ gate 62% / cisto 55%
                                          │ falhou → revisar hipótese física
                                          ▼
depois       Etapa 2  (semanas)        ─→ gate 75% + sonda de domínio < 70%
                                          ▼
depois       Etapa 3  (dias)           ─→ robustez e interpretabilidade
em paralelo  Etapa 4  (meses, aquisição) ─→ sem isso, só o Marco 1 existe
```

---

## 6. Avaliação obrigatória

- **Nested-OOF nos splits congelados**, agrupado por paciente. O número do subtipo **não**
  pode sair do benchmark in-sample: o último benchmark deu 87,76% no endpoint binário
  justamente porque 86 de 100 casos estavam no treino e o endpoint favorável foi usado
  (docs/127). Repetir esse enquadramento no subtipo seria autoengano.
- **Pré-especificação antes de cada etapa**, com gate fixado antes de ver número, como em
  docs/128, 130 e 132. Nenhum gate ajustado depois.
- **Precisão contra prevalência** reportada por classe, não só recall — foi o teste que
  desmontou o falso "90% de recall no cisto" em docs/131, que era colapso degenerado.
- **Sonda de invariância de domínio** em toda representação nova, antes da avaliação de
  endpoint.
- `clinical_use_allowed` permanece `false`; nada de subtipo é exposto na UI até um gate
  passar.

---

## 7. Avaliação honesta de viabilidade

| Classe | 75% é plausível? | Por quê |
|---|---|---|
| `hcc` | sim, já está | 76,32% hoje |
| `hepatic_cyst` | **sim, alta confiança** | Assinatura quase inconfundível com `C-pre` + `T2WI`; hoje falha por falta de dado, não por dificuldade |
| `hemangioma` | plausível | Preenchimento centrípeto é característico, mas exige ROI (Etapa 2) |
| `fnh` | **o mais incerto** | n=46, e a distinção contra hemangioma é a mais fina das quatro |

**Balanceada de 75% é uma meta defensável**, com o risco concentrado na FNH. Se a FNH
travar em ~60%, a balanceada fica em torno de 72–73% — e nesse cenário a decisão honesta
seria reportar por classe e declarar a FNH fora de alcance com os dados atuais, em vez de
inflar o agregado.
