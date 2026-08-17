ID: REF-STATISTICS-001

TITLE: Metrics, denominators, model selection, and statistical interpretation

SOURCE:
- Maier-Hein et al., Metrics Reloaded.
- Cawley and Talbot, On Over-fitting in Model Selection and Subsequent Selection Bias.
- scikit-learn official nested versus non-nested cross-validation example.

URL:
- https://www.nature.com/articles/s41592-023-02151-z
- https://www.jmlr.org/papers/v11/cawley10a.html
- https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html

AUTHORITY_LEVEL:
- `PEER_REVIEWED_METHOD` para Metrics Reloaded e Cawley/Talbot.
- `OFFICIAL_PRIMARY_DOCUMENTATION` para o exemplo do scikit-learn.

VERSION_OR_DATE: Fontes identificadas pelos URLs e identificadores de publicação; nenhuma versão de software ou data clínica é inferida. Registrar data de consulta no pacote de evidências.

TOPICS:
- seleção de métricas orientada ao problema;
- métricas complementares de segmentação/detecção;
- denominadores e falhas técnicas;
- casos one-class e métricas indefinidas;
- model-selection bias;
- nested CV;
- significância versus equivalência.

AFFECTED_ROUTES:
- máscara/referência -> métricas;
- candidatos/localização -> assignment -> avaliação;
- coorte/falhas -> denominador;
- inner CV -> seleção;
- outer CV -> estimativa;
- resultados -> relatório científico.

KEY_RULES:
- Escolher métricas conforme a pergunta e o tipo de tarefa; uma única métrica não é oráculo universal.
- Em segmentação, combinar famílias complementares, como overlap e superfície, quando a pergunta exigir.
- Em detecção/localização, definir assignment e reconhecer que muitos desenhos não possuem verdadeiros negativos úteis; não aplicar accuracy/especificidade automaticamente.
- Toda métrica deve declarar população, unidade, denominador, falhas incluídas/excluídas e regime de avaliação.
- Métrica matematicamente indefinida permanece N/E; não convertê-la silenciosamente em zero.
- Não excluir falhas pós-hoc para melhorar resultados quando o contrato científico as mantém no denominador.
- Não comparar métodos como ranking direto quando splits, endpoints ou denominadores diferem.
- Separar seleção de hiperparâmetros/threshold da estimativa final; usar inner/outer loops conforme contrato.
- Ausência de significância estatística não demonstra equivalência.
- Threshold operacional ou científico nunca deve ser alterado porque uma métrica parece melhorar; exige aprovação e provenance.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar cálculo de métrica, denominator, bootstrap, threshold ou avaliação.
- Ao revisar classificação, segmentação, localização ou registration quantitativo.
- Quando duas implementações produzirem métricas diferentes.

LIMITATIONS:
- As fontes não definem threshold clínico, segurança, eficácia ou validade clínica do ARGOS/OREN.
- A métrica correta depende da pergunta, dos dados e do custo dos erros.
- Políticas de falha, unidade de análise, bootstrap e endpoint são contratos internos que exigem aprovação.
