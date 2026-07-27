# OpenSwissHCC v9 — avaliação pós-inferência

Data: 2026-07-14

## Ordem obrigatória

1. Validar resumo completo da execução.
2. Validar todos os manifestos, hashes e scores.
3. Confirmar ausência de decisão final, métricas e acesso a ground truth.
4. Confirmar todos os casos dentro de 180 segundos.
5. Somente então abrir o arquivo protegido de labels.

Um artefato corrompido interrompe a avaliação antes da leitura dos labels.

## Sinais avaliados

- média, mediana e máximo por painel;
- médias dos dois e três maiores scores;
- focalidade;
- máximos adjacentes de dois e três planos;
- fração de painéis acima de 0,50;
- estatísticas independentes para os dois pares de frases.

## Robustez

Para cada sinal são calculados:

- limiar e métricas aparentes;
- leave-one-out cross-validation;
- validação estratificada repetida em cinco folds;
- validação aninhada repetida;
- matriz de confusão;
- intervalos de confiança Wilson de 95% para sensibilidade e especificidade.

A configuração só é classificada como candidata de desenvolvimento se:

- sensibilidade e especificidade LOOCV forem pelo menos 75%;
- todas as 50 repetições estratificadas passarem 75/75;
- todas as 50 repetições aninhadas passarem 75/75;
- o maior tempo observado por caso não exceder 180 segundos.

O holdout permanece fechado. Resultado no desenvolvimento não constitui validação clínica.

## Saídas

- `evaluation.json`;
- `case_features.csv`;
- hashes do ground truth protegido e do resumo cego;
- status explícito `qualified_development_candidate` ou `development_only_not_qualified`.

## Testes

- labels só são abertos depois da validação de todos os artefatos cegos;
- corrupção bloqueia antes da leitura dos labels;
- intervalos de confiança são persistidos;
- tempo acima de 180 segundos reprova a execução;
- suíte completa: 467 testes aprovados.
