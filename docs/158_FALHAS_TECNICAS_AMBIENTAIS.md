# Nove das quatorze falhas técnicas eram da minha máquina, não do algoritmo

**Data:** 31 de julho de 2026
**Artefatos:** `casos/qualification/lld_mmri_v23/prepared/external_segmentation_retry_v1/`

---

## 1. O que se investigou

A avaliação oficial conta **16 falhas técnicas como erro** — 14 no LLD, 1 em cada
coorte OpenSwiss. Todas com o mesmo motivo registrado:
`no_verified_liver_enriched_panel_collection`. A raiz é que a segmentação
hepática nunca produziu máscara válida, e sem máscara não há painel nem embedding.

Abrindo o log de tentativas da auditoria original, as 14 do LLD se separam em
duas naturezas distintas:

| Natureza | n | Evidência no log |
|---|---:|---|
| **Infraestrutura** | 9 | 8 × `excedeu timeout tecnico de 75 s`; 1 × `Segmentation export worker died ... insufficient available CPU RAM` |
| **Real** | 5 | rodou até o fim, dentro do tempo, e encontrou 0, 8 ou 216 voxels de fígado |

Nos 9 primeiros o TotalSegmentator **nunca terminou de rodar**. Isso é sintoma de
máquina sob contenção, não de imagem ruim.

---

## 2. O teste

Repetidas exatamente as duas tentativas originais — primária em resolução plena,
fallback rápido 3 mm — **com o mesmo timeout de 75 s** e o mesmo gate anatômico
(volume ≥ 300 mL, extensão axial ≥ 60 mm, extensão no plano ≥ 70 mm, maior
componente ≥ 90%). Máquina em melhor condição: 17 GB livres, CPU a 9%.

**O timeout não foi alterado.** Os 75 s por tentativa compõem o gate primário de
180 s por caso, que é requisito de viabilidade da triagem. Afrouxá-lo seria mudar
a régua depois de medir. Nenhum caso foi retirado do denominador.

**Previsão registrada antes de rodar:** os 5 casos da categoria "real" não devem
recuperar. Se recuperassem, a leitura do log estaria errada e haveria
não-determinismo no segmentador — achado diferente e bem menos confortável.

---

## 3. Resultado

| Categoria | Recuperados |
|---|---|
| Infraestrutura | **9 de 9** |
| Real | **0 de 5** |

**Separação perfeita, nos dois sentidos.** A previsão se confirmou, o que descarta
não-determinismo e sustenta que as 9 falhas eram ambientais.

Os recuperados passaram em 35 a 84 s, folgadamente dentro do orçamento.

---

## 4. Impacto nos números — e a correção de uma projeção minha

Eu havia projetado que isso faria o LLD passar o gate. **Não faz.** A projeção
assumia que os 5 positivos faltantes recuperariam; a distribuição saiu
desfavorável:

| | Recuperados (9) | Ainda falhando (5) |
|---|---:|---:|
| Positivos (HCC) | **2** | **3** |
| Negativos | 7 | 2 |

Os casos que genuinamente quebram a segmentação são desproporcionalmente
positivos — 3 de 5.

| LLD | Sensibilidade | Especificidade |
|---|---:|---:|
| Oficial hoje | 73,25% | 76,97% |
| Realista após correção | 74,18% | 79,99% |
| **Melhor caso concebível** | **74,52%** | 80,90% |

**Mesmo no melhor caso — os 2 positivos recuperados ambos classificados
corretamente — a sensibilidade não alcança 75%.** O gate do LLD continua
reprovado.

---

## 5. O que isso significa para os números oficiais

Os números publicados **subestimam o sistema**: 9 casos são contados como erro
porque a máquina de execução estourou tempo e memória, não porque o algoritmo
falhou. A magnitude é de cerca de **+1 ponto de sensibilidade e +3 de
especificidade** no LLD.

Isso é uma limitação de execução que precisa constar de qualquer relato. Não é
ganho de método e não altera conclusão nenhuma sobre representação ou modelo.

---

## 6. Os 5 que permanecem

São limitação real: o TotalSegmentator roda até o fim, dentro do orçamento, e não
encontra fígado anatomicamente plausível. Três são HCC, um FNH, um hemangioma.

Ainda não sei se é limitação do **dado** (FOV truncado, artefato severo) ou do
**modelo de segmentação**. Uma inspeção visual resolve, e o resultado importa: se
o fígado estiver visível nas imagens, é um achado sobre a ferramenta.

---

## 7. Custo de aplicar a correção

Corrigir os números exige regenerar a cadeia: máscaras → painéis enriquecidos →
dataset de candidatos → embeddings → avaliação. Cada etapa é ferramenta
contratada com assinatura e saída imutável.

O caminho existe e é incremental — `build_candidate_dataset` aceita `sources`
como **lista**, então os 9 casos entram como segunda fonte sem regerar os 321, e
`build_liver_enriched_pilot` aceita `--case-id`. Mas é preciso montar um
`prepared_root` com as linhas de auditoria dos 9 (incluindo
`dynamic_liver_support_fraction`), e depois refazer embeddings e avaliação.

**Estimativa honesta: várias horas, com risco de esbarrar em vínculo de
assinatura entre a auditoria e os painéis.**

Contra um ganho que **não vira gate nenhum**.

**Recomendação:** documentar agora — o que este documento faz — e executar a
regeneração quando houver outro motivo para refazer a cadeia inteira, como a
chegada da segunda coorte. O achado fica registrado e o número corrigido é
conhecido; a diferença é apenas se ele já aparece nos artefatos assinados.

`clinical_use_allowed` permanece `false`.
