# MODULE_ID: BENCHMARK_METRICS_REPORTING

MODULE_NAME: Runner, métricas e relatórios de benchmark

## REAL_PATHS

- dtwin/benchmark/models.py
- dtwin/benchmark/runner.py
- dtwin/benchmark/metrics.py
- dtwin/benchmark/subtype_metrics.py
- dtwin/benchmark/reporting.py
- dtwin/benchmark/dataset_audit.py
- dtwin/benchmark/operational_timing.py
- tests/test_benchmark_runner.py
- tests/test_benchmark_metrics.py
- tests/test_benchmark_reporting.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Executar casos/benchmarks, classificar falhas, calcular métricas/intervalos/denominadores, produzir JSON/CSV/Markdown e registrar ambiente/timing.

## ENTRYPOINTS

- run_benchmark
- recalculate_existing_run
- compute_benchmark_metrics
- write_run_outputs
- build_summary

## PUBLIC INTERFACES

ExperimentConfig; InferenceCase; EvaluationCase; BenchmarkCaseResult; BenchmarkStatus; build_run_manifest; run_case; wilson_interval.

## INPUTS

Manifestos de coorte; ground truth protegido; predictions; configs de experimento/modelo; commit/ambiente.

## OUTPUTS

Run manifest, case results, métricas agregadas/subtipos, IC Wilson, report.json, report.csv e summary Markdown.

## SIDE_EFFECTS

Executa inferência; cria diretório de run; escreve artefatos atômicos; coleta ambiente e timing.

## UPSTREAM

DATASETS_REGISTRY; MEDGEMMA_INFERENCE; ML_CLASSIFIERS_SPLITS; ARTIFACT_PROVENANCE.

## DOWNSTREAM

EXPERIMENTAL_BENCHMARKS; documentação científica; decisões humanas de promoção.

## ARTIFACTS_READ

Dataset/label manifests; predictions; configs; runs existentes para recálculo.

## ARTIFACTS_WRITTEN

run_manifest.json; case results; metrics JSON; CSV; summary/report Markdown; timing.

## DEPENDENCIES

Python statistics/math; hashing; modelos benchmark; módulos de inferência.

## OBSERVED_BEHAVIOR

Calcula denominadores e razões com valores indefinidos explícitos e IC Wilson. Runner registra commit/ambiente e classifica estados terminais. O namespace também é importado pelo webapp, portanto não é removível em bloco.

## SOFTWARE_CONTRACTS

Escrita deve ser atômica; recálculo deve preservar inputs e identidade; cada caso precisa de estado terminal; relatório deve corresponder ao JSON canônico.

## GEOMETRIC_CONTRACTS

Métricas geométricas upstream devem conservar unidade, reference grid e definição; este módulo não deve reparar geometria silenciosamente.

## SCIENTIFIC_CONTRACTS

População, denominadores, falhas, positive/negative, subtipos, métrica, intervalo e nível de bootstrap exigem contrato aprovado.

## DOMAIN_POLICIES

Falhas/inconclusivos não podem desaparecer do denominador; ground truth protegido não deve contaminar inferência.

## KNOWN_FAILURE_MODES

Classe ausente; métrica indefinida; manifesto inconsistente; run parcial; prediction sem label; escrita interrompida.

## SILENT_FAILURE_MODES

Excluir falhas; contar painel como paciente; recálculo com código/config diferente; label leakage; intervalo no nível estatístico errado.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC.

## HUMAN_GATES

HG-06 para coorte/labels; HG-07 para desenho; HG-08 para métricas/denominadores; HG-01 para promover resultado a contrato.

## EXISTING_TESTS

tests/test_benchmark_runner.py; tests/test_benchmark_metrics.py; tests/test_benchmark_reporting.py; tests/test_dataset_audit.py; tests/test_benchmark_subtype_metrics.py.

## TEST_GAPS

Mutation testing; denominadores adversariais; restart parcial; bootstrap/group-level; golden recálculo; independência ground-truth/inferência.

## REQUIRED_TEST_TYPES

UNIT; CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; MUTATION; FAULT_INJECTION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/STATISTICS.md; .fable/references/REPRODUCIBILITY.md; configs/benchmark/.

## OPEN_QUESTIONS

Quais métricas/runs são baseline congelado? Qual unidade de bootstrap é autorizada em cada estudo? Quais falhas entram em cada denominador?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar status terminal, denominadores, métricas, IC, bootstrap, subtipos, failure accounting ou recálculo sem HG-08 e evidência before/after.
