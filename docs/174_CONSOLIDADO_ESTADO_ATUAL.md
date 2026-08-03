# Estado consolidado do ARGOS/OREN

**Data:** 3 de agosto de 2026
**Uso:** apresentação e discussão. Pesquisa, revisão humana obrigatória, sem uso clínico.

---

## 1. As duas missões, respondidas

| Missão | Situação |
|---|---|
| **Triagem 75% / 75%** | **Atingida no agregado**: 75,91% sensibilidade / 76,11% especificidade |
| **Identificar a variação em 75%** | **Não atingida.** Melhor medição honesta: 64,81%. O limite é aritmético e está demonstrado. |

---

## 2. Triagem — o que está estabelecido

Validação cruzada aninhada, 467 exames, três coortes.

| | Sensibilidade | Especificidade |
|---|---:|---:|
| **Agregado** | **75,91%** | **76,11%** |
| IC 95% | 69,8 – 81,1 | 70,4 – 81,0 |

AUC 0,853. O gate de 75/75 passa no agregado. **Por coorte, não passa em duas:**

| Coorte | n | Sens | Esp |
|---|---:|---:|---:|
| `lld_mmri` | 335 | **73,25%** | 76,97% |
| `openswisshcc_development` | 88 | 82,05% | 77,55% |
| `openswisshcc_consumed_holdout` | 44 | 83,33% | **65,00%** |

O holdout tem **20 negativos**: cada caso vale 5 pontos de especificidade. Mesmo
se passasse, não estaria estabelecido.

### Onde estão os erros

| Lesão | n | Acerto |
|---|---:|---:|
| HCC *(é o positivo)* | 157 | 73,25% detectado |
| FNH | 46 | 89,13% corretamente negativo |
| Hemangioma | 79 | 78,48% corretamente negativo |
| **Cisto hepático** | 53 | **64,15%** corretamente negativo |

O cisto é o maior modo de erro isolado — 36% chamados de positivo.
[docs/159](159_ANALISE_ERRO_CISTO.md) investigou: os cistos errados são
**indistinguíveis** dos acertados, na lesão e no parênquima, e o erro é confiante,
não marginal. Não há regra física que corrija isso.

---

## 3. Identificação da variação — o número correto

**Existem três números circulando e eles diferem por 44 pontos.** É essencial não
trocá-los numa apresentação.

| Número | O que é | Vale como |
|---|---:|---|
| **96,43%** | 25 casos LLD pelo frontend ([docs/171](171_RESULTADO_BENCHMARK_FRONTEND_PATOLOGIA_VARIACAO.md)) | **in-sample** — esses casos estão no treino do bundle. Prova que o fluxo funciona; **não é generalização** |
| **52,19%** | caminho de produção, nested-OOF | o que o sistema no ar entrega fora da amostra |
| **64,81%** | cascata de representações ([docs/156](156_SUBTIPO_HONESTO_FUSAO.md)) | melhor medição honesta obtida |

**Se perguntarem "qual a acurácia de subtipo?", a resposta defensável é 52,19%
para o que está no ar, e 64,81% para a melhor configuração medida.**

### Por que 75% não é alcançável

[docs/150](150_PLANO_FINAL_METAS_75.md) demonstrou a aritmética:

- o efetivo é `acerto de centro × discriminação`;
- a discriminação máxima, **com ROI de ground truth**, é 79,49%;
- atingir 75% exigiria **94% de acerto de centro**;
- o oráculo de seleção de componente é **82,4%** — em 17,6% dos casos o
  componente certo nem existe na predição.

Três mecanismos independentes tentaram fechar essa lacuna:

| Tentativa | Mecanismo | Resultado |
|---|---|---:|
| docs/148 | heurísticas geométricas | +0,0 |
| docs/149 | seleção aprendida | +0,9, gate falhou |
| docs/153 | não selecionar (MIL) | −0,35, gate falhou |

> Geometria, supervisão e ausência de seleção falharam sobre o mesmo oráculo. O
> componente que contém a lesão **não é distinguível** por nada que a
> representação atual codifique.

O alvo honesto é **65–70%**, e 75% depende de uma segunda coorte.

---

## 4. Ganho disponível, medido e não implementado

A cascata de representações (fusão onde há recorte, recorte ou fígado inteiro
como fallback) supera o caminho no ar **em todas as classes**:

| Classe | No ar | Cascata | Δ |
|---|---:|---:|---:|
| FNH | 52,2% | 67,4% | **+15,2** |
| HCC | 74,5% | 74,5% | 0 |
| Hemangioma | 48,1% | 57,0% | +8,9 |
| **Cisto** | 34,0% | 60,4% | **+26,4** |
| **Balanceada** | **52,19%** | **64,81%** | **+12,6** |

