# FIRST_TASK — primeira task recomendada do ciclo: DS-PROBE-01

Critério (missão §24): forte evidência + alto information gain + baixo risco
de confounding + patch pequeno + boa testabilidade. DS-PROBE-01 não é a task
de maior ganho potencial de OOF — é a investigação que elimina a maior
incerteza (onde o sinal de domínio entra), com risco zero ao sistema.

---

## TASK_CARD

```
id: TASK-POST-AUDIT-DS-PROBE-01
fase: OPT_03 (medição preparatória; pode rodar antes de OPT_01/02)
weakness: W-031 (SR-007)
hypothesis: H-01 (OOF_IMPROVEMENT_REGISTER.yaml)
tipo: MEDIÇÃO (nenhuma variável do sistema muda; outer OOF não é lido)
model: Fable 5
effort: UltraCode
human_gate: nenhum para a medição; qualquer ação decorrente volta ao gate
compute: CPU-only esperado; sem re-treino; sem re-scoring
prazo estimado: 1 sessão
```

## FABLE_PROMPT (auto-contido)

```
Você está no repositório ARGOS/OREN (research_only; auditoria completa —
ler .fable/CURRENT_STATE.yaml, .fable/SAFETY_KERNEL.md e
.fable/post_audit/README.md antes de começar).

TAREFA: DS-PROBE-01 — medir a separabilidade de ORIGEM (coorte) entre as
variantes de representação JÁ CONGELADAS em casos/qualification/hybrid_v1/
(crop_embeddings_v1, fixed_crop_embeddings_v1, enhancement_embeddings_v1,
enhancement_embeddings_edgeonly_v1, crop_embeddings_t2dwi_v1 — inventariar o
que existir de fato), globais e CONDICIONADAS a label, com validação cruzada
agrupada por patient_group_id e seed fixa.

CONTEXTO: probes globais já deram 100% (embeddings) / 98,75% (físicas) —
docs/131:21,85, docs/134:53; NÃO repita a probe global como resultado
principal (use-a só como sanity). A pergunta é ONDE o sinal entra/persiste:
compare variantes (cru vs fixed-crop vs realce vs edge-only vs modalidade) e
labels (positivos vs negativos separados). Interprete com cuidado:
separabilidade ≠ uso pelo classificador.

PASSOS:
1. Inventário: existência/shape/case_ids por variante; registre cobertura.
2. Probe determinística (ex.: regressão logística linear, seed fixa,
   GroupKFold por paciente) por variante: origem global e within-label.
3. Tabela comparativa + correlação qualitativa com os deltas LODO existentes
   (leitura do robustness report congelado; NÃO recompute o protocolo).
4. Reprodutibilidade: rode 2x com a mesma seed; números idênticos.
5. Evidence package em .fable/post_audit/evidence/DS-PROBE-01/ com
   OBSERVED/SOURCE_SUPPORTED/INFERRED/UNKNOWN + CONTEXT_EFFICIENCY.
6. Atualize .fable/post_audit/EXPERIMENT_LEDGER.yaml (nova entrada; medição
   não consome outer_inspection_counter).
7. Termine com recomendação: qual (se alguma) hipótese interventiva merece
   virar MICROEXPERIMENT gated — ou que nenhuma se justifica ainda.

PROIBIÇÕES: não alterar modelo, thresholds, folds, labels, embeddings,
preprocessing ou qualquer código de produção; não ler labels clínicos
protegidos (dataset_id/case_id bastam); não ler o outer OOF como métrica de
desenvolvimento; não commitar/pushar sem pedido; PHI nunca entra em
logs/pack. Se artefatos forem insuficientes: PARE, registre no ledger
(rejection_criteria de H-01) e reporte — não improvise proxies.
```

## Racional da escolha

- Evidência: SR-007 é o risco científico aberto de maior confiança (HIGH) do
  register, e o manuscrito o declara como limitação central.
- Information gain: o resultado reordena TODO o eixo domain-shift (D5/D8/D9
  do plano) e decide se existe hipótese interventiva defensável.
- Confounding: zero — nada muda, nada é treinado, outer não é lido.
- Patch: um script de análise + evidence; totalmente reversível (nada a
  reverter).
- Testabilidade: determinística por construção (seed fixa, 2 runs idênticos).
