# OpenSwissHCC v16 — score cego e protocolo de avaliação

Data de conclusão: 2026-07-17  
Estado: 87 scores cegos completos; protocolo de avaliação congelado antes dos labels  
Holdout: fechado

## 1. Aprovação humana

A galeria full87 v16 v1 foi aprovada pelo revisor `jm` e vinculada aos hashes da coorte e da galeria.

- assinatura da revisão: `0ab7b24bfa6a4eb0f8e3660985e83c6193a2bb46af2baa3cb7779f8fb425acc0`;
- casos: 87;
- stacks candidatos: 229;
- ground truth lido: não;
- holdout aberto: não.

## 2. Protocolo de scoring

O protocolo foi congelado antes da inferência completa:

`casos/qualification/openswisshcc_v1/protocols/v16_candidate_volume_full87_score_protocol.json`

Assinatura:

`d265353d3b16dd9ccfc79d7ffa5ac6d4675decdb59a0fe46cb45528c071b2040`

Regras principais:

- modelo `google/medgemma-1.5-4b-it`;
- uma requisição por candidato;
- nenhum retry automático;
- score por candidato como log-odds `POSITIVA/NEGATIVA`;
- score do caso como o maior log-odds entre os candidatos;
- gate de scoring de 180 segundos por caso;
- pesquisa e revisão humana obrigatória.

## 3. Rodada cega completa

Diretório:

`casos/qualification/openswisshcc_v1/scores/dev_v16_candidate_volume_full87_4b_v1`

Resultados técnicos:

- 87/87 casos completos;
- 229/229 candidatos processados;
- 87 arquivos de predição persistidos atomicamente;
- falhas HTTP, OOM, schema ou hash: zero;
- mínimo: 20,3923 s;
- mediana: 65,0938 s;
- média: 56,9085 s;
- máximo: 109,0265 s;
- casos sob 180 s: 87/87;
- ground truth lido: não;
- métricas calculadas: não;
- holdout aberto: não.

Hashes do índice final:

- `progress.json`: `7bcdfa7d7e24151c3ed5aa9d0932b87e3949850e9134b2bc66bfcffccb987106`;
- `summary.json`: `f20c74dc846cec0ba6cee67654c28a52e3dcf38fbc98a97214a69202ac29961d`.

Uma segunda passagem aceitou todos os 87 casos exclusivamente como `reused=true`, confirmando os hashes sem novas inferências.

## 4. Correção de schema

Durante o primeiro congelamento do avaliador, o gate recusou o run porque o `summary.json` possuía o schema de progresso. A causa era a ordem de expansão do dicionário em `_write_progress`: `**progress` sobrescrevia `SUMMARY_SCHEMA`.

A correção:

- preserva `PROGRESS_SCHEMA` em `progress.json`;
- aplica `SUMMARY_SCHEMA` em `summary.json` após a expansão;
- não altera nenhuma das 87 predições;
- possui teste de regressão dedicado;
- foi aplicada por reuso dos scores, sem inferência adicional.

## 5. Protocolo de avaliação congelado

Arquivo:

`casos/qualification/openswisshcc_v1/protocols/v16_candidate_volume_full87_evaluation_protocol.json`

Assinatura:

`a6953feb887e5a649a8f44edf3e75f11d70a9ff1f045f57db9d3dc0209a8cea5`

O protocolo fixa antes dos labels:

- sinal primário: maior log-odds positivo/negativo entre candidatos;
- direção: scores maiores indicam maior suspeita;
- estimador primário: leave-one-out, com limiar ajustado apenas no treino;
- seleção de limiar: maximizar o mínimo entre sensibilidade e especificidade e, depois, acurácia balanceada;
- robustez: 50 repetições de validação estratificada 5-fold, com limiar ajustado dentro de cada fold de treino;
- intervalos de confiança Wilson de 95%;
- sensibilidade mínima: 75%;
- especificidade mínima: 75%;
- inconclusivos contam como erro no diagnóstico categórico secundário;
- diagnósticos secundários não podem substituir o resultado primário.

## 6. Interpretação temporal

O gate de até 180 segundos foi comprovado para o scoring de candidatos já preparados. A execução integral a partir de DICOM cru ainda não foi medida ponta a ponta. Portanto:

- `score_time_gate_passed=true`;
- `full_raw_dicom_end_to_end_180_seconds_proven=false`;
- ainda não é permitido declarar que todo o fluxo termina em até três minutos.

## 7. Testes

- testes focados do scorer e avaliador: 18 aprovados;
- suíte completa: 653 aprovados, zero falhas;
- warnings: 389, todos não bloqueantes e já existentes em dependências/APIs depreciadas.

## 8. Próximo gate

O próximo passo exige autorização humana explícita para abrir somente `development_labels.jsonl` e calcular a avaliação v16 pelo protocolo assinado acima.

O holdout deve permanecer fechado. Nenhuma alteração de sinal, limiar, estimador ou critério de sucesso será permitida após a abertura dos labels nesta avaliação.
