# Remedição com recorte equiparado — a fusão não generaliza fora do LLD

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/hybrid_v1/remedicao_uniao_v1/`, `openswiss_roi_union_embeddings_v1/`, `openswisshcc_v1/calibration/dev_v22_arterial_union_chunk_*`
**Fecha a pergunta aberta em** [docs/154 §4](154_OPENSWISS_FUSAO_BINARIO_COMPLETO.md)

---

## 1. A pergunta

docs/154 mediu a fusão no endpoint binário completo. Ela ajudou muito no LLD
(+9 verdadeiros positivos) e atrapalhou no OpenSwiss (−2 no development, −3 no
holdout). Duas explicações competiam:

- **(a)** a fusão só funciona no LLD e não generaliza;
- **(b)** a fusão funciona, mas o recorte do OpenSwiss vinha de **um** localizador
  enquanto o do LLD vinha da **união de três** — recorte pior, ruído em vez de
  sinal.

Rodado o localizador de união venosa+arterial (`venous-registered-arterial-union-v22`)
nos **87 casos do development**, os recortes foram refeitos e a medição repetida.

---

## 2. Desenho, com controle

| | |
|---|---|
| **Braço de teste** | `development` — recorte mudou de 1 fase para união de 2 |
| **Controle** | `holdout` — recorte **não** mudou (a ferramenta é development-only) |

O controle existe porque o estimador oficial reseleciona `C`, agregação de painel
e limiar nos folds internos a cada corrida. Sem ele, eu poderia atribuir ao
recorte uma variação vinda dessa reseleção.

**Leitura pré-especificada, commitada antes de qualquer número:**
- sustenta (b): development com sens ≥ 80% e esp ≥ 75%;
- parcial: sensibilidade melhora mas fica < 80%;
- sustenta (a): sensibilidade não melhora;
- **anulada** se o holdout se mover mais de ~1,5 caso.

---

## 3. Resultado

Cobertura de recorte no development subiu de 77 para **79 casos**.

| Dataset | Recorte venoso | Recorte de união | Δ sens |
|---|---|---|---:|
| `lld_mmri` | 80,25 / 76,40 | 80,25 / 76,97 | 0,00 |
| **`openswisshcc_development`** | 76,92 / 79,59 | **74,36 / 75,51** | **−2,56** |
| `openswisshcc_consumed_holdout` | 70,83 / 70,00 | 75,00 / 70,00 | +4,17 |

**Controle:** o holdout moveu **1 caso** (18 VP contra 17). Dentro da tolerância
— a leitura é válida.

**A sensibilidade do development não subiu. Caiu 2,56 pontos**, e a
especificidade caiu 4,08. Com recorte melhor e mais cobertura, o resultado
piorou.

### Contra o pipeline oficial

| Dataset | Oficial | Fusão + união | Δ sens | Δ esp |
|---|---|---|---:|---:|
| `lld_mmri` | 73,25 / 76,97 | **80,25 / 76,97** | **+7,00** | 0,00 |
| `openswisshcc_development` | 82,05 / 77,55 | 74,36 / 75,51 | −7,69 | −2,04 |
| `openswisshcc_consumed_holdout` | 83,33 / 65,00 | 75,00 / 70,00 | −8,33 | +5,00 |

---

## 4. Veredito

> **Sustenta (a). A fusão não generaliza para fora do LLD.**

A hipótese do recorte pior — que era a minha, e a mais confortável — **foi
testada e reprovada**. Equiparar o procedimento não recuperou nada; piorou de
leve.

O ganho no LLD é grande e real (+7,00 pontos, 126 verdadeiros positivos contra
117). Mas custa 7 a 8 pontos de sensibilidade em **ambas** as coortes OpenSwiss,
com o efeito aparecendo igual na coorte cujo recorte mudou e na que não mudou.
Isso é assinatura de efeito de coorte, não de qualidade de recorte.

### Mecanismo plausível

No LLD, todo positivo é **HCC** — uma entidade morfológica única, e o recorte
ampliado captura exatamente a textura que a distingue. No OpenSwiss os positivos
são `positive_unspecified`, um conjunto heterogêneo cuja fonte protegida não
documenta o subtipo. Um detalhe local que caracteriza HCC não caracteriza "o que
quer que seja positivo aqui".

Se isso estiver certo, a fusão não é uma melhoria de representação de propósito
geral — é um **detector de HCC** disfarçado. E isso é consistente com docs/150 §3,
que já havia observado que a sensibilidade binária no LLD *é* detecção de HCC.

---

## 5. Consequência

**A fusão está encerrada como candidata a entrar no pipeline binário.** Não
promovo algo que melhora uma coorte e piora as outras duas, com a explicação
alternativa já eliminada por teste.

O que permanece válido dela:
- é o melhor substrato conhecido para o **subtipo** (docs/151), que é LLD-only por
  natureza e onde o viés de coorte não se aplica;
- os 87 recortes de união do development e os embeddings ficam em cache, sem
  custo de recomputação se forem úteis.

Nada é promovido. O pipeline oficial permanece **75,91% / 76,11%** agregado.

---

## 6. Nota operacional

A ferramenta contratada é tudo-ou-nada: monta um staging e o descarta inteiro em
qualquer exceção. Uma falha intermitente do nnU-Net
(`_dispatch_key_for_device`, dentro de um worker) no caso 68 de 86 destruiu **67
casos prontos e ~60 min de GPU**. Repetido em chunks de 10, o mesmo caso passou —
a falha era intermitente, não do dado.

O projeto já usava chunking no localizador venoso (`dev_v10_lesion_localizer_full87_chunks`),
e eu disparei os 87 de uma vez mesmo assim. Depois um desligamento do PC levou
mais um chunk — mas aí custou 7 casos, não 80.

**Para qualquer corrida futura desta ferramenta: chunks de 10, sempre.**

`clinical_use_allowed` permanece `false`.
