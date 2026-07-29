# Benchmark dos 120 casos executado pela camada web

**Data:** 29 de julho de 2026
**Coleção:** `ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1/webapp_input` (120 casos, 1103 arquivos, 15,97 GB)
**Fluxo:** Etapa C visual, completo — resolução de fases → harmonização na grade venosa →
segmentação hepática full-res → painéis liver-enriched → MedSigLIP-448 → bundle de produção
**Bundle:** `hybrid_v1_medsiglip_multiclass_supervised`, assinatura `2009ce7e071550d4`
**Execução:** HTTP `POST /api/benchmarks` no webapp (`:8080`), não pelo CLI
**Artefato:** `casos/webapp/web_layer_120_v1/report.json`

---

## 1. O que este documento é e o que não é

É o registro da **primeira execução do fluxo completo pela camada web** sobre a coleção
inteira, incluindo os casos que o adaptador não consegue ingerir.

**Não é uma estimativa de generalização.** Os 120 casos derivam de coortes usadas no
desenvolvimento e saíram todos com procedência `unknown` (§5). A estimativa honesta do
modelo continua sendo o nested-OOF da Etapa C: 75,91% sens. / 76,11% esp. (docs/121).

---

## 2. Execução

Rodado em 6 blocos retomáveis de 20 casos, cada um um benchmark real via HTTP, com o
relatório gravado ao fechar. Os 120 registros foram consolidados num relatório único
usando as mesmas funções do webapp (`calculate_benchmark_metrics`, `_provenance_summary`),
então os números são idênticos aos de uma rodada única.

O particionamento não é preferência de design: duas rodadas únicas anteriores de ~80 min
foram perdidas por interrupção (teardown de sessão e desligamento do notebook), porque o
estado de um benchmark vive só na memória do uvicorn. Em blocos, uma interrupção custa no
máximo ~15 min.

| Bloco | Casos | Decisivos | Falhas | Tempo |
|------:|------:|----------:|-------:|------:|
| 1 | 20 | 18 | 2 | 12,9 min |
| 2 | 20 | 16 | 4 | 11,0 min |
| 3 | 20 | 13 | 7 | 9,6 min |
| 4 | 20 | 16 | 4 | 12,4 min |
| 5 | 20 | 15 | 5 | 10,8 min |
| 6 | 20 | 20 | 0 | 14,2 min |
| **Total** | **120** | **98** | **22** | **70,7 min** |

Média 35,4 s/caso no geral; 42,6 s/caso entre os decisivos.

---

## 3. Resultados

Quatro leituras. As duas dimensões são independentes: **o que fazer com as falhas
técnicas** e **qual endpoint clínico**.

### Endpoint da coleção (rótulo como distribuído)

Hemangioma, cisto e FNH contam como POSITIVO. Não é o endpoint para o qual o modelo
foi treinado.

| Leitura | n | Sens. | Esp. | Acur. | Gate 75/75 |
|---|---:|---:|---:|---:|:--|
| A) todos, falha = erro | 120 | 60,00% | 48,00% | 55,00% | REPROVADO |
| B) só decisivos | 98 | 61,76% | 80,00% | 67,35% | REPROVADO |

### Endpoint de treino (benigno focal recodificado como NEGATIVO)

| Leitura | n | Sens. | Esp. | Acur. | Gate 75/75 |
|---|---:|---:|---:|---:|:--|
| C) todos, falha = erro | 120 | 84,00% | 62,86% | 71,67% | REPROVADO |
| D) só decisivos | 98 | 87,50% | 88,00% | 87,76% | APROVADO |

IC95 da leitura D: sensibilidade [75,3–94,1], especificidade [76,2–94,4].

**A leitura D não deve ser citada isolada.** Ela é otimista em duas frentes ao mesmo
tempo: descarta as 22 falhas e usa o endpoint favorável ao modelo. A diferença entre A
e D — 55,00% contra 87,76% — é inteiramente contabilística, não há mudança de modelo
entre elas.

---

## 4. As 22 falhas

| Motivo | n | Natureza |
|---|---:|---|
| Caso cego sem fase obrigatória autorizada: `t1_arterial` | 20 | Limitação de ingestão |
| Volume possui menos de 27 planos corporais | 1 | Rejeição determinística de qualidade |
| Não foi possível segmentar o fígado neste exame | 1 | Flake transitório |

As 20 primeiras são exatamente os casos inelegíveis mapeados antes da execução
(`0009, 0010, 0021, 0022, 0032, 0033, 0041, 0042, 0043, 0047, 0055, 0056, 0059, 0064,
0075, 0078, 0082, 0088, 0091, 0097`). Sem fase arterial não há painel multifásico. É
limitação da ingestão, não do classificador.

`ARGOS-BLIND-0092` (volume curto) falhou com a **mesma mensagem** no lote por CLI —
rejeição determinística, as duas camadas concordam.

`ARGOS-BLIND-0069` foi decisivo no lote por CLI e falhou aqui após 34,5 s, já dentro da
segmentação. Um retry documentado pela mesma camada web devolveu `decisive`, POSITIVA,
score `0.9782214229500796` — **idêntico ao do CLI**. Confirma flake transitório de
nnU-Net, já observado duas vezes neste projeto. O consolidado mantém a falha, porque é o
resultado real desta execução; o retry está em `web_layer_120_v1/retries/`.

---

## 5. Procedência

Os 120 casos saíram com veredito `unknown`: identificadores `ARGOS-BLIND-*` não são
comparáveis com os `anon-*` do treino. `unknown` **não** é out-of-sample. Por proveniência
real, sabe-se que a maior parte da coorte esteve no treino (docs/126).

O relatório carrega `metrics_are_generalization_estimate: false` e a UI renderiza o aviso
antes das métricas. O modelo também reporta `gate_75_75_stable_by_dataset: false`.

---

## 6. Equivalência entre webapp e CLI

Comparação caso a caso dos decisivos comuns às duas camadas (n=97):

- **95 idênticos bit a bit** no `visual_score`
- 2 divergentes: `ARGOS-BLIND-0102` (Δ 4,2e-2) e `ARGOS-BLIND-0076` (Δ 1,7e-2)

Os deltas são grandes demais para ruído de ponto flutuante; a origem provável é o
não-determinismo do nnU-Net, que produz máscara hepática levemente diferente e desloca o
recorte dos painéis. **Nenhum dos dois mudou de decisão** — ambos permaneceram NEGATIVA,
e ambos estão longe do limiar (0,16 e 0,27 contra limiar 0,4749).

Conclusão: webapp e CLI executam o mesmo pipeline. A variação residual é da segmentação,
não da camada de transporte.

---

## 7. Limitações

1. **Não é generalização.** Coorte majoritariamente in-sample; ver §5.
2. **16,7% dos casos não ingerem.** Enquanto a resolução de fases exigir `t1_arterial`
   explícita, um sexto desta coleção fica fora do alcance do classificador.
3. **O endpoint da coleção diverge do endpoint de treino.** Enquanto os dois não forem
   reconciliados, qualquer número precisa dizer qual endpoint está usando.
4. **Não-determinismo da segmentação.** Mensurado em 2/97 casos, sem impacto em decisão
   nesta amostra, mas não é zero e pode importar perto do limiar.
5. **Fragilidade operacional.** O estado do benchmark é só memória; uma interrupção perde
   a rodada. Além disso, a config do TotalSegmentator já corrompeu três vezes em morte
   abrupta de processo, e o sintoma é falha de 100% dos casos com mensagem genérica.