Ambos medidos em nested-OOF com denominador honesto — comparáveis.

**Não foi implementado**, e a razão é de método: exige rodar o localizador antes
do subtipo, o que muda a ordem do pipeline. Fazer isso sem teste ponta a ponta
seria trocar um número medido por um risco. É a próxima entrega, com custo
conhecido.

---

## 5. O achado científico mais forte

[docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md) — massa de probabilidade por
classe, mesmos modelos por fold, medido em **dados reais**:

| Coorte | Massa nas 4 classes de subtipo |
|---|---:|
| `lld_mmri` | **99,32%** |
| `openswisshcc_development` | 1,43% |
| `openswisshcc_consumed_holdout` | 1,47% |

O modelo roteia com ~99% de pureza **pela coorte de origem**. As quatro classes
de subtipo praticamente não são preditas fora do LLD.

Isso significa: **numa instituição nova, a identificação da variação não
degradaria — ela não dispararia.** A causa provável é o espaço de rótulos (o
OpenSwiss só tem classes `unspecified`), o que é corrigível — mas torna o rótulo
fino de subtipo **obrigatório** na próxima coorte.

O sistema já se protege disso: a guarda de subtipo exige ≥50% de massa nas
classes nomeadas antes de nomear. Verificado: determina em 321/321 do LLD,
**0/130 do OpenSwiss**, 1/330 da coorte sintética.

---

## 6. Primeiro sinal externo

[docs/168](168_VALIDACAO_DICOM_BRUTO_PAREADA.md), coorte **TCGA-LIHC** — externa,
nunca vista:

| | |
|---|---:|
| Casos | 11 |
| **Sensibilidade** | **45,45%** |
| IC 95% | 21,3 – 72,0% |
| Painéis byte-idênticos aos do mapeamento aprovado | 11/11 |

O desenho pareado é o que dá valor ao número: como os painéis são idênticos, a
queda **não vem** da ingestão automática de fases — é generalização do
classificador congelado.

É o primeiro sinal externo real do projeto, e ele é ruim. Coerente com docs/161.

---

## 7. O que foi construído

**Pipeline completo, do DICOM à resposta**, ~50 s por exame:

- ingestão de **DICOM bruto do PACS**, com resolução automática das fases
  ([docs/167](167_INGESTAO_DICOM_BRUTO_MULTIFASICO.md)) — exclui MPR/MIP/subtração,
  ordena por posição física e não por nome de arquivo;
- fallback monofásico explícito quando não há três fases
  ([docs/173](173_INGESTAO_MONOFASICA_EXPERIMENTAL.md)), sem fabricar fases;
- classificação binária + identificação da variação, com guarda contra nomear sem
  evidência;
- **visualizador 3D auditável** ([docs/166](166_VISUALIZADOR_3D_AUDITAVEL.md)):
  cortes ortogonais, régua, vistas anatômicas, painel 2D de RM com contorno da
  máscara, métricas de fidelidade malha-versus-máscara e checklist de revisão;
- **região candidata** localizada só **após** a decisão congelada
  ([docs/169](169_REGIAO_CANDIDATA_3D_POS_INFERENCIA.md)), sem vazamento circular;
- 1349 testes automatizados.

---

## 8. Limitações que devem ser ditas antes de perguntadas

1. **Não é desempenho clínico.** É validação cruzada em dados de desenvolvimento,
   com prevalência artificial. Numa triagem real a especificidade pesa muito mais.
2. **A coorte é previsível a 100%** por um classificador de domínio (docs/131).
   Há confundimento entre coortes não resolvido.
3. **O único sinal externo disponível é 45,45%** de sensibilidade (n=11).
4. **A segmentação hepática falha numa cauda de 10–15% dos casos**
   ([docs/165](165_QUALIDADE_VISUALIZADOR_3D.md)): mediana 1601 mL nos 321 casos
   LLD, mas p10 de 419 mL. O volume aparece na tela com aviso quando sai da faixa.
5. `clinical_use_allowed` permanece `false` em todo artefato.

---

## 9. O que destrava o resto

Uma **coorte real de outra instituição, com rótulo fino de subtipo**
([docs/157](157_ESPECIFICACAO_SEGUNDA_COORTE.md)):

- ~100 negativos — hoje o holdout tem 20, e o IC de especificidade tem 38 pontos
  de largura;
- ~50 FNH — hoje são 46, e é o teto da fonte pública; é a pior classe;
- instituição diferente — sem isso o confundimento de domínio não se resolve.

Verificado: **não existe dataset público de RM com os quatro subtipos vindo de
outra instituição.** O caminho é aquisição institucional. Prazo realista de 6 a 12
meses, sendo a rotulagem por dois leitores o gargalo real.
