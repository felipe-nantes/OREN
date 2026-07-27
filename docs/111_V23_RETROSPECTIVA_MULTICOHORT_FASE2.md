# V23 retrospectiva multicohort — Fase 2

## Objetivo

Vincular os 132 pacientes OpenSwissHCC ao contrato da Fase 1, congelar o
procedimento out-of-fold e registrar exatamente quais sinais v23 já existem.
Esta fase não executa MedGemma, não gera predições e não calcula métricas.

## Coorte vinculada

O inventário deve conter:

- 132 casos e 132 pacientes únicos;
- 63 positivos e 69 negativos, mantidos em artefato protegido;
- 88 casos do antigo desenvolvimento;
- 44 casos do holdout já consumido;
- todas as falhas técnicas mantidas no inventário;
- nenhuma máscara de lesão.

O `case_inventory.jsonl` não contém labels. Os labels aparecem somente em
`protected_ground_truth/fold_assignments.jsonl`, necessário para congelar a
estratificação e posteriormente avaliar as predições out-of-fold.

## Protocolo estatístico

Endpoint primário:

```text
patient-level LOOCV
```

Para cada caso:

1. o caso é removido do treinamento;
2. referências ECDF são ajustadas nos outros pacientes;
3. o limiar é selecionado somente nos outros pacientes;
4. o caso removido recebe uma única predição out-of-fold.

Robustez:

```text
50 repetições × 5 folds
seed 20260720
```

Os folds são produzidos por ranking SHA-256 estratificado e round-robin. A
regra, o seed e as atribuições ficam congelados antes das métricas.

## Matriz de disponibilidade

Para cada paciente são registrados:

- presença de T1 nativo;
- pelo menos uma arterial;
- fase venosa;
- fase tardia;
- três sinais v11;
- `candidate_weighted_linearity`;
- possibilidade de calcular o v23 exato.

Fase ausente é registrada como ausente. Nenhuma fase pode ser replicada ou
fabricada.

Os hashes declarados nos manifestos são vinculados ao inventário. Nesta fase
são verificados existência e tamanho dos arquivos, sem reler os pixels. O
rehash independente dos arquivos que precisarem ser processados ocorrerá antes
da geração de sinais.

## Comandos

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_v23_retrospective_multicohort_phase2.py build
.\.venv-win\Scripts\python.exe tools\prepare_v23_retrospective_multicohort_phase2.py verify
```

## Próximo gate

A Fase 3 deverá gerar somente os sinais ausentes:

- `candidate_weighted_linearity` nos 44 casos do holdout consumido;
- sinais ausentes do caso de desenvolvimento tecnicamente problemático;
- nenhuma recomputação dos 87 casos já congelados, salvo falha de verificação.

Antes de executar cada caso, os hashes dos arquivos de entrada utilizados
deverão ser recalculados. Predições e métricas continuarão bloqueadas até todos
os 132 casos possuírem um registro explícito: sinal completo ou falha técnica
contabilizável.

## Resultado executado

O gate real vinculou:

```text
casos: 132
pacientes únicos: 132
positivos protegidos: 63
negativos protegidos: 69
fases dinâmicas mínimas disponíveis: 132/132
sinais v11 existentes: 131/132
linearidade v23 existente: 87/132
entradas completas para score v23: 87/132
casos ainda pendentes: 45
```

Os 44 casos do holdout consumido já possuem os três sinais v11, mas ainda
precisam da linearidade geométrica. Um caso antigo de desenvolvimento permanece
sem v11 e sem linearidade e deverá produzir sinais válidos ou uma falha técnica
explícita na Fase 3.

Assinatura da Fase 2:

```text
168580057c7ae503072c762669c12bfe999bf80c03f6fa349aacacd2fe118010
```
