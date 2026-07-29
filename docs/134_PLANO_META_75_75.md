# Plano para atingir a meta 75/75

**Data:** 29 de julho de 2026
**Meta:** sensibilidade ≥ 75% **e** especificidade ≥ 75%, estáveis por dataset
**Definição em código:** `acceptance.sensitivity_minimum / specificity_minimum = 0.75`
([medsiglip_multiclass_classifier.py:831](../dtwin/learning/medsiglip_multiclass_classifier.py))

---

## 1. Contexto: onde estamos exatamente

O agregado **passa**, mas por margem estreita e com o limite inferior do IC bem abaixo do
alvo:

| | Valor | IC95 Wilson | IC95 bootstrap por paciente |
|---|---:|---|---|
| Sensibilidade | 75,91% | 69,84 – 81,08% | 70,25 – 81,82% |
| Especificidade | 76,11% | 70,42 – 81,01% | 70,99 – 81,47% |
| AUC | 0,8534 | — | — |

**O gate está atendido pela estimativa pontual, não estabelecido.** Ambos os limites
inferiores ficam perto de 70%. Isso precisa ser dito sempre que o número for citado.

E por dataset, **apenas 1 dos 3 passa**:

| Dataset | n | Sens | Esp | AUC | Gate | Falhas técnicas |
|---|---:|---:|---:|---:|:--|---:|
| `lld_mmri` | 335 | **73,25%** | 76,97% | 0,8630 | FALHA (sens) | 14 |
| `openswisshcc_development` | 88 | 82,05% | 77,55% | 0,8269 | OK | 1 |
| `openswisshcc_consumed_holdout` | 44 | 83,33% | **65,00%** | 0,8377 | FALHA (esp) | 1 |

Nota: `gate_75_75_stable_by_dataset: False` no manifesto do bundle **não é resultado de
cálculo** — é constante declarada
([medsiglip_multiclass_classifier.py:1030](../dtwin/learning/medsiglip_multiclass_classifier.py)).
É uma declaração conservadora honesta, e a tabela acima é a medida que a sustenta.

---

## 2. O diagnóstico que orienta o plano

**A AUC é estável (0,827–0,863) nos três datasets, mas sensibilidade e especificidade
oscilam — e as duas falhas pedem correções em direções opostas.**

| Dataset | Problema | Folga no eixo oposto | Movimento necessário |
|---|---|---|---|
| `lld_mmri` | limiar alto demais → perde positivos | esp tem 1,97 pt | **+3 verdadeiros positivos** (115→118 de 157) |
| `openswiss_holdout` | limiar baixo demais → falsos positivos | sens tem 8,33 pt | **−2 falsos positivos** (7→5 de 20) |

Isso significa que o obstáculo **não é qualidade de discriminação — é transferência do
ponto de operação entre coortes.** Um limiar global único não pode servir aos dois.

E há confirmação independente: a sonda de invariância de domínio (docs/131) mostrou coorte
previsível a **100,00%** a partir dos embeddings e **98,75%** a partir do radiomics. Se a
coorte é perfeitamente identificável, as distribuições de score estão deslocadas entre
coortes — um score de 0,47 não significa a mesma coisa no LLD e no OpenSwiss.

### Onde o erro se concentra

| Subtipo | Eixo | Valor |
|---|---|---:|
| `hcc` | sensibilidade | **73,25%** |
| `hepatic_cyst` | especificidade | **64,15%** |
| `hemangioma` | especificidade | 78,48% |
| `fnh` | especificidade | 89,13% |

A falha de sensibilidade do LLD **é** a falha do HCC (é o único positivo daquela coorte). As
falhas de especificidade são falsos positivos em cisto, e secundariamente hemangioma.

### O problema de poder estatístico

O holdout tem **44 casos e 20 negativos**. O IC95 da sua especificidade é
[43,29 – 81,88] — **38 pontos de largura**. Cada caso individual move a especificidade em
5 pontos. Ainda que o modelo fosse perfeito, **não é possível estabelecer estabilidade por
dataset com 20 negativos.** Isso é aquisição de dados, não modelagem.

---

## 3. O que já está eliminado por evidência

Para o plano não re-litigar caminhos fechados:

| Caminho | Resultado | Doc |
|---|---|---|
| Subtipo pela cabeça supervisionada atual | 52,18% balanceada (4 classes, LLD) | 129 |
| Zero-shot MedSigLIP (torre de texto) | 27,55%, acaso 25% | 131 |
| Radiomics como substrato invariante | coorte previsível a 98,75% | 131 |
| Zero-shot MedGemma 4B | 99,69% de abstenção | 133 |
| Localizador `liver_lesions_mr` venoso | recall 56,76%; união arterial descartada | 93 |

---

## 4. Três frentes, em ordem de informação por hora investida

### Frente A — Transferência do ponto de operação  ·  horas, CPU  ·  **COMEÇA AGORA**

Varrer o limiar por dataset sobre os scores OOF **já congelados**, sem retreino e sem GPU,
para medir o **teto** do que a calibração pode entregar.

**Ressalva metodológica central:** escolher o limiar ótimo sobre os próprios dados de
avaliação é otimista por construção — é ajustar o ponto de operação ao conjunto de teste.
O número resultante **não é desempenho honesto; é um limite superior.** Serve para uma
pergunta binária:

- **Se o teto não alcançar 75/75 nos três** → calibração está descartada por evidência, e a
  Frente B passa a ser obrigatória. Conclusão forte e definitiva.
