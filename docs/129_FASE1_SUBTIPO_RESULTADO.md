# Fase 1 — Resultado: o classificador NÃO sabe nomear o subtipo

**Data:** 29 de julho de 2026
**Pré-especificação:** [docs/128](128_FASE1_SUBTIPO_PRE_ESPECIFICACAO.md), commitada em
`72451ff` **antes** de qualquer número ser calculado
**Artefatos:** `casos/qualification/hybrid_v1/subtype_phase1_v1/`
**Veredito:** **REPROVADO** nos dois critérios do gate

---

## 1. Conclusão

O bundle da Etapa C **não deve expor subtipo clínico**. Ele acerta 52,18% de acurácia
balanceada ao nomear a lesão entre 4 subtipos (exigido: 60%), e erra dois terços dos
cistos hepáticos (recall 33,33%, exigido: ≥40%).

O motivo aparece com nitidez incomum: **o modelo discrimina coorte quase perfeitamente e
biologia mal**.

| O que o modelo separa | Acerto |
|---|---:|
| De qual coorte o exame veio (LLD-MMRI vs OpenSwiss) | **99,78%** (450/451) |
| Qual lesão é, dentro do LLD-MMRI | **52,18%** (balanceada, acaso 25%) |

Essa é a confirmação direta, em nível de predição, do que a ablação da Etapa C já havia
medido de forma agregada: +0,049 AUC vindos de separação de domínio contra apenas +0,010
dos rótulos finos. O multiclasse aprendeu geografia, não patologia.

---

## 2. Validade da extração

A pré-condição bloqueante de docs/128 **passou de forma perfeita**:

```
casos verificados  : 451
identicos bit a bit: 451
maior |delta|      : 0.000e+00
```

Somando a massa das classes positivas do vetor extraído e agregando com a agregação
selecionada de cada fold, o resultado reproduz **exatamente** o `score` congelado em
`oof_predictions.jsonl`, para todos os 451 casos com predição. Não há re-derivação
aproximada: as probabilidades avaliadas abaixo são as do modelo congelado, lidas dos
mesmos `outer_fold_{0..4}.joblib` que produziram a Etapa C.

> **Nota de execução.** A primeira tentativa acusou divergência de 4,1e-07 e abortou.
> A causa era minha: carreguei os embeddings em float32, enquanto o pipeline faz
> `.astype(np.float64)` ([medsiglip_multiclass_classifier.py:250](../dtwin/learning/medsiglip_multiclass_classifier.py)).
> Corrigi na origem, passando a usar a própria `_load_embedding_map` do módulo, em vez de
> afrouxar a tolerância. O gate científico não foi tocado.

---

## 3. Resultado primário (gate)

4 subtipos, apenas LLD-MMRI, onde a coorte é constante e portanto não serve de atalho.

**n = 321 · acaso = 25,0% · acurácia balanceada = 52,18% · top-1 = 59,50%**

| verdade \ predito | fnh | hcc | hemangioma | hepatic_cyst | recall |
|---|---:|---:|---:|---:|---:|
| **fnh** | **23** | 5 | 14 | 3 | 51,11% |
| **hcc** | 5 | **116** | 15 | 16 | 76,32% |
| **hemangioma** | 13 | 11 | **35** | 14 | 47,95% |
| **hepatic_cyst** | 5 | 14 | 15 | **17** | 33,33% |

| Subtipo | n | Recall | IC95 | Precisão |
|---|---:|---:|---|---:|
| `hcc` | 152 | 76,32% | [69,0 – 82,4] | 79,45% |
| `fnh` | 45 | 51,11% | [37,0 – 65,0] | 50,00% |
| `hemangioma` | 73 | 47,95% | [36,9 – 59,2] | 44,30% |
| `hepatic_cyst` | 51 | **33,33%** | [22,0 – 47,0] | 34,00% |

O cisto hepático é o caso mais grave: com 33,33% de recall e IC95 chegando a 22,0%, o
limite inferior está **abaixo do acaso de 4 classes (25%)**. O modelo confunde cisto com
hemangioma (15) e com HCC (14) quase tanto quanto acerta (17). Isso reencontra, agora no
nível do subtipo, o achado da Etapa A: o erro se concentrava em `hepatic_cyst`.

`hcc` é o único subtipo com sinal real — e não por acaso, é exatamente a classe que
sustenta o endpoint binário, cuja estimativa honesta continua sendo 75,91% / 76,11%.

---

## 4. Diagnóstico de confundimento (não é gate)

6 classes, todas as coortes. **n = 451 · acurácia balanceada = 60,43%**

O número sobe 8,26 pontos em relação ao primário — mas a matriz mostra que o ganho não é
clínico. As duas classes `*_unspecified` (que são o OpenSwiss) atingem recall de 76,12% e
77,78%, e o bloco cruzado é praticamente vazio: dos 321 casos LLD, **nenhum** foi predito
como `*_unspecified`; dos 130 casos OpenSwiss, apenas 1 vazou para um subtipo LLD.

Ou seja: o classificador de 6 classes resolve com folga uma pergunta que ninguém fez
("de qual dataset veio este exame?") e patina na pergunta clínica. Se a métrica de 6
classes fosse reportada como capacidade de subtipagem, seria enganosa por construção.

---

## 5. Consequência, conforme pré-especificado

Conforme a tabela de decisão de docs/128, com o gate reprovado:

- **Não expor `class_probabilities` na saída** do webapp nem em nenhuma outra superfície.
  A Fase 2 fica cancelada.
- A decisão oficial permanece **binária**, com o limiar e as métricas já validados.
- `clinical_use_allowed` permanece `false`.

Não houve iteração sobre o gate após ver o resultado, em coerência com o compromisso
honrado na Etapa B (duas sondas pré-especificadas falharam com AUC 0,486 e 0,554 e o
resultado foi aceito em vez de reajustado).

---

## 6. O que destravaria essa capacidade

O obstáculo não é o tamanho da amostra nem a escolha do classificador — é que **os 4
subtipos existem em uma única coorte**. Enquanto isso for verdade, qualquer modelo
treinado nesses rótulos pode acertar o subtipo reconhecendo o hospital, e nenhum
experimento interno consegue distinguir as duas explicações.

O que muda o quadro, em ordem de impacto:

1. **Uma segunda coorte com subtipo clínico anotado.** É o único caminho que quebra o
   confundimento. Com dois hospitais declarando hemangioma/cisto/FNH, a validação
   leave-one-dataset-out passa a existir para a tarefa de subtipo.
2. **Reforço específico de `hepatic_cyst`.** É a classe mais fraca e a de maior
   sobreposição de aparência com hemangioma nas fases usadas. Vale investigar se as três
   fases atuais (arterial/venosa/tardia) carregam o contraste que separa as duas, ou se
   falta uma sequência (por exemplo, T2 pesado, onde cisto é caracteristicamente muito
   hiperintenso).
3. **Só então** reabrir a Fase 2.

Enquanto (1) não existir, a recomendação é manter a saída binária e não prometer
subtipagem.
