ID: REF-SKLEARN-001

TITLE: Grouped evaluation, pipelines, and nested cross-validation

SOURCE:
- scikit-learn official example: Nested versus non-nested cross-validation.
- scikit-learn official API documentation for GroupKFold, StratifiedGroupKFold, and Pipeline.

URL:
- https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html
- https://scikit-learn.org/stable/modules/generated/sklearn.pipeline.Pipeline.html

AUTHORITY_LEVEL: `OFFICIAL_PRIMARY_DOCUMENTATION` para o comportamento das APIs e o exemplo metodológico fornecido pelo scikit-learn.

VERSION_OR_DATE: Documentação `stable`; a versão instalada deve ser obtida do ambiente/lockfile e registrada. Nenhuma versão é presumida.

TOPICS:
- grouped cross-validation;
- nested cross-validation;
- Pipeline e transforms aprendíveis;
- tuning e avaliação;
- patient/group leakage;
- previsões out-of-fold.

AFFECTED_ROUTES:
- coorte -> splits;
- treino -> preprocessing;
- inner CV -> tuning/threshold;
- outer CV -> estimativa;
- predictions -> métricas.

KEY_RULES:
- Nenhum patient/group ID pode aparecer em treino e validação/teste do mesmo split.
- Imputer, scaler, selector, PCA e outros transforms aprendíveis devem ser ajustados somente nos dados de treino do fold pertinente.
- Quando o desenho exigir nested CV, hiperparâmetros e threshold pertencem ao inner loop; o outer fold é reservado para estimativa.
- Preferir `Pipeline` para acoplar preprocessing aprendível e estimator quando isso reduzir o risco de leakage.
- Testar disjunção de grupos diretamente e observar chamadas a `fit` com spies/IDs, não apenas a métrica final.
- No regime OOF, cada unidade deve receber exatamente uma previsão fora de treino.
- A escolha entre `GroupKFold` e `StratifiedGroupKFold` depende do contrato e da viabilidade da coorte; não trocá-las automaticamente.
- Seleção e avaliação no mesmo dado produzem estimativa otimista.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar splits, preprocessing, tuning, threshold, pipelines ou geração OOF.
- Ao revisar qualquer código que use patient/exam IDs ou múltiplas observações por indivíduo.
- Quando métricas mudarem sem alteração aparente do modelo.

LIMITATIONS:
- O exemplo Iris é pedagógico e não valida o desenho específico do ARGOS/OREN.
- A API não define a unidade científica de agrupamento, o número de folds ou a política de threshold.
- Coortes pequenas, classes raras e grupos desequilibrados exigem análise estatística e aprovação do operador.