- **Se alcançar** → o teto atual é calibração, não representação. Aí o trabalho vira
  *como calibrar honestamente*, e passa a exigir avaliação aninhada própria (§4.1).

### Frente B — Elevar a AUC com as sequências que já temos  ·  semanas, GPU

A 335 casos LLD têm **6 sequências em disco** e usamos 3. As três descartadas atacam
exatamente as duas concentrações de erro:

| Sequência | Ataca | Por quê |
|---|---|---|
| `C-pre` | HCC (sens 73,25%) | Realce = pós − pré. Sem pré-contraste, "esta lesão realça?" é inrespondível; hoje só comparamos fases pós entre si |
| `T2WI` | cisto (esp 64,15%) | Cisto é marcadamente hiperintenso em T2 — o discriminador clássico contra hemangioma |
| `DWI` | cisto vs sólido | Cisto não restringe difusão; lesão sólida restringe |

Além disso, a AUC atual de 0,85 permite no melhor caso ~77/77. **Para 75/75 robusto entre
coortes seria desejável AUC ≥ 0,88–0,90** — ou seja, mesmo com calibração perfeita a margem
é pequena, e elevar a AUC é necessário de todo modo.

Requisito de desenho herdado de docs/131: features novas devem ser **razões contra
referência interna** à própria aquisição, e cada representação candidata passa pela sonda de
domínio (critério: coorte previsível < 70%) **antes** de qualquer avaliação de endpoint.

### Frente C — Poder estatístico  ·  meses, aquisição  ·  **INICIAR EM PARALELO JÁ**

Com 20 negativos no holdout, nenhuma das outras frentes consegue *demonstrar* estabilidade.
Esta é a frente com maior tempo de espera e a única que não depende de nós tecnicamente, por
isso precisa começar agora e não depois das outras.

---

## 4.1 Frente A em detalhe — o que será executado

**Entrada:** `casos/qualification/hybrid_v1/medsiglip_multiclass_oof_predictions_v1/oof_predictions.jsonl`
(467 predições OOF congeladas, campo `score`) unido aos rótulos via
`load_protected_cases` — os rótulos não estão no artefato
(`ground_truth_in_artifact: false`), como manda o protocolo.

**Cenários medidos, por dataset e no agregado:**

1. **Limiar congelado atual** — reproduz a tabela de §1, serve de sanidade.
2. **Limiar ótimo global** — o melhor limiar único para os três juntos, pelo mesmo critério
   de seleção que o projeto já usa (`maximizar min(sens, esp)`,
   [medsiglip_multiclass_classifier.py:401](../dtwin/learning/medsiglip_multiclass_classifier.py)).
   Responde: existe *algum* limiar único que satisfaz os três?
3. **Limiar ótimo por dataset** — o teto por coorte. Responde: a curva ROC de cada coorte
   *permite* 75/75, ou nem no melhor ponto ela permite?
4. **Calibração por taxa de positividade** — limiar escolhido para que a fração de positivos
   preditos iguale uma taxa alvo, por coorte, **sem usar rótulo**. É o candidato mais
   promissor a mecanismo honesto, porque só depende da distribuição de scores do lote que
   chega.

**Leituras pré-especificadas, fixadas antes de rodar:**

| Achado | Conclusão |
|---|---|
| Cenário 3 não alcança 75/75 em algum dataset | Calibração eliminada; Frente B obrigatória |
| Cenário 2 alcança 75/75 nos três | O limiar congelado está simplesmente mal escolhido — correção trivial |
| Cenário 3 alcança mas 2 não | Confirma deslocamento entre coortes; o trabalho é mecanismo de calibração |
| Cenário 4 chega perto do cenário 3 | Existe mecanismo honesto e sem rótulo; avaliar aninhado |

**O que este experimento NÃO faz:** não altera o bundle, não altera o limiar de produção,
não gera número reportável como desempenho. Produz um teto e uma decisão.

---

## 5. Sequenciamento

```
agora        Frente A (horas, CPU)  ─┬─→ decide se calibração resolve
                                     │
em paralelo  Frente C (aquisição) ───┼─→ sem isso nada é demonstrável
                                     │
depois de A  Frente B (semanas, GPU) ┴─→ necessária de todo modo p/ margem de AUC
```

Frente B é quase certamente necessária mesmo que A tenha sucesso, porque AUC 0,85 dá teto de
~77/77. A ordem existe para não gastar semanas de ingestão antes de saber se o problema é
calibração — e para que, se for, o ganho apareça imediatamente.

---

## 6. Verificação

**Frente A:**
- `casos/qualification/hybrid_v1/threshold_transfer_v1/` com os quatro cenários por dataset,
  ICs Wilson e a decisão contra as leituras pré-especificadas.
- Sanidade obrigatória: o cenário 1 tem de reproduzir exatamente sens 73,25% / esp 76,97%
  (LLD), 82,05% / 77,55% (development) e 83,33% / 65,00% (holdout). Se não reproduzir, a
  junção score↔rótulo está errada e nada mais vale.
- `.venv-win/Scripts/python.exe -m pytest -q` continua em 1287 passando.

**Frentes B e C:** pré-especificação própria antes de qualquer número, como em docs/128,
130 e 132.

---

## 7. Compromissos de honestidade que este plano mantém

1. Nenhum gate é ajustado depois de ver resultado (Etapa B, docs/128, 130, 132).
2. O teto da Frente A é reportado como teto, nunca como desempenho.
3. Toda representação nova passa pela sonda de domínio antes da avaliação de endpoint.
4. `clinical_use_allowed` permanece `false` até validação externa cega existir
   (`external_blind_validation: false` hoje).
