# Classificador visual no webapp — do DICOM à alteração identificada

**Data:** 1 de agosto de 2026
**Arquivos:** `dtwin/learning/visual_inference.py`, `webapp/server.py`,
`webapp/static/index.html`, `webapp/static/benchmark.html`,
`tests/test_visual_subtype.py`

---

## 1. O que mudou

O classificador da Etapa C — o de melhor acertividade medida do projeto — só
existia no benchmark, e não reportava qual alteração havia encontrado. Agora:

| | Antes | Depois |
|---|---|---|
| Exame individual | só MedGemma | **modo visual, agora o padrão** |
| Identificação da alteração | não existia | **sim, com guarda de evidência** |
| Benchmark | só positivo/negativo | coluna de alteração + CSV |

O endpoint binário **não mudou**: mesmo bundle congelado, mesmo limiar, mesmo
agregador. A fusão de representações foi avaliada e **reprovada**
([docs/155](155_REMEDICAO_UNIAO_VEREDITO_FUSAO.md)) por não generalizar; nada
disso entrou. A acertividade permanece **75,91% / 76,11%** no agregado nested-OOF.

O que é novo é o **subtipo**, que já existia dentro do modelo multiclasse e
simplesmente não era exposto.

---

## 2. A guarda de subtipo, que é o cerne

[docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md) mediu que a atribuição de
classe é condicionada à coorte de aquisição:

| Coorte | Massa nas 4 classes nomeadas |
|---|---:|
| `lld_mmri` real | 99,32% |
| `openswisshcc_development` real | 1,43% |
| `openswisshcc_consumed_holdout` real | 1,47% |
| sintética | 6,93% |

Sem guarda, um exame de origem não vista receberia o argmax entre as quatro
classes **mesmo com ~99% da massa em `unspecified`** — um subtipo inventado sobre
1% de evidência.

`resolve_subtype()` exige **≥ 50% de massa nas classes nomeadas** para afirmar um
subtipo. O limiar fica longe de todos os modos observados. Verificado sobre os
dados reais:

| | Subtipo determinado |
|---|---|
| LLD (321 casos) | **321/321** |
| OpenSwiss (130 casos) | **0/130** |
| Sintética (330 casos) | **1/330** |

Ela nomeia onde há base e recusa onde não há.

---

## 3. Um erro que o teste ponta a ponta revelou

Minha primeira versão suprimia o subtipo em exames negativos, com o texto
*"triagem negativa: não há alteração a caracterizar"*.

**Isso é falso.** Só o CHC é positivo neste endpoint — HNF, hemangioma e cisto são
negativos e continuam sendo alterações reais. O caso `ARGOS-BLIND-0016` (verdade
FNH) expôs o problema: a triagem deu NEGATIVA, corretamente, e o modelo
identificou **FNH com 97,7%** — que a interface descartava.

Corrigido: negativos mostram **"achado mais provável"**, marcado como benigno e
fora do alvo. E quando a triagem dá negativa mas a classe mais provável é o
próprio CHC, as duas leituras discordam e o card diz isso, em vez de escolher uma.

---

## 4. Verificação ponta a ponta

Casos reais do benchmark cego interno, enviados pelo endpoint HTTP como DICOM
multifásico, com o rótulo consultado só depois:

| Caso | Verdade | Predição | Alteração | Confiança |
|---|---|---|---|---:|
| `ARGOS-BLIND-0026` | HCC | **POSITIVA** | Carcinoma hepatocelular | 79,0% |
| `ARGOS-BLIND-0016` | FNH | **NEGATIVA** | Hiperplasia nodular focal | 97,7% |
| `ARGOS-BLIND-0001` | OpenSwiss, negativo | POSITIVA *(falso positivo)* | não determinado | — |

Os dois primeiros estão corretos nos dois eixos. O terceiro é um falso positivo —
esperado, com especificidade de ~77% — e nele a guarda **recusou** nomear
subtipo, coerente com a origem OpenSwiss do caso.

Tempo total por exame: **~48 s** (segmentação 38 s, painéis 1,5 s, classificação
8,6 s).

46 testes passam (39 do webapp + 7 novos).

---

## 5. A limitação que define o produto

> O modo visual **exige as três fases dinâmicas em subpastas nomeadas**:
> `arterial/`, `venous/`, `delayed/`.

Não é limitação de implementação. Identificar qual série é qual fase a partir do
DICOM bruto é problema não resolvido no projeto (docs/123), e todo o pipeline
depende de comparar as fases entre si. Adivinhar produziria harmonização e recorte
na fase errada, e uma resposta sem valor.

Os modos MedGemma continuam aceitando uma pasta DICOM qualquer, com acertividade
menor e sem identificação da alteração.

---

## 6. O que continua valendo

- `research_only: true`, `clinical_use_allowed: false`, revisão humana obrigatória
  em todo resultado.
- Nenhuma métrica nova foi produzida; a acertividade é a mesma já medida e
  documentada.
- Falha em qualquer etapa vira "não concluído", nunca uma decisão fabricada.
