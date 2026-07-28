# Lote label-blind de 100 casos — teste de operabilidade em escala

**Data:** 28 de julho de 2026
**Coleção:** `ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1` (120 casos; 100 elegíveis, 20 inelegíveis)
**Fluxo:** Etapa C visual — adaptador autorizado → segmentação venosa full-res →
harmonização arterial/tardia → painéis liver-enriched → MedSigLIP → classificador
**Natureza:** operabilidade em escala. **Nenhum rótulo foi lido nesta etapa.**

---

## 1. O que este documento é e o que não é

Registra que o fluxo visual roda de ponta a ponta, em escala, sobre DICOM
multifásico desidentificado. **Não** contém acurácia, sensibilidade,
especificidade ou qualquer comparação com verdade — nenhum rótulo foi aberto.
A distribuição de decisões abaixo é apenas isso: distribuição, não acerto.

---

## 2. Resultado operacional

```text
casos processados        100/100
decisões emitidas         98  (status=decisive)
falhas técnicas            2
painéis por caso           3 (em todos os 98)
tempo total de GPU       ~76 min
```

Decisões (sem verdade associada):

```text
NEGATIVA  50  (51,0%)
POSITIVA  48  (49,0%)
```

Tempo por caso: mediana **44,4 s** (mín 37,4 / máx 72,6).

Tempo por etapa (mediana):

| Etapa | Segundos |
|---|---:|
| ingestão multifásica + segmentação | 34,6 |
| geração de painéis | 1,5 |
| inferência visual (MedSigLIP + bundle) | 8,1 |

Score do classificador: mediana **0,4632** (mín 0,0012 / máx 0,9784), contra
threshold 0,4749. A distribuição é ampla e não colapsa num extremo.

Cobertura de fase após harmonização na grade venosa:

| Fase | Mediana | Mínimo |
|---|---:|---:|
| t1_arterial | 1,000 | 0,873 |
| t1_delayed | 1,000 | 0,906 |
| t1_venous | 1,000 | 1,000 |

Todos os casos ficaram muito acima do gate de 0,50; a venosa é 1,000 por
construção, por ser a referência.

---

## 3. Falhas

**Determinísticas (2 de 100 = 2%):**

- `ARGOS-BLIND-0092` — "Volume possui menos de 27 planos corporais". Gate
  legítimo: o painel 3×9 exige 27 planos. Fail-closed correto.
- `ARGOS-BLIND-0106` — segmentação hepática não convergiu.

**Transitórias (não contam como falha do fluxo):**

- `ARGOS-BLIND-0023` — `TypeError` em `transformers/_LazyModule.__init__`
  (`iter() returned non-iterator of type 'type'`). Não é código do projeto nem
  problema de dado: flake do carregamento preguiçoso da biblioteca, 1 ocorrência
  em 97 carregamentos do MedSigLIP. Reexecutado, passou (POSITIVA, 45,13 s).
- `ARGOS-BLIND-0073` — *segmentation fault* nativo numa tentativa, sucesso na
  seguinte. Flake conhecido de nnU-Net/TotalSegmentator no Windows.

Ambos os transitórios são retentáveis. Uma execução de produção deve prever
retry automático por caso.

---

## 4. Salvaguardas verificadas

Declaradas em **todos os 100** relatórios:

```text
labels_read              = false
lesion_masks_read        = 0
private_paths_persisted  = false
```

Verificado ainda que nenhum caminho privado, identificador original ou nome de
arquivo DICOM aparece nos relatórios.

---

## 5. Correção de orquestração (erro do operador, não do pipeline)

A primeira tentativa falhou nos 100 casos em 146 s. Causa: o script de lote leu
a lista de identificadores com terminadores de linha do Windows, então cada id
virou `ARGOS-BLIND-0001\r` — que o adaptador **corretamente** rejeitou por não
casar com `BLIND_CASE_PATTERN`. O pipeline estava íntegro (um caso executado
manualmente concluiu com sucesso no mesmo momento).

Corrigido com `tr -d '\r'` e validação de formato que aborta o lote cedo, em vez
de gastar a execução inteira produzindo falhas idênticas.

---

## 6. Ressalva metodológica

Os casos derivam de coortes **já usadas no desenvolvimento**. O campo
`in_sample=false` presente nos relatórios apenas indica que o identificador cego
não consta da lista de `case_id` de treino do bundle — **isso não comprova
independência**, porque os identificadores cegos usam esquema de nomenclatura
diferente do usado no treino.

Portanto, nada neste documento é evidência de generalização, e a distribuição
48%/51% não deve ser lida como desempenho.

---

## 7. Artefatos

```text
casos/webapp/internal_blind_batch_v1/ARGOS-BLIND-*.json   relatórios por caso
casos/webapp/internal_blind_batch_v1/_batch_run.log       log do lote
casos/webapp/benchmarks/internal-blind-visual-*           painéis, segmentações,
                                                          fases harmonizadas
```

Todos sob `casos/`, fora do controle de versão.
