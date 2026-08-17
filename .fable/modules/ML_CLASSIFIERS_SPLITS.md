# MODULE_ID: ML_CLASSIFIERS_SPLITS

MODULE_NAME: Classificadores supervisionados, splits e inferência visual

## REAL_PATHS

- dtwin/learning/splits.py
- dtwin/learning/medsiglip_classifier.py
- dtwin/learning/medsiglip_head_classifier.py
- dtwin/learning/medsiglip_multiclass_classifier.py
- dtwin/learning/medsiglip_pairwise_subtype.py
- dtwin/learning/patch25d_classifier.py
- dtwin/learning/radiomics_classifier.py
- dtwin/learning/visual_inference.py
- configs/training/hybrid_v1_nested_splits.json
- tests/test_learning_splits.py
- tests/test_learning_medsiglip_classifier.py

STATUS: EXPERIMENTAL

## RESPONSIBILITY

Construir splits agrupados/nested, treinar e avaliar classificadores, gerar OOF predictions, escolher thresholds segundo configuração e executar inferência visual supervisionada.

## ENTRYPOINTS

- build_nested_splits
- validate_nested_splits
- generate_oof_predictions
- evaluate_oof_predictions
- funções públicas dos classificadores e visual_inference

## PUBLIC INTERFACES

load_classifier_config; build_nested_splits; validate_nested_splits; generate_oof_predictions; evaluate_oof_predictions; APIs equivalentes de head, multiclass, pairwise, radiomics e patch25d.

## INPUTS

Embeddings/features; labels; patient/group IDs; configs; seeds; folds; manifests de dataset.

## OUTPUTS

Splits JSON, modelos/coeficientes, predictions OOF, thresholds, métricas e manifestos de inferência.

## SIDE_EFFECTS

Lê datasets/embeddings; treina modelos; grava splits, modelos e resultados; pode consumir CPU/GPU.

## UPSTREAM

MEDSIGLIP_EMBEDDINGS; PANELS_REPRESENTATION; DATASETS_REGISTRY; CONFIG_PROFILES.

## DOWNSTREAM

BENCHMARK_METRICS_REPORTING; WEBAPP_API_ORCHESTRATION; CANDIDATE_LOCALIZATION; EXPERIMENTAL_BENCHMARKS.

## ARTIFACTS_READ

Embedding manifests/NPY/JSONL; labels/registry; split config; feature tables.

## ARTIFACTS_WRITTEN

Nested splits, OOF ledger, modelos, thresholds, scores, relatórios intermediários.

## DEPENDENCIES

NumPy; pandas; scikit-learn; joblib; MEDSIGLIP_EMBEDDINGS.

## OBSERVED_BEHAVIOR

Há múltiplas famílias de classificador e experimentos mono/multifásicos. O webapp individual usa modo hybrid_supervised. Splits agrupam casos e validam isolamento, mas cada novo caminho precisa provar que patient/group identity é correta.

## SOFTWARE_CONTRACTS

Inputs/outputs devem ter schema e hashes; folds devem ser determinísticos por seed; todos os casos/falhas devem permanecer no ledger.

## GEOMETRIC_CONTRACTS

Features e painéis devem preservar identidade de source/representação; mudanças geométricas upstream invalidam modelos e resultados.

## SCIENTIFIC_CONTRACTS

Labels, polaridade, patient grouping, folds, nested CV, preprocessing fit, tuning, threshold e agregação são contratos científicos de alto risco.

## DOMAIN_POLICIES

PATIENT/GROUP LEAKAGE é falha crítica. Test/holdout não pode orientar tuning ou threshold. Classificação não é diagnóstico clínico.

## KNOWN_FAILURE_MODES

Classe única; fold vazio; IDs duplicados; feature ausente; modelo/config incompatível; não convergência.

## SILENT_FAILURE_MODES

Leakage entre pacientes; scaler/selector fit fora do fold; threshold escolhido no test; falhas excluídas; labels invertidos; group ID inadequado.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC; OUT_OF_AUTHORITY para diagnóstico.

## HUMAN_GATES

HG-06 para labels/coorte; HG-07 para CV/preprocessing/tuning; HG-08 para thresholds/métricas; HG-09 para representação/modelo; HG-12 para claim.

## EXISTING_TESTS

tests/test_learning_splits.py; tests/test_learning_medsiglip_classifier.py; tests/test_learning_medsiglip_head_classifier.py; tests/test_learning_medsiglip_multiclass_classifier.py; tests/test_learning_patch25d_classifier.py; tests/test_learning_radiomics_classifier.py.

## TEST_GAPS

Permuted-label; adversarial duplicate patient; nested-CV integral; mutation de branches críticos; leakage entre cohorts; recalibração externa; falhas no denominador.

## REQUIRED_TEST_TYPES

CONTRACT; INVARIANT; PROPERTY; NEGATIVE; INTEGRATION; SCIENTIFIC_REGRESSION; MUTATION; ADVERSARIAL.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/SKLEARN.md; .fable/references/STATISTICS.md; .fable/references/REPRODUCIBILITY.md; configs/training/hybrid_v1_nested_splits.json.

## OPEN_QUESTIONS

Qual classificador é autoritativo? Qual definição canônica de patient/group? Quais experimentos estão congelados versus históricos?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar labels, grupos, folds, seed, fit boundaries, features, tuning, threshold, agregação ou contabilização de falhas sem HG-06/HG-07/HG-08 e regressão completa.

