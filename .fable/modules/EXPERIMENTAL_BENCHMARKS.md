# MODULE_ID: EXPERIMENTAL_BENCHMARKS

MODULE_NAME: Estudos, coortes e benchmarks experimentais/históricos

## REAL_PATHS

- dtwin/benchmark/
- dtwin/learning/visual_benchmark.py
- configs/benchmark/
- configs/segmentation_benchmark_chaos_v2.yaml
- configs/segmentation_benchmark_liverhccseg_phase_fusion_v2.yaml
- tools/
- tests/
- docs/

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Implementar estudos CHAOS, LiverHCCSeg, LLD-MMRI, OpenSwissHCC, coortes públicas/externas, segmentação comparativa, localização, ablações, timing e consolidação científica.

## ENTRYPOINTS

- dtwin.benchmark.runner.run_benchmark
- dtwin/benchmark/lld_mmri_v23_evaluation.py
- dtwin/benchmark/openswisshcc_evaluation.py
- tools/run_lld_mmri_v23_signals.py
- tools/run_openswisshcc_volumetric_medsiglip.py

## PUBLIC INTERFACES

APIs específicas de preparação, inference, evaluation, review, gate, timing, freeze e consolidation; contratos JSON/YAML em configs/benchmark/.

## INPUTS

Datasets/registries; labels protegidos; configs; modelos/predictions; baselines congelados; decisões humanas documentadas.

## OUTPUTS

Runs, manifests, predictions, métricas, galleries, relatórios, decisões/gates e artefatos intermediários.

## SIDE_EFFECTS

Pode baixar dados, executar modelos/treinamento, consumir GPU/CPU, escrever grandes árvores de experimentos e atualizar relatórios por comando explícito.

## UPSTREAM

DATASETS_REGISTRY; PANELS_REPRESENTATION; MEDGEMMA_INFERENCE; MEDSIGLIP_EMBEDDINGS; ML_CLASSIFIERS_SPLITS; BENCHMARK_METRICS_REPORTING; CONFIG_PROFILES.

## DOWNSTREAM

Manuscrito/documentação, seleção humana de próximos experimentos e eventual promoção de componentes; alguns helpers são importados pelo runtime.

## ARTIFACTS_READ

Datasets, labels, masks, panels, embeddings, configs, frozen baselines e runs anteriores.

## ARTIFACTS_WRITTEN

Experiments/runs, predictions, metrics, reports, galleries, timing, frozen manifests e amendments.

## DEPENDENCIES

Todo o stack científico; módulos benchmark/learning; ferramentas externas e datasets.

## OBSERVED_BEHAVIOR

O namespace contém centenas de caminhos de versões sucessivas, sobretudo openswisshcc_*. Muitos possuem testes/scripts e não podem ser chamados dead apenas por não integrarem o webapp. Alguns helpers do namespace benchmark são dependências do runtime atual.

## SOFTWARE_CONTRACTS

Cada run deve registrar commit, config, environment, inputs, outputs, failures e hashes; versão histórica não deve ser sobrescrita; freeze deve ser imutável.

## GEOMETRIC_CONTRACTS

Preparação/registro/resampling/máscaras devem declarar reference grid, transforms, interpolação e unidades por experimento.

## SCIENTIFIC_CONTRACTS

Pergunta, coorte, labels, preprocessing, modelo, folds, tuning, thresholds, métricas, denominadores, bootstrap e stop/go são contratos científicos.

## DOMAIN_POLICIES

Experimento histórico não é automaticamente baseline atual; resultado interno não autoriza claim clínico; dados protegidos permanecem segregados.

## KNOWN_FAILURE_MODES

Dados/pesos ausentes; run parcial; config histórica; OOM; fold/coorte inválido; métrica indefinida; script Windows-only.

## SILENT_FAILURE_MODES

Leakage; baseline errado; tuning no holdout; failure omission; versão semelhante confundida; helper histórico importado pelo produto; documentação stale.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; OUT_OF_AUTHORITY para claims clínicos.

## HUMAN_GATES

HG-01, HG-02 a HG-10 conforme desenho; HG-11 para dados; HG-12 para qualquer conclusão clínica.

## EXISTING_TESTS

Cobertura específica inclui tests/test_openswisshcc_evaluation.py, tests/test_lld_mmri_v23_evaluation.py, tests/test_liverhccseg_v21_panels.py, tests/test_chaos_v21_panels.py e testes benchmark gerais.

## TEST_GAPS

Inventário current/legacy; reproduções completas independentes; leakage adversarial; environment locks; mutation em métricas/gates; ligação inequívoca relatório→run.

## REQUIRED_TEST_TYPES

CHARACTERIZATION; CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; MUTATION; ADVERSARIAL; REPRODUCIBILITY.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/REPRODUCIBILITY.md; .fable/LEGACY_AND_DEAD_CODE_CANDIDATES.md; .fable/references/STATISTICS.md; configs/benchmark/; docs/.

## OPEN_QUESTIONS

Quais versões são baseline atual, históricas ou abandonadas? Quais helpers precisam ser extraídos antes de arquivar pesquisa? Quais runs foram reproduzidos no commit atual?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não apagar/renomear versões, mudar coortes/labels/desenho, recalcular/reescrever baselines, promover resultados ou remover helpers sem tracing dinâmico, reprodução e autorização científica.
