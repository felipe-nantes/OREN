# Benchmark Patologia + Variação no frontend

## Objetivo

O frontend do ARGOS possui dois modos de avaliação, executados pelo mesmo
classificador visual supervisionado:

1. `binary`: triagem da patologia-alvo;
2. `pathology_and_subtype`: triagem da patologia-alvo e identificação da
   variação em quatro classes.

O modo binário anterior foi preservado integralmente.

## Taxonomia fechada

| Subtipo | Rótulo binário da patologia-alvo |
|---|---|
| `hcc` | `positive` |
| `fnh` | `negative` |
| `hemangioma` | `negative` |
| `hepatic_cyst` | `negative` |

O backend rejeita combinações inconsistentes. Isso impede que uma alteração
benigna seja cadastrada como positiva para HCC, como ocorreu em benchmarks
exploratórios antigos.

## Isolamento do ground truth

O manifesto recebido pelo endpoint contém `truth_subtype`, mas a chamada de
inferência recebe somente:

```json
{"id": "identificador-anonimo", "dataset": "nome-do-dataset"}
```

O rótulo binário e o subtipo verdadeiro são anexados por
`_evaluate_benchmark_result` somente depois que a inferência terminou. O
ground truth não é enviado ao classificador, ao gerador de painéis ou ao modelo.

## Métricas exibidas

### Patologia-alvo

- acurácia;
- sensibilidade;
- especificidade;
- precisão e F1;
- matriz de confusão binária;
- intervalos de confiança de 95% existentes;
- gate: sensibilidade e especificidade maiores ou iguais a 75%.

### Identificação da variação

- acurácia balanceada (recall macro das classes representadas);
- acurácia top-1;
- taxa de subtipo determinado;
- recall e IC 95% de Wilson por classe;
- matriz de confusão 4×5, incluindo `undetermined`;
- gate: acurácia balanceada maior ou igual a 75% e presença obrigatória das
  quatro classes.

Falha técnica, inconclusivo, classe fora do vocabulário ou subtipo não
determinado contam como erro. Nenhum desses casos é removido do denominador.

## Relatórios

O `benchmark_report.json` passa a registrar:

```text
evaluation_mode
metrics
subtype_metrics
combined_target
cases[].truth_subtype
cases[].predicted_subtype_for_scoring
cases[].subtype_correct
```

O CSV exporta os três campos de avaliação multiclasse por exame. O gate
completo somente passa quando os gates binário e multiclasse passam.
O arquivo atômico `metrics_subtype.json` preserva as métricas multiclasse para
auditoria independente da interface.

## Como executar pelo frontend

1. Abra `http://127.0.0.1:8080/benchmark.html`.
2. Selecione **Patologia + variação**.
3. Envie uma pasta com uma subpasta anônima por exame.
4. Para cada exame, escolha HCC, FNH, hemangioma ou cisto hepático.
5. Inclua pelo menos um caso de cada classe; para uma demonstração minimamente
   interpretável, use uma coorte maior e balanceada.
6. Inicie o benchmark e aguarde os dois painéis de métricas.

## Limitações metodológicas

- Um resultado com casos vistos no treino não estima generalização.
- O aviso de procedência continua aparecendo antes das métricas.
- A meta atingida no frontend descreve apenas a coorte executada.
- A medição OOF defensável do subtipo permanece 61,46% até que uma validação
  independente demonstre valor diferente.
- Uso exclusivamente em pesquisa, com revisão humana obrigatória.

## Validação da implementação

- 60 testes focados do benchmark e webapp: aprovados;
- JavaScript inline: sintaxe validada;
- smoke test em navegador: aprovado e sem erros de console;
- suíte completa: 1.343 testes aprovados.
