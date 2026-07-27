# OpenSwissHCC v16 — incidente de labels e gate de alinhamento

## Resumo

Durante a preparação cega do piloto temporal v16 foram identificados três casos
sem manifesto de alinhamento:

- `anon-openswiss-7bb936ce9f21d461`;
- `anon-openswiss-c83a32179466321d`;
- `anon-openswiss-40c09ebcf8178f92`.

Na investigação, uma busca textual foi executada com escopo amplo demais e
alcançou o diretório protegido de ground truth do desenvolvimento. Os labels
desses três casos apareceram na saída. O holdout não foi acessado.

## Consequência metodológica

A tentativa de gerar o plano temporal foi abortada antes da publicação de
qualquer artefato. A alegação `ground_truth_read=false` não pode ser usada para
essa tentativa de investigação.

A regra de seleção temporal já havia sido implementada e testada antes da
exposição:

```text
para cada cenário fixo, escolher o maior tempo conhecido
de localizador + alinhamento; desempatar por case_id
```

Ela não será alterada com base nos labels observados. Mesmo assim, toda análise
v16 no desenvolvimento deverá continuar sendo descrita como **exploratória**.
Somente o holdout ainda fechado poderá fornecer a avaliação final cega.

## Resultado técnico do alinhamento

O mesmo alinhador cego, com gate Dice hepático congelado em 0,80, foi executado
nos três casos:

| Caso | Melhor Dice | Resultado |
|---|---:|---|
| `anon-openswiss-7bb936ce9f21d461` | 0,749730 | recusado |
| `anon-openswiss-c83a32179466321d` | 0,362175 | recusado |
| `anon-openswiss-40c09ebcf8178f92` | 0,766499 | recusado |

Nenhum resultado de alinhamento foi publicado. O gate não será reduzido para
acomodar esses casos.

## Impacto na v16

O gerador focal atual exige arterial e tardio registrados. Portanto, sem uma
mudança explícita, esses três casos impediriam a geração completa dos 87 casos.
Excluí-los silenciosamente poderia inflar a métrica e invalidar o benchmark.

A solução metodologicamente aceitável deve seguir uma destas rotas, nesta
ordem:

1. usar as fases originais não registradas por coordenada física, registrando
   claramente `unregistered_original_phase` e mantendo o gate mínimo de três
   grupos T1 utilizáveis;
2. se a representação alternativa falhar, produzir `technical_failed` e contar
   o caso como erro na métrica principal;
3. exclusão só poderá ocorrer mediante critério técnico publicado antes da
   avaliação final e deverá ser reportada separadamente, sem recalcular uma
   métrica favorável ocultando o caso.

## Remediação obrigatória

Antes do batch v16:

- limitar buscas e ferramentas às raízes técnicas autorizadas;
- implementar fallback de fases originais sem reduzir o gate de evidência;
- gerar uma galeria técnica específica para os três casos;
- exigir revisão humana dessa galeria;
- registrar os três resultados de alinhamento recusados;
- incluir os 87 casos no denominador operacional, com falhas técnicas tratadas
  explicitamente;
- manter o holdout fechado.

## Estado das salvaguardas

```text
development_labels_visible_to_orchestrator = true
selection_rule_changed_after_label_visibility = false
timing_plan_published = false
alignment_gate_lowered = false
holdout_opened = false
```
